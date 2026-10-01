from __future__ import annotations

import threading
import time
import uuid
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

import lab
import storage
import worker
from runtime import MachineMindRuntime
from security import require_service

app=FastAPI(title="Machine Mind",version="2.0.0")
mind=MachineMindRuntime()
_ingest_lock=threading.RLock()

class NexusEnvelope(BaseModel):
    source_system:str
    target_system:str="MACHINE-MIND"
    message_type:str
    payload:dict[str,Any]=Field(default_factory=dict)
    message_id:str|None=None
    correlation_id:str|None=None
    trace_id:str|None=None
    schema_version:str="1.0"
    priority:int=50
    classification:str="internal"

class EventIn(BaseModel):
    event_type:str
    source_system:str
    payload:dict[str,Any]=Field(default_factory=dict)
    confidence:Optional[float]=None
    correlation_id:Optional[str]=None

class RecallIn(BaseModel):
    subject:str
    payload:dict[str,Any]=Field(default_factory=dict)
    limit:int=12

class SensorRegistration(BaseModel):
    sensor_id:str
    kind:str
    metadata:dict[str,Any]=Field(default_factory=dict)

class ActuatorRegistration(BaseModel):
    actuator_id:str
    kind:str
    metadata:dict[str,Any]=Field(default_factory=dict)

class BodyObservation(BaseModel):
    sensor_id:str
    value:Any
    quality:float=1.0
    timestamp:float|None=None

class SpikeIn(BaseModel):
    source:str
    channel:str
    value:float=1.0
    timestamp:float|None=None

@app.middleware("http")
async def internal_auth(request:Request,call_next):
    path=request.url.path
    if path.startswith("/mind/") or path=="/v1/nexus/inbound":
        auth=request.headers.get("authorization")
        try:
            require_service(auth,request.headers.get("host"))
        except HTTPException as exc:
            from fastapi.responses import JSONResponse
            return JSONResponse(status_code=exc.status_code,content={"detail":exc.detail})
    return await call_next(request)

@app.on_event("startup")
def startup():
    worker.start()

@app.on_event("shutdown")
def shutdown():
    worker.stop()

@app.get("/")
def root():
    return {"service":"MACHINE-MIND","status":"online","version":"2.0.0","persistent":mind.persistence_ready}

@app.get("/health")
def health():
    return {"status":"ok","service":"MACHINE-MIND","cycle":mind.state.cycle,"persistent":mind.persistence_ready}

@app.get("/ready")
def ready():
    db=storage.health()
    return {"status":"ready" if db.get("ready") else "degraded","service":"MACHINE-MIND","cycle":mind.state.cycle,"persistence":db}

@app.post("/v1/nexus/inbound",status_code=202)
def nexus_inbound(env:NexusEnvelope):
    message_id=env.message_id or str(uuid.uuid4())
    first,existing=storage.begin_message(message_id)
    if not first:
        return {"accepted":True,"duplicate":True,"message_id":message_id,"existing":existing}
    event={"event_id":message_id,"event_type":env.message_type,"source_system":env.source_system,
           "timestamp":time.time(),"payload":env.payload,"correlation_id":env.correlation_id}
    with _ingest_lock:
        result=mind.ingest(event)
    storage.finish_message(message_id,result)
    return result|{"duplicate":False,"message_id":message_id}

@app.post("/mind/event")
def mind_event(evt:EventIn):
    event={"event_id":str(uuid.uuid4()),"event_type":evt.event_type,"source_system":evt.source_system,
           "timestamp":time.time(),"payload":evt.payload,"confidence":evt.confidence,"correlation_id":evt.correlation_id}
    with _ingest_lock:
        return mind.ingest(event)

@app.post("/mind/perception")
def perception(evt:EventIn):
    evt.event_type="perception.observation"
    return mind_event(evt)

@app.post("/mind/evidence")
def evidence(evt:EventIn):
    evt.event_type="evidence.update"
    return mind_event(evt)

@app.post("/mind/recall")
def recall(body:RecallIn):
    return {"subject":body.subject,"memories":mind.recall(body.subject,body.payload,body.limit)}

@app.get("/mind/learning")
def learning(subject:str|None=None,limit:int=100):
    return storage.learning_history(subject,limit) if mind.persistence_ready else []

@app.get("/mind/hypotheses")
def hypotheses(subject:str|None=None,limit:int=100):
    return mind.get_hypotheses(subject,limit)

@app.get("/mind/inquiries")
def inquiries(limit:int=100):
    return storage.inquiries(limit) if mind.persistence_ready else ([mind.last_inquiry] if mind.last_inquiry else [])

@app.get("/mind/outbox")
def outbox(limit:int=100):
    return storage.outbox_status(limit) if mind.persistence_ready else []

@app.get("/mind/actions")
def actions(limit:int=100):
    return storage.actions(limit) if mind.persistence_ready else ([mind.last_action] if mind.last_action else [])

@app.get("/mind/affect")
def affect(limit:int=100):
    return storage.recent_affect(limit) if mind.persistence_ready else [{"cycle":mind.state.cycle,"affect_json":mind.affect}]

@app.get("/mind/workspace")
def workspace():
    return {"focus":mind.workspace.focus,"broadcast":mind.workspace.broadcast}

@app.get("/mind/self-model")
def self_model():
    return mind.last_self_report or mind.self_model.update(mind.state.confidence,0,None)

@app.get("/mind/substrate")
def substrate():
    return mind.substrate.status()

@app.post("/mind/substrate/spike")
def substrate_spike(body:SpikeIn):
    return mind.substrate.emit(body.source,body.channel,body.value,body.timestamp)

@app.get("/mind/embodiment")
def embodiment():
    return mind.embodiment.status()

@app.post("/mind/embodiment/sensors")
def register_sensor(body:SensorRegistration):
    return mind.embodiment.register_sensor(body.sensor_id,body.kind,body.metadata)

@app.post("/mind/embodiment/actuators")
def register_actuator(body:ActuatorRegistration):
    return mind.embodiment.register_actuator(body.actuator_id,body.kind,body.metadata)

@app.post("/mind/embodiment/observe")
def body_observe(body:BodyObservation):
    observation=mind.embodiment.observe(body.sensor_id,body.value,body.quality,body.timestamp)
    mind.substrate.emit(body.sensor_id,"body.observation",body.quality,body.timestamp)
    return observation

@app.post("/mind/lab/run")
def lab_run():
    return lab.run_suite(mind)

@app.get("/mind/lab/ablation/{layer}")
def lab_ablation(layer:str):
    return lab.ablation(mind,layer)

@app.get("/mind/state")
def state():
    return mind.state.view()

@app.get("/mind/goals")
def goals():
    return mind.goals

@app.get("/mind/beliefs")
def beliefs():
    return list(mind.beliefs.values())

@app.get("/mind/events")
def events(limit:int=100):
    return storage.recent_events(limit) if mind.persistence_ready else list(mind.events)[-max(1,min(limit,1000)):]

@app.get("/mind/memory/episodes")
def episodes(limit:int=100,min_importance:float=0.0):
    return storage.episodes(limit,min_importance) if mind.persistence_ready else []

@app.get("/mind/memory/semantic")
def semantic(limit:int=100):
    return storage.semantic_memories(limit) if mind.persistence_ready else []

@app.get("/mind/memory/belief-history")
def belief_history(subject:str|None=None,limit:int=100):
    return storage.belief_history(subject,limit) if mind.persistence_ready else []

@app.post("/mind/memory/consolidate")
def consolidate():
    return mind.consolidate()

@app.get("/mind/snapshot")
def snapshot():
    return mind.snapshot()

@app.get("/mind/persistence")
def persistence():
    return {"runtime_ready":mind.persistence_ready,"database":storage.health(),"cycle":mind.state.cycle,
            "belief_count":len(mind.beliefs),"goal_count":len(mind.goals),"event_count":len(mind.events)}

@app.get("/mind/health")
def mind_health():
    return health()
