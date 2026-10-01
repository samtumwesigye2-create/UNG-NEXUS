from __future__ import annotations
from collections import deque
from typing import Any
from state import MindState
import storage

class MachineMindRuntime:
    def __init__(self):
        self.state = MindState()
        self.events = deque(maxlen=5000)
        self.beliefs: dict[str, dict[str, Any]] = {}
        self.goals: list[dict[str, Any]] = []
        self.persistence_ready = False
        self.restore()

    def restore(self):
        try:
            self.persistence_ready = storage.init_schema()
            snap = storage.load_snapshot(self.state.identity) if self.persistence_ready else None
            if snap:
                saved = dict(snap.get("state_json") or {})
                for field in (
                    "identity","cycle","thought","goal","narrative",
                    "confidence","uncertainty","last_event_at"
                ):
                    if field in saved:
                        setattr(self.state, field, saved[field])
                self.state.cycle = int(snap.get("cycle") or self.state.cycle)
                self.beliefs = {
                    str(x.get("subject", i)): x
                    for i, x in enumerate(snap.get("beliefs_json") or [])
                }
                self.goals = list(snap.get("goals_json") or [])
                for event in storage.recent_events(5000):
                    self.events.append(event)
                print(
                    f"MACHINE_MIND_RESTORED cycle={self.state.cycle} "
                    f"beliefs={len(self.beliefs)} goals={len(self.goals)} events={len(self.events)}",
                    flush=True,
                )
        except Exception as exc:
            self.persistence_ready = False
            print(f"MACHINE_MIND_PERSISTENCE_RESTORE_ERROR {type(exc).__name__}", flush=True)

    def persist(self, event: dict[str, Any]):
        if not self.persistence_ready:
            return
        try:
            storage.save_event(event)
            storage.save_snapshot(
                self.state.identity,
                self.state.cycle,
                self.state.view(),
                list(self.beliefs.values()),
                self.goals,
            )
        except Exception as exc:
            self.persistence_ready = False
            print(f"MACHINE_MIND_PERSISTENCE_WRITE_ERROR {type(exc).__name__}", flush=True)

    def ingest(self, event: dict[str, Any]) -> dict[str, Any]:
        self.state.cycle += 1
        self.state.last_event_at = event.get("timestamp")
        et = str(event.get("event_type") or event.get("message_type") or "event")
        payload = dict(event.get("payload") or {})
        confidence = event.get("confidence")
        if confidence is None:
            confidence = payload.get("confidence", 0.5)
        try:
            confidence = float(confidence)
        except Exception:
            confidence = 0.5
        confidence = max(0.0,min(1.0,confidence))
        self.state.confidence = confidence
        self.state.uncertainty = 1.0-confidence

        label = str(payload.get("label") or payload.get("subject") or payload.get("data_type") or et)
        if et in {"perception.observation","analytics.observation","analytics.classification","analytics.anomaly","evidence.update"}:
            self.beliefs[label] = {
                "subject": label,
                "event_type": et,
                "confidence": confidence,
                "payload": payload,
                "source_system": event.get("source_system"),
            }

        if self.state.uncertainty > 0.45:
            goal = "Reduce uncertainty with additional evidence."
        elif "anomaly" in et:
            goal = "Investigate the detected anomaly."
        else:
            goal = "Maintain and refine the current world model."
        self.state.goal = goal
        self.state.thought = f"Processed {et} concerning {label}."
        self.state.narrative = (
            f"Cycle {self.state.cycle}: {self.state.thought} "
            f"Confidence={self.state.confidence:.2f}; goal={goal}"
        )
        self.events.append(event)
        if not self.goals or self.goals[0]["description"] != goal:
            self.goals.insert(0, {"description":goal,"priority":1.0-self.state.uncertainty/2})
            self.goals = self.goals[:100]

        self.persist(event)

        print(
            f"MACHINE_MIND_EVENT source={event.get('source_system')} "
            f"type={et} label={label} cycle={self.state.cycle} "
            f"persistent={self.persistence_ready}",
            flush=True,
        )
        return {
            "accepted": True,
            "cycle": self.state.cycle,
            "thought": self.state.thought,
            "goal": self.state.goal,
            "belief_count": len(self.beliefs),
            "persistent": self.persistence_ready,
        }

    def snapshot(self):
        return {
            "state": self.state.view(),
            "beliefs": list(self.beliefs.values()),
            "goals": self.goals,
            "event_count": len(self.events),
            "persistent": self.persistence_ready,
        }
