import json, os, time, urllib.error, urllib.request

PULSAR_BASE_URL=os.getenv('PULSAR_BASE_URL','https://ung-pulsar-production.up.railway.app').rstrip('/')
DELIVERY_TIMEOUT=float(os.getenv('NEXUS_DELIVERY_TIMEOUT','8'))
DELIVERY_RETRIES=max(1,min(5,int(os.getenv('NEXUS_DELIVERY_RETRIES','3'))))

def relay(envelope:dict,authorization:str):
    body=json.dumps(envelope,separators=(',',':')).encode();last_error=None;last_code=None;last_result=None
    for attempt in range(1,DELIVERY_RETRIES+1):
        req=urllib.request.Request(PULSAR_BASE_URL+'/v1/nexus/inbound',data=body,method='POST',headers={'Content-Type':'application/json','Authorization':authorization,'User-Agent':'UNG-NEXUS/0.6.0'})
        try:
            with urllib.request.urlopen(req,timeout=DELIVERY_TIMEOUT) as r:
                last_code=int(r.status);last_result=json.loads(r.read().decode() or '{}')
                if 200<=last_code<300:return True,attempt,last_code,None,last_result
                last_error=f'http_{last_code}'
        except urllib.error.HTTPError as e:
            last_code=int(e.code);last_error=f'http_{e.code}'
            if 400<=e.code<500 and e.code not in (408,429):break
        except Exception as e:last_error=type(e).__name__
        if attempt<DELIVERY_RETRIES:time.sleep(min(.25*(2**(attempt-1)),1.0))
    return False,attempt,last_code,last_error,last_result
