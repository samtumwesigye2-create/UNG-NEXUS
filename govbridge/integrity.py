import hashlib, json, os, time
from collections import deque
from persistent_state import configured as db_configured,claim_idempotency,cleanup_idempotency,append_audit,audit_events

_seen: dict[str,tuple[float,str]] = {}
_audit = deque(maxlen=10000)
_prev_hash = "GENESIS"

def canonical_hash(payload) -> str:
    raw=json.dumps(payload,sort_keys=True,separators=(",",":"),default=str).encode()
    return hashlib.sha256(raw).hexdigest()

def idempotent(message_id: str, payload=None, ttl: int = 86400) -> bool:
    digest=canonical_hash(payload if payload is not None else {})
    if db_configured():
        cleanup_idempotency(ttl)
        return claim_idempotency(message_id,digest)
    now=time.time()
    for k,v in list(_seen.items()):
        if now-v[0] > ttl:_seen.pop(k,None)
    if message_id in _seen:
        if _seen[message_id][1] != digest:raise ValueError("idempotency_key_payload_conflict")
        return False
    _seen[message_id]=(now,digest);return True

def audit(event: dict) -> dict:
    global _prev_hash
    body={**event,"recorded_at":time.time(),"previous_hash":_prev_hash}
    raw=json.dumps(body,sort_keys=True,separators=(",",":"),default=str).encode()
    body["hash"]=hashlib.sha256(_prev_hash.encode()+b"|" + raw).hexdigest()
    if db_configured():append_audit(body,_prev_hash,body["hash"])
    _prev_hash=body["hash"];_audit.append(body);return body

def audit_tail(limit=100):
    return audit_events(limit) if db_configured() else list(_audit)[-max(1,min(limit,1000)):]

def mask(value):
    if isinstance(value,dict):
        out={}
        for k,v in value.items():
            lk=str(k).lower()
            if any(x in lk for x in ("password","secret","token","nin","national_id","ssn","biometric")):out[k]="[REDACTED]"
            else:out[k]=mask(v)
        return out
    if isinstance(value,list):return [mask(x) for x in value]
    return value
