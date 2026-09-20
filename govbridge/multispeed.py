import hashlib,json,time
from collections import deque,defaultdict
POLICY={
 "financial":"synchronous","treasury":"synchronous","emergency":"synchronous",
 "border":"asynchronous","immigration":"asynchronous","identity":"asynchronous",
 "civilian":"asynchronous","health":"asynchronous","business":"asynchronous",
 "analytics":"batch","intelligence":"batch","archive":"batch","reporting":"batch",
}
_async=deque(maxlen=200000);_batch=deque(maxlen=500000);_versions=defaultdict(dict)

def speed_for(sector,payload):
    requested=str(payload.get("_sync_speed","")).lower()
    if requested in ("synchronous","asynchronous","batch"):return requested
    return POLICY.get(sector,"asynchronous")

def stamp(record_key,source,speed,payload):
    epoch=time.time_ns();current=_versions[record_key]
    vector=dict(current.get("vector") or {});vector[source]=int(vector.get(source,0))+1
    version={"record_key":record_key,"source":source,"speed":speed,"epoch_ns":epoch,"vector":vector,
             "digest":hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(",",":"),default=str).encode()).hexdigest()}
    _versions[record_key]=version;return version

def should_apply(record_key,incoming):
    current=_versions.get(record_key)
    if not current:return True,"no_current_version"
    if incoming["epoch_ns"]>current["epoch_ns"]:return True,"newer_epoch"
    if incoming["epoch_ns"]<current["epoch_ns"]:return False,"stale_write_discarded"
    rank={"synchronous":3,"asynchronous":2,"batch":1}
    return (rank.get(incoming["speed"],0)>=rank.get(current["speed"],0),
            "speed_override" if incoming["speed"]!=current["speed"] else "equal_epoch")

def enqueue_async(item):_async.append({**item,"queued_at_ns":time.time_ns()});return len(_async)
def enqueue_batch(item):_batch.append({**item,"queued_at_ns":time.time_ns()});return len(_batch)
def queues():return {"asynchronous":len(_async),"batch":len(_batch)}
def policy():return POLICY
