import os
from pathlib import Path
import io,importlib
import pytest
from sqlalchemy import create_engine,select,func
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient
from rdflib import Graph,Namespace,RDF
from backend.meraki.legacy import plan

ONTOLOGY=Path(__file__).parents[1]/'fixtures'/'prototype-ontology.owl'
@pytest.fixture
def migrated_client(tmp_path,monkeypatch):
    from backend.meraki import db,domain,security
    seedmod=importlib.import_module('backend.meraki.seed')
    engine=create_engine('sqlite:///'+str(tmp_path/'migration.db'),connect_args={'check_same_thread':False})
    factory=sessionmaker(engine,expire_on_commit=False)
    for module in (db,domain,security,seedmod):monkeypatch.setattr(module,'Session',factory)
    monkeypatch.setattr(seedmod,'engine',engine)
    domain._cached_candidates.cache_clear()
    from backend.meraki.app import app
    with TestClient(app) as c:yield c
    domain._cached_candidates.cache_clear();engine.dispose()

def headers(c,email):
    r=c.post('/api/auth/login',json={'email':email,'password':os.environ['DEMO_PASSWORD']});assert r.status_code==200,r.text
    return {'Authorization':'Bearer '+r.json()['token']}

def test_legacy_graph_resolution_is_lossless():
    data=plan(ONTOLOGY.read_bytes())
    assert data['degree_concepts']==201;assert data['offering_count']==211
    assert data['university_count']==3;assert data['faculty_class_count']==19;assert data['faculty_associations']==20
    assert data['tag_count']==207;assert data['unresolved']==[];assert len(data['resolved_shared_concepts'])==10
    chemistry=[c for c in data['offerings'] if c['legacy_id'].endswith('#BachelorOfScienceHonoursInChemistry')]
    assert {(c['university'],c['faculty']) for c in chemistry}=={('University of Kelaniya','Faculty of Science'),('University of Sri Jayewardenepura','Faculty of Applied Sciences')}
    assert len({c['course_id'] for c in data['offerings']})==211
    assert all(c['legacy_tags'] for c in data['offerings'])

def test_legacy_rejects_entity_declarations():
    with pytest.raises(ValueError,match='entity'):plan(b'<!DOCTYPE a [<!ENTITY x SYSTEM "file:///etc/passwd">]><rdf/>')

def test_full_legacy_review_publication_recommendation_and_restore(migrated_client):
    c=migrated_client;admin=headers(c,'admin@meraki.local');student=headers(c,'student@meraki.local');rep=headers(c,'university@meraki.local')
    blob=ONTOLOGY.read_bytes()
    assert c.post('/api/admin/legacy/preview',headers=student,files={'file':('ontology.owl',blob,'application/rdf+xml')}).status_code==403
    before=c.get('/api/admin/versions',headers=admin).json()[0]['id']
    preview=c.post('/api/admin/legacy/preview',headers=admin,files={'file':('ontology.owl',blob,'application/rdf+xml')});assert preview.status_code==200,preview.text
    id=preview.json()['id'];assert preview.json()['plan']['offering_count']==211
    staged=c.post('/api/admin/legacy/'+id+'/stage',headers=admin);assert staged.status_code==200,staged.text
    ids=staged.json()['revision_ids'];assert len(ids)==211
    assert c.post('/api/admin/legacy/'+id+'/stage',headers=admin).json()['already_staged']
    assert len(c.get('/api/courses').json())==6
    for rid in ids:
        r=c.post('/api/admin/decisions/'+rid,headers=admin,json={'decision':'approved','reason':'Structural migration review: original reciprocal affiliation and tag assertions preserved; current availability not verified.'});assert r.status_code==200,r.text
    for course in c.get('/api/courses').json():
        assert c.post('/api/admin/courses/'+course['course_id']+'/archive',headers=admin,json={'reason':'Replace illustrative seed with recoverable prototype migration'}).status_code==200
    published=c.post('/api/admin/publish',headers=admin);assert published.status_code==200,published.text
    version=published.json()['id'];courses=c.get('/api/courses').json();assert len(courses)==211
    assert not any(x.get('illustrative') for x in courses)
    assert len({x['university'] for x in courses})==3
    assert len(c.get('/api/courses',params={'q':'Moratuwa'}).json())==20
    tags=c.get('/api/taxonomy').json();interest=next(t['id'] for t in tags if t['label']=='Chemistry' and t['type']=='interest')
    run=c.post('/api/recommendations',headers=student,json={'tags':[interest,'mathematics']});assert run.status_code==200,run.text
    shared=[x for x in run.json()['items'] if x['legacy_id'].endswith('#BachelorOfScienceHonoursInChemistry')];assert len(shared)==2
    assert shared[0]['course_id']!=shared[1]['course_id'];assert all(0<x['match']<=100 and x['scoring_details']['interest']['degree_count']>=1 for x in shared)
    pdf=c.get('/api/recommendations/'+run.json()['id']+'/report',headers=student);assert pdf.status_code==200
    from pypdf import PdfReader
    text=' '.join(p.extract_text() for p in PdfReader(io.BytesIO(pdf.content)).pages)
    assert 'University of Kelaniya' in text;assert 'not reverified' in text
    assert c.get('/api/drafts',headers=rep).status_code==200
    assert not any(x.get('legacy_import') for x in c.get('/api/drafts',headers=rep).json())
    ttl=c.get('/api/admin/versions/'+version+'/rdf',headers=admin);g=Graph().parse(data=ttl.text,format='turtle');ns=Namespace('https://meraki.example/ontology/')
    assert len(set(g.subjects(RDF.type,ns.University)))==3
    assert len(set(g.subjects(RDF.type,ns.Faculty)))==20
    assert len(set(g.subjects(RDF.type,ns.DegreeConcept)))==201
    assert len(set(g.subjects(RDF.type,ns.CourseOffering)))==211
    assert c.post('/api/admin/versions/'+before+'/restore',headers=admin,json={'reason':'Migration recovery check'}).status_code==200
    assert len(c.get('/api/courses').json())==6
    assert c.post('/api/admin/versions/'+version+'/restore',headers=admin,json={'reason':'Reactivate tested migration snapshot'}).status_code==200
    assert len(c.get('/api/courses').json())==211
