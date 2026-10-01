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
                for field in ("identity","cycle","thought","goal","narrative","confidence","uncertainty","last_event_at"):
                    if field in saved:
                        setattr(self.state, field, saved[field])
                self.state.cycle = int(snap.get("cycle") or self.state.cycle)
                self.beliefs = {str(x.get("subject", i)): x for i,x in enumerate(snap.get("beliefs_json") or [])}
                self.goals = list(snap.get("goals_json") or [])
                for event in storage.recent_events(5000):
                    self.events.append(event)
                print(f"MACHINE_MIND_RESTORED cycle={self.state.cycle} beliefs={len(self.beliefs)} goals={len(self.goals)} events={len(self.events)}",flush=True)
        except Exception as exc:
            self.persistence_ready = False
            print(f"MACHINE_MIND_PERSISTENCE_RESTORE_ERROR {type(exc).__name__}",flush=True)

    def score_importance(self,event:dict[str,Any],confidence:float)->float:
        et=str(event.get("event_type") or "")
        p=dict(event.get("payload") or {})
        score=0.30 + 0.35*confidence
        if "anomaly" in et or "alert" in et: score+=0.25
        if et in {"evidence.update","action.result","plan.result","feedback.operator"}: score+=0.15
        if p.get("novel") or p.get("critical"): score+=0.20
        return max(0.0,min(1.0,score))

    def persist(self,event:dict[str,Any],importance:float,belief:dict[str,Any]|None=None):
        if not self.persistence_ready:
            return
        try:
            storage.save_event(event,importance)
            if belief:
                storage.save_belief_version(str(belief["subject"]),belief)
                storage.reinforce_semantic(
                    str(belief["subject"]),
                    {"subject":belief["subject"],"latest":belief["payload"],"event_type":belief["event_type"],"source_system":belief["source_system"]},
                    float(belief["confidence"]),
                )
            storage.save_snapshot(self.state.identity,self.state.cycle,self.state.view(),list(self.beliefs.values()),self.goals)
            if self.state.cycle % 100 == 0:
                storage.apply_forgetting()
        except Exception as exc:
            self.persistence_ready=False
            print(f"MACHINE_MIND_PERSISTENCE_WRITE_ERROR {type(exc).__name__}",flush=True)

    def ingest(self,event:dict[str,Any])->dict[str,Any]:
        self.state.cycle += 1
        self.state.last_event_at = event.get("timestamp")
        et=str(event.get("event_type") or event.get("message_type") or "event")
        payload=dict(event.get("payload") or {})
        confidence=event.get("confidence")
        if confidence is None: confidence=payload.get("confidence",0.5)
        try: confidence=float(confidence)
        except Exception: confidence=0.5
        confidence=max(0.0,min(1.0,confidence))
        self.state.confidence=confidence
        self.state.uncertainty=1.0-confidence

        label=str(payload.get("label") or payload.get("subject") or payload.get("data_type") or et)
        belief=None
        if et in {"perception.observation","analytics.observation","analytics.classification","analytics.anomaly","evidence.update"}:
            belief={"subject":label,"event_type":et,"confidence":confidence,"payload":payload,"source_system":event.get("source_system")}
            self.beliefs[label]=belief

        if self.state.uncertainty > 0.45:
            goal="Reduce uncertainty with additional evidence."
        elif "anomaly" in et:
            goal="Investigate the detected anomaly."
        else:
            goal="Maintain and refine the current world model."
        self.state.goal=goal
        self.state.thought=f"Processed {et} concerning {label}."
        self.state.narrative=f"Cycle {self.state.cycle}: {self.state.thought} Confidence={confidence:.2f}; goal={goal}"
        self.events.append(event)
        if not self.goals or self.goals[0]["description"] != goal:
            self.goals.insert(0,{"description":goal,"priority":1.0-self.state.uncertainty/2})
            self.goals=self.goals[:100]

        importance=self.score_importance(event,confidence)
        self.persist(event,importance,belief)

        print(f"MACHINE_MIND_EVENT source={event.get('source_system')} type={et} label={label} cycle={self.state.cycle} importance={importance:.2f} persistent={self.persistence_ready}",flush=True)
        return {"accepted":True,"cycle":self.state.cycle,"thought":self.state.thought,"goal":self.state.goal,"belief_count":len(self.beliefs),"importance":importance,"persistent":self.persistence_ready}

    def consolidate(self)->dict[str,Any]:
        result=storage.apply_forgetting() if self.persistence_ready else {"forgotten":0}
        return {"persistent":self.persistence_ready,**result,"semantic_count":len(storage.semantic_memories(1000)) if self.persistence_ready else 0}

    def snapshot(self):
        return {"state":self.state.view(),"beliefs":list(self.beliefs.values()),"goals":self.goals,"event_count":len(self.events),"persistent":self.persistence_ready}
