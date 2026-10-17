"""Read-only HTTP release smoke check. No login, seed or publication."""
import argparse,json,urllib.request

def main():
    p=argparse.ArgumentParser();p.add_argument('--base-url',default='http://127.0.0.1:8000');p.add_argument('--production',action='store_true');a=p.parse_args()
    base=a.base_url.rstrip('/')
    def get(path):
        with urllib.request.urlopen(base+path,timeout=30) as r:
            assert r.status==200
            return r.read()
    health=json.loads(get('/api/health'));assert health['status']=='ok'
    if a.production:assert health['environment']=='production' and health['auth_provider']=='firebase', 'Production auth/environment mismatch'
    html=get('/').decode();assert 'Meraki' in html and 'type="module"' in html
    courses=json.loads(get('/api/courses'));tags=json.loads(get('/api/taxonomy'))
    assert isinstance(courses,list) and isinstance(tags,list)
    assert len({c['course_id'] for c in courses})==len(courses)
    print(json.dumps({'health':health,'offerings':len(courses),'taxonomy_terms':len(tags),'http_smoke':'passed'},indent=2))
    print('This smoke check does not verify identity login, worker dispatch, storage, uploads or full production readiness.')
if __name__=='__main__':main()
