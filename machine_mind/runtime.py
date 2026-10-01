from __future__ import annotations
from collections import deque
from typing import Any
from state import MindState
import storage
import uuid
from cognitive_layers import GlobalWorkspace, SelfModel

CLAIM_KEYS=("value","status","state","classification","result","present","active")

class MachineMindRuntime:
    def __init__(self):
        self.state=MindState();self.events=deque(maxlen=5000);self.beliefs={};self.goals=[]
        self.persistence_ready=False;self.last_recall={};self.last_hypotheses=[];self.affect={};self.last_inquiry=None;self.last_action=None;self.workspace=GlobalWorkspace();self.self_model=SelfModel();self.last_self_report={};self.restore()

    def restore(self):
        try:
            self.persistence_ready=storage.init_schema()
            snap=storage.load_snapshot(self.state.identity) if self.persistence_ready else None
            if snap:
                saved=dict(snap.get("state_json") or {})
                for field in ("identity","cycle","thought","goal","narrative","confidence","uncertainty","last_event_at"):
                    if field in saved:setattr(self.state,field,saved[field])
                self.state.cycle=int(snap.get("cycle") or self.state.cycle)
                self.beliefs={str(x.get("subject",i)):x for i,x in enumerate(snap.get("beliefs_json") or [])}
                self.goals=list(snap.get("goals_json") or [])
                for event in storage.recent_events(5000):self.events.append(event)
                print(f"MACHINE_MIND_RESTORED cycle={self.state.cycle} beliefs={len(self.beliefs)} goals={len(self.goals)} events={len(self.events)}",flush=True)
        except Exception as exc:
            self.persistence_ready=False;print(f"MACHINE_MIND_PERSISTENCE_RESTORE_ERROR {type(exc).__name__}",flush=True)

    def score_importance(self,event,confidence):
        et=str(event.get("event_type") or "");p=dict(event.get("payload") or {});score=0.30+0.35*confidence
        if "anomaly" in et or "alert" in et:score+=0.25
        if et in {"evidence.update","action.result","plan.result","feedback.operator"}:score+=0.15
        if p.get("novel") or p.get("critical"):score+=0.20
        return max(0.0,min(1.0,score))

    def _claim(self,payload):
        for key in CLAIM_KEYS:
            if key in payload and isinstance(payload[key],(str,int,float,bool,type(None))):return key,payload[key]
        return None,None

    def active_recall(self,subject,payload,raw_confidence):
        memories=storage.recall(subject,payload,12) if self.persistence_ready else []
        current_key,current_value=self._claim(payload);support=contradiction=0;evidence=[];ss=sc=0.0
        for memory in memories:
            m=dict(memory.get("memory_json") or {});prior_payload=dict(m.get("latest") or m.get("payload") or {})
            prior_key,prior_value=self._claim(prior_payload);relation="context";mc=float(memory.get("confidence") or 0.0)
            if current_key and prior_key==current_key:
                if str(prior_value).strip().lower()==str(current_value).strip().lower():
                    relation="support";support+=1;ss=max(ss,mc)
                else:
                    relation="contradiction";contradiction+=1;sc=max(sc,mc)
            evidence.append({"memory_type":memory.get("memory_type"),"memory_key":memory.get("memory_key"),"relation":relation,"confidence":mc})
        revised=float(raw_confidence)
        if support:revised=revised+(1.0-revised)*(0.35*ss)
        if contradiction:revised=revised*(1.0-0.55*sc)
        revised=max(0.05,min(0.99,revised))
        learning={"subject":subject,"recalled_count":len(memories),"support_count":support,"contradiction_count":contradiction,
                  "raw_confidence":raw_confidence,"revised_confidence":revised,"claim_key":current_key,"claim_value":current_value,"evidence":evidence[:12]}
        self.last_recall=learning;return revised,learning

    def generate_hypotheses(self,subject,payload,confidence,learning):
        key,value=self._claim(payload)
        if not key:
            hypotheses=[{
                "hypothesis_id":str(uuid.uuid4()),"description":f"{subject}: current observation is representative",
                "probability":round(confidence,4),
                "prediction":{"expected":"similar future observations","claim_key":None},
                "next_observation":{"request":f"Collect another independent observation about {subject}","priority":"medium"},
                "evidence":{"support":learning["support_count"],"contradictions":learning["contradiction_count"]}
            }]
        else:
            p_main=max(0.05,min(0.95,confidence))
            p_alt=max(0.05,1.0-p_main)
            total=p_main+p_alt;p_main/=total;p_alt/=total
            hypotheses=[
                {
                    "hypothesis_id":str(uuid.uuid4()),
                    "description":f"{subject}: {key}={value}",
                    "probability":round(p_main,4),
                    "prediction":{"claim_key":key,"expected_value":value,"expected_next":"supporting observation"},
                    "next_observation":{"request":f"Measure {key} for {subject} again using an independent source","priority":"high" if learning["contradiction_count"] else "medium"},
                    "evidence":{"support":learning["support_count"],"contradictions":learning["contradiction_count"],"raw_confidence":learning["raw_confidence"]}
                },
                {
                    "hypothesis_id":str(uuid.uuid4()),
                    "description":f"{subject}: the current {key}={value} observation is misleading or transient",
                    "probability":round(p_alt,4),
                    "prediction":{"claim_key":key,"expected_value":f"not {value}","expected_next":"conflicting or reverting observation"},
                    "next_observation":{"request":f"Obtain a temporally separated or differently sourced {key} observation for {subject}","priority":"high"},
                    "evidence":{"support":learning["contradiction_count"],"contradictions":learning["support_count"]}
                }
            ]
        self.last_hypotheses=hypotheses
        if self.persistence_ready:storage.replace_hypotheses(subject,hypotheses)
        return hypotheses

    def update_affect(self,learning,confidence,importance):
        contradictions=int(learning.get("contradiction_count",0))
        novelty=1.0 if int(learning.get("recalled_count",0))==0 else 0.25
        self.affect={
            "curiosity":round(max(0.0,min(1.0,0.45*self.state.uncertainty+0.35*novelty+0.20*contradictions)),4),
            "urgency":round(max(0.0,min(1.0,importance*(0.7+0.3*contradictions))),4),
            "frustration":round(max(0.0,min(1.0,0.25*contradictions+0.35*self.state.uncertainty)),4),
            "satisfaction":round(max(0.0,min(1.0,confidence*(1.0-min(1.0,0.35*contradictions)))),4),
            "trust":round(max(0.0,min(1.0,confidence*(1.0-0.25*contradictions))),4),
            "goal_pressure":round(max(0.0,min(1.0,self.state.uncertainty+0.15*contradictions)),4),
        }
        if self.persistence_ready:
            storage.save_affect(self.state.cycle,self.affect)
        return self.affect

    def plan_inquiry(self,subject,hypotheses):
        if not hypotheses:return None
        request=hypotheses[0].get("next_observation") or {}
        text=str(request.get("request") or "")
        target="UNG-HEPHA"
        low=text.lower()
        if "plan" in low or "simulate" in low:target="UNG-APOLLO"
        elif "analytic" in low or "classif" in low:target="UNG-NOVA"
        elif "aerial" in low or "drone" in low or "overhead" in low:target="UNG-HORUS"
        inquiry={"inquiry_id":str(uuid.uuid4()),"subject":subject,"target_system":target,
                 "request":request,"status":"planned","reason":"reduce uncertainty / discriminate hypotheses"}
        self.last_inquiry=inquiry
        if self.persistence_ready:storage.save_inquiry(inquiry)
        return inquiry

    def update_agency(self,event):
        et=str(event.get("event_type") or "")
        p=dict(event.get("payload") or {})
        if et=="action.intent":
            action={"action_id":str(p.get("action_id") or event.get("event_id") or uuid.uuid4()),
                    "subject":str(p.get("subject") or p.get("action") or "action"),
                    "intended":p,"observed":None,"prediction_error":None,"status":"intended"}
            self.last_action=action
            if self.persistence_ready:storage.save_action(action)
            return action
        if et=="action.result":
            intended=dict(p.get("intended") or {})
            observed=dict(p.get("observed") or p)
            keys=set(intended).intersection(observed)
            mismatch=sum(1 for k in keys if str(intended.get(k))!=str(observed.get(k)))
            error=(mismatch/max(1,len(keys))) if keys else 0.0
            action={"action_id":str(p.get("action_id") or event.get("correlation_id") or event.get("event_id") or uuid.uuid4()),
                    "subject":str(p.get("subject") or p.get("action") or "action"),
                    "intended":intended,"observed":observed,"prediction_error":round(error,4),"status":"observed"}
            self.last_action=action
            if self.persistence_ready:storage.save_action(action)
            return action
        return None

    def persist(self,event,importance,belief=None,learning=None):
        if not self.persistence_ready:return
        try:
            storage.save_event(event,importance)
            if learning:storage.save_learning(event.get("event_id"),str(learning["subject"]),float(learning["raw_confidence"]),float(learning["revised_confidence"]),learning)
            if belief:
                storage.save_belief_version(str(belief["subject"]),belief)
                storage.reinforce_semantic(str(belief["subject"]),{"subject":belief["subject"],"latest":belief["payload"],"event_type":belief["event_type"],"source_system":belief["source_system"],"learning":learning or {}},float(belief["confidence"]))
            storage.save_snapshot(self.state.identity,self.state.cycle,self.state.view(),list(self.beliefs.values()),self.goals)
            if self.state.cycle%100==0:storage.apply_forgetting()
        except Exception as exc:
            self.persistence_ready=False;print(f"MACHINE_MIND_PERSISTENCE_WRITE_ERROR {type(exc).__name__}",flush=True)

    def ingest(self,event):
        self.state.cycle+=1;self.state.last_event_at=event.get("timestamp")
        et=str(event.get("event_type") or event.get("message_type") or "event");payload=dict(event.get("payload") or {})
        raw=event.get("confidence")
        if raw is None:raw=payload.get("confidence",0.5)
        try:raw=float(raw)
        except Exception:raw=0.5
        raw=max(0.0,min(1.0,raw));label=str(payload.get("label") or payload.get("subject") or payload.get("data_type") or et)
        confidence,learning=self.active_recall(label,payload,raw);self.state.confidence=confidence;self.state.uncertainty=1.0-confidence
        belief=None
        if et in {"perception.observation","analytics.observation","analytics.classification","analytics.anomaly","evidence.update"}:
            belief={"subject":label,"event_type":et,"confidence":confidence,"raw_confidence":raw,"payload":payload,"source_system":event.get("source_system"),"learning":learning}
            self.beliefs[label]=belief
        hypotheses=self.generate_hypotheses(label,payload,confidence,learning)
        inquiry=self.plan_inquiry(label,hypotheses) if (learning["contradiction_count"]>0 or self.state.uncertainty>0.35) else None
        agency=self.update_agency(event)
        if learning["contradiction_count"]>0:goal="Resolve contradictory evidence before increasing commitment."
        elif self.state.uncertainty>0.45:goal="Reduce uncertainty with additional evidence."
        elif "anomaly" in et:goal="Investigate the detected anomaly."
        else:goal="Maintain and refine the current world model."
        self.state.goal=goal;self.state.thought=f"Processed {et} concerning {label}; maintained {len(hypotheses)} hypotheses."
        self.state.narrative=f"Cycle {self.state.cycle}: {self.state.thought} Raw={raw:.2f}; revised={confidence:.2f}; support={learning['support_count']}; contradictions={learning['contradiction_count']}; goal={goal}"
        self.events.append(event)
        if not self.goals or self.goals[0]["description"]!=goal:self.goals.insert(0,{"description":goal,"priority":1.0-self.state.uncertainty/2});self.goals=self.goals[:100]
        importance=self.score_importance(event,confidence)
        affect=self.update_affect(learning,confidence,importance)
        workspace=self.workspace.select(subject=label,importance=importance,uncertainty=self.state.uncertainty,affect=affect,hypotheses=hypotheses,goal=goal)
        prediction_error=(agency or {}).get("prediction_error") if agency else None
        self_report=self.self_model.update(confidence,learning["contradiction_count"],prediction_error)
        self.last_self_report=self_report
        self.persist(event,importance,belief,learning)
        print(f"MACHINE_MIND_HYPOTHESES subject={label} count={len(hypotheses)} top={hypotheses[0]['probability']:.2f}",flush=True)
        return {"accepted":True,"cycle":self.state.cycle,"thought":self.state.thought,"goal":self.state.goal,"belief_count":len(self.beliefs),"importance":importance,"persistent":self.persistence_ready,"learning":learning,"hypotheses":hypotheses,"inquiry":inquiry,"agency":agency,"affect":affect,"workspace":workspace,"self_model":self_report}

    def recall(self,subject,payload=None,limit=12):return storage.recall(subject,payload or {},limit) if self.persistence_ready else []
    def get_hypotheses(self,subject=None,limit=100):return storage.hypotheses(subject,limit) if self.persistence_ready else self.last_hypotheses[:limit]
    def consolidate(self):
        result=storage.apply_forgetting() if self.persistence_ready else {"forgotten":0}
        return {"persistent":self.persistence_ready,**result,"semantic_count":len(storage.semantic_memories(1000)) if self.persistence_ready else 0}
    def snapshot(self):return {"state":self.state.view(),"beliefs":list(self.beliefs.values()),"goals":self.goals,"event_count":len(self.events),"persistent":self.persistence_ready,"last_recall":self.last_recall,"last_hypotheses":self.last_hypotheses,"affect":self.affect,"last_inquiry":self.last_inquiry,"last_action":self.last_action,"workspace":self.workspace.focus,"workspace_broadcast":self.workspace.broadcast,"self_model":self.last_self_report}
