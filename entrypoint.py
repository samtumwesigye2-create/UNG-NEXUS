import json
import urllib.error
import urllib.request

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
    if permission not in permissions and 'ung.admin' not in permissions:
        raise HTTPException(403, f'Missing JANUS permission: {permission}')
    return principal


nexus.auth = janus_auth
app = nexus.app
app.include_router(acceptance_router)
