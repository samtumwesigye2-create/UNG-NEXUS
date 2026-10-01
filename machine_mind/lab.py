from __future__ import annotations
import uuid
from typing import Any

def run_suite(runtime) -> dict[str, Any]:
    state=runtime.state.view()
    checks=[
        {"name":"persistence_ready","pass":bool(runtime.persistence_ready)},
        {"name":"memory_recall_available","pass":hasattr(runtime,"recall")},
        {"name":"hypothesis_layer_available","pass":hasattr(runtime,"generate_hypotheses")},
        {"name":"agency_layer_available","pass":hasattr(runtime,"update_agency")},
        {"name":"workspace_available","pass":hasattr(runtime,"workspace")},
        {"name":"self_model_available","pass":hasattr(runtime,"self_model")},
        {"name":"confidence_bounded","pass":0.0 <= float(state.get("confidence",0.5)) <= 1.0},
        {"name":"uncertainty_bounded","pass":0.0 <= float(state.get("uncertainty",0.5)) <= 1.0},
    ]
    passed=sum(1 for x in checks if x["pass"])
    return {
        "run_id":str(uuid.uuid4()),
        "suite":"machine-mind-functional-v1",
        "passed":passed,
        "failed":len(checks)-passed,
        "checks":checks,
        "note":"Functional architecture checks; not a test of phenomenal consciousness.",
    }

def ablation(runtime, layer: str) -> dict[str, Any]:
    supported={"memory","hypotheses","affect","workspace","self_model","agency"}
    return {
        "layer":layer,
        "supported":layer in supported,
        "method":"non-destructive simulated ablation",
        "expected_effect":{
            "memory":"reduced continuity and evidence recall",
            "hypotheses":"single-track interpretation",
            "affect":"reduced motivational salience modulation",
            "workspace":"reduced cross-layer prioritization",
            "self_model":"reduced confidence/limit reporting",
            "agency":"reduced intended-vs-observed learning",
        }.get(layer,"unknown"),
    }
