import httpx,time
async def replay_one(item,legacy_url,authorization):
    if not legacy_url:return {"ok":False,"error":"legacy_endpoint_not_configured"}
    try:
        async with httpx.AsyncClient(timeout=15.0) as c:r=await c.post(legacy_url,json=item["envelope"],headers={"Authorization":authorization,"User-Agent":"UNG-GOVBRIDGE-RECOVERY/1"})
        return {"ok":200<=r.status_code<300,"status":r.status_code}
    except Exception as e:return {"ok":False,"error":type(e).__name__}
