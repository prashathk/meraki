"""Run an authorized local migration through admin review/publication APIs.

Defaults to preview-only; --apply stages/reviews/publishes in development and
retires only illustrative Demo seed offerings through the archive workflow.
"""
from backend.meraki.local_config import demo_password
import argparse,json,os,sqlite3,hashlib
from pathlib import Path
from datetime import datetime,timezone
import httpx

def run(path,apply=False,base='http://127.0.0.1:8000'):
    content=Path(path).read_bytes();checksum=hashlib.sha256(content).hexdigest()
    with httpx.Client(base_url=base,timeout=120) as c:
        health=c.get('/api/health').json()
        if health.get('environment')!='development' or health.get('auth_provider')!='development':raise RuntimeError('This runner uses local fixture identity and cannot operate on production')
        auth=c.post('/api/auth/login',json={'email':'admin@meraki.local','password':demo_password()});auth.raise_for_status();admin={'Authorization':'Bearer '+auth.json()['token']}
        if apply:
            from backend.meraki.db import DATABASE_URL
            if DATABASE_URL.startswith('sqlite:///'):
                source=Path(DATABASE_URL.removeprefix('sqlite:///'));dest=Path('data/backups')/('before-legacy-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'.db');dest.parent.mkdir(parents=True,exist_ok=True)
                with sqlite3.connect(source) as src,sqlite3.connect(dest) as dst:src.backup(dst)
                print('Consistent pre-migration backup:',dest)
        preview=c.post('/api/admin/legacy/preview',headers=admin,files={'file':('ontology.owl',content,'application/rdf+xml')});preview.raise_for_status();migration=preview.json();plan=migration['plan']
        result={k:plan[k] for k in ['checksum','triples','degree_concepts','offering_count','university_count','faculty_class_count','faculty_associations','tag_count','unresolved','notice']}
        result['by_university']={u['name']:sum(o['org']==u['id'] for o in plan['offerings']) for u in plan['universities']}
        result['shared_concepts_resolved']=len(plan['resolved_shared_concepts']);result['migration_id']=migration['id']
        if apply:
            assert plan['unresolved']==[]
            before=c.get('/api/admin/versions',headers=admin).json();previous=next(v['id'] for v in before if v['active'])
            staged=c.post('/api/admin/legacy/'+migration['id']+'/stage',headers=admin);staged.raise_for_status();ids=set(staged.json()['revision_ids'])
            queue=c.get('/api/admin/queue',headers=admin).json()
            unrelated=[r for r in queue if r['state']=='approved' and r['id'] not in ids]
            if unrelated:raise RuntimeError('Unrelated approved changes exist; migration refuses to publish them implicitly')
            approved=0
            for row in queue:
                if row['id'] in ids and row['state']=='submitted':
                    r=c.post('/api/admin/decisions/'+row['id'],headers=admin,json={'decision':'approved','reason':'User-authorized structural legacy migration review: faculty pairing and tags preserved from ontology. Not university endorsement or current offering verification.'});r.raise_for_status();approved+=1
            archived=[]
            for course in c.get('/api/courses').json():
                if course.get('illustrative') and course.get('provider')=='Demo seed':
                    r=c.post('/api/admin/courses/'+course['course_id']+'/archive',headers=admin,json={'reason':'Retire illustrative seed from active discovery after original ontology migration; preserve earlier recoverable snapshot'});r.raise_for_status();archived.append(course['course_id'])
            if approved or archived:
                published=c.post('/api/admin/publish',headers=admin);published.raise_for_status();active=published.json()['id']
            else:active=previous
            rows=c.get('/api/courses').json();imported=[r for r in rows if r.get('migration_id')==migration['id']]
            assert len(imported)==plan['offering_count'];assert len({r['course_id'] for r in imported})==len(imported)
            for name,count in result['by_university'].items():assert sum(r['university']==name for r in imported)==count
            result.update({'approved_through_review_api':approved,'retired_demo_offerings':len(archived),'active_version':active,'previous_version':previous,'published_offerings':len(imported),'idempotent_stage':staged.json()['already_staged']})
            if active!=previous:
                for id,reason in [(previous,'Verify pre-migration recovery during authorized migration test'),(active,'Re-activate structurally verified legacy migration after recovery test')]:
                    r=c.post('/api/admin/versions/'+id+'/restore',headers=admin,json={'reason':reason});r.raise_for_status()
                    actual=c.get('/api/courses').json()
                    if id==active:assert sum(x.get('migration_id')==migration['id'] for x in actual)==plan['offering_count']
                result['restore_and_reactivate_test']='passed'
        result['applied']=apply
        Path('output').mkdir(exist_ok=True);Path('output/legacy-migration-result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
        print(json.dumps(result,indent=2))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--ontology',default='backend/fixtures/prototype-ontology.owl');p.add_argument('--apply',action='store_true');p.add_argument('--base-url',default='http://127.0.0.1:8000');a=p.parse_args();run(a.ontology,a.apply,a.base_url)
