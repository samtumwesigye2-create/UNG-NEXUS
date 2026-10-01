from __future__ import annotations
import hmac, os
from fastapi import Header, HTTPException

TOKEN=os.getenv("MACHINE_MIND_SERVICE_TOKEN","").strip()

def require_service(authorization:str|None=Header(None)):
    if not TOKEN:
        raise HTTPException(503,"machine_mind_service_token_not_configured")
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401,"service bearer token required")
    supplied=authorization.split(" ",1)[1].strip()
    if not hmac.compare_digest(supplied,TOKEN):
        raise HTTPException(403,"invalid service token")
    return {"id":"internal-service","permissions":["machine-mind:read","machine-mind:write"]}
