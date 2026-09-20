import os,httpx,time
from persistent_state import configured as db_configured,claim_failsafe_dlq,finish_failsafe_dlq

async def replay_one(item,legacy_url,authorization):
    if not legacy_url:return {"ok":False,"error":"legacy_endpoint_not_configured"}
    try:
        headers={"User-Agent":"UNG-GOVBRIDGE-RECOVERY/1"}
        if authorization:headers["Authorization"]=authorization
        async with httpx.AsyncClient(timeout=15.0) as client:
            r=await client.post(legacy_url,json=item["envelope"],headers=headers)
        return {"ok":200<=r.status_code<300,"status":r.status_code,"error":None if 200<=r.status_code<300 else "http_"+str(r.status_code)}
    except Exception as exc:return {"ok":False,"error":type(exc).__name__}

async def recover_batch(limit=25,legacy_url=None,authorization=None):
    if not db_configured():return {"processed":0,"acked":0,"retried":0,"dead_or_pending":0,"reason":"postgres_not_configured"}
    url=(legacy_url or os.getenv("GOVBRIDGE_RECOVERY_URL","")).strip()
    token=authorization or os.getenv("GOVBRIDGE_RECOVERY_AUTHORIZATION","").strip()
    claimed=claim_failsafe_dlq(limit);acked=0;retried=0
    for item in claimed:
        result=await replay_one(item,url,token)
        finish_failsafe_dlq(item["sequence"],bool(result.get("ok")),result.get("error"))
        if result.get("ok"):acked+=1
        else:retried+=1
    return {"processed":len(claimed),"acked":acked,"retried":retried,"dead_or_pending":retried}
