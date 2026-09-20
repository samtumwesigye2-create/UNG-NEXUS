import hashlib,time
from collections import deque
TIERS={
 "financial":{"tier":1,"failure":"fail-closed"},
 "treasury":{"tier":1,"failure":"fail-closed"},
 "emergency":{"tier":1,"failure":"fail-closed"},
 "critical-infrastructure":{"tier":1,"failure":"fail-closed"},
 "national-security":{"tier":1,"failure":"fail-closed"},
 "border":{"tier":2,"failure":"degrade-gracefully"},
 "immigration":{"tier":2,"failure":"degrade-gracefully"},
 "identity":{"tier":2,"failure":"degrade-gracefully"},
 "health":{"tier":2,"failure":"degrade-gracefully"},
 "land":{"tier":2,"failure":"degrade-gracefully"},
 "business":{"tier":3,"failure":"degrade-gracefully"},
 "civilian":{"tier":3,"failure":"degrade-gracefully"},
 "analytics":{"tier":3,"failure":"degrade-gracefully"},
}
_burned=set();_pending={};_manual=deque(maxlen=20000);_dlq=deque(maxlen=200000)

def classify(sector,payload):
    base=dict(TIERS.get(sector,TIERS["civilian"]))
    override=payload.get("_criticality_tier")
    if override in (1,2,3):
        base={"tier":int(override),"failure":"fail-closed" if int(override)==1 else "degrade-gracefully"}
    return base
def nonce(message_id,payload):
    return hashlib.sha256((message_id+"|"+str(payload.get("_nonce",""))).encode()).hexdigest()
def burn(n):_burned.add(n)
def burned(n):return n in _burned
def dlq_add(envelope,error):
    rec={"sequence":len(_dlq)+1,"message_id":envelope.get("message_id"),"envelope":envelope,"error":error,"state":"pending","queued_at":time.time()}
    _dlq.append(rec);_pending[str(envelope.get("message_id"))]=rec;return rec
def dlq(limit=100):return list(_dlq)[-max(1,min(limit,1000)):]
def pending(mid):return _pending.get(mid)
def manual_hold(item,reason):
    rec={"item":item,"reason":reason,"held_at":time.time(),"state":"manual-hold"};_manual.append(rec);return rec
def holds(limit=100):return list(_manual)[-max(1,min(limit,1000)):]
