import copy,hashlib,re,time
_sessions={};_baselines={};_state={};_faults={}
BANNER="SANDBOX ENVIRONMENT — SYNTHETIC DATA ONLY"
def create_session(principal,scenario="default"):
    sid=hashlib.sha256(f"{principal}|{time.time_ns()}".encode()).hexdigest()[:24]
    _sessions[sid]={"principal":principal,"scenario":scenario,"created_at":time.time(),"sandbox":True}
    _state[sid]=copy.deepcopy(_baselines.get(scenario,{}));_faults[sid]={"delay_seconds":0,"failure":None}
    return {"session_id":sid,"banner":BANNER,"sandbox":True}
def require(sid,principal):
    s=_sessions.get(sid)
    return bool(s and s["principal"]==principal and s["sandbox"])
def seed(scenario,records):_baselines[scenario]=copy.deepcopy(records);return {"scenario":scenario,"records":len(records)}
def reset(sid):
    sc=_sessions[sid]["scenario"];_state[sid]=copy.deepcopy(_baselines.get(sc,{}));_faults[sid]={"delay_seconds":0,"failure":None};return _state[sid]
def state(sid):return _state.get(sid,{})
def update(sid,key,value):_state.setdefault(sid,{})[key]=value;return _state[sid]
def faults(sid):return _faults.get(sid,{})
def set_fault(sid,delay=0,failure=None):_faults[sid]={"delay_seconds":max(0,min(int(delay),120)),"failure":failure};return _faults[sid]
def scrub(records):
    out=[]
    for r in records:
        x=copy.deepcopy(r)
        for k in list(x):
            lk=k.lower()
            if any(p in lk for p in ("name","email","phone","address","nin","passport","biometric","dob")):
                x[k]=f"SYNTH-{hashlib.sha256(str(x[k]).encode()).hexdigest()[:10]}"
        out.append(x)
    return out
