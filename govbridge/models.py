from typing import Any, Literal
from pydantic import BaseModel, Field

class BridgeMessage(BaseModel):
    message_id: str
    source_system: str
    target_system: str
    message_type: str
    payload: dict[str, Any] = Field(default_factory=dict)
    correlation_id: str | None = None
    trace_id: str | None = None
    classification: Literal["public","internal","confidential","restricted"] = "internal"

class BridgeResult(BaseModel):
    message_id: str
    agency: str
    status: str
    http_status: int | None = None
    response: dict[str, Any] | None = None
    error: str | None = None
