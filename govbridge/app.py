import os, time, httpx
from fastapi import FastAPI, Header, HTTPException
from models import BridgeMessage, BridgeResult
from policy import allowed
from adapters import AGENCY_ENV, configured, send

app = FastAPI(title="UNG-GOVBRIDGE", version="1.0.0")
JANUS_BASE_URL = os.getenv("JANUS_BASE_URL","https://ung-iam-production.up.railway.app").rstrip("/")

async def authorize(authorization: str | None):
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "janus_bearer_token_required")
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.post(
                JANUS_BASE_URL + "/v1/auth/introspect",
                headers={"Authorization": authorization, "User-Agent":"UNG-GOVBRIDGE/1.0"},
            )
        if r.status_code in (401,403):
            raise HTTPException(401, "janus_token_invalid_or_expired")
        if r.status_code >= 500:
            raise HTTPException(503, "janus_authorization_unavailable")
        data = r.json()
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(503, "janus_authorization_unavailable")
    principal = data.get("principal") or {}
    perms = set(principal.get("permissions") or [])
    if "govbridge.access" not in perms and "platform:service" not in perms and "ung.admin" not in perms:
        raise HTTPException(403, "missing_govbridge_access")
    return principal

@app.get("/")
def root():
    return {"service":"UNG-GOVBRIDGE","status":"online","version":"1.0.0","role":"UNG-to-Uganda-government interoperability gateway"}

@app.get("/health")
def health():
    return {
        "status":"ok",
        "service":"UNG-GOVBRIDGE",
        "janus":JANUS_BASE_URL,
        "configured_adapters":[k for k in AGENCY_ENV if configured(k)],
    }

@app.get("/v1/adapters")
async def adapters(authorization: str | None = Header(None)):
    await authorize(authorization)
    return [{"agency":k,"configured":configured(k)} for k in AGENCY_ENV]

@app.post("/v1/bridge", response_model=BridgeResult)
async def bridge(message: BridgeMessage, authorization: str | None = Header(None)):
    principal = await authorize(authorization)
    if not allowed(message.target_system, message.message_type):
        raise HTTPException(403, "route_not_allowed")
    envelope = message.model_dump()
    envelope["bridge"] = {
        "system":"UNG-GOVBRIDGE",
        "received_at_epoch":int(time.time()),
        "principal_id":str(principal.get("id") or ""),
    }
    ok, code, response, error = await send(message.target_system, envelope)
    return BridgeResult(
        message_id=message.message_id,
        agency=message.target_system,
        status="delivered" if ok else "failed",
        http_status=code,
        response=response,
        error=error,
    )

@app.get("/v1/system")
def system():
    return {
        "system_id":"UNG-GOVBRIDGE",
        "capabilities":[
            "government-adapter-registry","policy-gated-routing","canonical-envelope",
            "janus-federated-auth","protocol-edge","trace-preservation","health-reporting"
        ],
        "supported_targets":list(AGENCY_ENV.keys())
    }
