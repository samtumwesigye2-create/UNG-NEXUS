import time,datetime
_regions={};_queue=[]
def configure(region,timezone="UTC",work_start=8,work_end=17,min_capacity=10,max_capacity=1000,warmup_minutes=30):
    _regions[region]={"timezone":timezone,"work_start":work_start,"work_end":work_end,"min_capacity":min_capacity,"max_capacity":max_capacity,"warmup_minutes":warmup_minutes,"desired":min_capacity,"mode":"baseline"}
    return _regions[region]
def telemetry_scale(region,active_sessions,p95_reflection_ms,queue_depth):
    r=_regions.setdefault(region,{"timezone":"UTC","work_start":8,"work_end":17,"min_capacity":10,"max_capacity":1000,"warmup_minutes":30,"desired":10,"mode":"baseline"})
    pressure=max(active_sessions/75 if active_sessions else 0,queue_depth/50 if queue_depth else 0)
    if p95_reflection_ms>=100:pressure=max(pressure,r["desired"]*1.25)
    desired=max(r["min_capacity"],min(r["max_capacity"],int(pressure)+1))
    r["desired"]=desired;r["mode"]="scale-out" if desired>r["min_capacity"] else "baseline";return dict(r)
def drain(region):
    r=_regions[region];r["mode"]="draining";return dict(r)
def enqueue(principal,region):
    token=f"Q-{int(time.time()*1000)}-{len(_queue)+1}";_queue.append({"token":token,"principal":principal,"region":region,"joined":time.time()});return {"token":token,"position":len(_queue)}
def admit(limit=100):
    n=max(0,min(int(limit),len(_queue)));items=_queue[:n];del _queue[:n];return items
def status():return {"regions":_regions,"waiting":len(_queue)}
