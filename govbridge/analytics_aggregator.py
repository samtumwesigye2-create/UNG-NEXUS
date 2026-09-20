import time,collections
_events=[];_hourly={}
def ingest(event):
    _events.append({**event,"ts":time.time()})
    if len(_events)>500000:del _events[:-500000]
    return {"accepted":True}
def aggregate_hour(hour=None):
    hour=hour or time.strftime("%Y-%m-%dT%H",time.gmtime())
    rows=[e for e in _events if time.strftime("%Y-%m-%dT%H",time.gmtime(e["ts"]))==hour]
    by_role=collections.defaultdict(lambda:{"sessions":0,"completed":0,"errors":0,"duration_ms":0})
    bottlenecks=collections.Counter();regions=collections.Counter()
    for e in rows:
        role=e.get("persona","unknown");b=by_role[role];b["sessions"]+=1;b["completed"]+=1 if e.get("completed") else 0;b["errors"]+=int(e.get("errors") or 0);b["duration_ms"]+=float(e.get("duration_ms") or 0)
        if e.get("step") and int(e.get("errors") or 0)>0:bottlenecks[e["step"]]+=1
        if e.get("region"):regions[e["region"]]+=1
    out={"hour":hour,"personas":dict(by_role),"bottlenecks":bottlenecks.most_common(20),"regions":dict(regions),"events":len(rows)}
    _hourly[hour]=out;return out
def dashboard(persona,scope=None):
    latest=aggregate_hour()
    if persona=="class-instructor":return {"persona":persona,"scope":scope,"view":"live-classroom-progress","hourly":latest}
    if persona=="ministry-director":return {"persona":persona,"scope":scope,"view":"department-readiness-rollup","hourly":latest}
    return {"persona":"national-architect","scope":"national","view":"capacity-ring-matrix","hourly":latest}
