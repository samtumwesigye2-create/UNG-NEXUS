import hashlib,time
_state={}
PHASES=("shadow","canary","split","modern-primary","legacy-read-only","sunset")
def _s(sector):
    return _state.setdefault(sector,{"phase":"shadow","modern_percent":0,"legacy_writes":True,"modern_source_of_truth":False,"stability_started":None,"last_failure":None})
def state(sector):return dict(_s(sector))
def route(sector,stable_key):
    s=_s(sector);bucket=int(hashlib.sha256(str(stable_key).encode()).hexdigest()[:8],16)%100
    return "modern" if bucket<int(s["modern_percent"]) else "legacy"
def record_failure(sector,reason):
    s=_s(sector);s["last_failure"]={"at":time.time(),"reason":reason};s["stability_started"]=None;return dict(s)
def promote(sector,phase,modern_percent=None):
    if phase not in PHASES:raise ValueError("invalid_cutover_phase")
    s=_s(sector);s["phase"]=phase
    defaults={"shadow":0,"canary":1,"split":50,"modern-primary":100,"legacy-read-only":100,"sunset":100}
    s["modern_percent"]=max(0,min(100,int(defaults[phase] if modern_percent is None else modern_percent)))
    if phase in ("modern-primary","legacy-read-only","sunset"):s["modern_source_of_truth"]=True
    if phase in ("legacy-read-only","sunset"):s["legacy_writes"]=False
    if s["modern_percent"]==100 and not s["stability_started"]:s["stability_started"]=time.time()
    return dict(s)
def eligible_for_freeze(sector,window_days=30):
    s=_s(sector)
    if s["modern_percent"]<100 or not s["stability_started"]:return False
    return (time.time()-s["stability_started"])>=window_days*86400 and s["last_failure"] is None
