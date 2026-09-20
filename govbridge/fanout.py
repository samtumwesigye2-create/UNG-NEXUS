import asyncio,httpx,os
LEGACY_URL=os.getenv("GOVBRIDGE_PARALLEL_LEGACY_URL","").rstrip("/")
MODERN_URL=os.getenv("GOVBRIDGE_PARALLEL_MODERN_URL","").rstrip("/")
async def _post(url,envelope,authorization):
    if not url:return {"ok":False,"error":"endpoint_not_configured"}
    try:
        async with httpx.AsyncClient(timeout=15.0) as c:r=await c.post(url,json=envelope,headers={"Authorization":authorization,"Content-Type":"application/json","User-Agent":"UNG-GOVBRIDGE-PARALLEL/1"})
        return {"ok":200<=r.status_code<300,"status":r.status_code}
    except Exception as e:return {"ok":False,"error":type(e).__name__}
async def fanout(envelope,authorization):
    legacy,modern=await asyncio.gather(_post(LEGACY_URL,envelope,authorization),_post(MODERN_URL,envelope,authorization))
    return {"legacy":legacy,"modern":modern}
