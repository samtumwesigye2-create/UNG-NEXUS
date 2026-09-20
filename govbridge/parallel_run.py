import asyncio,hashlib,json,os,time\nfrom persistent_state import configured as db_configured,advisory_lock,advisory_unlock
from collections import deque
_wal=deque(maxlen=200000);_divergence=deque(maxlen=20000);_authority={};_read_slice={};_locks={};_db_locks={}

def wal_append(envelope):
    seq=(_wal[-1]["seq"]+1) if _wal else 1
    rec={"seq":seq,"message_id":envelope.get("message_id"),"recorded_at_ns":time.time_ns(),"digest":hashlib.sha256(json.dumps(envelope,sort_keys=True,separators=(",",":"),default=str).encode()).hexdigest(),"envelope":envelope,"legacy":"pending","modern":"pending"}
    _wal.append(rec);return rec
def wal_status(limit=100):return list(_wal)[-max(1,min(limit,1000)):]
def mark(mid,side,status,error=None):
    for r in reversed(_wal):
        if r["message_id"]==mid:r[side]=status;r[side+"_error"]=error;return r
def divergence(mid,legacy,modern,severity="high"):
    if legacy==modern:return None
    d={"message_id":mid,"legacy":legacy,"modern":modern,"severity":severity,"detected_at":time.time()}
    _divergence.append(d);return d
def divergences(limit=100):return list(_divergence)[-max(1,min(limit,1000)):]

def set_authority(route,source):
    if source not in ("legacy","modern"):raise ValueError("authority_must_be_legacy_or_modern")
    _authority[route]=source;return {"route":route,"source_of_truth":source}
def authority(route):return _authority.get(route,"legacy")
def set_read_slice(route,modern_percent):
    p=max(0,min(100,int(modern_percent)));_read_slice[route]=p;return {"route":route,"modern_read_percent":p}
def choose_read(route,stable_key):
    p=_read_slice.get(route,0)
    bucket=int(hashlib.sha256(str(stable_key).encode()).hexdigest()[:8],16)%100
    return "modern" if bucket<p else "legacy"

def acquire(record_key,owner,ttl=30):
    if db_configured():
        key=str(record_key)
        cur=_db_locks.get(key)
        if cur and cur["owner"]==owner:return True
        handle=advisory_lock(key)
        if not handle:return False
        _db_locks[key]={"owner":owner,"handle":handle,"acquired_at":time.time()};return True
    now=time.time();cur=_locks.get(record_key)
    if cur and cur["expires_at"]>now and cur["owner"]!=owner:return False
    _locks[record_key]={"owner":owner,"expires_at":now+ttl};return True
def release(record_key,owner):
    key=str(record_key)
    if db_configured():
        cur=_db_locks.get(key)
        if not cur or cur["owner"]!=owner:return False
        ok=advisory_unlock(cur["handle"],key);_db_locks.pop(key,None);return ok
    if _locks.get(record_key,{}).get("owner")==owner:_locks.pop(record_key,None);return True
    return False
def lock_state():
    if db_configured():return {k:{"owner":v["owner"],"acquired_at":v["acquired_at"],"backend":"postgres-advisory"} for k,v in _db_locks.items()}
    return _locks

def reconcile_pair(mid,legacy_record,modern_record,legal_source="legacy"):
    lh=hashlib.sha256(json.dumps(legacy_record,sort_keys=True,separators=(",",":"),default=str).encode()).hexdigest()
    mh=hashlib.sha256(json.dumps(modern_record,sort_keys=True,separators=(",",":"),default=str).encode()).hexdigest()
    if lh==mh:return {"message_id":mid,"aligned":True,"legacy_hash":lh,"modern_hash":mh}
    source=legacy_record if legal_source=="legacy" else modern_record
    divergence(mid,lh,mh,"critical")
    return {"message_id":mid,"aligned":False,"legacy_hash":lh,"modern_hash":mh,"proposed_repair":{"source":legal_source,"record":source},"automatic_writeback":False}
