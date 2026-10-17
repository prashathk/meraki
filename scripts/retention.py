"""Explicit maintenance command. Dry-run by default; --apply makes changes."""
import argparse
from datetime import datetime,timezone,timedelta
from sqlalchemy import select
from backend.meraki.db import Session,Record
def cleanup(apply=False):
    cutoff=(datetime.now(timezone.utc)-timedelta(days=90)).isoformat();current=datetime.now(timezone.utc).isoformat()
    with Session() as db:
        rows=[r for r in db.scalars(select(Record).where(Record.kind.in_(['event','rate','session']))) if (r.kind=='event' and r.created_at<cutoff) or (r.kind=='rate' and r.created_at<(datetime.now(timezone.utc)-timedelta(days=2)).isoformat()) or (r.kind=='session' and r.data.get('expires_at','')<current)]
        print(('Deleting' if apply else 'Would delete'),len(rows),'expired behavioral/rate/session records')
        if apply:
            for r in rows:db.delete(r)
            db.commit()
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--apply',action='store_true');a=p.parse_args();cleanup(a.apply)
