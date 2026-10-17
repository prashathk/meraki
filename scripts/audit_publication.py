"""Scan staged/committed publication content without printing secret values.

Run `python -m scripts.audit_publication` before committing or use `--ref HEAD`
to verify the complete published tree. Local secrets are only compared in memory.
"""
import argparse
import fnmatch
import json
import re
import subprocess
from pathlib import Path

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
BLOCKED_DIRS = {'.git', '.venv', 'node_modules', 'dist', 'data', 'output', 'tmp',
                '__pycache__', '.pytest_cache', '.terraform', 'test-results', 'playwright-report'}
BLOCKED_FILES = ('*.pem', '*.key', '*.p12', '*.pfx', '*.jks', '*credentials*.json',
                 '*service-account*.json', '*-firebase-adminsdk-*.json', 'client_secret*.json',
                 '*.db', '*.db-*', '*.sqlite*', '*.log', '*.bak', '*.backup', '*.zip',
                 '*.tfvars', '*.tfstate*', '*.tfplan', '*.tsbuildinfo')
RULES = {
    'Google API key': re.compile(rb'AIza[0-9A-Za-z_-]{35}'),
    'GitHub token': re.compile(rb'(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{30,})'),
    'AWS access key': re.compile(rb'(?:AKIA|ASIA)[A-Z0-9]{16}'),
    'Private key': re.compile(rb'-----BEGIN (?:[A-Z0-9 ]+ )?PRIVATE KEY-----'),
    'Slack token': re.compile(rb'xox[baprs]-[A-Za-z0-9-]{20,}'),
    'JWT': re.compile(rb'eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}'),
}


def git(*args):
    return subprocess.run(['git', *args], cwd=ROOT, check=True, capture_output=True).stdout


def blocked(path):
    parts = Path(path).parts
    name = parts[-1]
    environment_file = name != '.env.example' and (name.startswith('.env') or name.endswith('.env'))
    return environment_file or bool(set(parts) & BLOCKED_DIRS) or any(fnmatch.fnmatch(name.lower(), pattern) for pattern in BLOCKED_FILES)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ref', help='Inspect the complete tree at a Git ref instead of the index')
    args = parser.parse_args()
    if args.ref:
        entries = git('ls-tree', '-rz', args.ref).split(b'\0')
    else:
        entries = git('ls-files', '--stage', '-z').split(b'\0')
    # Match exact local credentials in addition to recognizable token formats.
    secrets = []
    for name, value in dotenv_values(ROOT / '.env').items():
        if re.search(r'PASSWORD|SECRET|TOKEN|API_KEY|PRIVATE_KEY', name, re.I) and value and len(value) >= 8:
            secrets.append(value.encode())
    findings = []
    count = 0
    for entry in entries:
        if not entry:
            continue
        metadata, raw_path = entry.split(b'\t', 1)
        path = raw_path.decode('utf-8')
        mode, blob, *_ = metadata.split()
        if args.ref:
            blob = metadata.split()[2]
        count += 1
        if blocked(path):
            findings.append({'path': path, 'rule': 'Private/generated file'})
        if mode == b'120000':
            findings.append({'path': path, 'rule': 'Symbolic link requires review'})
        data = git('cat-file', 'blob', blob.decode())
        if any(secret in data for secret in secrets):
            findings.append({'path': path, 'rule': 'Exact local credential'})
        for rule, pattern in RULES.items():
            if pattern.search(data):
                findings.append({'path': path, 'rule': rule})
    print(json.dumps({'files_scanned': count, 'findings': findings, 'passed': not findings}, indent=2))
    raise SystemExit(bool(findings))


if __name__ == '__main__':
    main()
