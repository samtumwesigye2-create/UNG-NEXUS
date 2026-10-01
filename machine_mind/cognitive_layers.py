from __future__ import annotations
from typing import Any

class GlobalWorkspace:
    def __init__(self):
        self.focus: dict[str, Any] = {}
        self.broadcast: list[dict[str, Any]] = []

    def select(self, *, subject: str, importance: float, uncertainty: float, affect: dict[str, float], hypotheses: list[dict[str, Any]], goal: str) -> dict[str, Any]:
        contradiction = max((int(h.get("evidence",{}).get("contradictions",0)) for h in hypotheses), default=0)
        salience = min(1.0, 0.35*importance + 0.30*uncertainty + 0.20*float(affect.get("urgency",0)) + 0.15*min(1,contradiction))
        self.focus = {
            "subject": subject,
            "salience": round(salience,4),
            "goal": goal,
            "hypothesis_count": len(hypotheses),
            "attention_reason": "uncertainty/contradiction" if uncertainty > .35 or contradiction else "importance",
        }
        self.broadcast.insert(0, dict(self.focus))
        self.broadcast = self.broadcast[:100]
        return self.focus

class SelfModel:
    def __init__(self):
        self.identity="machine-mind-001"
        self.capabilities={
            "persistent_memory": True,
            "active_recall": True,
            "hypothesis_tracking": True,
            "planning": True,
            "agency_tracking": True,
            "affect_model": True,
        }
        self.calibration={"observations":0,"mean_abs_error":0.0,"confidence_bias":0.0}
        self.last_report={}

    def update(self, confidence: float, contradiction_count: int, prediction_error: float|None=None) -> dict[str, Any]:
        n=self.calibration["observations"]+1
        err = float(prediction_error if prediction_error is not None else min(1.0, contradiction_count*0.25))
        old=self.calibration["mean_abs_error"]
        self.calibration["observations"]=n
        self.calibration["mean_abs_error"]=round(old+(abs(err)-old)/n,4)
        self.calibration["confidence_bias"]=round(confidence-(1.0-err),4)
        limits=[]
        if contradiction_count: limits.append("conflicting evidence")
        if confidence < .55: limits.append("low confidence")
        if prediction_error is not None and prediction_error > .3: limits.append("action prediction mismatch")
        self.last_report={
            "identity":self.identity,
            "confidence":round(confidence,4),
            "known_limits":limits,
            "calibration":dict(self.calibration),
            "capabilities":dict(self.capabilities),
        }
        return self.last_report
