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

@app.on_event('startup')
def register_core_routes():
    routes=[]
    if MIDAS_BASE_URL: routes.append(('UNG-MIDAS',MIDAS_BASE_URL+'/v1/nexus/inbound','UNG-MIDAS'))
    if VECTOR_BASE_URL: routes.append(('UNG-VECTOR',VECTOR_BASE_URL+'/v1/nexus/inbound','UNG-VECTOR'))
    if not routes:return
    with nexus.conn() as c:
        for name,url,system_id in routes:
            c.execute('''INSERT INTO nexus_endpoints(id,name,base_url,system_id,enabled,created_at)
                         VALUES(%s,%s,%s,%s,true,%s)
                         ON CONFLICT(name) DO UPDATE SET base_url=EXCLUDED.base_url,system_id=EXCLUDED.system_id,enabled=true''',
                      (str(uuid4()),name,url,system_id,nexus.utcnow()))
