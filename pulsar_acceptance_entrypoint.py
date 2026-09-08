import json, os, urllib.request, urllib.error
from uuid import uuid4
from datetime import datetime, timezone
import entrypoint as base

app = base.app
PULSAR_BASE_URL = os.getenv('PULSAR_BASE_URL','').rstrip('/')

def _run_pulsar_acceptance():
    mid = str(uuid4()); first=None; second=None; status=None; error=None
    try:
        body=json.dumps({'message_id':mid,'source_system':'UNG-NEXUS','target_system':'UNG-PULSAR'}).encode()
        req=lambda: urllib.request.Request(PULSAR_BASE_URL+'/v1/nexus/acceptance',data=body,method='POST',headers={'Content-Type':'application/json','User-Agent':'UNG-NEXUS-cert/1'})
        with urllib.request.urlopen(req(),timeout=8) as r:first=json.loads(r.read().decode())
        with urllib.request.urlopen(req(),timeout=8) as r:second=json.loads(r.read().decode())
        with urllib.request.urlopen(PULSAR_BASE_URL+'/v1/nexus/acceptance/'+mid,timeout=8) as r:status=json.loads(r.read().decode())
        passed=bool(first and first.get('accepted') and not first.get('duplicate') and second and second.get('duplicate') and status and status.get('persisted') and status.get('records')==1)
    except Exception as exc:
        passed=False;error=type(exc).__name__
    if base.nexus.DB:
        try:
            with base.nexus.conn() as c:c.execute('INSERT INTO nexus_acceptance_checks(id,target_system,status,response_code,message_id,error,created_at) VALUES(%s,%s,%s,%s,%s,%s,%s)',(str(uuid4()),'UNG-PULSAR','passed' if passed else 'failed',202 if passed else None,mid,error,datetime.now(timezone.utc)))
        except Exception:pass
    return {'verified':passed,'route':'UNG-NEXUS -> UNG-PULSAR','message_id':mid,'first_delivery':first,'duplicate_replay':second,'pulsar_persistence':status,'error':error}

@app.on_event('startup')
def run_pulsar_acceptance_on_startup():
    if PULSAR_BASE_URL:_run_pulsar_acceptance()

@app.post('/v1/acceptance/pulsar/run')
def run_pulsar_acceptance():return _run_pulsar_acceptance()

@app.get('/v1/acceptance/pulsar')
def pulsar_acceptance_status():
    try:
        with base.nexus.conn() as c:row=c.execute("SELECT target_system,status,response_code,message_id,error,created_at FROM nexus_acceptance_checks WHERE target_system='UNG-PULSAR' ORDER BY created_at DESC LIMIT 1").fetchone()
        return {'verified':bool(row and row.get('status')=='passed'),'route':'UNG-NEXUS -> UNG-PULSAR','check':row}
    except Exception as exc:return {'verified':False,'error':type(exc).__name__}
