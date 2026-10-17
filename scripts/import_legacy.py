"""Read-only legacy ontology audit. Import requires manual identity resolution first."""
import argparse,json
from rdflib import Graph,Namespace,RDFS,OWL
def audit(path):
    g=Graph().parse(path);ns=Namespace('http://www.educationalguide.org/ontologies/ontology.owl#');rows=[]
    for course in sorted(set(g.subjects(RDFS.subClassOf,ns.Degree)),key=str):
        relations=[]
        for restriction in g.objects(course,RDFS.subClassOf):
            prop=g.value(restriction,OWL.onProperty);value=g.value(restriction,OWL.someValuesFrom)
            if prop and value:relations.append((str(prop).split('#')[-1],str(value)))
        universities=[];faculties=[]
        for prop,value in relations:
            if prop=='isDegreeOf':
                from rdflib import URIRef
                if (URIRef(value),RDFS.subClassOf,ns.University) in g:universities.append(value)
                if (URIRef(value),RDFS.subClassOf,ns.Faculty) in g:faculties.append(value)
        rows.append({'legacy_id':str(course),'universities':sorted(set(universities)),'faculties':sorted(set(faculties)),'requires_review':len(set(universities))!=1 or len(set(faculties))!=1,'public_url':None,'provenance':'legacy; unverified','relations':relations})
    return {'triples':len(g),'degree_concepts':len(rows),'ambiguous':sum(r['requires_review'] for r in rows),'publication_blocked':'No verified source evidence or student course URL. Ambiguous university/faculty associations are not expanded as a cross-product.','records':rows}
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('ontology');p.add_argument('--output',default='output/legacy-audit.json');a=p.parse_args();data=audit(a.ontology)
    from pathlib import Path
    Path(a.output).parent.mkdir(parents=True,exist_ok=True);Path(a.output).write_text(json.dumps(data,indent=2),encoding='utf-8');print(json.dumps({k:v for k,v in data.items() if k!='records'},indent=2))
