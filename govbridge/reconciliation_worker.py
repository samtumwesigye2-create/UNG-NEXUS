import hashlib,json,time
def canonical_hash(record):
    return hashlib.sha256(json.dumps(record,sort_keys=True,separators=(",",":"),default=str).encode()).hexdigest()
def compare(legacy:dict,modern:dict):
    keys=sorted(set(legacy)|set(modern));drift=[]
    for key in keys:
        lh=canonical_hash(legacy.get(key));mh=canonical_hash(modern.get(key))
        if lh!=mh:drift.append({"record":key,"legacy_hash":lh,"modern_hash":mh})
    return {"checked_at":time.time(),"records_checked":len(keys),"drift_count":len(drift),"drift":drift}
