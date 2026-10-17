from fastapi import APIRouter,Depends,UploadFile,File,HTTPException
from sqlalchemy import select
from .security import user,role,db_session
from .db import Record,add,record,audit
from .legacy import plan,stage
from .storage import put

router=APIRouter(prefix='/api/admin/legacy',tags=['Legacy migration'])
@router.post('/preview')
async def preview(file:UploadFile=File(...),u=Depends(user),db=Depends(db_session)):
    role(u,'admin');content=await file.read(20*1024*1024+1)
    try:result=plan(content)
    except Exception as e:raise HTTPException(422,str(e))
    id='migration:'+result['checksum'];r=db.get(Record,id)
    if not r:
        uri=put('legacy/'+result['checksum']+'.owl',content,'application/rdf+xml')
        r=add(db,'migration',{'plan':result,'object_uri':uri},id=id,owner=u.id,state='previewed');audit(db,u.id,'legacy_migration_preview',id);db.commit()
    return record(r)
@router.get('')
def migrations(u=Depends(user),db=Depends(db_session)):
    role(u,'admin');return [record(r) for r in db.scalars(select(Record).where(Record.kind=='migration').order_by(Record.created_at.desc()))]
@router.post('/{id}/stage')
def stage_migration(id:str,u=Depends(user),db=Depends(db_session)):
    role(u,'admin');r=db.get(Record,id)
    if not r or r.kind!='migration':raise HTTPException(404)
    return stage(db,r,u)
