import hashlib, hmac, os, secrets, ipaddress, socket
from urllib.parse import urlparse
from datetime import datetime, timezone, timedelta
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer
from sqlalchemy import select
from .db import Session, Record, now

ENV=os.getenv('APP_ENV','development')
AUTH=os.getenv('AUTH_PROVIDER','development')
if ENV=='production' and AUTH!='firebase': raise RuntimeError('Production requires Firebase authentication')
bearer=HTTPBearer(auto_error=False)
def db_session():
    with Session() as db: yield db
def password_hash(password,salt=None):
    salt=salt or secrets.token_hex(16)
    return salt+':'+hashlib.scrypt(password.encode(),salt=salt.encode(),n=16384,r=8,p=1).hex()
def password_ok(password,stored): return hmac.compare_digest(password_hash(password,stored.split(':')[0]),stored)
def user(db=Depends(db_session),credentials=Depends(bearer)):
    if not credentials: raise HTTPException(401,'Sign in to continue')
    if AUTH=='firebase':
        import firebase_admin
        from firebase_admin import auth
        if not firebase_admin._apps: firebase_admin.initialize_app()
        try:
            claims=auth.verify_id_token(credentials.credentials,check_revoked=True)
        except Exception: raise HTTPException(401,'Invalid or revoked identity token')
        if not claims.get('email_verified'): raise HTTPException(403,'Verify your email first')
        account=db.get(Record,'firebase:'+claims['uid'])
    else:
        token=hashlib.sha256(credentials.credentials.encode()).hexdigest()
        session=db.get(Record,'session:'+token)
        if not session or session.data['expires_at']<now(): raise HTTPException(401,'Session expired')
        account=db.get(Record,session.owner)
    if not account or account.state!='active': raise HTTPException(403,'Account unavailable')
    return account
def role(u,*roles):
    if u.data['role'] not in roles: raise HTTPException(403,'This action is not permitted for your role')
def representative(db,u):
    role(u,'representative')
    org=db.get(Record,u.org)
    if not org or org.state!='verified': raise HTTPException(403,'Your university membership is awaiting verification')
    return org
def public_url(value,resolve=False):
    try:
        p=urlparse(value)
        if p.scheme not in ('https','http') or not p.hostname or p.username or p.password or (p.port and p.port not in (80,443)): raise ValueError()
        host=p.hostname.lower()
        if host in ('localhost','metadata.google.internal') or '.' not in host or host.endswith(('.localhost','.local','.internal')):raise ValueError()
        try:ip=ipaddress.ip_address(host)
        except ValueError:ip=None
        if ip is not None and not ip.is_global:raise ValueError()
        if ip is None and all(x.isdigit() or x in '.:' for x in host):raise ValueError()
        if resolve:
            addresses=socket.getaddrinfo(host,p.port or (443 if p.scheme=='https' else 80),type=socket.SOCK_STREAM)
            if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):raise ValueError()
        return value
    except (ValueError,OSError):raise HTTPException(422,'Use a public HTTP(S) URL without credentials or private addresses')
