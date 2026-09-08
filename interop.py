"""Shared NEXUS interoperability contracts.
Preserves LAGRANGE's useful universal-envelope/vendor abstraction while NEXUS stays the integration owner.
"""
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Callable
from uuid import uuid4

@dataclass(frozen=True)
class NexusEnvelope:
    source_system: str
    target_system: str
    message_type: str
    payload: dict[str, Any]
    message_id: str = field(default_factory=lambda: str(uuid4()))
    correlation_id: str | None = None
    trace_id: str | None = None
    schema_version: str = "1.0"
    priority: int = 50
    classification: str = "internal"
    sent_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["priority"] = max(0, min(100, int(self.priority)))
        return data

@dataclass
class Connector:
    name: str
    kind: str
    capabilities: set[str]
    send: Callable[[NexusEnvelope], dict[str, Any]]
    enabled: bool = True

class ConnectorRegistry:
    def __init__(self):
        self._connectors: dict[str, Connector] = {}

    def register(self, connector: Connector) -> None:
        self._connectors[connector.name.lower()] = connector

    def get(self, name: str) -> Connector | None:
        c = self._connectors.get(name.lower())
        return c if c and c.enabled else None

    def discover(self, capability: str) -> list[Connector]:
        cap = capability.lower()
        return sorted([c for c in self._connectors.values() if c.enabled and cap in {x.lower() for x in c.capabilities}], key=lambda c: c.name)

connectors = ConnectorRegistry()
