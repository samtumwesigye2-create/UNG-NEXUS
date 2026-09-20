import os, time
from fastapi import FastAPI, Header, HTTPException
from models import BridgeMessage, BridgeResult
from policy import allowed
from adapters import AGENCY_ENV, configured, send

app = FastAPI(title="UNG-GOVBRIDGE", version="1.0.0")
BRIDGE_TOKEN = os.getenv("UNG_GOVBRIDGE_TOKEN","").strip()

def authorize(authorization: str | None):
    if not BRIDGE_TOKEN:
        raise HTTPException(503, "bridge_service_token_not_configured")
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "bearer_token_required")
    if authorization.split(" ",1)[1].strip() != BRIDGE_TOKEN:
        raise HTTPException(401, "invalid_service_token")

@app.get("/")
def root():
    return {"service":"UNG-GOVBRIDGE","status":"online","version":"1.0.0","role":"UNG-to-Uganda-government interoperability gateway"}

@app.get("/health")
def health():
    return {"status":"ok","service":"UNG-GOVBRIDGE","configured_adapters":[k for k in AGENCY_ENV if configured(k)]}

@app.get("/v1/adapters")
def adapters(authorization: str | None = Header(None)):
    authorize(authorization)
    return [{"agency":k,"configured":configured(k)} for k in AGENCY_ENV]

@app.post("/v1/bridge", response_model=BridgeResult)
async def bridge(message: BridgeMessage, authorization: str | None = Header(None)):
    authorize(authorization)
    if not allowed(message.target_system, message.message_type):
        raise HTTPException(403, "route_not_allowed")
    envelope = message.model_dump()
    envelope["bridge"] = {"system":"UNG-GOVBRIDGE","received_at_epoch":int(time.time())}
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
            "bearer-service-auth","protocol-edge","trace-preservation","health-reporting"
        ],
        "supported_targets":list(AGENCY_ENV.keys())
    }
