import hashlib,time
_cells={};_regions={}
def region_for(key,requested=None):
    if requested:return requested
    regions=["central","east","north","west"]
    return regions[int(hashlib.sha256(str(key).encode()).hexdigest()[:8],16)%len(regions)]
def provision(session_id,principal,region=None,ttl=7200):
    r=region_for(principal,region);cid=hashlib.sha256(f"{session_id}|{r}".encode()).hexdigest()[:20]
    cell={"cell_id":cid,"session_id":session_id,"region":r,"created_at":time.time(),"expires_at":time.time()+ttl,"state":"active","storage":"ephemeral","production_access":False}
    _cells[cid]=cell;return cell
def destroy(cell_id):
    c=_cells.pop(cell_id,None)
    return {"destroyed":bool(c),"cell_id":cell_id}
def reap():
    now=time.time();dead=[k for k,v in _cells.items() if v["expires_at"]<=now]
    for k in dead:_cells.pop(k,None)
    return len(dead)
def stats():
    reap();by={}
    for c in _cells.values():by[c["region"]]=by.get(c["region"],0)+1
    return {"active_cells":len(_cells),"by_region":by}
