import hashlib,hmac,json,os,time,base64
_progress={};_issued={}
def record(principal,module,completed,errors=0,state_verified=False):
    k=f"{principal}:{module}";_progress[k]={"principal":principal,"module":module,"completed":bool(completed),"errors":int(errors),"state_verified":bool(state_verified),"updated_at":time.time()}
    return _progress[k]
def eligible(principal,modules):
    rows=[_progress.get(f"{principal}:{m}") for m in modules]
    return bool(rows) and all(r and r["completed"] and r["errors"]==0 and r["state_verified"] for r in rows)
def _b64(b):return base64.urlsafe_b64encode(b).decode().rstrip("=")
def issue(principal,modules,ttl=2592000):
    if not eligible(principal,modules):raise ValueError("training_requirements_not_met")
    secret=os.getenv("GOVBRIDGE_TRAINING_SIGNING_KEY","")
    if not secret:raise RuntimeError("training_signing_key_not_configured")
    now=int(time.time());payload={"sub":principal,"modules":modules,"iat":now,"exp":now+int(ttl),"iss":"UNG-GOVBRIDGE-SANDBOX","purpose":"training-compliance"}
    header={"alg":"HS256","typ":"JWT"};h=_b64(json.dumps(header,separators=(",",":")).encode());p=_b64(json.dumps(payload,separators=(",",":")).encode());sig=_b64(hmac.new(secret.encode(),f"{h}.{p}".encode(),hashlib.sha256).digest());token=f"{h}.{p}.{sig}"
    _issued[hashlib.sha256(token.encode()).hexdigest()]={"principal":principal,"modules":modules,"expires":payload["exp"]};return {"token":token,"expires_at":payload["exp"],"credential_type":"signed-jwt"}
def progress(principal):return [v for v in _progress.values() if v["principal"]==principal]
