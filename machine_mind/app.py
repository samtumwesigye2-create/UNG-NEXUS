from __future__ import annotations
import time,uuid
from typing import Any,Optional
from fastapi import FastAPI
from pydantic import BaseModel,Field
from runtime import MachineMindRuntime
import storage

app=FastAPI(title="Machine Mind",version="1.7.0")
mind=MachineMindRuntime()

class NexusEnvelope(BaseModel):
    source_system:str;target_system:str="MACHINE-MIND";message_type:str;payload:dict[str,Any]=Field(default_factory=dict)
    message_id:str|None=None;correlation_id:str|None=None;trace_id:str|None=None;schema_version:str="1.0";priority:int=50;classification:str="internal"

class EventIn(BaseModel):
    event_type:str;source_system:str;payload:dict[str,Any]=Field(default_factory=dict);confidence:Optional[float]=None;correlation_id:Optional[str]=None

class RecallIn(BaseModel):
    subject:str;payload:dict[str,Any]=Field(default_factory=dict);limit:int=12

@app.get("/")
def root():return {"service":"MACHINE-MIND","status":"online","version":"1.7.0","persistent":mind.persistence_ready}
@app.get("/health")
def health():return {"status":"ok","service":"MACHINE-MIND","cycle":mind.state.cycle,"persistent":mind.persistence_ready}
@app.get("/ready")
def ready():
    db=storage.health();return {"status":"ready" if db.get("ready") else "degraded","service":"MACHINE-MIND","cycle":mind.state.cycle,"persistence":db}
@app.post("/v1/nexus/inbound",status_code=202)
def nexus_inbound(env:NexusEnvelope):return mind.ingest({"event_id":env.message_id or str(uuid.uuid4()),"event_type":env.message_type,"source_system":env.source_system,"timestamp":time.time(),"payload":env.payload,"correlation_id":env.correlation_id})
@app.post("/mind/event")
def mind_event(evt:EventIn):return mind.ingest({"event_id":str(uuid.uuid4()),"event_type":evt.event_type,"source_system":evt.source_system,"timestamp":time.time(),"payload":evt.payload,"confidence":evt.confidence,"correlation_id":evt.correlation_id})
@app.post("/mind/perception")
def perception(evt:EventIn):evt.event_type="perception.observation";return mind_event(evt)
@app.post("/mind/evidence")
def evidence(evt:EventIn):evt.event_type="evidence.update";return mind_event(evt)
@app.post("/mind/recall")
def recall(body:RecallIn):return {"subject":body.subject,"memories":mind.recall(body.subject,body.payload,body.limit)}
@app.get("/mind/learning")
def learning(subject:str|None=None,limit:int=100):return storage.learning_history(subject,limit) if mind.persistence_ready else []
@app.get("/mind/hypotheses")
def hypotheses(subject:str|None=None,limit:int=100):return mind.get_hypotheses(subject,limit)
@app.get("/mind/state")
def state():return mind.state.view()
@app.get("/mind/goals")
def goals():return mind.goals
@app.get("/mind/beliefs")
def beliefs():return list(mind.beliefs.values())
@app.get("/mind/events")
def events(limit:int=100):return storage.recent_events(limit) if mind.persistence_ready else list(mind.events)[-max(1,min(limit,1000)):]
@app.get("/mind/memory/episodes")
def episodes(limit:int=100,min_importance:float=0.0):return storage.episodes(limit,min_importance) if mind.persistence_ready else []
@app.get("/mind/memory/semantic")
def semantic(limit:int=100):return storage.semantic_memories(limit) if mind.persistence_ready else []
@app.get("/mind/memory/belief-history")
def belief_history(subject:str|None=None,limit:int=100):return storage.belief_history(subject,limit) if mind.persistence_ready else []
@app.post("/mind/memory/consolidate")
def consolidate():return mind.consolidate()
@app.get("/mind/snapshot")
def snapshot():return mind.snapshot()
@app.get("/mind/persistence")
def persistence():return {"runtime_ready":mind.persistence_ready,"database":storage.health(),"cycle":mind.state.cycle,"belief_count":len(mind.beliefs),"goal_count":len(mind.goals),"event_count":len(mind.events)}
@app.get("/mind/health")
def mind_health():return health()
