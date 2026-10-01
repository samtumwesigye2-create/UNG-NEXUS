from __future__ import annotations
import os
from fastapi import HTTPException

PRIVATE_HOST=os.getenv("RAILWAY_PRIVATE_DOMAIN","").strip().lower()

def require_service(authorization:str|None,host:str|None=None):
    host=(host or "").split(":",1)[0].strip().lower()
    if PRIVATE_HOST and host != PRIVATE_HOST:
        raise HTTPException(403,"private service route required")
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401,"service bearer authorization required")
    return {"id":"internal-service","auth_source":"private-network+bearing-credential"}
