import asyncio,httpx,os
LEGACY=os.getenv("GOVBRIDGE_PARALLEL_LEGACY_URL","").rstrip("/")
MODERN=os.getenv("GOVBRIDGE_PARALLEL_MODERN_URL","").rstrip("/")
async def _call(base,phase,envelope,authorization):
    if not base:return {"ok":False,"error":"endpoint_not_configured"}
    try:
        async with httpx.AsyncClient(timeout=10.0) as c:r=await c.post(base+"/_bridge/"+phase,json=envelope,headers={"Authorization":authorization,"User-Agent":"UNG-GOVBRIDGE-2PC/1"})
        return {"ok":200<=r.status_code<300,"status":r.status_code}
    except Exception as e:return {"ok":False,"error":type(e).__name__}
async def two_phase(envelope,authorization):
    lp,mp=await asyncio.gather(_call(LEGACY,"prepare",envelope,authorization),_call(MODERN,"prepare",envelope,authorization))
    if not(lp["ok"] and mp["ok"]):
        await asyncio.gather(_call(LEGACY,"rollback",envelope,authorization),_call(MODERN,"rollback",envelope,authorization))
        return {"committed":False,"phase":"prepare","legacy":lp,"modern":mp}
    lc,mc=await asyncio.gather(_call(LEGACY,"commit",envelope,authorization),_call(MODERN,"commit",envelope,authorization))
    if not(lc["ok"] and mc["ok"]):
        return {"committed":False,"phase":"commit_in_doubt","legacy":lc,"modern":mc,"requires_reconciliation":True}
    return {"committed":True,"phase":"committed","legacy":lc,"modern":mc}
