"""Exercise browser multipart URL submissions through the API and worker."""
import importlib
import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


def browser_multipart(url='', method='nlp', filename='', content=b''):
    # An unused browser file input includes filename="". Some HTTP clients omit
    # that attribute for empty filenames, which would miss this regression.
    boundary = 'meraki-browser-form-boundary'
    body = (f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{filename}"\r\n'
            'Content-Type: application/octet-stream\r\n\r\n').encode() + content
    for name, value in [('url', url), ('method', method)]:
        body += f'\r\n--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}'.encode()
    body += f'\r\n--{boundary}--\r\n'.encode()
    return {'content': body, 'headers': {'Content-Type': 'multipart/form-data; boundary=' + boundary}}


@pytest.fixture
def source_client(monkeypatch):
    from backend.meraki.db import Base, add
    from backend.meraki.security import db_session, user
    module = importlib.import_module('backend.meraki.app')
    worker = importlib.import_module('worker.run')
    gemini = importlib.import_module('backend.meraki.gemini')
    storage = importlib.import_module('backend.meraki.storage')
    scanning = importlib.import_module('backend.meraki.scanning')
    tasks = importlib.import_module('backend.meraki.tasks')
    engine = create_engine('sqlite://', poolclass=StaticPool, connect_args={'check_same_thread': False})
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    with factory() as db:
        org = add(db, 'organization', {'name': 'Extraction test university'}, state='verified')
        representative = add(db, 'user', {'name': 'Test representative', 'role': 'representative'}, org=org.id, state='active')
        db.commit()
    calls = {'scans': [], 'uploads': [], 'dispatch': [], 'fetches': []}
    def session():
        with factory() as db:
            yield db
    module.app.dependency_overrides[db_session] = session
    module.app.dependency_overrides[user] = lambda: representative
    monkeypatch.setattr(worker, 'Session', factory)
    monkeypatch.setattr(scanning, 'scan', lambda content: calls['scans'].append(content) or 'passed')
    monkeypatch.setattr(storage, 'put', lambda *args: calls['uploads'].append(args) or 'local:fixture')
    monkeypatch.setattr(tasks, 'dispatch', lambda id: calls['dispatch'].append(id))
    html = b'<h1>Faculty of Computing</h1><h2>BSc Computer Science</h2><h2>BEng Software Engineering</h2>'
    def fetch(url):
        calls['fetches'].append(url)
        return html, 'text/html', url
    monkeypatch.setattr(worker, 'fetch_public', fetch)
    monkeypatch.setattr(gemini, 'require_configuration', lambda: {})
    monkeypatch.setattr(gemini, 'generate_courses', lambda prompt, schema: (json.dumps({'courses': [
        {'title': 'BSc Computer Science', 'faculty': 'Faculty of Computing', 'evidence': 'BSc Computer Science', 'tags': []},
        {'title': 'BEng Software Engineering', 'faculty': 'Faculty of Computing', 'evidence': 'BEng Software Engineering', 'tags': []},
    ]}), 'Gemini test provider'))
    client = TestClient(module.app)
    yield client, factory, calls, worker
    client.close()
    module.app.dependency_overrides.clear()
    engine.dispose()


@pytest.mark.parametrize('method', ['nlp', 'gemini'])
def test_url_with_unused_browser_file_input_completes_extraction(source_client, method):
    from backend.meraki.db import Record
    client, factory, calls, worker = source_client
    url = 'https://university.example/degrees/'
    response = client.post('/api/sources', **browser_multipart('  ' + url + '  ', method))
    assert response.status_code == 200, response.text
    source = response.json()
    assert source['name'] == source['url'] == url
    assert 'object_uri' not in source
    assert calls['scans'] == calls['uploads'] == []
    assert calls['dispatch'] == [source['id']]
    assert worker.once(source['id'])
    with factory() as db:
        result = db.get(Record, source['id'])
        assert result.state == 'completed'
        assert result.data['count'] == 2
        courses = list(db.scalars(select(Record).where(Record.kind == 'course')))
        assert all(course.data['course_url'] == url and not course.data['reviewed'] for course in courses)
    assert calls['fetches'] == [url]


@pytest.mark.parametrize('url', ['', '  '])
def test_unused_file_without_url_requests_a_source(source_client, url):
    client, _, calls, _ = source_client
    response = client.post('/api/sources', **browser_multipart(url))
    assert response.status_code == 422
    assert 'public URL' in response.json()['detail']
    assert calls['dispatch'] == calls['uploads'] == calls['scans'] == []


def test_selected_zero_byte_document_is_not_silently_replaced_by_url(source_client):
    client, _, calls, _ = source_client
    response = client.post('/api/sources', **browser_multipart('https://university.example/degrees/', filename='empty.pdf'))
    assert response.status_code == 422
    assert 'empty' in response.json()['detail']
    assert calls['dispatch'] == calls['uploads'] == []


def test_nameless_nonempty_upload_is_rejected(source_client):
    client, _, calls, _ = source_client
    response = client.post('/api/sources', **browser_multipart('https://university.example/degrees/', content=b'not an unused file input'))
    assert response.status_code == 422
    assert 'filename' in response.json()['detail']
    assert calls['dispatch'] == []


def test_real_pdf_upload_still_requires_scan_and_private_storage(source_client):
    client, _, calls, _ = source_client
    content = b'%PDF-test upload bytes'
    response = client.post('/api/sources', **browser_multipart(filename='prospectus.pdf', content=content))
    assert response.status_code == 200
    assert response.json()['object_uri'] == 'local:fixture'
    assert calls['scans'] == [content]
    assert calls['uploads'][0][1] == content
    assert len(calls['dispatch']) == 1
