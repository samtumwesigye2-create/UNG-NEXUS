import json
import os
import urllib.error
import urllib.request
from uuid import uuid4

from fastapi import HTTPException

import app as nexus
from acceptance_view import router as acceptance_router


def janus_auth(permission, authorization):
    if not authorization or not authorization.lower().startswith('bearer '):
        raise HTTPException(401, 'JANUS bearer token required')
    req = urllib.request.Request(
        nexus.JANUS_BASE_URL + '/v1/auth/introspect',
        data=b'',
        method='POST',
        headers={'Authorization': authorization},
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            raise HTTPException(401, 'JANUS token invalid or expired')
        raise HTTPException(503, 'JANUS authorization unavailable')
    except Exception:
        raise HTTPException(503, 'JANUS authorization unavailable')

    principal = data.get('principal') or {}
    permissions = set(principal.get('permissions') or [])
    if permission not in permissions and 'ung.admin' not in permissions and 'platform:service' not in permissions:
        raise HTTPException(403, f'Missing JANUS permission: {permission}')
    return principal


nexus.auth = janus_auth
app = nexus.app
app.include_router(acceptance_router)

MIDAS_BASE_URL=os.getenv('MIDAS_BASE_URL','').rstrip('/')
VECTOR_BASE_URL=os.getenv('VECTOR_BASE_URL','').rstrip('/')
MACHINE_MIND_BASE_URL=os.getenv('MACHINE_MIND_BASE_URL','').rstrip('/')

def run_machine_mind_acceptance_probe():
    if not MACHINE_MIND_BASE_URL:
        return
    payload = {
        "source_system": "UNG-NEXUS",
        "target_system": "MACHINE-MIND",
        "message_type": "system.health",
        "payload": {"status": "acceptance-test", "source": "UNG-NEXUS"},
    }
    code = None
    status = "failed"
    error = None
    try:
        req = urllib.request.Request(
            MACHINE_MIND_BASE_URL + "/v1/nexus/inbound",
            data=json.dumps(payload).encode(),
            method="POST",
            headers={"Content-Type": "application/json", "User-Agent": "UNG-NEXUS/acceptance"},
        )
        with urllib.request.urlopen(req, timeout=8) as response:
            code = int(response.status)
            body = json.loads(response.read().decode() or "{}")
            status = "passed" if 200 <= code < 300 and body.get("accepted") else "failed"
    except urllib.error.HTTPError as exc:
        code = int(exc.code)
        error = f"http_{exc.code}"
    except Exception as exc:
        error = type(exc).__name__
    print(f"MACHINE_MIND_ACCEPTANCE status={status} code={code} error={error}")
    try:
        with nexus.conn() as db:
            db.execute(
                "INSERT INTO nexus_acceptance_checks(id,target_system,status,response_code,message_id,error,created_at) VALUES(%s,%s,%s,%s,%s,%s,%s)",
                (str(uuid4()), "MACHINE-MIND", status, code, None, error, nexus.utcnow()),
            )
    except Exception:
        pass


@app.on_event('startup')
def register_core_routes():
    routes=[]
    if MIDAS_BASE_URL: routes.append(('UNG-MIDAS',MIDAS_BASE_URL+'/v1/nexus/inbound','UNG-MIDAS'))
    if VECTOR_BASE_URL: routes.append(('UNG-VECTOR',VECTOR_BASE_URL+'/v1/nexus/inbound','UNG-VECTOR'))
    if MACHINE_MIND_BASE_URL: routes.append(('MACHINE-MIND',MACHINE_MIND_BASE_URL+'/v1/nexus/inbound','MACHINE-MIND'))
    if not routes:return
    with nexus.conn() as c:
        for name,url,system_id in routes:
            c.execute('''INSERT INTO nexus_endpoints(id,name,base_url,system_id,enabled,created_at)
                         VALUES(%s,%s,%s,%s,true,%s)
                         ON CONFLICT(name) DO UPDATE SET base_url=EXCLUDED.base_url,system_id=EXCLUDED.system_id,enabled=true''',
                      (str(uuid4()),name,url,system_id,nexus.utcnow()))
    run_machine_mind_acceptance_probe()
