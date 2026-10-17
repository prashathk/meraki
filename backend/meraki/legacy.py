"""Lossless, evidence-based import of the prototype's RDF/XML ontology."""
import hashlib,re,unicodedata,uuid
from rdflib import Graph,Namespace,RDFS,OWL,URIRef
from sqlalchemy import select
from fastapi import HTTPException
from .db import Record,Edge,add,record,audit
from .domain import taxonomy,new_revision

NS=Namespace('http://www.educationalguide.org/ontologies/ontology.owl#')
UNIVERSITIES={
 'UinversityOfMoratuwa':('University of Moratuwa','https://uom.lk/education/degrees/undergraduate','university_catalogue'),
 'UinversityOfKelaniya':('University of Kelaniya','https://www.kln.ac.lk/','university_homepage'),
 'UniversityOfSriJayewardenepura':('University of Sri Jayewardenepura','https://www.sjp.ac.lk/undergraduate-courses/','university_catalogue')}
def label(uri):
    name=str(uri).split('#')[-1]
    name=re.sub(r'([a-z0-9])([A-Z])',r'\1 \2',name)
    name=re.sub(r'\b(Of|And|In|The|As)\b',lambda m:m.group().lower(),name)
    return name
def stable(kind,*parts):return str(uuid.uuid5(uuid.NAMESPACE_URL,'meraki:legacy:'+kind+':'+':'.join(parts)))
def tag_id(uri,kind):
    name=re.sub(r'(Interest|Aptitude)$','',str(uri).split('#')[-1]);name=label(name)
    slug=re.sub('[^a-z0-9]+','-',unicodedata.normalize('NFKD',name).encode('ascii','ignore').decode().lower()).strip('-')
    return 'legacy-'+kind[0]+'-'+slug[:38]+'-'+hashlib.sha256(str(uri).encode()).hexdigest()[:8]
def restrictions(g,node,prop):
    return {str(g.value(r,OWL.someValuesFrom)) for r in g.objects(URIRef(node),RDFS.subClassOf) if g.value(r,OWL.onProperty)==NS[prop] and g.value(r,OWL.someValuesFrom)}
def plan(content):
    if len(content)>20*1024*1024:raise ValueError('Ontology exceeds 20 MB')
    if re.search(br'<!\s*(DOCTYPE|ENTITY)',content,re.I):raise ValueError('XML document type/entity declarations are not allowed')
    g=Graph().parse(data=content,format='xml')
    if len(g)>100000:raise ValueError('Ontology exceeds 100,000 triples')
    university_nodes=sorted(str(n) for n in g.subjects(RDFS.subClassOf,NS.University))
    faculty_nodes={str(n) for n in g.subjects(RDFS.subClassOf,NS.Faculty)}
    degrees=sorted({str(n) for n in g.subjects(RDFS.subClassOf,NS.Degree)})
    terms=[]
    for typ,klass in [('interest',NS.Interest),('aptitude',NS.Aptitude)]:
        for uri in sorted({str(n) for n in g.subjects(RDFS.subClassOf,klass)}):
            terms.append({'legacy_id':uri,'label':re.sub(r' (Interest|Aptitude)$','',label(uri)),'type':typ})
    institutions=[];faculties=[];offers=[];unresolved=[];resolved=[]
    for uri in university_nodes:
        key=uri.split('#')[-1]
        if key not in UNIVERSITIES:raise ValueError('Unknown university requires an explicit reviewed name/URL mapping: '+key)
        name,url,url_kind=UNIVERSITIES[key];oid='org-legacy-'+stable('university',uri)
        institutions.append({'id':oid,'legacy_id':uri,'name':name,'catalogue_url':url,'url_kind':url_kind})
        for faculty in sorted(restrictions(g,uri,'hasFaculty')&faculty_nodes):
            if uri not in restrictions(g,faculty,'isFacultyOf'):continue
            faculties.append({'id':stable('faculty',uri,faculty),'org':oid,'legacy_id':faculty,'name':label(faculty),'university_id':uri})
    for degree in degrees:
        links=restrictions(g,degree,'isDegreeOf');unis=sorted(links&set(university_nodes));facs=links&faculty_nodes
        if len(unis)>1 or len(facs)>1:resolved.append({'legacy_id':degree,'universities':len(unis),'faculties':len(facs),'resolution':'Intersect course faculty links with reciprocal university hasFaculty / faculty isFacultyOf assertions.'})
        for uri in unis:
            candidates=facs&restrictions(g,uri,'hasFaculty')
            candidates={f for f in candidates if uri in restrictions(g,f,'isFacultyOf') and degree in restrictions(g,f,'hasDegree') and degree in restrictions(g,uri,'hasDegree')}
            if len(candidates)!=1:
                unresolved.append({'legacy_id':degree,'university_id':uri,'faculty_candidates':sorted(candidates)});continue
            faculty=next(iter(candidates));inst=next(u for u in institutions if u['legacy_id']==uri)
            term_refs=sorted(restrictions(g,degree,'hasInterest')|restrictions(g,degree,'hasAptitude'))
            offers.append({'course_id':stable('offering',degree,uri,faculty),'legacy_id':degree,'legacy_university_id':uri,'legacy_faculty_id':faculty,'faculty_id':stable('faculty',uri,faculty),'org':inst['id'],'title':label(degree),'university':inst['name'],'faculty':label(faculty),'legacy_tags':term_refs,'course_url':inst['catalogue_url'],'url_kind':inst['url_kind'],'url_mode':'source','legacy_import':True,'current_availability':'not reverified','tag_origin':'prototype ontology; inherited degree-concept suitability tags, not verified admission prerequisites','legacy_tag_scope':'shared degree concept' if len(unis)>1 else 'degree concept','evidence':f'Prototype RDF: {degree} isDegreeOf {uri} and {faculty}. Faculty affiliation confirmed by reciprocal hasFaculty/isFacultyOf and hasDegree assertions.','provider':'Legacy RDF migration v1','mode':'Not specified','duration':'Not specified','illustrative':False})
        if not unis:unresolved.append({'legacy_id':degree,'reason':'No university assertion'})
    return {'checksum':hashlib.sha256(content).hexdigest(),'triples':len(g),'degree_concepts':len(degrees),'university_count':len(institutions),'faculty_class_count':len(faculty_nodes),'faculty_associations':len(faculties),'offering_count':len(offers),'tag_count':len(terms),'universities':institutions,'faculties':faculties,'tags':terms,'offerings':offers,'resolved_shared_concepts':resolved,'unresolved':unresolved,'notice':'Historical prototype migration. University affiliation, current availability, fees, admissions and inferred tags have not been independently reverified. Links are university catalogues/homepages, not fabricated degree-specific URLs.'}

def stage(db,migration,u):
    data=migration.data['plan']
    if data['unresolved']:raise HTTPException(422,'Resolve all reported affiliation conflicts before staging')
    if migration.state=='staged':return {'migration_id':migration.id,'revision_ids':migration.data['revision_ids'],'already_staged':True}
    aliases={};existing={(t['type'],t['label'].casefold()):t['id'] for t in taxonomy(db)}
    for term in data['tags']:
        tid=existing.get((term['type'],term['label'].casefold())) or tag_id(term['legacy_id'],term['type'])
        aliases[term['legacy_id']]=tid;r=db.get(Record,'tag:'+tid)
        if not r:add(db,'tag',{'label':term['label'],'type':term['type'],'legacy_ids':[term['legacy_id']]},id='tag:'+tid,state='active')
        else:r.data={**r.data,'legacy_ids':sorted(set(r.data.get('legacy_ids',[])+[term['legacy_id']]))}
    for inst in data['universities']:
        if not db.get(Record,inst['id']):add(db,'organization',{**inst,'contact':'','origin':'legacy ontology; no verified representative','institution_verification':'not reverified'},id=inst['id'],state='legacy_imported')
    for f in data['faculties']:
        if not db.get(Record,f['id']):add(db,'faculty',f,id=f['id'],org=f['org'],state='legacy_imported')
    source_id='source-'+migration.id
    if not db.get(Record,source_id):add(db,'source',{'name':'Prototype ontology.owl','url':'','object_uri':migration.data['object_uri'],'hash':data['checksum'],'method':'RDF import','count':len(data['offerings']),'notice':data['notice']},id=source_id,owner='legacy-import-service',state='completed')
    ids=[]
    for offer in data['offerings']:
        previous=next((r for r in db.scalars(select(Record).where(Record.kind=='course',Record.org==offer['org'])) if r.data.get('course_id')==offer['course_id']),None)
        if previous:ids.append(previous.id);continue
        tags=[aliases[t] for t in offer['legacy_tags'] if t in aliases]
        if len(tags)!=len(offer['legacy_tags']):raise HTTPException(422,'Missing taxonomy mapping; import aborted')
        r=new_revision(db,{**offer,'tags':tags,'reviewed':True,'source_id':source_id,'migration_id':migration.id,'migration_review':'Structurally validated against original graph; current institution verification remains outstanding'},owner='legacy-import-service',org=offer['org'],course_id=offer['course_id'],state='submitted');ids.append(r.id)
    for inst in data['universities']:
        members=[id for id in ids if db.get(Record,id).org==inst['id']]
        batch=add(db,'batch',{'ids':members,'migration_id':migration.id,'origin':'legacy-import-service'},owner='legacy-import-service',org=inst['id'],state='submitted')
        for id in members:
            r=db.get(Record,id)
            if r.state=='submitted':r.data={**r.data,'batch_id':batch.id}
    migration.state='staged';migration.data={**migration.data,'revision_ids':ids};audit(db,u.id,'legacy_migration_staged',migration.id,f'{len(ids)} evidence-backed offerings; not university endorsement');db.commit()
    return {'migration_id':migration.id,'revision_ids':ids,'already_staged':False}
