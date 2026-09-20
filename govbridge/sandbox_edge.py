import hashlib,time
_nodes={};_rooms={};_telemetry=[]
def register_node(name,site,capabilities=None):
    nid=hashlib.sha256(f"{name}|{site}".encode()).hexdigest()[:16]
    _nodes[nid]={"node_id":nid,"name":name,"site":site,"capabilities":capabilities or [],"mode":"sandbox-only","registered_at":time.time(),"last_seen":time.time()}
    return _nodes[nid]
def nodes():return list(_nodes.values())
def room(room_id,instructor=None):
    return _rooms.setdefault(room_id,{"room_id":room_id,"instructor":instructor,"sessions":[],"generation":1})
def attach(room_id,sid,instructor=None):
    r=room(room_id,instructor)
    if sid not in r["sessions"]:r["sessions"].append(sid)
    return r
def reset_room(room_id):
    r=room(room_id);r["generation"]+=1;return r
def record(metric):
    rec={**metric,"recorded_at":time.time()};_telemetry.append(rec)
    if len(_telemetry)>100000:del _telemetry[:-100000]
    return rec
def analytics():
    by_mode={}
    for x in _telemetry:
        mode=x.get("ui","unknown");b=by_mode.setdefault(mode,{"events":0,"duration_ms":0})
        b["events"]+=1;b["duration_ms"]+=float(x.get("duration_ms",0) or 0)
    for b in by_mode.values():b["avg_duration_ms"]=round(b["duration_ms"]/b["events"],2) if b["events"] else 0
    return {"events":len(_telemetry),"by_ui":by_mode}
