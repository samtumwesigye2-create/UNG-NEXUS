import os,time,httpx
from fastapi import FastAPI,Header,HTTPException,Request
from models import BridgeMessage,BridgeResult
from policy import allowed
from adapters import AGENCY_ENV,configured,send
from integrity import idempotent,audit,audit_tail,mask
from schema_translate import translate
from resilience import circuit_allow,circuit_success,circuit_failure,circuit_state
from sync import enqueue,queue_status,reconcile,reconciliation_tail

app=FastAPI(title="UNG-GOVBRIDGE",version="1.1.0")
JANUS_BASE_URL=os.getenv("JANUS_BASE_URL","https://ung-iam-production.up.railway.app").rstrip("/")
SHADOW_TARGET=os.getenv("GOVBRIDGE_SHADOW_URL","").rstrip("/")
RATE_LIMIT=int(os.getenv("GOVBRIDGE_RATE_LIMIT_PER_MINUTE","600"))
_rate={}

async def authorize(authorization):
    if not authorization or not authorization.lower().startswith("bearer "):raise HTTPException(401,"janus_bearer_token_required")
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:r=await client.post(JANUS_BASE_URL+"/v1/auth/introspect",headers={"Authorization":authorization,"User-Agent":"UNG-GOVBRIDGE/1.1"})
        if r.status_code in (401,403):raise HTTPException(401,"janus_token_invalid_or_expired")
        if r.status_code>=500:raise HTTPException(503,"janus_authorization_unavailable")
        data=r.json()
    except HTTPException:raise
    except Exception:raise HTTPException(503,"janus_authorization_unavailable")
    principal=data.get("principal") or {};perms=set(principal.get("permissions") or [])
    if "govbridge.access" not in perms and "platform:service" not in perms and "ung.admin" not in perms:raise HTTPException(403,"missing_govbridge_access")
    return principal

def throttle(principal):
    key=str(principal.get("id") or "service");bucket=int(time.time()//60);k=f"{key}:{bucket}";_rate[k]=_rate.get(k,0)+1
    if _rate[k]>RATE_LIMIT:raise HTTPException(429,"govbridge_rate_limit_exceeded")

async def shadow(envelope,authorization):
    if not SHADOW_TARGET:return
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            await client.post(SHADOW_TARGET,json={**envelope,"shadow":True},headers={"Authorization":authorization})
    except Exception:pass

@app.get("/")
def root():return {"service":"UNG-GOVBRIDGE","status":"online","version":"1.1.0","role":"UNG-to-Uganda-government interoperability gateway"}
@app.get("/health")
def health():return {"status":"ok","service":"UNG-GOVBRIDGE","janus":JANUS_BASE_URL,"configured_adapters":[k for k in AGENCY_ENV if configured(k)],"queue":queue_status(),"circuits":circuit_state()}
@app.get("/v1/adapters")
async def adapters(authorization:str|None=Header(None)):
    await authorize(authorization);return [{"agency":k,"configured":configured(k)} for k in AGENCY_ENV]

@app.post("/v1/bridge",response_model=BridgeResult)
async def bridge(message:BridgeMessage,authorization:str|None=Header(None)):
    principal=await authorize(authorization);throttle(principal)
    if not allowed(message.target_system,message.message_type):raise HTTPException(403,"route_not_allowed")
    if not idempotent(message.message_id):
        audit({"action":"duplicate_suppressed","message_id":message.message_id,"target":message.target_system,"principal":principal.get("id")})
        return BridgeResult(message_id=message.message_id,agency=message.target_system,status="duplicate_suppressed")
    try: payload=translate(message.payload)
    except ValueError as e:raise HTTPException(422,str(e))
    envelope={**message.model_dump(),"payload":payload,"bridge":{"system":"UNG-GOVBRIDGE","received_at_epoch":int(time.time()),"principal_id":str(principal.get("id") or "")}}
    audit({"action":"bridge_request","message_id":message.message_id,"source":message.source_system,"target":message.target_system,"type":message.message_type,"principal":principal.get("id"),"payload":mask(payload)})
    enqueue("modern_to_legacy",mask(envelope))
    await shadow(mask(envelope),authorization)
    if not circuit_allow(message.target_system):
        audit({"action":"circuit_open","message_id":message.message_id,"target":message.target_system})
        return BridgeResult(message_id=message.message_id,agency=message.target_system,status="queued_fallback",error="circuit_open")
    ok,code,response,error=await send(message.target_system,envelope)
    if ok:circuit_success(message.target_system)
    else:circuit_failure(message.target_system)
    audit({"action":"bridge_result","message_id":message.message_id,"target":message.target_system,"status":"delivered" if ok else "failed","http_status":code,"error":error})
    return BridgeResult(message_id=message.message_id,agency=message.target_system,status="delivered" if ok else "failed",http_status=code,response=mask(response),error=error)

@app.post("/v1/legacy/inbound",status_code=202)
async def legacy_inbound(message:BridgeMessage,authorization:str|None=Header(None)):
    principal=await authorize(authorization);throttle(principal)
    if not idempotent(message.message_id):return {"accepted":True,"duplicate":True,"message_id":message.message_id}
    env=message.model_dump();enqueue("legacy_to_modern",mask(env));audit({"action":"legacy_sync_inbound","message_id":message.message_id,"source":message.source_system,"target":message.target_system,"principal":principal.get("id")})
    return {"accepted":True,"duplicate":False,"message_id":message.message_id,"sync":"queued"}

@app.post("/v1/reconcile")
async def reconcile_states(body:dict,authorization:str|None=Header(None)):
    await authorize(authorization);return reconcile(body.get("legacy") or {},body.get("modern") or {},str(body.get("key") or "id"))
@app.get("/v1/reconcile")
async def reconciliation(authorization:str|None=Header(None)):await authorize(authorization);return {"results":reconciliation_tail()}
@app.get("/v1/audit")
async def audits(authorization:str|None=Header(None)):await authorize(authorization);return {"results":audit_tail()}
@app.get("/v1/operations")
async def operations(authorization:str|None=Header(None)):await authorize(authorization);return {"queue":queue_status(),"circuits":circuit_state(),"shadow_enabled":bool(SHADOW_TARGET),"rate_limit_per_minute":RATE_LIMIT}

@app.get("/v1/system")
def system():return {"system_id":"UNG-GOVBRIDGE","version":"1.1.0","capabilities":["bi-directional-sync","idempotency","schema-translation","fixed-width-import","csv-import","circuit-breaker","fallback-queue","janus-federated-auth","immutable-hash-chain-audit","pii-masking","api-gateway","rate-limiting","message-buffer","shadow-mirroring","reconciliation","government-adapter-registry","policy-gated-routing","trace-preservation"],"supported_targets":list(AGENCY_ENV)}
