from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, HttpUrl
from uuid import uuid4
from datetime import datetime, timezone
import json, os, psycopg, urllib.error, urllib.request
from psycopg.rows import dict_row

app=FastAPI(title='UNG-NEXUS',version='0.2.0')
DB=os.getenv('DATABASE_URL','')
JANUS_BASE_URL=os.getenv('JANUS_BASE_URL','https://ung-iam-production.up.railway.app').rstrip('/')

def auth(permission, authorization):
    if not authorization or not authorization.lower().startswith('bearer '):
        raise HTTPException(401,'JANUS bearer token required')
    req=urllib.request.Request(JANUS_BASE_URL+'/v1/auth/introspect',data=b'',method='POST',headers={'Authorization':authorization})
    try:
        with urllib.request.urlopen(req,timeout=5) as r:
            data=json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        if e.code in (401,403): raise HTTPException(401,'JANUS token invalid or expired')
        raise HTTPException(503,'JANUS authorization unavailable')
    except Exception:
        raise HTTPException(503,'JANUS authorization unavailable')
    principal=data.get('principal') or {}
    perms=set(principal.get('permissions') or [])
    if permission not in perms and 'ung.admin' not in perms:
        raise HTTPException(403,f'Missing JANUS permission: {permission}')
    return principal

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
def health(): return {'status':'ok','service':'UNG-NEXUS','version':'0.2.0'}
@app.get('/ready')
def ready():
    try:
        with conn() as c:c.execute('SELECT 1')
        return {'status':'ready','database':'connected','janus':JANUS_BASE_URL}
    except Exception:return {'status':'degraded','database':'unavailable','janus':JANUS_BASE_URL}
@app.get('/v1/system')
def system(): return {'system_id':'UNG-NEXUS','domain':'integration-interoperability','capabilities':['endpoint-registry','message-routing','integration-audit','janus-bearer-auth']}
@app.get('/v1/endpoints')
def endpoints(authorization:str|None=Header(None)):
    auth('nexus.endpoints.read',authorization)
    with conn() as c:return c.execute('SELECT * FROM nexus_endpoints ORDER BY created_at DESC').fetchall()
@app.post('/v1/endpoints',status_code=201)
def add_endpoint(b:EndpointIn,authorization:str|None=Header(None)):
    auth('nexus.endpoints.write',authorization)
    with conn() as c:return c.execute('INSERT INTO nexus_endpoints VALUES(%s,%s,%s,%s,%s,%s) RETURNING *',(str(uuid4()),b.name,str(b.base_url),b.system_id,b.enabled,datetime.now(timezone.utc))).fetchone()
@app.get('/v1/messages')
def messages(authorization:str|None=Header(None)):
    auth('nexus.messages.read',authorization)
    with conn() as c:return c.execute('SELECT * FROM nexus_messages ORDER BY created_at DESC LIMIT 500').fetchall()
@app.post('/v1/messages',status_code=202)
def route_message(b:MessageIn,authorization:str|None=Header(None)):
    auth('nexus.messages.write',authorization)
    with conn() as c:
        target=c.execute('SELECT id FROM nexus_endpoints WHERE system_id=%s AND enabled=true LIMIT 1',(b.target_system,)).fetchone()
        status='accepted' if target else 'unroutable'
        return c.execute('INSERT INTO nexus_messages VALUES(%s,%s,%s,%s,%s,%s,%s) RETURNING *',(str(uuid4()),b.source_system,b.target_system,b.message_type,psycopg.types.json.Jsonb(b.payload),status,datetime.now(timezone.utc))).fetchone()
