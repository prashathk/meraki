"""Run: python -m worker.run. Jobs survive restarts; failed leases need retry."""
import time,hashlib
from sqlalchemy import select,update
from backend.meraki.db import Session,Record,now,uid
from backend.meraki.domain import taxonomy,new_revision
from backend.meraki.extraction import fetch_public,parse_source,extract
from backend.meraki.seed import seed

def once(source_id=None):
    with Session() as db:
        query=select(Record).where(Record.kind=='source',Record.state=='queued')
        if source_id:query=query.where(Record.id==source_id)
        job=db.scalar(query.order_by(Record.created_at).limit(1))
        if not job:return False
        claim=uid()
        claimed=db.execute(update(Record).where(Record.id==job.id,Record.state=='queued').values(state='running',data={**job.data,'claim_token':claim,'started_at':now()}))
        if claimed.rowcount!=1:db.rollback();return True
        db.commit();jid=job.id
    try:
        with Session() as db:
            job=db.get(Record,jid);data=dict(job.data);org=db.get(Record,job.org)
            if 'text' not in data:
                if data.get('object_uri'):
                    from backend.meraki.storage import get
                    content=get(data['object_uri']);mime=data['mime']
                else:
                    content,mime,final=fetch_public(data['url']);data['final_url']=final
                    if content.startswith((b'%PDF',b'PK')):
                        from backend.meraki.scanning import scan
                        data['malware_scan']=scan(content)
                data['text']=parse_source(content,mime);data['hash']=hashlib.sha256(content).hexdigest()
            courses=extract(data['text'],data['method'],taxonomy(db),org.data['name'])
            db.refresh(job)
            if job.state!='running' or job.data.get('claim_token')!=claim:return True
            for course in courses:
                course.update({'source_id':jid,'reviewed':False,'mode':'Not specified','duration':'Not specified'})
                if data.get('url'):course.update({'url_mode':'source','course_url':data['url']})
                new_revision(db,course,owner=job.owner,org=job.org)
            changed=db.execute(update(Record).where(Record.id==jid,Record.state=='running',Record.data['claim_token'].as_string()==claim).values(state='completed',data={**data,'count':len(courses),'completed_at':now()}))
            if changed.rowcount!=1:db.rollback();return True
            db.commit()
    except Exception as e:
        with Session() as db:
            job=db.get(Record,jid)
            db.execute(update(Record).where(Record.id==jid,Record.state=='running',Record.data['claim_token'].as_string()==claim).values(state='failed',data={**job.data,'error':str(e)[:500]}));db.commit()
    return True
if __name__=='__main__':
    seed();print('Meraki local worker ready',flush=True)
    while True:
        if not once():time.sleep(2)
