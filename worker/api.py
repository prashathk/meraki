"""Private Cloud Run worker service. Cloud Run IAM must require the task identity."""
from fastapi import FastAPI,HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from backend.meraki.db import Session,Record
from worker.run import once
app=FastAPI(docs_url=None,openapi_url=None)
class ExtractTask(BaseModel):source_id:str
@app.get('/health')
def health():return {'ok':True}
@app.post('/internal/extract')
def extract_task(body:ExtractTask):
    # IAM authentication is enforced by Cloud Run, not by caller-supplied headers.
    once(body.source_id)
    with Session() as db:
        r=db.get(Record,body.source_id)
        if not r:raise HTTPException(404)
        if r.state in ('queued','running'):raise HTTPException(503,'Task is not complete; retry later')
        return {'state':r.state}
