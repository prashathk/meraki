"""Explicit production initialization. Never exposes a public admin sign-up route."""
import argparse,hashlib
from backend.meraki.db import Session,Record,Active,add
from backend.meraki.domain import rdf_snapshot,TAXONOMY
def main(uid,email,name):
    import firebase_admin
    from firebase_admin import auth
    if not firebase_admin._apps:firebase_admin.initialize_app()
    identity=auth.get_user(uid)
    if identity.email!=email or not identity.email_verified:raise ValueError('Verified Firebase email and UID must match')
    with Session() as db:
        id='firebase:'+uid
        if db.get(Record,id):raise ValueError('Account exists; use a reviewed privilege-change procedure')
        add(db,'user',{'name':name,'email':email,'role':'admin','profile':{'tags':[]}},id=id,state='active')
        for t in TAXONOMY:
            if not db.get(Record,'tag:'+t['id']):add(db,'tag',{'label':t['label'],'type':t['type']},id='tag:'+t['id'],state='active')
        if not db.get(Active,1):
            snapshot=rdf_snapshot([]);v=add(db,'version',{'count':0,'summary':'Empty production catalogue','parent':None,'snapshot':snapshot,'checksum':hashlib.sha256(snapshot.encode()).hexdigest()},state='published')
            db.add(Active(id=1,version_id=v.id,generation=1))
        auth.set_custom_user_claims(uid,{**(identity.custom_claims or {}),'role':'admin'});db.commit()
    print('Administrator and production catalogue initialized.')
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--uid',required=True);p.add_argument('--email',required=True);p.add_argument('--name',required=True);a=p.parse_args();main(a.uid,a.email,a.name)
