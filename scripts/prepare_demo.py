"""Prepare one local, explicitly illustrative extraction/approval demonstration."""
from backend.meraki.local_config import demo_password
import os,time
from pathlib import Path
import httpx
from sqlalchemy import select
from backend.meraki.db import Session,Record
if os.getenv('APP_ENV','development')!='development' or os.getenv('AUTH_PROVIDER','development')!='development':raise RuntimeError('Demo preparation is development-only')
with httpx.Client(base_url='http://127.0.0.1:8000',timeout=30) as client:
    r=client.post('/api/auth/login',json={'email':'university@meraki.local','password':demo_password()});r.raise_for_status();headers={'Authorization':'Bearer '+r.json()['token']}
    existing=client.get('/api/sources',headers=headers).json()
    if any(s['name']=='sample-prospectus.txt' and s['state']=='completed' for s in existing):print('Sample source already exists; leaving reviewed data unchanged.')
    else:
        r=client.post('/api/sources',headers=headers,data={'method':'nlp','url':'https://northbridge.example/courses'},files={'file':('sample-prospectus.txt',Path('docs/sample-prospectus.txt').read_bytes(),'text/plain')});r.raise_for_status();sid=r.json()['id']
        for _ in range(20):
            source=next(s for s in client.get('/api/sources',headers=headers).json() if s['id']==sid)
            if source['state'] in ('failed','completed'):break
            time.sleep(1)
        if source['state']!='completed':raise RuntimeError('Start the local worker and check sample source state: '+source['state'])
        with Session() as db:
            for course in db.scalars(select(Record).where(Record.kind=='course')):
                if course.data.get('source_id')==sid:course.data={**course.data,'illustrative':True}
            db.commit()
        rows=sorted([r for r in client.get('/api/drafts',headers=headers).json() if r.get('source_id')==sid],key=lambda r:r['title']);ids=[]
        for i,course in enumerate(rows[:2]):
            body={'title':course['title'],'faculty':course['faculty'],'tags':['technology','mathematics','analytical-thinking'],'course_url':'https://northbridge.example/courses/'+course['title'].lower().replace(' ','-'),'url_mode':'source' if i==0 else 'custom','revision':course['revision']}
            result=client.put('/api/drafts/'+course['id'],headers=headers,json=body);result.raise_for_status();ids.append(course['id'])
        r=client.post('/api/submissions',headers=headers,json={'ids':ids});r.raise_for_status()
        print('Demo prepared: 3 illustrative extracted courses, 2 submitted for admin review, 1 draft. No courses published or emails sent.')
