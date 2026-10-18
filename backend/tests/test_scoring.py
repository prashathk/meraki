import io
import os
import uuid
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pypdf import PdfReader
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from backend.meraki import domain
from backend.meraki.app import app
from backend.meraki.db import Base, Record, VersionCourse, add
from backend.meraki.scoring import inputs, POLICY_VERSION, POLICY_DESCRIPTION, LEGACY_POLICY_DESCRIPTION

TERMS = domain.TAXONOMY
TAGS = ['technology', 'business', 'mathematics', 'analytical-thinking']


def course(tags=TAGS, title='Example', id='example'):
    return {'id': id, 'course_id': id, 'title': title, 'university': 'Example University',
            'faculty': 'Example Faculty', 'tags': tags, 'course_url': 'https://example.com/'}


def ranked(tags, scores=None, contribution=60, degree=None):
    return domain.rank([course(degree if degree is not None else TAGS)], tags, TERMS, scores, contribution)


def test_requested_example_and_full_degree_denominators():
    c = ranked(['technology', 'mathematics'], {'technology': 80, 'mathematics': 60})[0]
    assert c['match'] == 36
    assert c['scoring_details'] == {
        'interest': {'matched_score_sum': 80, 'degree_count': 2, 'coverage': 40, 'contribution': 60},
        'aptitude': {'matched_score_sum': 60, 'degree_count': 2, 'coverage': 30, 'contribution': 40},
    }
    unrelated = ranked(['technology', 'mathematics', 'design'], {'technology': 80, 'mathematics': 60, 'design': 100})[0]
    assert unrelated['match'] == 36
    duplicate = ranked(['technology', 'mathematics'], {'technology': 80, 'mathematics': 60}, degree=TAGS + TAGS)[0]
    assert duplicate['scoring_details'] == c['scoring_details']


def test_full_and_multiple_matches():
    assert ranked(TAGS)[0]['match'] == 100
    assert ranked(TAGS, {'technology': 80, 'business': 40, 'mathematics': 60, 'analytical-thinking': 20})[0]['match'] == 52
    assert ranked(['design'], degree=TAGS) == []
    assert ranked(['technology'], degree=[]) == []


@pytest.mark.parametrize('tags,scores,weight,degree,expected', [
    (['technology', 'mathematics'], {'technology': 80, 'mathematics': 60}, 0, TAGS, 30),
    (['technology', 'mathematics'], {'technology': 80, 'mathematics': 60}, 100, TAGS, 40),
    (['technology'], {'technology': 80}, 0, TAGS, 40),
    (['mathematics'], {'mathematics': 60}, 100, TAGS, 30),
    (['technology', 'mathematics'], {'technology': 80, 'mathematics': 60}, 60, ['mathematics', 'analytical-thinking'], 12),
    (['technology', 'mathematics'], {'technology': 80, 'mathematics': 60}, 60, ['technology', 'business'], 24),
    (['technology', 'mathematics'], {'technology': 0, 'mathematics': 60}, 0, TAGS, 30),
    (['technology', 'mathematics'], {'technology': 80, 'mathematics': 0}, 100, TAGS, 40),
])
def test_boundaries_missing_categories_and_effective_contributions(tags, scores, weight, degree, expected):
    assert ranked(tags, scores, weight, degree)[0]['match'] == expected


@pytest.mark.parametrize('tags,scores,weight', [
    ([], {}, 70), (['unknown'], {}, 70),
    (['technology'], {'design': 80}, 70),
    (['technology'], {'technology': -1}, 70),
    (['technology'], {'technology': 101}, 70),
    (['technology'], {'technology': float('nan')}, 70),
    (['technology'], {'technology': float('inf')}, 70),
    (['technology'], {'technology': True}, 70),
    (['technology'], {'technology': '80'}, 70),
    (['technology'], {'technology': 0}, 70),
    (['technology', 'mathematics'], {'technology': 0, 'mathematics': 50}, 70),
    (['technology', 'mathematics'], {'technology': 50, 'mathematics': 0}, 70),
    (['technology'], {}, -1), (['technology'], {}, 101),
    (['technology'], {}, float('nan')), (['technology'], {}, True),
])
def test_invalid_scoring_inputs(tags, scores, weight):
    with pytest.raises(HTTPException) as e:
        ranked(tags, scores, weight)
    assert e.value.status_code == 422


@pytest.fixture
def sql_catalogue():
    engine = create_engine('sqlite://', poolclass=StaticPool, connect_args={'check_same_thread': False})
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    with factory() as db:
        version = add(db, 'version', {}, state='published')
        examples = [course(TAGS), course(['technology', 'mathematics'], 'Full', 'full'),
                    course(TAGS + TAGS, 'Duplicate', 'duplicate'), course(['mathematics'], 'Aptitude only', 'apt'),
                    course(['business'], 'Unrelated', 'unrelated'), course([], 'Empty', 'empty')]
        for c in examples:
            r = domain.new_revision(db, c, state='published', course_id=c['course_id'])
            db.add(VersionCourse(version_id=version.id, course_id=c['course_id'], revision_id=r.id))
        db.commit()
        yield db, version.id, examples, factory
    engine.dispose()


@pytest.mark.parametrize('tags,scores,weight', [
    (['technology', 'mathematics'], {'technology': 80, 'mathematics': 60}, 60),
    (['technology', 'mathematics', 'design'], {'technology': 80, 'mathematics': 60, 'design': 100}, 60),
    (['technology', 'mathematics'], {}, 0), (['technology', 'mathematics'], {}, 100),
    (['technology'], {}, 0), (['mathematics'], {}, 100),
    (TAGS, {'technology': 33.33, 'business': 77.7, 'mathematics': 45.5, 'analytical-thinking': 99.9}, 65.25),
])
def test_sql_order_and_limiting_match_final_ranking(sql_catalogue, tags, scores, weight):
    db, version, examples, _ = sql_catalogue
    expected = domain.rank(examples, tags, TERMS, scores, weight)
    for limit in (1, 2, 100):
        actual = domain._query_candidates(db, tags, version, limit, scores, weight, TERMS)
        assert [c['course_id'] for c in actual] == [c['course_id'] for c in expected[:limit]]
        final = domain.rank(actual, tags, TERMS, scores, weight)
        assert [c['match'] for c in final] == [c['match'] for c in expected[:limit]]


def test_cache_accounts_for_scores_contribution_and_category_mapping(sql_catalogue, monkeypatch):
    db, version, _, factory = sql_catalogue
    monkeypatch.setattr(domain, 'Session', factory)
    domain._cached_candidates.cache_clear()
    for scores, weight, terms in [({'technology': 80, 'mathematics': 60}, 60, TERMS),
                                  ({'technology': 80, 'mathematics': 60}, 60, TERMS),
                                  ({'technology': 20, 'mathematics': 60}, 60, TERMS),
                                  ({'technology': 80, 'mathematics': 60}, 10, TERMS),
                                  ({'technology': 80, 'mathematics': 60}, 60, TERMS + [{'id': 'extra', 'type': 'interest'}])]:
        domain.candidates(db, ['technology', 'mathematics'], version, scores=scores, interest_contribution=weight, terms=terms)
    info = domain._cached_candidates.cache_info()
    assert info.hits == 1 and info.misses == 4
    domain._cached_candidates.cache_clear()


@pytest.fixture
def student_client(monkeypatch):
    import importlib
    from backend.meraki.security import db_session
    seed_module = importlib.import_module('backend.meraki.seed')
    engine = create_engine('sqlite://', poolclass=StaticPool, connect_args={'check_same_thread': False})
    factory = sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(seed_module, 'engine', engine)
    monkeypatch.setattr(seed_module, 'Session', factory)
    monkeypatch.setattr(domain, 'Session', factory)
    domain._cached_candidates.cache_clear()
    def session_override():
        with factory() as db: yield db
    app.dependency_overrides[db_session] = session_override
    with TestClient(app) as c:
        email = str(uuid.uuid4()) + '@example.test'
        registered=c.post('/api/auth/register', json={'name': 'Scoring test', 'email': email, 'password': os.environ['DEMO_PASSWORD'], 'role': 'student'})
        assert registered.status_code == 200, registered.text
        result = c.post('/api/auth/login', json={'email': email, 'password': os.environ['DEMO_PASSWORD']})
        yield c, {'Authorization': 'Bearer ' + result.json()['token']}
    app.dependency_overrides.clear()
    domain._cached_candidates.cache_clear()
    engine.dispose()


def pdf_text(response):
    assert response.status_code == 200
    return ' '.join(p.extract_text() for p in PdfReader(io.BytesIO(response.content)).pages)


def test_private_profile_snapshots_and_pdf_preserve_exact_inputs(student_client, monkeypatch):
    c, h = student_client
    body = {'tags': ['technology', 'mathematics'], 'scores': {'technology': 80, 'mathematics': 60}, 'interest_contribution': 60}
    saved = c.put('/api/profile', headers=h, json=body)
    assert saved.status_code == 200, saved.text
    assert c.get('/api/me', headers=h).json()['profile'] == {**body, 'tags': ['mathematics', 'technology'], 'aptitude_contribution': 40, 'contributions': {'interest': 60, 'aptitude': 40}, 'scoring_version': POLICY_VERSION}
    run = c.post('/api/recommendations', headers=h, json=body).json()
    assert run['scores'] == body['scores'] and run['scoring_policy'] == POLICY_DESCRIPTION
    assert run['items'][0]['match'] == 60  # degree has 1 interest, 2 aptitudes: 80*.6 + 30*.4
    old = c.get('/api/history', headers=h).json()
    report = pdf_text(c.get('/api/recommendations/'+run['id']+'/report', headers=h))
    assert 'Technology: 80%' in report and 'Mathematics: 60%' in report
    assert 'matched score sum 80 / degree count 1 = 80.00%' in report
    assert 'matched score sum 60 / degree count 2 = 30.00%' in report
    assert 'Preference match: 60.0%' in report and POLICY_VERSION in report
    assert 'interests 60%; aptitudes 40%' in report
    assert 'admission probability or verified academic performance' in report
    c.put('/api/profile', headers=h, json={'tags': ['design'], 'scores': {'design': 25}, 'interest_contribution': 10})
    assert c.get('/api/history', headers=h).json() == old
    import backend.meraki.app as module
    monkeypatch.setattr(module, 'POLICY_DESCRIPTION', 'A future policy description must not replace saved policy text.')
    assert pdf_text(c.get('/api/recommendations/'+run['id']+'/report', headers=h)) == report


def test_legacy_history_and_pdf_are_not_reinterpreted(student_client):
    c, h = student_client
    user = c.get('/api/me', headers=h).json()['id']
    saved = {'tags': ['technology'], 'items': [{**course(), 'match': 100, 'matched_tags': ['technology'], 'components': {'interest': 100, 'aptitude': 0}}],
             'version_id': 'historical-version', 'scoring_version': 'selected-coverage-70-30-v1'}
    with domain.Session() as db:
        r = add(db, 'recommendation', saved, owner=user);db.commit();id = r.id
    text = pdf_text(c.get('/api/recommendations/'+id+'/report', headers=h))
    assert '70% selected-interest coverage + 30% selected-aptitude coverage' in text
    assert 'degree count' not in text and 'Preference match: 100%' in text
    assert c.get('/api/history', headers=h).json()[0]['items'] == saved['items']


@pytest.mark.parametrize('body', [
    {'tags': ['technology'], 'scores': {'design': 50}},
    {'tags': ['technology'], 'scores': {'technology': True}},
    {'tags': ['technology'], 'scores': {'technology': '80'}},
    {'tags': ['technology'], 'scores': {'technology': -1}},
    {'tags': ['technology'], 'scores': {'technology': 101}},
    {'tags': ['technology'], 'interest_contribution': 101},
    {'tags': ['technology'], 'interest_contribution': False},
    {'tags': ['technology'], 'interest_contribution': '70'},
    {'tags': ['technology'], 'scores': {'technology': 0}},
])
def test_api_rejects_invalid_inputs_without_saving(student_client, body):
    c, h = student_client
    before = c.get('/api/me', headers=h).json()['profile']
    for url in ['/api/profile', '/api/recommendations']:
        r = c.request('PUT' if url.endswith('profile') else 'POST', url, headers=h, json=body)
        assert r.status_code == 422, r.text
    assert c.get('/api/me', headers=h).json()['profile'] == before


@pytest.mark.parametrize('value', ['NaN', 'Infinity', '-Infinity'])
def test_nonfinite_json_returns_validation_error(student_client,value):
    c,h=student_client
    body='{"tags":["technology"],"scores":{"technology":'+value+'}}'
    r=c.post('/api/recommendations',headers={**h,'Content-Type':'application/json'},content=body)
    assert r.status_code==422
    assert 'finite' in r.json()['detail']


def test_pdf_preserves_fractional_scores_and_profile_is_private(student_client):
    c,h=student_client
    body={'tags':['design'],'scores':{'design':80.123456789},'interest_contribution':60.123456789}
    r=c.post('/api/recommendations',headers=h,json=body)
    assert r.status_code==200,r.text
    run=r.json()
    text=pdf_text(c.get('/api/recommendations/'+run['id']+'/report',headers=h))
    assert 'Design: 80.123456789%' in text
    assert 'interests 60.123456789%; aptitudes 39.876543211%' in text
    assert run['contributions']=={'interest':100,'aptitude':0}
    other=c.post('/api/auth/login',json={'email':'student@meraki.local','password':os.environ['DEMO_PASSWORD']}).json()['token']
    headers={'Authorization':'Bearer '+other}
    assert c.get('/api/me',headers=headers).json()['profile'].get('scores',{}) != body['scores']
    assert c.get('/api/recommendations/'+run['id']+'/report',headers=headers).status_code==404
