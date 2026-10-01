from __future__ import annotations
import time, uuid
from typing import Any, Optional
from fastapi import FastAPI
from pydantic import BaseModel, Field
from runtime import MachineMindRuntime

app = FastAPI(title="Machine Mind", version="1.3.1")
mind = MachineMindRuntime()

class NexusEnvelope(BaseModel):
    source_system: str
    target_system: str = "MACHINE-MIND"
    message_type: str
    payload: dict[str, Any] = Field(default_factory=dict)
    message_id: str | None = None
    correlation_id: str | None = None
    trace_id: str | None = None
    schema_version: str = "1.0"
    priority: int = 50
    classification: str = "internal"

class EventIn(BaseModel):
    event_type: str
    source_system: str
    payload: dict[str, Any] = Field(default_factory=dict)
    confidence: Optional[float] = None
    correlation_id: Optional[str] = None

@app.get("/")
def root():
    return {"service":"MACHINE-MIND","status":"online","version":"1.3.1"}

@app.get("/health")
def health():
    return {"status":"ok","service":"MACHINE-MIND","cycle":mind.state.cycle}

@app.get("/ready")
def ready():
    return {"status":"ready","service":"MACHINE-MIND","cycle":mind.state.cycle}

@app.post("/v1/nexus/inbound", status_code=202)
def nexus_inbound(env: NexusEnvelope):
    event = {
        "event_id": env.message_id or str(uuid.uuid4()),
        "event_type": env.message_type,
        "source_system": env.source_system,
        "timestamp": time.time(),
        "payload": env.payload,
        "correlation_id": env.correlation_id,
    }
    return mind.ingest(event)

@app.post("/mind/event")
def mind_event(evt: EventIn):
    return mind.ingest({
        "event_id": str(uuid.uuid4()),
        "event_type": evt.event_type,
        "source_system": evt.source_system,
        "timestamp": time.time(),
        "payload": evt.payload,
        "confidence": evt.confidence,
        "correlation_id": evt.correlation_id,
    })

@app.post("/mind/perception")
def perception(evt: EventIn):
    evt.event_type = "perception.observation"
    return mind_event(evt)

@app.post("/mind/evidence")
def evidence(evt: EventIn):
    evt.event_type = "evidence.update"
    return mind_event(evt)

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
def events(limit: int = 100):
    return list(mind.events)[-max(1,min(limit,1000)):]

@app.get("/mind/health")
def mind_health():
    return health()
