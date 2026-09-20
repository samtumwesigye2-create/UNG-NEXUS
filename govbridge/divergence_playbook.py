import hashlib,json,time
_locked={};_holds={};_ledger=[]
TIER1={"balance","identity_lock","security_authorization","border_alert","clearance"}
def digest(v):return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(",",":"),default=str).encode()).hexdigest()
def triage(entity_id,legacy,modern,field=None):
    if digest(legacy)==digest(modern):return {"state":"equal","entity_id":entity_id}
    tier=1 if field in TIER1 else 2
    event={"entity_id":entity_id,"tier":tier,"legacy_hash":digest(legacy),"modern_hash":digest(modern),"field":field,"at":time.time()}
    _ledger.append({**event,"action":"drift_detected"})
    if tier==1:
        _locked[entity_id]=event;_holds[entity_id]={"legacy":legacy,"modern":modern,"event":event,"state":"manual-review"}
        return {**event,"state":"locked","http_status":423,"manual_review":True}
    # Timestamp resolution is explicit and never described as globally synchronized TrueTime.
    lt=float(legacy.get("updated_at_epoch",0) or 0);mt=float(modern.get("updated_at_epoch",0) or 0)
    winner="modern" if mt>lt else "legacy" if lt>mt else None
    _ledger.append({**event,"action":"auto_repair_proposed","winner":winner})
    return {**event,"state":"repair-proposed","winner":winner,"automatic_writeback":False}
def locked(entity_id):return entity_id in _locked
def diff(entity_id):
    h=_holds.get(entity_id)
    if not h:return None
    keys=set(h["legacy"])|set(h["modern"]);return {"entity_id":entity_id,"differences":{k:{"legacy":h["legacy"].get(k),"modern":h["modern"].get(k)} for k in keys if h["legacy"].get(k)!=h["modern"].get(k)}}
def resolve(entity_id,direction,principal,authority_reference):
    if direction not in ("FORCE_SYNC_TO_LEGACY","FORCE_SYNC_TO_MODERN"):raise ValueError("invalid_resolution_direction")
    if entity_id not in _holds:raise ValueError("entity_not_on_hold")
    event={"entity_id":entity_id,"action":"human_resolution_authorized","direction":direction,"principal":principal,"authority_reference":authority_reference,"at":time.time()}
    _ledger.append(event);_locked.pop(entity_id,None);_holds[entity_id]["state"]="resolved";return event
def ledger():return list(_ledger)
