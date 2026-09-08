from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, HttpUrl
from uuid import uuid4
from datetime import datetime, timezone
import json, os, time, psycopg, urllib.error, urllib.request
from psycopg.rows import dict_row
from interop import NexusEnvelope, connectors
from pulsar_transport import relay as relay_to_pulsar
app=FastAPI(title='UNG-NEXUS',version='0.6.0');DB=os.getenv('DATABASE_URL','');JANUS_BASE_URL=os.getenv('JANUS_BASE_URL','https://ung-iam-production.up.railway.app').rstrip('/');APOLLO_BASE_URL=os.getenv('APOLLO_BASE_URL','').rstrip('/');PULSAR_BASE_URL=os.getenv('PULSAR_BASE_URL','').rstrip('/');DELIVERY_TIMEOUT=float(os.getenv('NEXUS_DELIVERY_TIMEOUT','8'));DELIVERY_RETRIES=max(1,min(5,int(os.getenv('NEXUS_DELIVERY_RETRIES','3'))))
def auth(permission,authorization):
 if not authorization or not authorization.lower().startswith('bearer '):raise HTTPException(401,'JANUS bearer token required')
 req=urllib.request.Request(JANUS_BASE_URL+'/v1/auth/introspect',data=b'',method='POST',headers={'Authorization':authorization,'User-Agent':'UNG-NEXUS/0.6.0'})
 try:
  with urllib.request.urlopen(req,timeout=5) as r:data=json.loads(r.read().decode())
 except urllib.error.HTTPError as e:
  if e.code in (401,403):raise HTTPException(401,'JANUS token invalid or expired')
  raise HTTPException(503,'JANUS authorization unavailable')
 except Exception:raise HTTPException(503,'JANUS authorization unavailable')
 principal=data.get('principal') or {};perms=set(principal.get('permissions') or [])
 if permission not in perms and 'ung.admin' not in perms and 'platform:service' not in perms:raise HTTPException(403,f'Missing JANUS permission: {permission}')
 return principal
def conn():return psycopg.connect(DB,row_factory=dict_row)
def utcnow():return datetime.now(timezone.utc)
def run_apollo_acceptance_probe():
 if not APOLLO_BASE_URL or not DB:return
 t=utcnow();status='failed';code=None;mid=None;error=None
 try:
  req=urllib.request.Request(APOLLO_BASE_URL+'/v1/nexus/acceptance',data=b'',method='POST',headers={'User-Agent':'UNG-NEXUS/0.6.0'})
  with urllib.request.urlopen(req,timeout=DELIVERY_TIMEOUT) as r:
   code=int(r.status);body=json.loads(r.read().decode() or '{}');mid=body.get('message_id');status='passed' if 200<=code<300 and body.get('accepted') else 'failed'
 except urllib.error.HTTPError as e:code=int(e.code);error=f'http_{e.code}'
 except Exception as e:error=type(e).__name__
 try:
  with conn() as c:c.execute('INSERT INTO nexus_acceptance_checks(id,target_system,status,response_code,message_id,error,created_at) VALUES(%s,%s,%s,%s,%s,%s,%s)',(str(uuid4()),'UNG-APOLLO',status,code,mid,error,t))
 except Exception:pass
@app.on_event('startup')
def init():
 if not DB:return
 with conn() as c:
  c.execute('CREATE TABLE IF NOT EXISTS nexus_endpoints(id UUID PRIMARY KEY,name TEXT UNIQUE,base_url TEXT,system_id TEXT,enabled BOOLEAN,created_at TIMESTAMPTZ)');c.execute('CREATE TABLE IF NOT EXISTS nexus_messages(id UUID PRIMARY KEY,source_system TEXT,target_system TEXT,message_type TEXT,payload JSONB,status TEXT,created_at TIMESTAMPTZ)');c.execute('CREATE TABLE IF NOT EXISTS nexus_acceptance_checks(id UUID PRIMARY KEY,target_system TEXT,status TEXT,response_code INTEGER,message_id TEXT,error TEXT,created_at TIMESTAMPTZ)')
  for sql in ['ALTER TABLE nexus_messages ADD COLUMN IF NOT EXISTS attempts INTEGER NOT NULL DEFAULT 0','ALTER TABLE nexus_messages ADD COLUMN IF NOT EXISTS response_code INTEGER','ALTER TABLE nexus_messages ADD COLUMN IF NOT EXISTS delivery_error TEXT','ALTER TABLE nexus_messages ADD COLUMN IF NOT EXISTS delivered_at TIMESTAMPTZ','ALTER TABLE nexus_messages ADD COLUMN IF NOT EXISTS direction TEXT NOT NULL DEFAULT \'outbound\'','ALTER TABLE nexus_messages ADD COLUMN IF NOT EXISTS principal_id TEXT','ALTER TABLE nexus_messages ADD COLUMN IF NOT EXISTS correlation_id TEXT','ALTER TABLE nexus_messages ADD COLUMN IF NOT EXISTS trace_id TEXT','ALTER TABLE nexus_messages ADD COLUMN IF NOT EXISTS schema_version TEXT NOT NULL DEFAULT \'1.0\'','ALTER TABLE nexus_messages ADD COLUMN IF NOT EXISTS priority INTEGER NOT NULL DEFAULT 50','ALTER TABLE nexus_messages ADD COLUMN IF NOT EXISTS classification TEXT NOT NULL DEFAULT \'internal\'']:c.execute(sql)
  if APOLLO_BASE_URL:c.execute('INSERT INTO nexus_endpoints(id,name,base_url,system_id,enabled,created_at) VALUES(%s,%s,%s,%s,true,%s) ON CONFLICT(name) DO UPDATE SET base_url=EXCLUDED.base_url,system_id=EXCLUDED.system_id,enabled=true',(str(uuid4()),'UNG-APOLLO',APOLLO_BASE_URL+'/v1/nexus/inbound','UNG-APOLLO',utcnow()))
 run_apollo_acceptance_probe()
class EndpointIn(BaseModel):name:str;base_url:HttpUrl;system_id:str;enabled:bool=True
class MessageIn(BaseModel):source_system:str;target_system:str;message_type:str;payload:dict;message_id:str|None=None;correlation_id:str|None=None;trace_id:str|None=None;schema_version:str='1.0';priority:int=50;classification:str='internal';connector:str|None=None
@app.get('/')
def root():return {'service':'UNG-NEXUS','status':'online','version':'0.6.0','transport':'UNG-PULSAR' if PULSAR_BASE_URL else 'direct','acceptance':'/v1/acceptance/status','docs':'/docs'}
@app.get('/health')
def health():return {'status':'ok','service':'UNG-NEXUS','version':'0.6.0','connectors':len(connectors._connectors),'pulsar_transport':bool(PULSAR_BASE_URL)}
@app.get('/ready')
def ready():
 try:
  with conn() as c:c.execute('SELECT 1');probe=c.execute("SELECT status,response_code,message_id,error,created_at FROM nexus_acceptance_checks WHERE target_system='UNG-APOLLO' ORDER BY created_at DESC LIMIT 1").fetchone()
  return {'status':'ready','database':'connected','janus':JANUS_BASE_URL,'pulsar':PULSAR_BASE_URL or None,'pulsar_configured':bool(PULSAR_BASE_URL),'apollo_registered':bool(APOLLO_BASE_URL),'apollo_acceptance':probe}
 except Exception:return {'status':'degraded','database':'unavailable','janus':JANUS_BASE_URL,'pulsar':PULSAR_BASE_URL or None,'pulsar_configured':bool(PULSAR_BASE_URL),'apollo_registered':False,'apollo_acceptance':None}
@app.get('/v1/system')
def system():return {'system_id':'UNG-NEXUS','domain':'integration-interoperability','capabilities':['endpoint-registry','message-routing','inbound-gateway','pulsar-transport','outbound-http-delivery','integration-audit','standard-envelope','connector-registry','vendor-adapters','idempotent-inbound','idempotent-outbound','retry','janus-bearer-auth','apollo-route','apollo-acceptance-probe']}
@app.get('/v1/acceptance/status')
def acceptance_status():
 try:
  with conn() as c:row=c.execute("SELECT target_system,status,response_code,message_id,error,created_at FROM nexus_acceptance_checks WHERE target_system='UNG-APOLLO' ORDER BY created_at DESC LIMIT 1").fetchone()
  return {'service':'UNG-NEXUS','target':'UNG-APOLLO','check':row}
 except Exception as e:raise HTTPException(503,f'acceptance_status_unavailable:{type(e).__name__}')
@app.get('/v1/endpoints')
def endpoints(authorization:str|None=Header(None)):
 auth('nexus.endpoints.read',authorization)
 with conn() as c:return c.execute('SELECT * FROM nexus_endpoints ORDER BY created_at DESC').fetchall()
@app.post('/v1/endpoints',status_code=201)
def add_endpoint(b:EndpointIn,authorization:str|None=Header(None)):
 auth('nexus.endpoints.write',authorization)
 with conn() as c:return c.execute('INSERT INTO nexus_endpoints VALUES(%s,%s,%s,%s,%s,%s) RETURNING *',(str(uuid4()),b.name,str(b.base_url),b.system_id,b.enabled,utcnow())).fetchone()
@app.get('/v1/connectors')
def list_connectors(authorization:str|None=Header(None)):
 auth('nexus.endpoints.read',authorization);return {'connectors':[{'name':c.name,'kind':c.kind,'capabilities':sorted(c.capabilities),'enabled':c.enabled} for c in connectors._connectors.values()]}
@app.get('/v1/connectors/discover/{capability}')
def discover_connectors(capability:str,authorization:str|None=Header(None)):
 auth('nexus.endpoints.read',authorization);return {'capability':capability,'connectors':[{'name':c.name,'kind':c.kind,'capabilities':sorted(c.capabilities)} for c in connectors.discover(capability)]}
@app.get('/v1/messages')
def messages(authorization:str|None=Header(None)):
 auth('nexus.messages.read',authorization)
 with conn() as c:return c.execute('SELECT * FROM nexus_messages ORDER BY created_at DESC LIMIT 500').fetchall()
def deliver(url,envelope,authorization):
 body=json.dumps(envelope,separators=(',',':')).encode();last_error=None;last_code=None
 for attempt in range(1,DELIVERY_RETRIES+1):
  req=urllib.request.Request(url,data=body,method='POST',headers={'Content-Type':'application/json','Authorization':authorization,'User-Agent':'UNG-NEXUS/0.6.0'})
  try:
   with urllib.request.urlopen(req,timeout=DELIVERY_TIMEOUT) as r:
    code=int(r.status)
    if 200<=code<300:return True,attempt,code,None
    last_code=code;last_error=f'http_{code}'
  except urllib.error.HTTPError as e:
   last_code=int(e.code);last_error=f'http_{e.code}'
   if 400<=e.code<500 and e.code not in (408,429):break
  except Exception as e:last_error=type(e).__name__
  if attempt<DELIVERY_RETRIES:time.sleep(min(.25*(2**(attempt-1)),1.0))
 return False,attempt,last_code,last_error
@app.post('/v1/inbound',status_code=202)
def inbound(b:MessageIn,authorization:str|None=Header(None)):
 principal=auth('nexus.messages.write',authorization);env=NexusEnvelope(b.source_system,b.target_system,b.message_type,b.payload,b.message_id or str(uuid4()),b.correlation_id,b.trace_id,b.schema_version,b.priority,b.classification);d=env.to_dict();created=utcnow()
 with conn() as c:
  existing=c.execute('SELECT * FROM nexus_messages WHERE id=%s',(d['message_id'],)).fetchone()
  if existing:return {'accepted':True,'duplicate':True,'message':existing}
  row=c.execute('INSERT INTO nexus_messages(id,source_system,target_system,message_type,payload,status,created_at,direction,principal_id,correlation_id,trace_id,schema_version,priority,classification) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *',(d['message_id'],b.source_system,b.target_system,b.message_type,psycopg.types.json.Jsonb(b.payload),'accepted',created,'inbound',str(principal.get('id') or ''),d['correlation_id'],d['trace_id'],d['schema_version'],d['priority'],d['classification'])).fetchone()
 return {'accepted':True,'duplicate':False,'message':row}
@app.post('/v1/messages',status_code=202)
def route_message(b:MessageIn,authorization:str|None=Header(None)):
 principal=auth('nexus.messages.write',authorization);env=NexusEnvelope(b.source_system,b.target_system,b.message_type,b.payload,b.message_id or str(uuid4()),b.correlation_id,b.trace_id,b.schema_version,b.priority,b.classification);d=env.to_dict();created=utcnow()
 with conn() as c:
  existing=c.execute('SELECT * FROM nexus_messages WHERE id=%s',(d['message_id'],)).fetchone()
  if existing:return {'accepted':True,'duplicate':True,'message':existing}
 if b.connector:
  adapter=connectors.get(b.connector)
  if not adapter:raise HTTPException(404,'connector_not_found_or_disabled')
  result=adapter.send(env);return {'message_id':d['message_id'],'connector':b.connector,'result':result,'envelope':d}
 if PULSAR_BASE_URL:
  ok,attempts,code,error,result=relay_to_pulsar(d,authorization);status='relayed' if ok else 'failed';delivered_at=utcnow() if ok else None
 else:
  with conn() as c:target=c.execute('SELECT * FROM nexus_endpoints WHERE system_id=%s AND enabled=true ORDER BY created_at DESC LIMIT 1',(b.target_system,)).fetchone()
  if not target:status='unroutable';attempts=0;code=None;error='no_enabled_endpoint';delivered_at=None
  else:ok,attempts,code,error=deliver(target['base_url'],d,authorization);status='delivered' if ok else 'failed';delivered_at=utcnow() if ok else None
 with conn() as c:return c.execute('INSERT INTO nexus_messages(id,source_system,target_system,message_type,payload,status,created_at,attempts,response_code,delivery_error,delivered_at,direction,principal_id,correlation_id,trace_id,schema_version,priority,classification) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *',(d['message_id'],b.source_system,b.target_system,b.message_type,psycopg.types.json.Jsonb(b.payload),status,created,attempts,code,error,delivered_at,'outbound',str(principal.get('id') or ''),d['correlation_id'],d['trace_id'],d['schema_version'],d['priority'],d['classification'])).fetchone()
