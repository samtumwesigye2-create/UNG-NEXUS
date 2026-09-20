import hashlib,json,time
_state={}
def delta(dataset,rows):
    prior=_state.get(dataset,{})
    current={str(r.get("id") or r.get("key")):hashlib.sha256(json.dumps(r,sort_keys=True,separators=(",",":"),default=str).encode()).hexdigest() for r in rows}
    changed=[r for r in rows if prior.get(str(r.get("id") or r.get("key")))!=current.get(str(r.get("id") or r.get("key")))]
    deleted=[k for k in prior if k not in current]
    _state[dataset]=current
    return {"dataset":dataset,"changed":changed,"deleted":deleted,"processed_at":time.time(),"delta_count":len(changed)+len(deleted)}
