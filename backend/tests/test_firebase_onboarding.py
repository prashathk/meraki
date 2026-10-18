"""First login after email verification must be able to finish university setup."""
import importlib

import firebase_admin
import pytest
from fastapi.testclient import TestClient
from firebase_admin import auth
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

@pytest.fixture
def firebase_client(monkeypatch):
    from backend.meraki.db import Base
    from backend.meraki.security import db_session
    module = importlib.import_module('backend.meraki.app')
    security = importlib.import_module('backend.meraki.security')
    engine = create_engine('sqlite://', poolclass=StaticPool, connect_args={'check_same_thread': False})
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    claims = {'uid': 'verified-university', 'email': 'team@example.test', 'email_verified': True}
    monkeypatch.setattr(module, 'AUTH', 'firebase')
    monkeypatch.setattr(security, 'AUTH', 'firebase')
    monkeypatch.setattr(firebase_admin, '_apps', {'test': object()})
    monkeypatch.setattr(auth, 'verify_id_token', lambda *args, **kwargs: claims)
    def session():
        with factory() as db:
            yield db
    module.app.dependency_overrides[db_session] = session
    client = TestClient(module.app, headers={'Authorization': 'Bearer test-identity'})
    yield client, factory, claims
    client.close()
    module.app.dependency_overrides.clear()
    engine.dispose()


@pytest.mark.parametrize('university', ['', '   '])
def test_first_university_login_requests_profile_then_completes(firebase_client, university):
    from backend.meraki.db import Record
    client, factory, _ = firebase_client
    body = {'name': 'University Team', 'role': 'representative', 'university': university}
    response = client.post('/api/auth/firebase-onboard', json=body)
    assert response.status_code == 422
    assert response.json()['detail']['code'] == 'university_required'
    with factory() as db:
        assert list(db.scalars(select(Record))) == []
    response = client.post('/api/auth/firebase-onboard', json={**body, 'university': '  Example University  '})
    assert response.status_code == 200
    account = client.get('/api/me').json()
    assert account['role'] == 'representative'
    assert account['organization']['name'] == 'Example University'
    assert account['organization']['state'] == 'pending'
    assert client.get('/api/drafts').status_code == 403
    # A later login has no university input, and must reuse the existing profile.
    again = client.post('/api/auth/firebase-onboard', json=body)
    assert again.status_code == 200
    assert again.json()['org'] == account['org']
    with factory() as db:
        assert len(list(db.scalars(select(Record).where(Record.kind == 'organization')))) == 1


def test_existing_admin_role_is_not_changed_by_login_selector(firebase_client):
    from backend.meraki.db import add
    client, factory, claims = firebase_client
    with factory() as db:
        add(db, 'user', {'name': 'Administrator', 'email': claims['email'], 'role': 'admin', 'profile': {'tags': []}},
            id='firebase:' + claims['uid'], state='active')
        db.commit()
    response = client.post('/api/auth/firebase-onboard', json={'name': 'Team', 'role': 'representative'})
    assert response.status_code == 200
    assert response.json()['role'] == 'admin'


def test_unverified_identity_cannot_complete_university_setup(firebase_client):
    from backend.meraki.db import Record
    client, factory, claims = firebase_client
    claims['email_verified'] = False
    response = client.post('/api/auth/firebase-onboard', json={'name': 'Team', 'role': 'representative', 'university': 'Example University'})
    assert response.status_code == 403
    with factory() as db:
        assert list(db.scalars(select(Record))) == []


def test_student_onboarding_does_not_require_university(firebase_client):
    client, _, _ = firebase_client
    response = client.post('/api/auth/firebase-onboard', json={'name': 'Student', 'role': 'student'})
    assert response.status_code == 200
    assert response.json()['role'] == 'student'
    assert response.json()['org'] == ''
