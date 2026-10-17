"""Synthetic local workload, isolated temp SQLite; not a Cloud SQL capacity claim."""
from backend.meraki.local_config import demo_password
import os,tempfile,time,json,statistics
from pathlib import Path
os.environ['DATABASE_URL']='sqlite:///'+str(Path(tempfile.mkdtemp())/'benchmark.db')
os.environ['APP_ENV']='development';os.environ['AUTH_PROVIDER']='development'
from concurrent.futures import ThreadPoolExecutor
from fastapi.testclient import TestClient
from backend.meraki.app import app
from backend.meraki.db import Session,Record,Edge,VersionCourse,Active,uid
def main():
    with TestClient(app) as client:
        with Session() as db:
            version=db.get(Active,1).version_id;records=[];edges=[];members=[]
            for i in range(10000):
                id=uid();cid=uid();tags=['technology','mathematics','analytical-thinking'] if i%2 else ['design','creativity']
                records.append({'id':id,'kind':'course','owner':'','org':'org-northbridge','state':'published','data':{'course_id':cid,'title':f'Benchmark Course {i:05d}','university':'Synthetic University','faculty':'Synthetic Faculty','tags':tags,'course_url':'https://example.com/course'}})
                edges.extend({'revision_id':id,'tag_id':tag} for tag in tags);members.append({'version_id':version,'course_id':cid,'revision_id':id})
            from sqlalchemy import insert
            db.execute(insert(Record),records);db.execute(insert(Edge),edges);db.execute(insert(VersionCourse),members);db.commit()
        token=client.post('/api/auth/login',json={'email':'student@meraki.local','password':demo_password()}).json()['token']
        headers={'Authorization':'Bearer '+token}
        # Different existing users share preference fixture; this measures HTTP request concurrency.
        # Disable recommendation rate bucket by pre-staggering 50 distinct test sessions/users.
        subjects=[]
        with Session() as db:
            original=db.get(Record,'student-demo')
            import hashlib
            from datetime import datetime,timezone,timedelta
            for i in range(50):
                id='bench-user-'+str(i);db.add(Record(id=id,kind='user',state='active',data=original.data))
                t=uid();db.add(Record(id='session:'+hashlib.sha256(t.encode()).hexdigest(),kind='session',owner=id,data={'expires_at':(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat()}));subjects.append(t)
            db.commit()
        def run(t):
            started=time.perf_counter();r=client.post('/api/recommendations',headers={'Authorization':'Bearer '+t},json={'tags':['technology','mathematics']})
            return {'seconds':time.perf_counter()-started,'status':r.status_code}
        with ThreadPoolExecutor(max_workers=50) as pool:results=list(pool.map(run,subjects))
        times=sorted(r['seconds'] for r in results);report={'environment':'Local FastAPI TestClient + temporary SQLite, no network or cloud','synthetic_courses_added':10000,'concurrent_requests':50,'successes':sum(r['status']==200 for r in results),'p50_seconds':round(statistics.median(times),3),'p95_seconds':round(times[int(len(times)*.95)-1],3),'max_seconds':round(max(times),3),'result_limit':100,'note':'Synthetic local test only; Cloud SQL/Cloud Run target needs a separate deployed benchmark.'}
        Path('output/benchmark-local.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
if __name__=='__main__':main()
