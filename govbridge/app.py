import os,time,httpx

@app.on_event("startup")
async def initialize_persistence_on_startup():
    if persistence_configured():
        persistence_init()

from fastapi import FastAPI,Header,HTTPException,Request
from models import BridgeMessage,BridgeResult
from policy import allowed
from adapters import AGENCY_ENV,configured,send
from integrity import idempotent,audit,audit_tail,mask
from schema_translate import translate
from resilience import circuit_allow,circuit_success,circuit_failure,circuit_state
from sync import enqueue,queue_status,reconcile,reconciliation_tail
from governance import sector_for,profile,cross_domain_allowed
from conflict_resolver import resolve as resolve_conflict
from finality import reserve,finalize,status as finality_status
from reconciliation_worker import compare as continuous_compare
from parallel_run import wal_append,wal_status,mark,divergence,divergences,set_authority,authority,set_read_slice,choose_read,acquire,release,lock_state,reconcile_pair
from fanout import fanout
from multispeed import speed_for,stamp,should_apply,enqueue_async,enqueue_batch,queues as speed_queues,policy as speed_policy
from twophase import two_phase
from batch_etl import delta as etl_delta
from failsafe import classify as risk_classify,nonce,burn,burned,dlq_add,dlq,pending,manual_hold,holds
from recovery import replay_one
from compliance import posture as compliance_posture
from zero_trust import enforce as zero_trust_enforce
from compliance_audit import signed_event,export as export_compliance_event
from cutover import state as cutover_state,route as cutover_route,record_failure as cutover_failure,promote as cutover_promote,eligible_for_freeze
from archive import archive_records,query as archive_query,catalog as archive_catalog
from sandbox import create_session,require as require_sandbox,seed as sandbox_seed,reset as sandbox_reset,state as sandbox_state,update as sandbox_update,set_fault,scrub,BANNER
from terminal_emulator import modern_to_terminal,terminal_to_modern
from sandbox_edge import register_node,nodes as edge_nodes,attach as edge_attach,reset_room,record as training_record,analytics as training_analytics
from sandbox_peripherals import emulate as emulate_peripheral
from sandbox_cells import provision as provision_cell,destroy as destroy_cell,stats as cell_stats
from synthetic_weaver import generate as generate_synthetic,templates as scenario_templates
from rollout import set_phase,current as rollout_current
from elastic_ring import configure as ring_configure,telemetry_scale,drain as ring_drain,enqueue as ring_enqueue,admit as ring_admit,status as ring_status
from edge_cache import publish_asset,mount_reference,manifest as cache_manifest
from migration_velocity import plan as velocity_plan
from stress_vault import create as stress_create,update as stress_update,runs as stress_runs
from adaptive_transport import select as transport_select,profile as transport_profile,batch as transport_batch
from training_compliance import record as compliance_record,issue as training_issue,progress as training_progress
from low_bandwidth_vtr import configure as vtr_configure,encode_delta,decode_delta,validate as vtr_validate,reconstitute as vtr_reconstitute
from training_credentials import issue_rs256
from analytics_aggregator import ingest as analytics_ingest,aggregate_hour,dashboard as analytics_dashboard
from civil_registry_mapping import legacy_to_modern as civil_legacy_to_modern,modern_to_legacy as civil_modern_to_legacy
from divergence_playbook import triage as divergence_triage,locked as divergence_locked,diff as divergence_diff,resolve as divergence_resolve,ledger as divergence_ledger
from mainframe_gateway import pack_comarea,health_stub
from jcl_gateway import render as render_jcl
from terminal_gateway import compile_actions
from network_policy import classify as network_classify,enforce as network_enforce,matrix as network_matrix
from hybrid_backbone import configure_path,health as backbone_health,selected as backbone_selected,posture as backbone_posture
from network_spillover import route as spillover_route,items as spillover_items
from persistent_state import init as persistence_init,configured as persistence_configured

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
    sector=sector_for(message.message_type,payload);policy=profile(sector)
    if not cross_domain_allowed(sector,payload):raise HTTPException(403,"approved_cross_domain_guard_required")
    if policy.get("finality"):
        hold=reserve(message.message_id,payload)
        if not hold["created"] and not hold["same_payload"]:raise HTTPException(409,"idempotency_key_payload_conflict")
    envelope={**message.model_dump(),"payload":payload,"bridge":{"system":"UNG-GOVBRIDGE","received_at_epoch":int(time.time()),"principal_id":str(principal.get("id") or ""),"sector":sector,"sector_policy":policy}}
    audit({"action":"bridge_request","message_id":message.message_id,"source":message.source_system,"target":message.target_system,"type":message.message_type,"principal":principal.get("id"),"payload":mask(payload)})
    enqueue("modern_to_legacy",mask(envelope))
    await shadow(mask(envelope),authorization)
    if not circuit_allow(message.target_system):
        audit({"action":"circuit_open","message_id":message.message_id,"target":message.target_system})
        return BridgeResult(message_id=message.message_id,agency=message.target_system,status="queued_fallback",error="circuit_open")
    ok,code,response,error=await send(message.target_system,envelope)
    if ok:circuit_success(message.target_system)
    else:circuit_failure(message.target_system)
    if policy.get("finality"):finalize(message.message_id,"committed" if ok else "pending-retry")
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

@app.post("/v1/conflicts/resolve")
async def conflicts(body:dict,authorization:str|None=Header(None)):
    await authorize(authorization);return resolve_conflict(str(body.get("domain") or ""),body.get("records") or [])
@app.get("/v1/finality/{message_id}")
async def finality(message_id:str,authorization:str|None=Header(None)):
    await authorize(authorization);return finality_status(message_id) or {"message_id":message_id,"state":"not_found"}
@app.post("/v1/reconcile/continuous")
async def reconcile_continuous(body:dict,authorization:str|None=Header(None)):
    await authorize(authorization);return continuous_compare(body.get("legacy") or {},body.get("modern") or {})
@app.get("/v1/governance/sectors")
async def sectors(authorization:str|None=Header(None)):
    await authorize(authorization)
    from governance import SECTOR_PROFILES
    return SECTOR_PROFILES

@app.post("/v1/parallel/write",status_code=202)
async def parallel_write(message:BridgeMessage,authorization:str|None=Header(None)):
    principal=await authorize(authorization);throttle(principal)
    if not idempotent("parallel:"+message.message_id):return {"accepted":True,"duplicate":True,"message_id":message.message_id}
    env=message.model_dump();env["_bridge_order"]={"received_at_ns":time.time_ns(),"clock":"system_utc_ns"}
    wal=wal_append(mask(env))
    results=await fanout(env,authorization)
    mark(message.message_id,"legacy","committed" if results["legacy"].get("ok") else "pending",results["legacy"].get("error"))
    mark(message.message_id,"modern","committed" if results["modern"].get("ok") else "pending",results["modern"].get("error"))
    d=divergence(message.message_id,results["legacy"].get("ok"),results["modern"].get("ok"),"critical")
    audit({"action":"parallel_fanout","message_id":message.message_id,"wal_seq":wal["seq"],"legacy":results["legacy"],"modern":results["modern"],"divergence":bool(d),"principal":principal.get("id")})
    return {"accepted":True,"message_id":message.message_id,"wal_seq":wal["seq"],"fanout":results,"divergence":d}

@app.get("/v1/parallel/wal")
async def parallel_wal(authorization:str|None=Header(None)):await authorize(authorization);return {"results":wal_status()}
@app.get("/v1/parallel/divergence")
async def parallel_divergence(authorization:str|None=Header(None)):await authorize(authorization);return {"results":divergences()}
@app.post("/v1/parallel/reconcile")
async def parallel_reconcile(body:dict,authorization:str|None=Header(None)):
    await authorize(authorization);return reconcile_pair(str(body.get("message_id") or ""),body.get("legacy") or {},body.get("modern") or {},str(body.get("legal_source") or "legacy"))
@app.post("/v1/parallel/authority")
async def parallel_authority(body:dict,authorization:str|None=Header(None)):
    await authorize(authorization);return set_authority(str(body.get("route") or "*"),str(body.get("source") or "legacy"))
@app.post("/v1/parallel/read-slice")
async def parallel_slice(body:dict,authorization:str|None=Header(None)):
    await authorize(authorization);return set_read_slice(str(body.get("route") or "*"),int(body.get("modern_percent") or 0))
@app.get("/v1/parallel/read-route")
async def parallel_read_route(route:str,key:str,authorization:str|None=Header(None)):
    await authorize(authorization);return {"route":route,"key":key,"source":choose_read(route,key),"legal_authority":authority(route)}
@app.post("/v1/parallel/lock")
async def parallel_lock(body:dict,authorization:str|None=Header(None)):
    principal=await authorize(authorization);owner=str(principal.get("id") or "service");key=str(body.get("record_key") or "")
    if not key:raise HTTPException(422,"record_key_required")
    ok=acquire(key,owner,int(body.get("ttl") or 30))
    if not ok:raise HTTPException(409,"record_locked")
    return {"locked":True,"record_key":key,"owner":owner}
@app.delete("/v1/parallel/lock/{record_key}")
async def parallel_unlock(record_key:str,authorization:str|None=Header(None)):
    principal=await authorize(authorization);return {"released":release(record_key,str(principal.get("id") or "service"))}
@app.get("/v1/parallel/status")
async def parallel_status(authorization:str|None=Header(None)):
    await authorize(authorization);return {"wal_records":len(wal_status(1000)),"recent_divergence":divergences(100),"locks":lock_state()}

@app.post("/v1/sync/route",status_code=202)
async def sync_route(message:BridgeMessage,authorization:str|None=Header(None)):
    principal=await authorize(authorization);throttle(principal)
    payload=translate(message.payload);sector=sector_for(message.message_type,payload);speed=speed_for(sector,payload)
    record_key=str(payload.get("_record_key") or message.message_id)
    version=stamp(record_key,message.source_system,speed,payload)
    envelope={**message.model_dump(),"payload":payload,"sync":{"speed":speed,"sector":sector,"version":version}}
    wal_append(mask(envelope))
    if speed=="synchronous":
        result=await two_phase(envelope,authorization)
        audit({"action":"sync_2pc","message_id":message.message_id,"sector":sector,"result":result,"principal":principal.get("id")})
        if not result.get("committed"):raise HTTPException(503,{"sync":"synchronous","result":result})
        return {"accepted":True,"sync":"synchronous","result":result,"version":version}
    if speed=="asynchronous":
        depth=enqueue_async(mask(envelope));audit({"action":"sync_async_queued","message_id":message.message_id,"queue_depth":depth,"sector":sector})
        return {"accepted":True,"sync":"asynchronous","queue_depth":depth,"version":version}
    depth=enqueue_batch(mask(envelope));audit({"action":"sync_batch_queued","message_id":message.message_id,"queue_depth":depth,"sector":sector})
    return {"accepted":True,"sync":"batch","queue_depth":depth,"version":version}

@app.post("/v1/sync/version/check")
async def version_check(body:dict,authorization:str|None=Header(None)):
    await authorize(authorization);ok,reason=should_apply(str(body.get("record_key") or ""),body.get("incoming") or {});return {"apply":ok,"reason":reason}
@app.post("/v1/sync/batch/delta")
async def batch_delta(body:dict,authorization:str|None=Header(None)):
    await authorize(authorization);return etl_delta(str(body.get("dataset") or "default"),body.get("rows") or [])
@app.get("/v1/sync/policy")
async def sync_policy(authorization:str|None=Header(None)):
    await authorize(authorization);return {"routing_policy":speed_policy(),"queues":speed_queues(),"paths":["synchronous","asynchronous","batch"]}

@app.post("/v1/failsafe/execute",status_code=202)
async def failsafe_execute(message:BridgeMessage,authorization:str|None=Header(None)):
    principal=await authorize(authorization);throttle(principal)
    payload=translate(message.payload);sector=sector_for(message.message_type,payload);risk=risk_classify(sector,payload);n=nonce(message.message_id,payload)
    ztok,ztreason=zero_trust_enforce(principal,payload,risk)
    if not ztok:raise HTTPException(403,ztreason)
    if burned(n):raise HTTPException(409,"transaction_nonce_invalidated")
    record_key=str(payload.get("_record_key") or message.message_id);owner=str(principal.get("id") or "service")
    env={**message.model_dump(),"payload":payload,"failsafe":{"sector":sector,**risk,"nonce":n,"received_at_ns":time.time_ns()}}
    if risk["failure"]=="fail-closed":
        if not acquire(record_key,owner,120):raise HTTPException(409,"record_frozen_by_active_transaction")
        result=await two_phase(env,authorization)
        if not result.get("committed"):
            burn(n)
            audit({"action":"fail_closed","message_id":message.message_id,"record_key":record_key,"nonce_invalidated":True,"result":result})
            # Lock intentionally remains until authorized operator resolution.
            raise HTTPException(503,{"failure_mode":"fail-closed","record_frozen":True,"nonce_invalidated":True,"result":result})
        release(record_key,owner)
        return {"accepted":True,"failure_mode":"fail-closed","committed":True,"result":result}
    result=await fanout(env,authorization)
    if result["legacy"].get("ok") and result["modern"].get("ok"):
        return {"accepted":True,"failure_mode":"degrade-gracefully","state":"confirmed","fanout":result}
    item=dlq_add(mask(env),{"legacy":result["legacy"],"modern":result["modern"]})
    audit({"action":"degraded_to_dlq","message_id":message.message_id,"sequence":item["sequence"],"sector":sector})
    return {"accepted":True,"failure_mode":"degrade-gracefully","state":"processing","pending_legacy_confirmation":not result["legacy"].get("ok"),"dlq_sequence":item["sequence"],"fanout":result}

@app.get("/v1/failsafe/dlq")
async def failsafe_dlq(authorization:str|None=Header(None)):await authorize(authorization);return {"results":dlq()}
@app.get("/v1/failsafe/pending/{message_id}")
async def failsafe_pending(message_id:str,authorization:str|None=Header(None)):await authorize(authorization);return pending(message_id) or {"message_id":message_id,"state":"not_pending"}
@app.post("/v1/failsafe/manual-hold")
async def failsafe_hold(body:dict,authorization:str|None=Header(None)):
    await authorize(authorization);return manual_hold(body.get("item") or {},str(body.get("reason") or "operator-review"))
@app.get("/v1/failsafe/manual-hold")
async def failsafe_holds(authorization:str|None=Header(None)):await authorize(authorization);return {"results":holds()}
@app.get("/v1/failsafe/policy")
async def failsafe_policy(authorization:str|None=Header(None)):
    await authorize(authorization)
    from failsafe import TIERS
    return TIERS

@app.get("/v1/compliance/posture")
async def compliance(authorization:str|None=Header(None)):
    await authorize(authorization);return compliance_posture()
@app.post("/v1/compliance/event",status_code=202)
async def compliance_event(body:dict,authorization:str|None=Header(None)):
    principal=await authorize(authorization);event=signed_event({**body,"principal_id":principal.get("id")});await export_compliance_event(event);return {"accepted":True,"digest":event["digest"],"signed":bool(event["signature"])}

@app.get("/v1/cutover/{sector}")
async def get_cutover(sector:str,authorization:str|None=Header(None)):
    await authorize(authorization);return cutover_state(sector)
@app.get("/v1/cutover/{sector}/route")
async def get_cutover_route(sector:str,key:str,authorization:str|None=Header(None)):
    await authorize(authorization);return {"sector":sector,"key":key,"read_from":cutover_route(sector,key),**cutover_state(sector)}
@app.post("/v1/cutover/{sector}/promote")
async def promote_cutover(sector:str,body:dict,authorization:str|None=Header(None)):
    principal=await authorize(authorization)
    try:s=cutover_promote(sector,str(body.get("phase") or "shadow"),body.get("modern_percent"))
    except ValueError as ex:raise HTTPException(422,str(ex))
    audit({"action":"cutover_promotion","sector":sector,"state":s,"principal":principal.get("id")});return s
@app.post("/v1/cutover/{sector}/failure")
async def fail_cutover(sector:str,body:dict,authorization:str|None=Header(None)):
    await authorize(authorization);return cutover_failure(sector,str(body.get("reason") or "unspecified"))
@app.get("/v1/cutover/{sector}/freeze-eligibility")
async def freeze_eligibility(sector:str,days:int=30,authorization:str|None=Header(None)):
    await authorize(authorization);return {"sector":sector,"eligible":eligible_for_freeze(sector,days),"required_stability_days":days,**cutover_state(sector)}

@app.post("/v1/archive/{sector}",status_code=201)
async def create_archive(sector:str,body:dict,authorization:str|None=Header(None)):
    principal=await authorize(authorization);result=archive_records(sector,body.get("records") or []);audit({"action":"legacy_archive_created","sector":sector,"archive":result,"principal":principal.get("id")});return result
@app.post("/v1/archive/{sector}/query")
async def query_archive(sector:str,body:dict,authorization:str|None=Header(None)):
    await authorize(authorization);return {"sector":sector,"results":archive_query(sector,body.get("where") or {})}
@app.get("/v1/archive")
async def list_archives(authorization:str|None=Header(None)):await authorize(authorization);return {"archives":archive_catalog()}

@app.post("/v1/sandbox/session",status_code=201)
async def sandbox_session(body:dict,authorization:str|None=Header(None)):
    p=await authorize(authorization);return create_session(str(p.get("id") or "service"),str(body.get("scenario") or "default"))
def _sandbox_guard(sid,p):
    if not require_sandbox(sid,str(p.get("id") or "service")):raise HTTPException(403,"invalid_sandbox_session")
@app.post("/v1/sandbox/seed")
async def sandbox_seed_data(body:dict,authorization:str|None=Header(None)):
    await authorize(authorization);records=scrub(body.get("records") or []);return sandbox_seed(str(body.get("scenario") or "default"),records)
@app.post("/v1/sandbox/{sid}/reset")
async def sandbox_reset_state(sid:str,authorization:str|None=Header(None)):
    p=await authorize(authorization);_sandbox_guard(sid,p);return {"banner":BANNER,"state":sandbox_reset(sid)}
@app.get("/v1/sandbox/{sid}/state")
async def sandbox_get_state(sid:str,authorization:str|None=Header(None)):
    p=await authorize(authorization);_sandbox_guard(sid,p);return {"banner":BANNER,"state":sandbox_state(sid)}
@app.post("/v1/sandbox/{sid}/modern-action")
async def sandbox_modern(sid:str,body:dict,authorization:str|None=Header(None)):
    p=await authorize(authorization);_sandbox_guard(sid,p);fields=body.get("fields") or {};mapping=body.get("mapping") or {}
    for k,v in fields.items():sandbox_update(sid,k,v)
    return {"banner":BANNER,"modern":sandbox_state(sid),"legacy_screen":modern_to_terminal(fields,mapping)}
@app.post("/v1/sandbox/{sid}/legacy-action")
async def sandbox_legacy(sid:str,body:dict,authorization:str|None=Header(None)):
    p=await authorize(authorization);_sandbox_guard(sid,p);fields=terminal_to_modern(body.get("buffer") or {},body.get("mapping") or {})
    for k,v in fields.items():sandbox_update(sid,k,v)
    return {"banner":BANNER,"modern_fields":fields,"state":sandbox_state(sid)}
@app.post("/v1/sandbox/{sid}/simulate")
async def sandbox_simulate(sid:str,body:dict,authorization:str|None=Header(None)):
    p=await authorize(authorization);_sandbox_guard(sid,p);return {"banner":BANNER,"simulation":set_fault(sid,body.get("delay_seconds") or 0,body.get("failure"))}

@app.post("/v1/sandbox/edge/node",status_code=201)
async def sandbox_edge_node(body:dict,authorization:str|None=Header(None)):
    await authorize(authorization);return register_node(str(body.get("name") or "training-edge"),str(body.get("site") or "unspecified"),body.get("capabilities") or [])
@app.get("/v1/sandbox/edge/nodes")
async def sandbox_edge_nodes(authorization:str|None=Header(None)):await authorize(authorization);return {"nodes":edge_nodes()}
@app.post("/v1/sandbox/{sid}/room/{room_id}")
async def sandbox_room_attach(sid:str,room_id:str,authorization:str|None=Header(None)):
    p=await authorize(authorization);_sandbox_guard(sid,p);return edge_attach(room_id,sid,str(p.get("id") or "service"))
@app.post("/v1/sandbox/room/{room_id}/reset")
async def sandbox_room_reset(room_id:str,authorization:str|None=Header(None)):
    await authorize(authorization);r=reset_room(room_id);return {"room":r,"reset_scope":"room","synthetic_only":True}
@app.post("/v1/sandbox/{sid}/peripheral")
async def sandbox_peripheral(sid:str,body:dict,authorization:str|None=Header(None)):
    p=await authorize(authorization);_sandbox_guard(sid,p)
    try:return emulate_peripheral(str(body.get("kind") or ""),body.get("payload") or {})
    except ValueError as ex:raise HTTPException(422,str(ex))
@app.post("/v1/sandbox/{sid}/telemetry",status_code=202)
async def sandbox_telemetry(sid:str,body:dict,authorization:str|None=Header(None)):
    p=await authorize(authorization);_sandbox_guard(sid,p);return training_record({**body,"session_id":sid,"principal_id":p.get("id")})
@app.get("/v1/sandbox/analytics")
async def sandbox_analytics(authorization:str|None=Header(None)):await authorize(authorization);return training_analytics()
@app.get("/v1/sandbox/portal/config")
async def sandbox_portal_config(authorization:str|None=Header(None)):
    await authorize(authorization);return {"access":"zero-trust-authenticated","workspace":"sandbox-only","terminal_rendering":"html5-emulator-ready","production_routes_exposed":False,"banner":BANNER}

@app.post("/v1/sandbox/cell/{sid}",status_code=201)
async def sandbox_cell_create(sid:str,body:dict,authorization:str|None=Header(None)):
    p=await authorize(authorization);_sandbox_guard(sid,p);return provision_cell(sid,str(p.get("id") or "service"),body.get("region"),int(body.get("ttl") or 7200))
@app.delete("/v1/sandbox/cell/{cell_id}")
async def sandbox_cell_delete(cell_id:str,authorization:str|None=Header(None)):
    await authorize(authorization);return destroy_cell(cell_id)
@app.get("/v1/sandbox/cells")
async def sandbox_cells(authorization:str|None=Header(None)):await authorize(authorization);return cell_stats()
@app.get("/v1/sandbox/synthetic")
async def sandbox_synthetic(count:int=100,offset:int=0,region:str="central",authorization:str|None=Header(None)):
    await authorize(authorization);return {"synthetic":True,"offset":offset,"count":min(count,10000),"records":generate_synthetic(count,offset,region)}
@app.get("/v1/sandbox/scenarios")
async def sandbox_scenarios(authorization:str|None=Header(None)):await authorize(authorization);return scenario_templates()
@app.get("/v1/sandbox/rollout")
async def sandbox_rollout(authorization:str|None=Header(None)):await authorize(authorization);return rollout_current()
@app.post("/v1/sandbox/rollout")
async def sandbox_rollout_set(body:dict,authorization:str|None=Header(None)):
    await authorize(authorization)
    try:return set_phase(int(body.get("phase") or 1))
    except ValueError as ex:raise HTTPException(422,str(ex))

@app.post("/v1/sandbox/ring/{region}/configure")
async def ring_cfg(region:str,body:dict,authorization:str|None=Header(None)):
    await authorize(authorization);return ring_configure(region,str(body.get("timezone") or "UTC"),int(body.get("work_start") or 8),int(body.get("work_end") or 17),int(body.get("min_capacity") or 10),int(body.get("max_capacity") or 1000),int(body.get("warmup_minutes") or 30))
@app.post("/v1/sandbox/ring/{region}/scale")
async def ring_scale(region:str,body:dict,authorization:str|None=Header(None)):
    await authorize(authorization);return telemetry_scale(region,int(body.get("active_sessions") or 0),float(body.get("p95_reflection_ms") or 0),int(body.get("queue_depth") or 0))
@app.post("/v1/sandbox/ring/{region}/drain")
async def ring_drain_api(region:str,authorization:str|None=Header(None)):await authorize(authorization);return ring_drain(region)
@app.post("/v1/sandbox/waiting-room")
async def waiting_room(body:dict,authorization:str|None=Header(None)):
    p=await authorize(authorization);return ring_enqueue(str(p.get("id") or "service"),str(body.get("region") or "central"))
@app.post("/v1/sandbox/waiting-room/admit")
async def waiting_admit(body:dict,authorization:str|None=Header(None)):await authorize(authorization);return {"admitted":ring_admit(int(body.get("limit") or 100))}
@app.get("/v1/sandbox/ring")
async def ring_get(authorization:str|None=Header(None)):await authorize(authorization);return ring_status()
@app.post("/v1/sandbox/cache/{region}/asset")
async def cache_asset(region:str,body:dict,authorization:str|None=Header(None)):await authorize(authorization);return publish_asset(region,str(body["key"]),str(body["digest"]))
@app.post("/v1/sandbox/cache/reference")
async def cache_reference(body:dict,authorization:str|None=Header(None)):await authorize(authorization);return mount_reference(str(body["name"]),str(body["version"]),str(body["digest"]))
@app.get("/v1/sandbox/cache/{region}")
async def cache_get(region:str,authorization:str|None=Header(None)):await authorize(authorization);return cache_manifest(region)
@app.get("/v1/sandbox/migration-velocity")
async def migration_velocity(authorization:str|None=Header(None)):await authorize(authorization);return velocity_plan()
@app.post("/v1/sandbox/stress-vault",status_code=201)
async def stress_new(body:dict,authorization:str|None=Header(None)):await authorize(authorization);return stress_create(int(body.get("target_concurrency") or 500000),str(body.get("scenario") or "mixed-failure"))
@app.get("/v1/sandbox/stress-vault")
async def stress_list(authorization:str|None=Header(None)):await authorize(authorization);return {"runs":stress_runs()}

@app.post("/v1/sandbox/{sid}/transport/probe")
async def transport_probe(sid:str,body:dict,authorization:str|None=Header(None)):
    p=await authorize(authorization);_sandbox_guard(sid,p);return transport_select(sid,body.get("mbps"),body.get("rtt_ms"))
@app.get("/v1/sandbox/{sid}/transport")
async def transport_get(sid:str,authorization:str|None=Header(None)):
    p=await authorize(authorization);_sandbox_guard(sid,p);return transport_profile(sid) or {"mode":"probe-required"}
@app.post("/v1/sandbox/{sid}/transport/batch")
async def transport_submit_batch(sid:str,body:dict,authorization:str|None=Header(None)):
    p=await authorize(authorization);_sandbox_guard(sid,p);return transport_batch(body.get("changes") or [])
@app.post("/v1/sandbox/{sid}/training/progress")
async def training_progress_record(sid:str,body:dict,authorization:str|None=Header(None)):
    p=await authorize(authorization);_sandbox_guard(sid,p);return compliance_record(str(p.get("id")),str(body["module"]),bool(body.get("completed")),int(body.get("errors") or 0),bool(body.get("state_verified")))
@app.get("/v1/sandbox/training/progress")
async def training_progress_get(authorization:str|None=Header(None)):
    p=await authorize(authorization);return {"progress":training_progress(str(p.get("id")))}
@app.post("/v1/sandbox/training/credential")
async def training_credential(body:dict,authorization:str|None=Header(None)):
    p=await authorize(authorization)
    try:return training_issue(str(p.get("id")),body.get("modules") or [],int(body.get("ttl") or 2592000))
    except ValueError as ex:raise HTTPException(403,str(ex))
    except RuntimeError as ex:raise HTTPException(503,str(ex))

@app.post("/v1/sandbox/{sid}/vtr/configure")
async def vtr_cfg(sid:str,body:dict,authorization:str|None=Header(None)):
    p=await authorize(authorization);_sandbox_guard(sid,p);return vtr_configure(sid,float(body.get("target_kbps") or 15))
@app.post("/v1/sandbox/{sid}/vtr/validate")
async def vtr_check(sid:str,body:dict,authorization:str|None=Header(None)):
    p=await authorize(authorization);_sandbox_guard(sid,p);return vtr_validate(body.get("fields") or {},body.get("rules") or {})
@app.post("/v1/sandbox/{sid}/vtr/encode")
async def vtr_enc(sid:str,body:dict,authorization:str|None=Header(None)):
    p=await authorize(authorization);_sandbox_guard(sid,p);return encode_delta(body.get("fields") or {})
@app.post("/v1/sandbox/{sid}/vtr/reconstitute")
async def vtr_rec(sid:str,body:dict,authorization:str|None=Header(None)):
    p=await authorize(authorization);_sandbox_guard(sid,p);fields=decode_delta(str(body["payload"]));return vtr_reconstitute(fields,body.get("mapping") or {})
@app.post("/v1/sandbox/training/credential/rs256")
async def training_credential_rs256(body:dict,authorization:str|None=Header(None)):
    p=await authorize(authorization);principal=str(p.get("id"))
    modules=body.get("modules") or []
    try:
        # Reuse deterministic completion gate before asymmetric credential issuance.
        training_issue(principal,modules,60)
    except ValueError as ex:raise HTTPException(403,str(ex))
    except RuntimeError:
        # Legacy HMAC issuer may be unconfigured; eligibility was already checked above.
        pass
    metrics=body.get("compliance_metrics") or {}
    if metrics.get("proctor_evaluation",{}).get("status")!="VERIFIED_COMPETENT":raise HTTPException(403,"verified_competence_required")
    if int(metrics.get("proctor_evaluation",{}).get("catastrophic_error_count",1))!=0:raise HTTPException(403,"catastrophic_errors_present")
    try:return issue_rs256(principal,body.get("identity_context") or {},metrics,body.get("production_entitlements") or {},modules,int(body.get("ttl") or 2592000))
    except RuntimeError as ex:raise HTTPException(503,str(ex))
@app.post("/v1/sandbox/analytics/event",status_code=202)
async def sandbox_analytics_event(body:dict,authorization:str|None=Header(None)):
    p=await authorize(authorization);return analytics_ingest({**body,"principal_id":p.get("id")})
@app.post("/v1/sandbox/analytics/hourly")
async def sandbox_analytics_hourly(body:dict,authorization:str|None=Header(None)):
    await authorize(authorization);return aggregate_hour(body.get("hour"))
@app.get("/v1/sandbox/analytics/dashboard")
async def sandbox_analytics_dashboard(persona:str,scope:str|None=None,authorization:str|None=Header(None)):
    await authorize(authorization);return analytics_dashboard(persona,scope)

@app.post("/v1/translation/civil/legacy-to-modern")
async def civil_translate_in(body:dict,authorization:str|None=Header(None)):
    await authorize(authorization)
    try:return civil_legacy_to_modern(bytes.fromhex(str(body["ebcdic_hex"])))
    except (ValueError,UnicodeError) as ex:raise HTTPException(422,str(ex))
@app.post("/v1/translation/civil/modern-to-legacy")
async def civil_translate_out(body:dict,authorization:str|None=Header(None)):
    await authorize(authorization);raw=civil_modern_to_legacy(body);return {"encoding":"cp500","row_length":len(raw),"ebcdic_hex":raw.hex()}
@app.post("/v1/divergence/triage")
async def divergence_triage_api(body:dict,authorization:str|None=Header(None)):
    await authorize(authorization);return divergence_triage(str(body["entity_id"]),body.get("legacy") or {},body.get("modern") or {},body.get("field"))
@app.get("/v1/divergence/{entity_id}/lock")
async def divergence_lock_status(entity_id:str,authorization:str|None=Header(None)):
    await authorize(authorization);return {"entity_id":entity_id,"locked":divergence_locked(entity_id)}
@app.get("/v1/divergence/{entity_id}/diff")
async def divergence_diff_api(entity_id:str,authorization:str|None=Header(None)):
    await authorize(authorization);d=divergence_diff(entity_id)
    if d is None:raise HTTPException(404,"entity_not_on_hold")
    return d
@app.post("/v1/divergence/{entity_id}/resolve")
async def divergence_resolve_api(entity_id:str,body:dict,authorization:str|None=Header(None)):
    p=await authorize(authorization)
    try:return divergence_resolve(entity_id,str(body["direction"]),str(p.get("id")),str(body.get("authority_reference") or ""))
    except ValueError as ex:raise HTTPException(422,str(ex))
@app.get("/v1/divergence/ledger/events")
async def divergence_events(authorization:str|None=Header(None)):await authorize(authorization);return {"events":divergence_ledger()}

@app.post("/api/v1/bridge/mainframe/cics/transaction")
async def mainframe_cics(body:dict,authorization:str|None=Header(None),x_gov_criticality_tier:str|None=Header(None)):
    p=await authorize(authorization)
    if x_gov_criticality_tier!="TIER_1_ATOMIC":raise HTTPException(400,"tier1_atomic_required")
    try:buf=pack_comarea(body)
    except (ValueError,UnicodeError) as ex:raise HTTPException(422,str(ex))
    audit({"action":"mainframe_comarea_compiled","correlation_id":body.get("correlation_id"),"principal":p.get("id"),"bytes":len(buf)})
    return {"state":"compiled-not-submitted","encoding":"cp500","length":len(buf),"comarea_hex":buf.hex(),"connector_required":True}
@app.put("/api/v1/bridge/mainframe/jes/job-submit")
async def mainframe_jes(body:dict,authorization:str|None=Header(None),x_gov_bridge_job_class:str|None=Header(None)):
    p=await authorize(authorization)
    try:jcl=render_jcl(body,x_gov_bridge_job_class or "A")
    except ValueError as ex:raise HTTPException(422,str(ex))
    audit({"action":"mainframe_jcl_rendered","job":body.get("job_name"),"principal":p.get("id")})
    return {"state":"rendered-not-submitted","jcl":jcl,"connector_required":True}
@app.get("/api/v1/bridge/mainframe/health/ping")
async def mainframe_health(authorization:str|None=Header(None)):
    await authorize(authorization);return health_stub()
@app.post("/api/v1/bridge/mainframe/terminal/screen-action")
async def mainframe_terminal(body:dict,authorization:str|None=Header(None)):
    p=await authorize(authorization)
    try:compiled=compile_actions(body)
    except ValueError as ex:raise HTTPException(422,str(ex))
    audit({"action":"terminal_macro_compiled","screen":compiled["target_screen_id"],"principal":p.get("id"),"action_count":len(compiled["actions"])})
    return {**compiled,"state":"compiled-not-executed","emulator_or_connector_required":True}

@app.get("/v1/network/segments")
async def network_segments(authorization:str|None=Header(None)):await authorize(authorization);return network_matrix()
@app.post("/v1/network/segments/enforce")
async def network_segment_enforce(body:dict,authorization:str|None=Header(None)):
    await authorize(authorization);seg=str(body.get("segment") or network_classify(body.get("envelope") or {}))
    try:return network_enforce(seg,str(body.get("target") or ""))
    except PermissionError as ex:raise HTTPException(403,str(ex))
    except ValueError as ex:raise HTTPException(422,str(ex))
@app.post("/v1/network/backbone/path")
async def backbone_path(body:dict,authorization:str|None=Header(None)):
    await authorize(authorization)
    try:return configure_path(str(body["name"]),str(body["kind"]),int(body.get("priority") or 100),bool(body.get("private",True)))
    except ValueError as ex:raise HTTPException(422,str(ex))
@app.post("/v1/network/backbone/path/{name}/health")
async def backbone_path_health(name:str,body:dict,authorization:str|None=Header(None)):
    await authorize(authorization)
    try:return backbone_health(name,str(body.get("state") or "unknown"),body.get("latency_ms"))
    except KeyError:raise HTTPException(404,"backbone_path_not_found")
@app.get("/v1/network/backbone")
async def backbone_get(authorization:str|None=Header(None)):
    await authorize(authorization);return {"selected":backbone_selected(),"security_posture":backbone_posture()}
@app.post("/v1/network/spillover")
async def network_spillover(body:dict,authorization:str|None=Header(None)):
    await authorize(authorization);env=body.get("envelope") or {};seg=str(body.get("segment") or network_classify(env));return spillover_route(seg,env,bool(body.get("backbone_available")))
@app.get("/v1/network/spillover")
async def network_spillover_get(authorization:str|None=Header(None)):await authorize(authorization);return {"items":spillover_items()}

@app.post("/v1/persistence/initialize")
async def persistence_initialize(authorization:str|None=Header(None)):
    await authorize(authorization)
    try:return persistence_init()
    except Exception as ex:raise HTTPException(503,f"persistence_init_failed:{type(ex).__name__}")
@app.get("/v1/persistence/status")
async def persistence_status(authorization:str|None=Header(None)):
    await authorize(authorization);return {"postgres_configured":persistence_configured()}

@app.get("/v1/system")
def system():return {"system_id":"UNG-GOVBRIDGE","version":"1.1.0","capabilities":["postgres-persistence-foundation","durable-spillover-when-database-configured","hybrid-private-backbone-policy","network-microsegmentation","sandbox-production-route-deny","tier1-network-fail-closed","async-network-spillover","private-path-health-selection","hsm-and-fips-posture-hooks","pqc-profile-hook","mainframe-api-facade","cics-comarea-cp500-compiler","allowlisted-jcl-template-renderer","mainframe-health-contract","guarded-terminal-macro-compiler","civil-registry-fixed-width-mapping","cp500-ebcdic-bidirectional-translation","registry-postgres-schema","data-divergence-playbook","tier1-record-lock","manual-hold-diff","authority-referenced-force-resolution","text-driven-sync-mesh","virtual-terminal-reconstitution","differential-sync-payloads","local-validation-contract","rs256-training-credentials","hourly-analytics-aggregation","persona-scoped-training-dashboards","adaptive-transport-fabric","bandwidth-probed-stream-selection","headless-low-bandwidth-terminal","batched-low-bandwidth-sync","training-state-verification","zero-error-training-gate","signed-training-credential","iam-training-gate-ready","dynamic-elastic-ring","scheduled-capacity-ring","telemetry-driven-scaling","graceful-cluster-draining","branded-waiting-room-api","regional-edge-cache-manifest","read-only-reference-shards","migration-velocity-plan","synthetic-stress-test-vault","hyperscale-cellular-sandbox","ephemeral-session-cells","regional-session-sharding","automatic-cell-expiration","paged-algorithmic-synthetic-data","scenario-template-engine","three-phase-training-rollout","unified-sandbox-edge","on-prem-training-node-registry","cloud-sandbox-portal","sandbox-only-ztna-context","dummy-peripheral-emulation","room-and-session-reset","training-performance-analytics","isolated-dual-ui-training-sandbox","synthetic-data-scrubbing","sandbox-session-routing","persistent-context-banner","legacy-terminal-emulator","modern-terminal-field-mapping","instant-sandbox-reset","delay-and-failure-simulation","traffic-cutover-framework","shadow-to-live-promotion","deterministic-canary-routing","sector-read-write-cutover","legacy-read-only-freeze","reverse-sync-ready","stability-window-gating","historical-archive-facade","federal-control-target-framework","zero-trust-policy-enforcement-point","per-request-device-posture","high-assurance-tier1-auth","sector-microsegmentation","external-hsm-interface","worm-audit-export","siem-conmon-export","adaptive-fail-safe-circuit","risk-classification-engine","fail-closed-tier","degrade-gracefully-tier","nonce-invalidation","durable-dlq","pending-legacy-confirmation","manual-hold-vault","three-speed-sync-engine","metadata-driven-sync-routing","two-phase-commit","atomic-prepare-rollback","near-real-time-stream-buffer","batch-delta-etl","vector-clock-versioning","global-epoch-ordering","last-write-wins-speed-override","cross-speed-reconciliation","parallel-run-migration","dual-write-fanout","write-ahead-log","independent-multi-commit","read-slicing","source-of-truth-toggle","distributed-record-locking","nanosecond-ordering","divergence-alerting","replay-ready-wal","distributed-integration-fabric","unified-governance-gateway","dynamic-sector-routing","bi-directional-sync","strict-transaction-finality","idempotency","schema-translation","fixed-width-import","ebcdic-import","csv-import","circuit-breaker","fallback-queue","janus-federated-auth","immutable-hash-chain-audit","pii-masking","api-gateway","rate-limiting","message-buffer","shadow-mirroring","continuous-hash-reconciliation","authoritative-source-conflict-resolution","cross-domain-guard-enforcement","sector-policy-profiles","reconciliation","government-adapter-registry","policy-gated-routing","trace-preservation"],"supported_targets":list(AGENCY_ENV)}
