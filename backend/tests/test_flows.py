import os,tempfile
from pathlib import Path
os.environ['DATABASE_URL']='sqlite:///'+str(Path(tempfile.mkdtemp())/'test.db')
os.environ['APP_ENV']='development';os.environ['AUTH_PROVIDER']='development'
from fastapi.testclient import TestClient
from backend.meraki.app import app
from backend.meraki.domain import rank
from backend.meraki.security import public_url
from worker.run import once
import pytest

@pytest.fixture(scope='module')
def client():
    with TestClient(app) as c:yield c
def login(c,email='student@meraki.local'):
    r=c.post('/api/auth/login',json={'email':email,'password':os.environ['DEMO_PASSWORD']});assert r.status_code==200,r.text
    return {'Authorization':'Bearer '+r.json()['token']}

def test_catalogue_and_deterministic_scoring(client):
    s=login(client);courses=client.get('/api/courses').json();assert len(courses)==6
    a=client.post('/api/recommendations',headers=s,json={'tags':['technology','mathematics']});assert a.status_code==200,a.text
    rows=a.json()['items'];assert len({x['course_id'] for x in rows})==len(rows);assert rows[0]['match']==85
    assert client.post('/api/recommendations',headers=s,json={'tags':[]}).status_code==422
    assert client.post('/api/recommendations',headers=s,json={'tags':['bad']} ).status_code==422
    assert rank([{'course_id':'x','title':'A','tags':['technology']}],['technology'])[0]['match']==100
    assert rank([{'course_id':'x','title':'A','tags':[]}],['technology'])==[]

def test_private_report_and_sessions(client):
    s=login(client);run=client.post('/api/recommendations',headers=s,json={'tags':['technology']}).json()
    report=client.get('/api/recommendations/'+run['id']+'/report',headers=s);assert report.status_code==200;assert report.content.startswith(b'%PDF')
    from pypdf import PdfReader
    import io
    assert 'Meraki' in PdfReader(io.BytesIO(report.content)).pages[0].extract_text()
    email='other@example.test';assert client.post('/api/auth/register',json={'name':'Other Student','email':email,'password':os.environ['DEMO_PASSWORD'],'role':'student'}).status_code==200
    other=login(client,email)
    assert client.get('/api/recommendations/'+run['id']+'/report',headers=other).status_code==404
    assert client.get('/api/history',headers=other).json()==[]
    client.put('/api/profile',headers=other,json={'tags':[]})
    assert client.get('/api/me',headers=s).json()['profile']['tags']!=[]
    client.post('/api/auth/logout',headers=other)
    assert client.get('/api/me',headers=other).status_code==401

def test_permissions_and_verification(client):
    s=login(client);r=login(client,'university@meraki.local')
    assert client.get('/api/admin/queue',headers=s).status_code==403
    assert client.post('/api/admin/publish',headers=r).status_code==403
    assert client.post('/api/sources',headers=s,data={'url':'https://example.com','method':'nlp'}).status_code==403
    client.post('/api/auth/register',json={'name':'New Representative','email':'newrep@example.test','password':os.environ['DEMO_PASSWORD'],'role':'representative','university':'New University'})
    pending=login(client,'newrep@example.test')
    assert client.get('/api/drafts',headers=pending).status_code==403
    org=client.get('/api/me',headers=pending).json()['org'];admin=login(client,'admin@meraki.local')
    assert client.post('/api/admin/organizations/'+org+'/verify',headers=admin,json={'verified':True}).status_code==200
    assert client.get('/api/drafts',headers=pending).status_code==200
    assert client.get('/api/drafts',headers=pending).json()==[]

def test_multi_course_to_publication_restore_and_partial_approval(client):
    rep=login(client,'university@meraki.local');admin=login(client,'admin@meraki.local');student=login(client)
    old=client.get('/api/admin/versions',headers=admin).json()[0]['id']
    text=b'Faculty of Computing\nBSc Applied Robotics\nBSc Applied Statistics\nBSc Applied Software Engineering\n'
    source=client.post('/api/sources',headers=rep,data={'method':'nlp','url':'https://example.com/catalogue'},files={'file':('prospectus.txt',text,'text/plain')});assert source.status_code==200,source.text
    assert once()
    drafts=[x for x in client.get('/api/drafts',headers=rep).json() if x.get('source_id')==source.json()['id']];assert len(drafts)==3
    ids=[]
    for i,d in enumerate(drafts):
        body={'title':d['title'],'faculty':d['faculty'],'tags':['technology','mathematics'],'course_url':'https://example.com/robotics','url_mode':'source' if i==1 else 'custom','revision':d['revision']}
        edited=client.put('/api/drafts/'+d['id'],headers=rep,json=body);assert edited.status_code==200,edited.text
        assert edited.json()['course_url']==('https://example.com/catalogue' if i==1 else 'https://example.com/robotics')
        ids.append(d['id'])
    baseline=client.get('/api/courses').json();assert len(baseline)==6
    sub=client.post('/api/submissions',headers=rep,json={'ids':ids});assert sub.status_code==200,sub.text
    assert client.put('/api/drafts/'+ids[0],headers=rep,json=body).status_code==409
    for i,id in enumerate(ids):
        r=client.post('/api/admin/decisions/'+id,headers=admin,json={'decision':'approved' if i<2 else 'changes_requested','reason':'Checked source evidence; please correct missing details' });assert r.status_code==200,r.text
    assert len(client.get('/api/courses').json())==6
    p=client.post('/api/admin/publish',headers=admin);assert p.status_code==200,p.text
    assert len(client.get('/api/courses').json())==8
    assert client.post('/api/admin/publish',headers=admin).status_code==409
    restored=client.post('/api/admin/versions/'+old+'/restore',headers=admin,json={'reason':'Testing restoration of previous catalogue'});assert restored.status_code==200
    assert len(client.get('/api/courses').json())==6
    assert client.get('/api/admin/audit',headers=admin).json()

def test_events_and_consent(client):
    s=login(client);rep=login(client,'university@meraki.local');c=next(x for x in client.get('/api/courses').json() if x['org']=='org-northbridge')
    body={'event_id':'duplicate-test-event','type':'course_view','course_id':c['course_id']}
    assert client.post('/api/events',headers=s,json=body).status_code==200
    assert client.post('/api/events',headers=s,json={'event_id':'catalogue-search-test','type':'catalogue_search','query_length':12}).status_code==200
    client.post('/api/events',headers=s,json=body)
    enq={'course_id':c['course_id'],'message':'Please share more information about this course','consent':False,'idempotency_key':'enquiry-test-key'}
    assert client.post('/api/enquiries',headers=s,json=enq).status_code==422
    enq['consent']=True
    r=client.post('/api/enquiries',headers=s,json=enq);assert r.status_code==200
    assert client.post('/api/enquiries',headers=s,json=enq).json()['id']==r.json()['id']
    assert any(x['id']==r.json()['id'] for x in client.get('/api/enquiries',headers=rep).json())
    counts=client.get('/api/analytics',headers=rep).json()['counts'];assert counts['course_view']==1;assert counts['enquiry']==1

@pytest.mark.parametrize('url',['http://127.0.0.1/a','http://10.0.0.1','http://169.254.169.254','http://localhost','http://metadata.google.internal','file:///etc/passwd',pytest.param('https://'+'user:'+os.environ['DEMO_PASSWORD']+'@example.com',id='embedded-credentials')])
def test_block_unsafe_urls(url):
    with pytest.raises(Exception):public_url(url)

def test_failed_source_does_not_modify_catalogue(client):
    rep=login(client,'university@meraki.local');baseline=client.get('/api/courses').json()
    response=client.post('/api/sources',headers=rep,data={'method':'nlp'},files={'file':('empty.txt',b'This source has no degree headings at all.','text/plain')});assert response.status_code==200
    once();source=next(s for s in client.get('/api/sources',headers=rep).json() if s['id']==response.json()['id'])
    assert source['state']=='failed';assert client.get('/api/courses').json()==baseline

def test_unconfigured_gemini_is_rejected_before_queuing(client,monkeypatch,tmp_path):
    from backend.meraki import gemini
    monkeypatch.setattr(gemini,'ENV_FILE',tmp_path/'.env')
    for name in ('GEMINI_API_KEY','GEMINI_PROVIDER','GEMINI_MODEL'):
        monkeypatch.delenv(name,raising=False)
    rep=login(client,'university@meraki.local')
    before=client.get('/api/sources',headers=rep).json()
    response=client.post('/api/sources',headers=rep,data={'method':'gemini'},files={'file':('sample.txt',b'Faculty of Computing\nBSc Computing','text/plain')})
    assert response.status_code==503
    assert 'GEMINI_API_KEY' in response.json()['detail']
    assert client.get('/api/sources',headers=rep).json()==before
    health=client.get('/api/health').json()
    assert not health['gemini_configured']
    assert health['gemini']['provider']=='developer'

def test_dynamic_taxonomy_manual_draft_and_cross_tenant_denial(client):
    admin=login(client,'admin@meraki.local');rep=login(client,'university@meraki.local');student=login(client)
    r=client.post('/api/admin/taxonomy',headers=admin,json={'id':'scientific-reasoning','label':'Scientific reasoning','type':'aptitude'});assert r.status_code==200
    assert any(t['id']=='scientific-reasoning' for t in client.get('/api/taxonomy').json())
    manual=client.post('/api/drafts',headers=rep,json={'title':'BSc Materials Design','faculty':'Faculty of Engineering','course_url':'https://example.com/materials','evidence':'The university prospectus lists BSc Materials Design.'});assert manual.status_code==200
    d=manual.json()
    body={'title':d['title'],'faculty':d['faculty'],'tags':['scientific-reasoning'],'course_url':d['course_url'],'url_mode':'custom','revision':d['revision']}
    other=login(client,'newrep@example.test')
    assert client.put('/api/drafts/'+d['id'],headers=other,json=body).status_code==404
    assert client.put('/api/drafts/'+d['id'],headers=rep,json=body).status_code==200
    assert client.post('/api/admin/taxonomy',headers=student,json={'id':'bad-tag','label':'Bad tag','type':'interest'}).status_code==403

def test_cancelled_job_does_not_extract(client):
    rep=login(client,'university@meraki.local')
    r=client.post('/api/sources',headers=rep,data={'method':'nlp'},files={'file':('cancel.txt',b'Faculty of Science\nBSc Cancelled Test Course\n','text/plain')});assert r.status_code==200
    id=r.json()['id'];assert client.post('/api/sources/'+id+'/cancel',headers=rep).status_code==200
    assert once(id)==False
    assert not any(c['title']=='BSc Cancelled Test Course' for c in client.get('/api/drafts',headers=rep).json())

def test_account_deletion_removes_private_history(client):
    email='deletion@example.test';client.post('/api/auth/register',json={'name':'Delete Me','email':email,'password':os.environ['DEMO_PASSWORD'],'role':'student'})
    h=login(client,email);r=client.post('/api/recommendations',headers=h,json={'tags':['technology']});assert r.status_code==200
    assert client.delete('/api/account',headers=h).status_code==200
    assert client.get('/api/me',headers=h).status_code==401

def test_private_ipv6_links_are_blocked():
    for url in ['http://[::1]','http://[fd00::1]']:
        with pytest.raises(Exception):public_url(url)
