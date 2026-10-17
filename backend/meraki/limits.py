"""Persistent coarse rate budgets. Enforce edge-level limits too before public release."""
import time,hashlib
from fastapi import HTTPException
from sqlalchemy import select
from .db import Record,add
def budget(db,subject,action,limit,window=60):
    slot=int(time.time())//window
    id='rate:'+hashlib.sha256(f'{subject}:{action}:{slot}'.encode()).hexdigest()
    r=db.get(Record,id)
    if r and r.data['count']>=limit:raise HTTPException(429,'Too many requests. Please try again later.')
    if r:r.data={**r.data,'count':r.data['count']+1}
    else:add(db,'rate',{'count':1,'slot':slot,'window':window},id=id)
    db.commit()
