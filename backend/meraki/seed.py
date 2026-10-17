import os
from sqlalchemy import select
from .db import Base,engine,Session,Record,VersionCourse,Active,add,uid
from .security import password_hash,AUTH,ENV
from .domain import new_revision,rdf_snapshot,TAXONOMY
from .local_config import demo_password

def seed():
    if ENV=='production':return
    os.makedirs('data',exist_ok=True);Base.metadata.create_all(engine)
    with Session() as db:
        for tag in TAXONOMY:
            if not db.get(Record,'tag:'+tag['id']):add(db,'tag',{'label':tag['label'],'type':tag['type']},id='tag:'+tag['id'],state='active')
        db.commit()
        if db.get(Active,1):return
        if ENV=='production':return
        org=add(db,'organization',{'name':'Northbridge University','contact':'courses@northbridge.example'},id='org-northbridge',state='verified')
        add(db,'organization',{'name':'Lakeside University','contact':'hello@lakeside.example'},id='org-lakeside',state='verified')
        if AUTH=='development':
            password=demo_password()
            for id,email,name,role,oid in [('student-demo','student@meraki.local','Alex Morgan','student',''),('university-demo','university@meraki.local','Sam Fernando','representative',org.id),('admin-demo','admin@meraki.local','Jordan Silva','admin','')]:
                add(db,'user',{'email':email,'name':name,'role':role,'password':password_hash(password),'profile':{'tags':['technology','design','mathematics','analytical-thinking']}},id=id,state='active',org=oid)
        data=[('BSc Computer Science','Faculty of Computing',['technology','mathematics','analytical-thinking'],'org-northbridge'),('BSc Information Systems','Faculty of Technology',['technology','business','analytical-thinking','communication'],'org-northbridge'),('BA Digital Design','Faculty of Design',['design','technology','creativity'],'org-lakeside'),('BSc Environmental Science','Faculty of Science',['environment','mathematics','analytical-thinking'],'org-lakeside'),('BBA Business Management','Faculty of Business',['business','communication','analytical-thinking'],'org-northbridge'),('BSc Data Science','Faculty of Computing',['technology','mathematics','analytical-thinking'],'org-northbridge')]
        revisions=[]
        for title,faculty,tags,oid in data:
            org=db.get(Record,oid);r=new_revision(db,{'title':title,'university':org.data['name'],'faculty':faculty,'tags':tags,'course_url':'https://'+('northbridge' if oid.endswith('northbridge') else 'lakeside')+'.example/courses/'+title.lower().replace(' ','-'),'url_mode':'custom','mode':'Full-time','duration':'3 years','evidence':'Illustrative demonstration course; not a real offering.','provider':'Demo seed','tag_origin':'illustrative','illustrative':True},org=oid,state='published');revisions.append(r)
        courses=[{**r.data,'id':r.id} for r in revisions];snap=rdf_snapshot(courses)
        v=add(db,'version',{'count':len(courses),'parent':None,'snapshot':snap,'summary':'Illustrative seed catalogue','publisher':'development'},state='published')
        for r in revisions:db.add(VersionCourse(version_id=v.id,course_id=r.data['course_id'],revision_id=r.id))
        db.add(Active(id=1,version_id=v.id,generation=1));db.commit()
