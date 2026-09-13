from pydantic import BaseModel, ConfigDict, Field


class LagrangeEnvelope(BaseModel):
    model_config = ConfigDict(extra='forbid')

    message_id: str = Field(min_length=1)
    source_system: str = Field(min_length=1)
    target_system: str = Field(min_length=1)
    message_type: str = Field(min_length=1)
    payload: dict
    correlation_id: str | None = None
    trace_id: str | None = None
    schema_version: str = '1.0'
