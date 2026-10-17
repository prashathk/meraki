"""Build an allowlisted source release, excluding all live data and secrets."""
import hashlib,json,zipfile
from pathlib import Path
from datetime import datetime,timezone

ROOT=Path(__file__).resolve().parents[1]
ROOT_FILES=['HANDOVER.md','README.md','.env.example','.gitignore','.dockerignore','.gcloudignore','alembic.ini','Dockerfile','compose.yaml','cloudbuild.yaml']
TREES=['backend','worker','frontend','scripts','docs','infra']
EXCLUDED={'node_modules','__pycache__','.pytest_cache','test-results','playwright-report','.terraform','.git'}

def build():
    files=[ROOT/p for p in ROOT_FILES]
    for name in TREES:
        for p in (ROOT/name).rglob('*'):
            if not p.is_file():continue
            rel=p.relative_to(ROOT)
            if any(part in EXCLUDED for part in rel.parts):continue
            if p.name=='.env' or (p.name.startswith('.env.') and p.name!='.env.example'):continue
            if p.suffix in {'.pyc','.pyo','.tsbuildinfo','.tfvars','.tfplan','.db','.sqlite','.log','.pem','.key'} or '.tfstate' in p.name:continue
            files.append(p)
    manifest={'release':'Meraki handover 2026-10-17','created_utc':datetime.now(timezone.utc).isoformat(),'files':[]}
    target=ROOT/'output'/'handover';target.mkdir(parents=True,exist_ok=True)
    archive=target/'Meraki-Deployment-Handover-2026-10-17.zip'
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for p in sorted(files):
            rel=p.relative_to(ROOT).as_posix();blob=p.read_bytes()
            manifest['files'].append({'path':rel,'bytes':len(blob),'sha256':hashlib.sha256(blob).hexdigest()})
            z.writestr('Meraki/'+rel,blob)
        z.writestr('Meraki/MANIFEST.json',json.dumps(manifest,indent=2))
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        names=set(z.namelist())
        assert len(names)==len(files)+1
        for item in manifest['files']:
            assert hashlib.sha256(z.read('Meraki/'+item['path'])).hexdigest()==item['sha256']
        assert not any('/data/' in n or '/node_modules/' in n or n.endswith('/.env') for n in names)
    digest=hashlib.sha256(archive.read_bytes()).hexdigest()
    archive.with_suffix('.zip.sha256').write_text(digest+'  '+archive.name+'\n',encoding='utf-8')
    print(json.dumps({'archive':str(archive),'bytes':archive.stat().st_size,'payload_files':len(files),'sha256':digest},indent=2))
if __name__=='__main__':build()
