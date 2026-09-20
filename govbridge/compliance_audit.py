import hashlib,hmac,json,os,time,httpx
def signed_event(event):
    body={**event,"timestamp":time.time()}
    key=os.getenv("GOVBRIDGE_AUDIT_SIGNING_KEY","")
    raw=json.dumps(body,sort_keys=True,separators=(",",":"),default=str).encode()
    body["digest"]=hashlib.sha256(raw).hexdigest()
    body["signature"]=hmac.new(key.encode(),raw,hashlib.sha256).hexdigest() if key else None
    return body
async def export(event):
    destinations=[os.getenv("GOVBRIDGE_WORM_AUDIT_URL",""),os.getenv("GOVBRIDGE_SIEM_URL","")]
    async with httpx.AsyncClient(timeout=5.0) as c:
        for url in destinations:
            if url:
                try: await c.post(url,json=event)
                except Exception: pass
