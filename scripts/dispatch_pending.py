"""Scheduled maintenance job: re-dispatch durable queued tasks after transient dispatch errors."""
from sqlalchemy import select,update
from backend.meraki.db import Session,Record
from backend.meraki.tasks import dispatch
from datetime import datetime,timezone,timedelta
with Session() as db:
    cutoff=(datetime.now(timezone.utc)-timedelta(minutes=15)).isoformat()
    db.execute(update(Record).where(Record.kind=='source',Record.state=='running',Record.data['started_at'].as_string()<cutoff).values(state='queued'))
    db.commit()
    for r in db.scalars(select(Record).where(Record.kind=='source',Record.state=='queued').limit(100)):dispatch(r.id)
