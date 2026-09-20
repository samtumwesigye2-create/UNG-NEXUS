import json,time,zlib,base64
_sessions={}
def configure(session_id,threshold_kbps=15):
    _sessions[session_id]={"mode":"text-driven-sync","target_kbps":float(threshold_kbps),"configured_at":time.time()}
    return _sessions[session_id]
def encode_delta(fields):
    raw=json.dumps(fields,separators=(",",":"),ensure_ascii=False).encode()
    comp=zlib.compress(raw,9)
    return {"encoding":"zlib+base64","payload":base64.urlsafe_b64encode(comp).decode(),"raw_bytes":len(raw),"compressed_bytes":len(comp)}
def decode_delta(payload):
    return json.loads(zlib.decompress(base64.urlsafe_b64decode(payload.encode())).decode())
def validate(fields,rules):
    errors={}
    for name,rule in (rules or {}).items():
        val=str(fields.get(name,""))
        if "length" in rule and len(val)!=int(rule["length"]):errors[name]="invalid_length"
        if rule.get("required") and not val:errors[name]="required"
        if rule.get("digits_only") and val and not val.isdigit():errors[name]="digits_only"
    return {"valid":not errors,"errors":errors}
def reconstitute(fields,mapping):
    ops=[]
    for name,val in fields.items():
        m=(mapping or {}).get(name)
        if m:ops.append({"field":name,"row":int(m.get("row",0)),"col":int(m.get("col",0)),"text":str(val)})
    return {"terminal_ops":ops,"field_count":len(ops)}
