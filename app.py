from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, HttpUrl
from uuid import uuid4
from datetime import datetime, timezone
import os, psycopg
from psycopg.rows import dict_row

app=FastAPI(title='UNG-NEXUS',version='0.1.0')
DB=os.getenv('DATABASE_URL','')

def auth(permission, header):
    perms={x.strip() for x in (header or '').split(',')}
    if permission not in perms and 'ung.admin' not in perms: raise HTTPException(403,'JANUS permission required')
def conn(): return psycopg.connect(DB,row_factory=dict_row)
@app.on_event('startup')
def init():
    if DB:
        with conn() as c:
            c.execute('CREATE TABLE IF NOT EXISTS nexus_endpoints(id UUID PRIMARY KEY,name TEXT UNIQUE,base_url TEXT,system_id TEXT,enabled BOOLEAN,created_at TIMESTAMPTZ)')
            c.execute('CREATE TABLE IF NOT EXISTS nexus_messages(id UUID PRIMARY KEY,source_system TEXT,target_system TEXT,message_type TEXT,payload JSONB,status TEXT,created_at TIMESTAMPTZ)')
class EndpointIn(BaseModel): name:str; base_url:HttpUrl; system_id:str; enabled:bool=True
class MessageIn(BaseModel): source_system:str; target_system:str; message_type:str; payload:dict
@app.get('/health')
def health(): return {'status':'ok','service':'UNG-NEXUS','version':'0.1.0'}
@app.get('/ready')
def ready():
    try:
        with conn() as c:c.execute('SELECT 1')
        return {'status':'ready','database':'connected'}
    except Exception:return {'status':'degraded','database':'unavailable'}
@app.get('/v1/system')
def system(): return {'system_id':'UNG-NEXUS','domain':'integration-interoperability','capabilities':['endpoint-registry','message-routing','integration-audit']}
@app.get('/v1/endpoints')
def endpoints(x_ung_permissions:str|None=Header(None)):
    auth('nexus.endpoints.read',x_ung_permissions)
    with conn() as c:return c.execute('SELECT * FROM nexus_endpoints ORDER BY created_at DESC').fetchall()
@app.post('/v1/endpoints',status_code=201)
def add_endpoint(b:EndpointIn,x_ung_permissions:str|None=Header(None)):
    auth('nexus.endpoints.write',x_ung_permissions)
    with conn() as c:return c.execute('INSERT INTO nexus_endpoints VALUES(%s,%s,%s,%s,%s,%s) RETURNING *',(str(uuid4()),b.name,str(b.base_url),b.system_id,b.enabled,datetime.now(timezone.utc))).fetchone()
@app.get('/v1/messages')
def messages(x_ung_permissions:str|None=Header(None)):
    auth('nexus.messages.read',x_ung_permissions)
    with conn() as c:return c.execute('SELECT * FROM nexus_messages ORDER BY created_at DESC LIMIT 500').fetchall()
@app.post('/v1/messages',status_code=202)
def route_message(b:MessageIn,x_ung_permissions:str|None=Header(None)):
    auth('nexus.messages.write',x_ung_permissions)
    with conn() as c:
        target=c.execute('SELECT id FROM nexus_endpoints WHERE system_id=%s AND enabled=true LIMIT 1',(b.target_system,)).fetchone()
        status='accepted' if target else 'unroutable'
        return c.execute('INSERT INTO nexus_messages VALUES(%s,%s,%s,%s,%s,%s,%s) RETURNING *',(str(uuid4()),b.source_system,b.target_system,b.message_type,psycopg.types.json.Jsonb(b.payload),status,datetime.now(timezone.utc))).fetchone()
