import hashlib,json
from functools import lru_cache
from threading import RLock
from sqlalchemy import select,delete,update,func,case
from fastapi import HTTPException
from rdflib import Graph,Namespace,RDF,RDFS,OWL,URIRef,Literal
from .db import Session,Record,Edge,VersionCourse,Active,add,record,uid,now,audit

TAXONOMY=[{'id':i,'label':label,'type':typ} for typ,items in [('interest',[('technology','Technology'),('design','Design'),('business','Business'),('environment','Environment')]),('aptitude',[('mathematics','Mathematics'),('analytical-thinking','Analytical thinking'),('creativity','Creativity'),('communication','Communication')])] for i,label in items]
def taxonomy(db):
    terms=db.scalars(select(Record).where(Record.kind=='tag',Record.state=='active')).all()
    return [{**r.data,'id':r.id.removeprefix('tag:')} for r in terms] or TAXONOMY
def get_active(db):
    active=db.get(Active,1)
    if not active:raise HTTPException(503,'No published ontology')
    return active
def catalogue(db,version=None,tags=None):
    version=version or get_active(db).version_id
    query=select(Record).join(VersionCourse,VersionCourse.revision_id==Record.id).where(VersionCourse.version_id==version)
    if tags:query=query.join(Edge,Edge.revision_id==Record.id).where(Edge.tag_id.in_(tags)).distinct()
    return [record(r) for r in db.scalars(query).all()]
_candidate_lock=RLock()
@lru_cache(maxsize=128)
def _cached_candidates(tags,version,limit):
    with Session() as db:return _query_candidates(db,tags,version,limit)
def candidates(db,tags,version,limit=100):
    # Only immutable published public catalogue data is cached. Profiles/runs stay in DB.
    # Version UUID is part of the key, so publication/restore cannot return stale-version rows.
    with _candidate_lock:return _cached_candidates(tuple(sorted(set(tags))),version,limit)
def _query_candidates(db,tags,version,limit):
    """Rank indexed graph edges in SQL before loading bounded course aggregates."""
    terms=taxonomy(db);interests={t['id'] for t in terms if t['type']=='interest'}&set(tags);aptitudes=set(tags)-interests
    wi=(.7 if aptitudes else 1)/len(interests) if interests else 0
    wa=(.3 if interests else 1)/len(aptitudes) if aptitudes else 0
    weight=func.sum(case((Edge.tag_id.in_(interests),wi),else_=wa)).label('score')
    scores=select(Edge.revision_id,weight).join(VersionCourse,VersionCourse.revision_id==Edge.revision_id).where(VersionCourse.version_id==version,Edge.tag_id.in_(tags)).group_by(Edge.revision_id).subquery()
    query=select(Record).join(scores,scores.c.revision_id==Record.id).order_by(scores.c.score.desc(),Record.data['title'].as_string(),Record.id).limit(limit)
    return [record(r) for r in db.scalars(query)]
def new_revision(db,data,owner='',org='',state='draft',course_id=None):
    d={**data,'course_id':course_id or uid(),'revision':1};r=add(db,'course',d,owner=owner,org=org,state=state)
    for tag in set(d.get('tags',[])):db.add(Edge(revision_id=r.id,tag_id=tag))
    return r
def rdf_snapshot(courses,terms=None):
    g=Graph();ns=Namespace('https://meraki.example/ontology/');prov=Namespace('http://www.w3.org/ns/prov#');g.bind('meraki',ns);g.bind('prov',prov)
    tag_map={t['id']:t for t in (terms or TAXONOMY)}
    for klass in ['University','Faculty','CourseOffering','DegreeConcept','Interest','Aptitude']:g.add((ns[klass],RDF.type,OWL.Class))
    for course in courses:
        node=URIRef(ns['course/'+course['course_id']]);g.add((node,RDF.type,ns.CourseOffering));g.add((node,RDFS.label,Literal(course['title'])))
        uni=URIRef(ns['university/'+course.get('org',hashlib.sha256(course['university'].encode()).hexdigest()[:16])])
        fid=course.get('faculty_id') or hashlib.sha256((str(uni)+course['faculty']).encode()).hexdigest()[:24]
        faculty=URIRef(ns['faculty/'+fid]);g.add((uni,RDF.type,ns.University));g.add((uni,RDFS.label,Literal(course['university'])));g.add((faculty,RDF.type,ns.Faculty));g.add((faculty,RDFS.label,Literal(course['faculty'])))
        g.add((faculty,ns.isFacultyOf,uni));g.add((uni,ns.hasFaculty,faculty));g.add((node,ns.isDegreeOf,uni));g.add((node,ns.isDegreeOf,faculty));g.add((uni,ns.hasDegree,node));g.add((faculty,ns.hasDegree,node))
        g.add((node,ns.university,Literal(course['university'])));g.add((node,ns.faculty,Literal(course['faculty'])))
        if course.get('course_url'):g.add((node,ns.courseURL,URIRef(course['course_url'])))
        if course.get('legacy_id'):
            concept=URIRef(ns['degree-concept/'+hashlib.sha256(course['legacy_id'].encode()).hexdigest()[:24]])
            g.add((concept,RDF.type,ns.DegreeConcept));g.add((node,ns.degreeConcept,concept));g.add((concept,prov.wasDerivedFrom,URIRef(course['legacy_id'])));g.add((node,prov.wasDerivedFrom,URIRef(course['legacy_id'])))
            g.add((node,ns.verificationStatus,Literal('Historical prototype; current offering not reverified')))
        for key,target in [('legacy_university_id',uni),('legacy_faculty_id',faculty)]:
            if course.get(key):g.add((target,prov.wasDerivedFrom,URIRef(course[key])))
        for tag in course.get('tags',[]):
            t=URIRef(ns['tag/'+tag]);g.add((node,ns.hasTag,t));term=tag_map.get(tag)
            if term:
                klass=ns.Interest if term['type']=='interest' else ns.Aptitude
                prop=ns.hasInterest if term['type']=='interest' else ns.hasAptitude
                g.add((t,RDF.type,klass));g.add((t,RDFS.label,Literal(term['label'])));g.add((node,prop,t))
    return g.serialize(format='turtle')
def publish(db,u):
    active=get_active(db);generation=active.generation
    pending=db.scalars(select(Record).where(Record.kind=='course',Record.state=='approved')).all()
    if not pending:raise HTTPException(409,'No approved revisions to publish')
    existing={r['course_id']:r for r in catalogue(db)}
    for r in pending:
        d=record(r)
        if d.get('archived'):
            existing.pop(d['course_id'],None);continue
        if not d.get('title') or not d.get('faculty') or not d.get('course_url'):raise HTTPException(422,'Approved courses need title, faculty and public course URL')
        existing[d['course_id']]=d
    version_id=uid();snapshot=rdf_snapshot(list(existing.values()),taxonomy(db))
    from pyshacl import validate
    shapes='''@prefix sh: <http://www.w3.org/ns/shacl#> . @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> . @prefix m: <https://meraki.example/ontology/> .
    m:CourseShape a sh:NodeShape; sh:targetClass m:CourseOffering; sh:property [ sh:path rdfs:label; sh:minCount 1; sh:maxCount 1 ]; sh:property [ sh:path m:faculty; sh:minCount 1 ]; sh:property [ sh:path m:courseURL; sh:minCount 1; sh:nodeKind sh:IRI ].'''
    conforms,_,report=validate(Graph().parse(data=snapshot,format='turtle'),shacl_graph=Graph().parse(data=shapes,format='turtle'))
    if not conforms:raise HTTPException(422,'Ontology failed SHACL validation')
    from .storage import put
    snapshot_uri=put('ontology/'+version_id+'.ttl',snapshot.encode(),'text/turtle')
    version=add(db,'version',{'parent':active.version_id,'count':len(existing),'checksum':hashlib.sha256(snapshot.encode()).hexdigest(),'snapshot':snapshot,'snapshot_uri':snapshot_uri,'publisher':u.id,'summary':f'Published {len(pending)} approved revisions'},id=version_id,state='published',owner=u.id)
    for d in existing.values():db.add(VersionCourse(version_id=version.id,course_id=d['course_id'],revision_id=d['id']))
    changed=db.execute(update(Active).where(Active.id==1,Active.generation==generation).values(version_id=version.id,generation=generation+1))
    if changed.rowcount!=1:raise HTTPException(409,'Concurrent publication changed the ontology. Retry.')
    for r in pending:r.state='published'
    audit(db,u.id,'publish',version.id);db.commit();return record(version)
def rank(courses,tags,terms=None):
    terms=terms or TAXONOMY
    valid={t['id'] for t in terms}
    if not tags or not set(tags)<=valid:raise HTTPException(422,'Choose at least one valid interest or aptitude')
    interests={t['id'] for t in terms if t['type']=='interest'}&set(tags)
    aptitudes=set(tags)-interests;wi=.7 if aptitudes else 1;wa=.3 if interests else 1
    out=[]
    for c in courses:
        matched=set(c['tags'])&set(tags)
        if not matched:continue
        ic=len(matched&interests)/len(interests) if interests else 0
        ac=len(matched&aptitudes)/len(aptitudes) if aptitudes else 0
        out.append({**c,'match':round(100*(wi*ic+wa*ac),2),'matched_tags':sorted(matched),'unmatched_tags':sorted(set(tags)-matched),'eligibility':'unknown','components':{'interest':round(ic*100,2),'aptitude':round(ac*100,2)}})
    return sorted(out,key=lambda x:(-x['match'],x['title'],x['course_id']))
