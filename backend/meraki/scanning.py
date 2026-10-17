import os,subprocess,tempfile
from pathlib import Path
def scan(content):
    scanner=os.getenv('CLAMSCAN_PATH')
    if not scanner:
        if os.getenv('APP_ENV')=='production':raise ValueError('Production document uploads require a configured malware scanner; CLAMSCAN_PATH is missing')
        return 'not scanned - local development only'
    with tempfile.TemporaryDirectory() as d:
        path=Path(d)/'source';path.write_bytes(content)
        result=subprocess.run([scanner,'--no-summary',str(path)],capture_output=True,timeout=60)
        if result.returncode:raise ValueError('Document failed the malware scan or scanner is unavailable')
    return 'passed'
