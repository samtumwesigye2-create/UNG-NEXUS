import hashlib,hmac,json,os,time
def verify_hmac(raw,signature):
    key=os.getenv("GOVBRIDGE_MAINFRAME_HMAC_KEY","")
    if not key:return False
    expected="sha256="+hmac.new(key.encode(),raw,hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected,signature or "")
def _field(v,n,align="left"):
    s=str(v or "")[:n]
    return (s.ljust(n) if align=="left" else s.rjust(n,"0")).encode("cp500")
def pack_comarea(body):
    d=body.get("comarea_data") or {};p=d.get("payload_fields") or {}
    # Strict 75-byte approved COMAREA profile. No arbitrary copybook execution.
    bal=str(p.get("balance_delta","")).replace("+","").replace("-","")
    buf=b"".join([_field(body.get("transaction_code"),4),_field(body.get("operator_terminal_id"),8),
      _field(d.get("citizen_id"),9),_field(d.get("sector_code"),3),_field(d.get("action_type"),1),
      _field(p.get("family_name"),40),_field(bal,10,"right")])
    if len(buf)!=75:raise ValueError("invalid_comarea_length")
    return buf
def health_stub():
    return {"status":"UNCONFIGURED","mainframe_timestamp":None,"metrics":{},"circuit_breaker_override":False,"live_probe":False}
