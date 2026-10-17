import os
import uuid
from datetime import datetime, timezone
from sqlalchemy import create_engine, String, Text, JSON, Integer, ForeignKey, UniqueConstraint, Index
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

def uid(): return str(uuid.uuid4())
def now(): return datetime.now(timezone.utc).isoformat()
DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///./data/meraki.db')
engine = create_engine(DATABASE_URL, connect_args={'check_same_thread':False} if DATABASE_URL.startswith('sqlite') else {}, pool_pre_ping=True,**({} if DATABASE_URL.startswith('sqlite') else {'pool_size':3,'max_overflow':2,'pool_timeout':15}))
Session = sessionmaker(engine, expire_on_commit=False)
class Base(DeclarativeBase): pass
class Record(Base):
    """Small indexed document aggregate. Immutable revision records preserve history."""
    __tablename__='records'
    id: Mapped[str] = mapped_column(String(300),primary_key=True,default=uid)
    kind: Mapped[str] = mapped_column(String(40),index=True)
    owner: Mapped[str] = mapped_column(String(100),default='',index=True)
    org: Mapped[str] = mapped_column(String(100),default='',index=True)
    state: Mapped[str] = mapped_column(String(40),default='',index=True)
    data: Mapped[dict] = mapped_column(JSON,default=dict)
    created_at: Mapped[str] = mapped_column(String(50),default=now)
class Edge(Base):
    __tablename__='course_tags'
    id: Mapped[int] = mapped_column(Integer,primary_key=True)
    revision_id: Mapped[str] = mapped_column(ForeignKey('records.id'),index=True)
    tag_id: Mapped[str] = mapped_column(String(100),index=True)
    __table_args__=(UniqueConstraint('revision_id','tag_id'),)
class VersionCourse(Base):
    __tablename__='version_courses'
    id: Mapped[int] = mapped_column(Integer,primary_key=True)
    version_id: Mapped[str] = mapped_column(ForeignKey('records.id'),index=True)
    course_id: Mapped[str] = mapped_column(String(100),index=True)
    revision_id: Mapped[str] = mapped_column(ForeignKey('records.id'))
    __table_args__=(UniqueConstraint('version_id','course_id'),)
class Active(Base):
    __tablename__='active_version'
    id: Mapped[int] = mapped_column(Integer,primary_key=True,default=1)
    version_id: Mapped[str] = mapped_column(ForeignKey('records.id'))
    generation: Mapped[int] = mapped_column(Integer,default=1)

def record(r): return {**r.data,'id':r.id,'state':r.state,'created_at':r.created_at,'owner':r.owner,'org':r.org}
def add(db,kind,data,**kw):
    r=Record(kind=kind,data=data,**kw);db.add(r);db.flush();return r
def audit(db,actor,action,target,detail=''):
    add(db,'audit',{'action':action,'target':target,'detail':detail},owner=actor)
