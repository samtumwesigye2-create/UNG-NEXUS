import gzip,hashlib,json,time
_archive={}
def archive_records(sector,records):
    # Portable long-term NDJSON payload; external object storage can persist the bytes.
    text="\n".join(json.dumps(r,sort_keys=True,separators=(",",":"),default=str) for r in records).encode()
    blob=gzip.compress(text);aid=hashlib.sha256(blob).hexdigest()
    _archive[aid]={"sector":sector,"created_at":time.time(),"count":len(records),"sha256":aid,"format":"ndjson+gzip","records":records}
    return {k:v for k,v in _archive[aid].items() if k!="records"}
def query(sector,predicate):
    out=[]
    for a in _archive.values():
        if a["sector"]!=sector:continue
        for r in a["records"]:
            if all(str(r.get(k))==str(v) for k,v in predicate.items()):out.append(r)
    return out
def catalog():return [{k:v for k,v in a.items() if k!="records"} for a in _archive.values()]
