import os,io,json,hashlib,secrets,time
from datetime import datetime,timezone,timedelta
from contextlib import asynccontextmanager
from collections import defaultdict
from typing import Literal,Annotated
from pathlib import Path
from fastapi import FastAPI,Depends,HTTPException,UploadFile,File,Form,Request
from fastapi.responses import Response,FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel,Field,ConfigDict
from sqlalchemy import select,update,delete,func
from .db import Session,Record,Active,VersionCourse,Edge,record,add,uid,now,audit
from .security import user,role,representative,db_session,password_hash,password_ok,AUTH,ENV,public_url
from .domain import TAXONOMY,taxonomy as get_taxonomy,get_active,catalogue,candidates,new_revision,rank,publish
from .seed import seed
from .extraction import MAX_BYTES,parse_source
from .limits import budget
from .scoring import inputs as scoring_inputs,POLICY_VERSION,POLICY_DESCRIPTION,LEGACY_POLICY_DESCRIPTION,number_text,rounded

@asynccontextmanager
async def lifespan(app):
    seed();yield
app=FastAPI(title='Meraki API',version='0.1.0',lifespan=lifespan,docs_url='/api/docs',openapi_url='/api/openapi.json')
@app.exception_handler(RequestValidationError)
async def validation_error(request,error):
    # Do not echo passwords or non-finite input values into error responses.
    return JSONResponse(status_code=422,content={'detail':'; '.join('.'.join(str(p) for p in e['loc'][1:])+': '+e['msg'] for e in error.errors())})
from .legacy_api import router as legacy_router
app.include_router(legacy_router)
app.add_middleware(CORSMiddleware,allow_origins=os.getenv('CORS_ORIGINS','http://127.0.0.1:5173,http://localhost:5173').split(','),allow_methods=['GET','POST','PUT','DELETE'],allow_headers=['Authorization','Content-Type','Idempotency-Key'])
@app.middleware('http')
async def headers(request,call_next):
    response=await call_next(request)
    response.headers['X-Content-Type-Options']='nosniff';response.headers['Referrer-Policy']='strict-origin-when-cross-origin';response.headers['X-Frame-Options']='DENY';response.headers['Cache-Control']='no-store'
    return response

def safe_user(u):return {k:v for k,v in record(u).items() if k!='password'}
def owned(db,id,u,kind=None):
    r=db.get(Record,id)
    if not r or (kind and r.kind!=kind):raise HTTPException(404,'Record not found')
    if r.owner!=u.id and (not u.org or r.org!=u.org) and u.data['role']!='admin':raise HTTPException(404,'Record not found')
    return r
def own_private(db,id,u,kind):
    r=db.get(Record,id)
    if not r or r.kind!=kind or r.owner!=u.id:raise HTTPException(404,'Record not found')
    return r
def event(db,u,type,**data):
    eid=data.pop('event_id',uid());key=f'event:{u.id}:{eid}'
    if not db.get(Record,key):add(db,'event',{'type':type,**data},id=key,owner=u.id,org=data.get('organization_id',''))
def validate_tags(tags,db=None):
    terms=get_taxonomy(db) if db else TAXONOMY
    if not set(tags)<={t['id'] for t in terms}:raise HTTPException(422,'Unknown taxonomy tag')
def current_course(db,cid):
    courses=catalogue(db);c=next((c for c in courses if c['course_id']==cid),None)
    if not c:raise HTTPException(404,'Published course not found')
    return c

@app.get('/api/health')
def health():
    from .gemini import status
    gemini=status()
    return {'status':'ok','auth_provider':AUTH,'environment':ENV,'google_sign_in_enabled':os.getenv('FIREBASE_GOOGLE_SIGN_IN_ENABLED','false').lower()=='true','gemini_configured':gemini['configured'],'gemini':gemini}
@app.get('/api/taxonomy')
def taxonomy(db=Depends(db_session)):return get_taxonomy(db)
@app.get('/api/me')
def me(u=Depends(user),db=Depends(db_session)):
    result=safe_user(u);org=db.get(Record,u.org) if u.org else None
    result['organization']=record(org) if org else None;return result

class Register(BaseModel):
    name:str=Field(min_length=2,max_length=100)
    email:str=Field(min_length=5,max_length=200,pattern=r'^[^\s@]+@[^\s@]+\.[^\s@]+$')
    password:str=Field(min_length=12,max_length=128)
    role:Literal['student','representative']='student'
    university:str=Field(default='',max_length=200)
class Login(BaseModel):
    email:str=Field(max_length=200)
    password:str=Field(max_length=128)
@app.post('/api/auth/register')
def register(body:Register,request:Request,db=Depends(db_session)):
    if AUTH!='development':raise HTTPException(404,'Register using Firebase client authentication')
    budget(db,request.client.host,'register',10)
    email=body.email.lower()
    if any(r.data['email']==email for r in db.scalars(select(Record).where(Record.kind=='user'))):raise HTTPException(409,'An account already exists')
    org=''
    if body.role=='representative':
        if not body.university.strip():raise HTTPException(422,'University name is required')
        org=add(db,'organization',{'name':body.university,'contact':email},state='pending').id
    u=add(db,'user',{'name':body.name,'email':email,'password':password_hash(body.password),'role':body.role,'profile':{'tags':[]}},org=org,state='active');db.commit()
    return {'id':u.id,'message':'Development account created. Email verification is not simulated.'}
@app.post('/api/auth/login')
def login(body:Login,request:Request,db=Depends(db_session)):
    if AUTH!='development':raise HTTPException(404,'Use Firebase sign in')
    budget(db,request.client.host,'login',60)
    u=next((r for r in db.scalars(select(Record).where(Record.kind=='user')) if r.data['email']==body.email.lower()),None)
    if not u or not password_ok(body.password,u.data['password']):raise HTTPException(401,'Invalid email or password')
    token=secrets.token_urlsafe(40);key='session:'+hashlib.sha256(token.encode()).hexdigest()
    add(db,'session',{'expires_at':(datetime.now(timezone.utc)+timedelta(hours=8)).isoformat()},id=key,owner=u.id);db.commit();return {'token':token,'user':safe_user(u)}
@app.post('/api/auth/logout')
def logout(request:Request,u=Depends(user),db=Depends(db_session)):
    if AUTH=='development':
        token=request.headers.get('authorization','').removeprefix('Bearer ');r=db.get(Record,'session:'+hashlib.sha256(token.encode()).hexdigest())
        if r:db.delete(r);db.commit()
    return {'ok':True}

class Provision(BaseModel):
    name:str=Field(min_length=2,max_length=100)
    role:Literal['student','representative']
    university:str=Field(default='',max_length=200)
@app.post('/api/auth/firebase-onboard')
def firebase_onboard(body:Provision,request:Request,db=Depends(db_session)):
    if AUTH!='firebase':raise HTTPException(404)
    import firebase_admin
    from firebase_admin import auth
    if not firebase_admin._apps:firebase_admin.initialize_app()
    try:claims=auth.verify_id_token(request.headers.get('authorization','').removeprefix('Bearer '),check_revoked=True)
    except Exception:raise HTTPException(401,'Invalid identity')
    if not claims.get('email_verified'):raise HTTPException(403,'Verify your email before onboarding')
    id='firebase:'+claims['uid'];existing=db.get(Record,id)
    if existing:return safe_user(existing)
    org=''
    if body.role=='representative':
        university=body.university.strip()
        if not university:raise HTTPException(422,{'code':'university_required','message':'Enter your university name to complete account setup.'})
        org=add(db,'organization',{'name':university,'contact':claims['email']},state='pending').id
    u=add(db,'user',{'name':body.name,'email':claims['email'],'role':body.role,'profile':{'tags':[]}},id=id,org=org,state='active');db.commit();return safe_user(u)

Percentage=Annotated[float,Field(strict=True,ge=0,le=100,allow_inf_nan=False)]
class ScoringRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    tags:list[str]=Field(max_length=30)
    scores:dict[str,Percentage]=Field(default_factory=dict)
    interest_contribution:Percentage=70
class Profile(ScoringRequest):pass
@app.put('/api/profile')
def profile(body:Profile,u=Depends(user),db=Depends(db_session)):
    role(u,'student')
    preferences=scoring_inputs(body.tags,body.scores,body.interest_contribution,get_taxonomy(db),allow_empty=True)
    u=db.get(Record,u.id);u.data={**u.data,'profile':preferences}
    audit(db,u.id,'profile_changed',u.id);db.commit();return safe_user(u)
@app.get('/api/courses')
def courses(q:str='',tag:str='',db=Depends(db_session)):
    if len(q)>200:raise HTTPException(422,'Search is too long')
    rows=catalogue(db)
    return [r for r in rows if (not q or q.casefold() in (r['title']+' '+r['university']+' '+r['faculty']).casefold()) and (not tag or tag in r['tags'])]
@app.get('/api/courses/{cid}')
def course(cid:str,u=Depends(user),db=Depends(db_session)):
    c=current_course(db,cid);event(db,u,'course_view',course_id=cid,organization_id=c['org']);db.commit();return c
class Recommend(ScoringRequest):
    tags:list[str]=Field(min_length=1,max_length=30)
@app.post('/api/recommendations')
def recommendations(body:Recommend,u=Depends(user),db=Depends(db_session)):
    role(u,'student');terms=get_taxonomy(db)
    preferences=scoring_inputs(body.tags,body.scores,body.interest_contribution,terms)
    budget(db,u.id,'recommend',30)
    active=get_active(db)
    options={'scores':preferences['scores'],'interest_contribution':preferences['interest_contribution'],'terms':terms}
    rows=rank(candidates(db,body.tags,active.version_id,**options),body.tags,**options)
    r=add(db,'recommendation',{**preferences,'tag_labels':{t['id']:t['label'] for t in terms},
        'items':rows,'version_id':active.version_id,'scoring_policy':POLICY_DESCRIPTION,'result_limit':100},owner=u.id)
    u=db.get(Record,u.id);u.data={**u.data,'profile':preferences}
    event(db,u,'search',run_id=r.id,version_id=active.version_id);db.commit();return record(r)
@app.get('/api/history')
def history(u=Depends(user),db=Depends(db_session)):
    role(u,'student');return [record(r) for r in db.scalars(select(Record).where(Record.kind=='recommendation',Record.owner==u.id).order_by(Record.created_at.desc()).limit(30))]
@app.get('/api/saved')
def saved(u=Depends(user),db=Depends(db_session)):
    role(u,'student');ids={r.data['course_id'] for r in db.scalars(select(Record).where(Record.kind=='saved',Record.owner==u.id))};return [c for c in catalogue(db) if c['course_id'] in ids]
@app.post('/api/saved/{cid}')
def toggle_save(cid:str,u=Depends(user),db=Depends(db_session)):
    role(u,'student');current_course(db,cid);key=f'saved:{u.id}:{cid}';r=db.get(Record,key)
    if r:db.delete(r)
    else:add(db,'saved',{'course_id':cid},id=key,owner=u.id)
    db.commit();return {'saved':not bool(r)}

class Activity(BaseModel):
    event_id:str=Field(min_length=8,max_length=100)
    type:Literal['course_view','contact_intent','explore_course','catalogue_search']
    course_id:str|None=None
    query_length:int=Field(default=0,ge=0,le=200)
    run_id:str|None=None
@app.post('/api/events')
def activity(body:Activity,u=Depends(user),db=Depends(db_session)):
    if body.type=='catalogue_search':
        event(db,u,'search',event_id=body.event_id,search_kind='catalogue',query_length=body.query_length);db.commit();return {'ok':True}
    if not body.course_id:raise HTTPException(422,'Course ID is required for course activity')
    c=current_course(db,body.course_id)
    if body.run_id:own_private(db,body.run_id,u,'recommendation')
    event(db,u,body.type,event_id=body.event_id,course_id=body.course_id,run_id=body.run_id,organization_id=c['org']);db.commit();return {'ok':True}
class Enquiry(BaseModel):
    course_id:str
    message:str=Field(min_length=10,max_length=3000)
    consent:bool
    idempotency_key:str=Field(min_length=8,max_length=100)
    run_id:str|None=None
@app.post('/api/enquiries')
def enquiry(body:Enquiry,u=Depends(user),db=Depends(db_session)):
    role(u,'student')
    if not body.consent:raise HTTPException(422,'Consent is required to share contact details')
    key='enquiry:'+u.id+':'+body.idempotency_key;existing=db.get(Record,key)
    if existing:return record(existing)
    c=current_course(db,body.course_id)
    run_id=None
    if body.run_id:
        r=own_private(db,body.run_id,u,'recommendation')
        if any(x['course_id']==body.course_id for x in r.data['items']) and (datetime.now(timezone.utc)-datetime.fromisoformat(r.created_at)).days<7:run_id=r.id
    r=add(db,'enquiry',{'course_id':body.course_id,'course_title':c['title'],'name':u.data['name'],'email':u.data['email'],'message':body.message,'consent_at':now(),'run_id':run_id,'delivery':'stored in university inbox; no external email sent'},id=key,owner=u.id,org=c['org'],state='submitted')
    event(db,u,'enquiry',course_id=body.course_id,organization_id=c['org'],run_id=run_id);db.commit();return record(r)
@app.get('/api/enquiries')
def enquiries(u=Depends(user),db=Depends(db_session)):
    query=select(Record).where(Record.kind=='enquiry')
    if u.data['role']=='student':query=query.where(Record.owner==u.id)
    elif u.data['role']=='representative':representative(db,u);query=query.where(Record.org==u.org)
    else:role(u,'admin')
    return [record(r) for r in db.scalars(query.order_by(Record.created_at.desc()))]

@app.get('/api/recommendations/{rid}/report')
def report(rid:str,u=Depends(user),db=Depends(db_session)):
    r=own_private(db,rid,u,'recommendation')
    from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer
    from reportlab.lib.styles import getSampleStyleSheet
    from xml.sax.saxutils import escape
    from reportlab.lib.colors import HexColor
    out=io.BytesIO();styles=getSampleStyleSheet();styles['Title'].textColor=HexColor('#0B2E63');styles['Heading2'].textColor=HexColor('#0B2E63');story=[Paragraph('Meraki | Your course shortlist',styles['Title']),Paragraph('Find Your Path. Follow Your Passion.',styles['Normal']),Spacer(1,15)]
    story.append(Paragraph(escape(f'Created: {r.created_at[:10]} | Ontology: {r.data["version_id"]}'),styles['Normal']))
    labels=r.data.get('tag_labels',{})
    story.append(Paragraph(escape('Preferences: '+', '.join(labels.get(t,t) for t in r.data['tags'])),styles['Normal']))
    modern=r.data.get('scoring_version')=='degree-category-score-coverage-v2'
    if modern:
        story.append(Paragraph(escape('Student scores: '+', '.join(f'{labels.get(t,t)}: {number_text(r.data["scores"][t])}%' for t in r.data['tags'])),styles['Normal']))
        configured=f'Configured contributions: interests {number_text(r.data["interest_contribution"])}%; aptitudes {number_text(r.data["aptitude_contribution"])}%.'
        effective=r.data['contributions']
        story.append(Paragraph(escape(configured+f' Effective contributions: interests {number_text(effective["interest"])}%; aptitudes {number_text(effective["aptitude"])}%.'),styles['Normal']))
        story.append(Paragraph(escape('Scoring policy: '+r.data['scoring_version']),styles['Normal']))
    for c in r.data['items']:
        story += [Spacer(1,16),Paragraph(escape(c['title']),styles['Heading2']),Paragraph(escape(c['university']+' | '+c['faculty']),styles['Normal']),Paragraph(escape(f'Preference match: {c["match"]}% | Matched: '+', '.join(labels.get(t,t) for t in c['matched_tags'])),styles['Normal']),Paragraph(escape(c.get('course_url','')),styles['Normal']),Paragraph(escape('Evidence: '+c.get('evidence','Source not provided')),styles['Normal'])]
        if modern:
            for kind,label in [('interest','Interest'),('aptitude','Aptitude')]:
                d=c['scoring_details'][kind]
                formula=f'{label}: matched score sum {number_text(d["matched_score_sum"])} / degree count {d["degree_count"]} = {rounded(d["coverage"]):.2f}% coverage; contribution {number_text(d["contribution"])}%.' if d['degree_count'] else f'{label}: matched score sum {number_text(d["matched_score_sum"])}; degree count 0; coverage 0% (no listed tags); contribution {number_text(d["contribution"])}%.'
                story.append(Paragraph(escape(formula),styles['Normal']))
        if c.get('legacy_import'):story.append(Paragraph('Imported historical prototype record. Current availability and admission requirements are not reverified; the link opens the university catalogue or homepage.',styles['Normal']))
    story += [Spacer(1,20),Paragraph(escape(r.data.get('scoring_policy',LEGACY_POLICY_DESCRIPTION)),styles['Normal'])]
    def footer(canvas,doc):
        canvas.setFont('Helvetica',8);canvas.setFillColor(HexColor('#52627A'));canvas.drawString(45,22,'Meraki | Private recommendation snapshot');canvas.drawRightString(doc.pagesize[0]-45,22,str(doc.page))
    SimpleDocTemplate(out,title='Meraki shortlist',topMargin=40,bottomMargin=40,leftMargin=45,rightMargin=45).build(story,onFirstPage=footer,onLaterPages=footer)
    return Response(out.getvalue(),media_type='application/pdf',headers={'Content-Disposition':'attachment; filename="meraki-shortlist.pdf"'})

@app.get('/api/sources')
def sources(u=Depends(user),db=Depends(db_session)):
    representative(db,u);return [record(r) for r in db.scalars(select(Record).where(Record.kind=='source',Record.org==u.org).order_by(Record.created_at.desc()))]
@app.post('/api/sources')
async def source(url:str=Form(''),method:Literal['nlp','gemini']=Form('nlp'),file:UploadFile|None=File(None),u=Depends(user),db=Depends(db_session)):
    representative(db,u)
    url=url.strip()
    # Browsers include an empty, nameless upload part for an unused file input.
    # It is not a supplied document and must not hide a valid URL source.
    if file is not None and not file.filename:
        if await file.read(1):raise HTTPException(422,'The uploaded document must have a filename')
        await file.close()
        file=None
    if method=='gemini':
        from .gemini import require_configuration
        try:require_configuration()
        except ValueError as error:raise HTTPException(503,str(error))
    budget(db,u.id,'ingestion',10,3600)
    if not url and not file:raise HTTPException(422,'Upload a document or supply a public URL')
    if url:public_url(url)
    count=db.scalar(select(func.count()).select_from(Record).where(Record.kind=='source',Record.org==u.org,Record.state.in_(['queued','running'])))
    if count>=3:raise HTTPException(429,'Three extraction jobs are already pending for your university')
    source_data={'url':url,'method':method,'name':file.filename[:200] if file else url,'parser_version':'v1','provider':method}
    if file:
        content=await file.read(MAX_BYTES+1)
        if not content:raise HTTPException(422,'The selected document is empty. Choose another file or clear it to use a URL.')
        if len(content)>MAX_BYTES:raise HTTPException(422,'Maximum upload size is 20 MB')
        from .scanning import scan
        try:source_data['malware_scan']=scan(content)
        except ValueError as e:raise HTTPException(422,str(e))
        if not (content.startswith((b'%PDF',b'PK')) or file.content_type in ('text/plain','text/markdown')):raise HTTPException(422,'Upload a PDF, DOCX or UTF-8 text document')
        from .storage import put
        uri=put('sources/'+uid(),content,file.content_type or 'application/octet-stream')
        source_data.update({'object_uri':uri,'mime':file.content_type or '', 'hash':hashlib.sha256(content).hexdigest()})
    r=add(db,'source',source_data,owner=u.id,org=u.org,state='queued');db.commit()
    from .tasks import dispatch
    try:dispatch(r.id)
    except Exception:
        # Durable outbox remains queued; dispatch-pending maintenance job retries.
        audit(db,u.id,'dispatch_pending',r.id,'Task delivery needs retry');db.commit()
    return record(r)
@app.get('/api/drafts')
def drafts(u=Depends(user),db=Depends(db_session)):
    representative(db,u);return [record(r) for r in db.scalars(select(Record).where(Record.kind=='course',Record.org==u.org).order_by(Record.created_at.desc()))]
class CourseEdit(BaseModel):
    title:str=Field(min_length=3,max_length=200)
    faculty:str=Field(min_length=3,max_length=200)
    tags:list[str]=Field(max_length=30)
    course_url:str=Field(max_length=2000)
    url_mode:Literal['source','custom']='custom'
    revision:int
@app.put('/api/drafts/{id}')
def edit_draft(id:str,body:CourseEdit,u=Depends(user),db=Depends(db_session)):
    representative(db,u);r=owned(db,id,u,'course')
    if r.state not in ('draft','changes_requested','rejected'):raise HTTPException(409,'Submitted revisions are frozen. Create a new revision to edit.')
    if r.data.get('revision',1)!=body.revision:raise HTTPException(409,'This draft changed. Reload before saving.')
    validate_tags(body.tags,db);url=body.course_url
    if body.url_mode=='source':
        source=db.get(Record,r.data.get('source_id',''));url=source.data.get('url','') if source else ''
    if url:public_url(url)
    d={**r.data,**body.model_dump(),'course_url':url,'revision':body.revision+1,'reviewed':True}
    r.data=d;r.state='draft';db.execute(delete(Edge).where(Edge.revision_id==id))
    for tag in set(body.tags):db.add(Edge(revision_id=id,tag_id=tag))
    audit(db,u.id,'edit_draft',id);db.commit();return record(r)
@app.post('/api/drafts/{id}/revise')
def revise(id:str,u=Depends(user),db=Depends(db_session)):
    representative(db,u);r=owned(db,id,u,'course');new=new_revision(db,{**r.data,'parent_revision':id},owner=u.id,org=u.org,course_id=r.data['course_id']);db.commit();return record(new)
@app.post('/api/sources/{id}/retry')
def retry(id:str,u=Depends(user),db=Depends(db_session)):
    representative(db,u);r=owned(db,id,u,'source')
    if r.state!='failed':raise HTTPException(409,'Only failed sources can be retried')
    r.state='queued';r.data={**r.data,'error':None};db.commit()
    from .tasks import dispatch
    try:dispatch(r.id)
    except Exception:pass
    return record(r)
@app.post('/api/sources/{id}/cancel')
def cancel_source(id:str,u=Depends(user),db=Depends(db_session)):
    representative(db,u);r=owned(db,id,u,'source')
    if r.state not in ('queued','running'):raise HTTPException(409,'This job is no longer cancellable')
    changed=db.execute(update(Record).where(Record.id==id,Record.state.in_(['queued','running'])).values(state='cancelled'))
    if changed.rowcount!=1:raise HTTPException(409,'The job completed before cancellation')
    audit(db,u.id,'cancel_source',id);db.commit();db.refresh(r);return record(r)
@app.post('/api/sources/{id}/refresh')
def refresh_source(id:str,u=Depends(user),db=Depends(db_session)):
    representative(db,u);r=owned(db,id,u,'source');budget(db,u.id,'ingestion',10,3600)
    data={k:v for k,v in r.data.items() if k not in ('text','hash','count','completed_at','error','claim_token','started_at')}
    data['parent_source']=id
    fresh=add(db,'source',data,owner=u.id,org=u.org,state='queued');db.commit()
    from .tasks import dispatch
    try:dispatch(fresh.id)
    except Exception:pass
    return record(fresh)
class ManualCourse(BaseModel):
    title:str=Field(min_length=3,max_length=200)
    faculty:str=Field(min_length=3,max_length=200)
    course_url:str=Field(max_length=2000)
    evidence:str=Field(min_length=10,max_length=2000)
@app.post('/api/drafts')
def manual_course(body:ManualCourse,u=Depends(user),db=Depends(db_session)):
    org=representative(db,u);public_url(body.course_url)
    r=new_revision(db,{**body.model_dump(),'university':org.data['name'],'tags':[],'url_mode':'custom','reviewed':False,'provider':'Representative-entered','tag_origin':'representative review required'},owner=u.id,org=u.org);audit(db,u.id,'manual_draft',r.id);db.commit();return record(r)
class Submit(BaseModel):ids:list[str]=Field(min_length=1,max_length=100)
@app.post('/api/submissions')
def submit(body:Submit,u=Depends(user),db=Depends(db_session)):
    representative(db,u);rows=[]
    for id in set(body.ids):
        r=owned(db,id,u,'course')
        if r.state!='draft' or not r.data.get('reviewed'):raise HTTPException(422,'Review and save every draft before submitting')
        if not r.data.get('course_url'):raise HTTPException(422,'Every course needs a public student-facing URL')
        public_url(r.data['course_url']);rows.append(r)
    batch=add(db,'batch',{'ids':[r.id for r in rows]},org=u.org,owner=u.id,state='submitted')
    for r in rows:r.state='submitted';r.data={**r.data,'batch_id':batch.id}
    audit(db,u.id,'submit_batch',batch.id);db.commit();return record(batch)
@app.get('/api/admin/queue')
def queue(u=Depends(user),db=Depends(db_session)):
    role(u,'admin');return [record(r) for r in db.scalars(select(Record).where(Record.kind=='course',Record.state.in_(['submitted','approved','changes_requested','rejected'])).order_by(Record.created_at.desc()))]
class Decision(BaseModel):
    decision:Literal['approved','changes_requested','rejected']
    reason:str=Field(min_length=5,max_length=2000)
@app.post('/api/admin/decisions/{id}')
def decision(id:str,body:Decision,u=Depends(user),db=Depends(db_session)):
    role(u,'admin');r=db.get(Record,id)
    if not r or r.kind!='course':raise HTTPException(404)
    if r.owner==u.id:raise HTTPException(403,'You cannot approve your own submission')
    if r.state!='submitted':raise HTTPException(409,'This revision is no longer awaiting review')
    r.state=body.decision;add(db,'decision',{'revision_id':id,**body.model_dump()},owner=u.id,org=r.org)
    batch=db.get(Record,r.data.get('batch_id',''))
    if batch:
        db.flush();members=[db.get(Record,item) for item in batch.data['ids']]
        batch.state='in_review' if any(m.state=='submitted' for m in members) else 'reviewed'
        batch.data={**batch.data,'decisions':{m.id:m.state for m in members}}
    r.data={**r.data,'review_comment':body.reason};audit(db,u.id,body.decision,id,body.reason);db.commit();return record(r)
@app.get('/api/admin/organizations')
def organizations(u=Depends(user),db=Depends(db_session)):
    role(u,'admin');return [record(r) for r in db.scalars(select(Record).where(Record.kind=='organization'))]
class Verify(BaseModel):verified:bool
@app.post('/api/admin/organizations/{id}/verify')
def verify(id:str,body:Verify,u=Depends(user),db=Depends(db_session)):
    role(u,'admin');r=db.get(Record,id)
    if not r or r.kind!='organization':raise HTTPException(404)
    r.state='verified' if body.verified else 'rejected';audit(db,u.id,'verify_organization',id,r.state);db.commit();return record(r)
@app.post('/api/admin/publish')
def publish_version(u=Depends(user),db=Depends(db_session)):
    role(u,'admin');return publish(db,u)
@app.get('/api/admin/versions')
def versions(u=Depends(user),db=Depends(db_session)):
    role(u,'admin');active=get_active(db)
    return [{**record(r),'snapshot':None,'active':r.id==active.version_id} for r in db.scalars(select(Record).where(Record.kind=='version').order_by(Record.created_at.desc()))]
class Restore(BaseModel):reason:str=Field(min_length=5,max_length=2000)
@app.post('/api/admin/versions/{id}/restore')
def restore(id:str,body:Restore,u=Depends(user),db=Depends(db_session)):
    role(u,'admin');r=db.get(Record,id)
    if not r or r.kind!='version':raise HTTPException(404)
    if r.data.get('checksum') and hashlib.sha256(r.data['snapshot'].encode()).hexdigest()!=r.data['checksum']:raise HTTPException(409,'Snapshot checksum mismatch; restore blocked')
    active=get_active(db);old=active.version_id;generation=active.generation
    result=db.execute(update(Active).where(Active.id==1,Active.generation==generation).values(version_id=id,generation=generation+1))
    if result.rowcount!=1:raise HTTPException(409,'Version changed; retry')
    audit(db,u.id,'restore',id,body.reason+'; previous='+old);db.commit();return {'active':id,'previous':old}
@app.get('/api/admin/versions/{id}/rdf')
def rdf(id:str,u=Depends(user),db=Depends(db_session)):
    role(u,'admin');r=db.get(Record,id)
    if not r or r.kind!='version':raise HTTPException(404)
    return Response(r.data['snapshot'],media_type='text/turtle')
@app.get('/api/analytics')
def analytics(u=Depends(user),db=Depends(db_session)):
    role(u,'admin','representative')
    query=select(Record).where(Record.kind=='event')
    if u.data['role']=='representative':representative(db,u);query=query.where(Record.org==u.org)
    events=db.scalars(query).all();counts=defaultdict(int);courses=defaultdict(int)
    for r in events:
        counts[r.data['type']]+=1
        if r.data.get('course_id'):courses[r.data['course_id']]+=1
    rows=catalogue(db)
    return {'counts':dict(counts),'distinct_users':len({e.owner for e in events}),'courses':[{'title':r['title'],'count':courses[r['course_id']]} for r in rows if courses[r['course_id']]],'notes':'Event counts, not a causal conversion measure. Contact intent and submitted enquiries are separate. University search totals exclude searches not attributable to their course.'}
@app.get('/api/admin/audit')
def audits(u=Depends(user),db=Depends(db_session)):
    role(u,'admin');return [record(r) for r in db.scalars(select(Record).where(Record.kind=='audit').order_by(Record.created_at.desc()).limit(100))]

class TaxonomyTerm(BaseModel):
    id:str=Field(pattern=r'^[a-z][a-z0-9-]{1,60}$')
    label:str=Field(min_length=2,max_length=100)
    type:Literal['interest','aptitude']
@app.post('/api/admin/taxonomy')
def add_term(body:TaxonomyTerm,u=Depends(user),db=Depends(db_session)):
    role(u,'admin')
    if db.get(Record,'tag:'+body.id):raise HTTPException(409,'Tag ID already exists; IDs are immutable')
    r=add(db,'tag',{'label':body.label,'type':body.type},id='tag:'+body.id,state='active');audit(db,u.id,'add_taxonomy',r.id);db.commit();return record(r)
@app.post('/api/admin/courses/{cid}/archive')
def archive_course(cid:str,body:Restore,u=Depends(user),db=Depends(db_session)):
    role(u,'admin');c=current_course(db,cid)
    r=new_revision(db,{**c,'archived':True,'archive_reason':body.reason},owner=u.id,org=c['org'],course_id=cid,state='approved')
    audit(db,u.id,'archive_queued',r.id,body.reason);db.commit();return record(r)
@app.delete('/api/account')
def delete_account(u=Depends(user),db=Depends(db_session)):
    role(u,'student')
    for r in db.scalars(select(Record).where(Record.owner==u.id,Record.kind.in_(['session','saved','recommendation','event']))):db.delete(r)
    for r in db.scalars(select(Record).where(Record.owner==u.id,Record.kind=='enquiry')):
        r.data={**r.data,'name':'Deleted account','email':'','message':'Removed at account deletion'}
    account=db.get(Record,u.id);account.state='deleted';account.data={'name':'Deleted account','email':'','role':'student','profile':{'tags':[]}}
    audit(db,u.id,'account_deleted',u.id,'Private profiles and history removed; minimal consent/decision audit retained.');db.commit()
    return {'ok':True,'note':'Application account data removed; Firebase identity deletion requires provider account deletion separately.'}

# Production container can serve the built SPA. API routes always take priority.
if Path('frontend/dist').exists():
    from fastapi.staticfiles import StaticFiles
    app.mount('/assets',StaticFiles(directory='frontend/dist/assets'),name='assets')
    @app.get('/{path:path}',include_in_schema=False)
    def frontend(path:str):
        root=Path('frontend/dist').resolve();candidate=(root/path).resolve()
        if candidate.is_relative_to(root) and candidate.is_file():return FileResponse(candidate)
        if path.startswith('api/'):raise HTTPException(404)
        return FileResponse(root/'index.html')
