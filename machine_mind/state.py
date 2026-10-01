from dataclasses import dataclass, asdict
from typing import Any
import time

@dataclass
class MindState:
    identity: str = "machine-mind-001"
    cycle: int = 0
    thought: str | None = None
    goal: str | None = None
    narrative: str = ""
    confidence: float = 0.5
    uncertainty: float = 0.5
    last_event_at: float | None = None

    def view(self) -> dict[str, Any]:
        return asdict(self)
