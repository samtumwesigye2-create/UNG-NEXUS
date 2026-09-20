import hashlib,json,time
_ledger={}
def reserve(message_id:str,payload:dict):
    digest=hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(",",":"),default=str).encode()).hexdigest()
    old=_ledger.get(message_id)
    if old:
        return {"created":False,"same_payload":old["digest"]==digest,"record":old}
    rec={"message_id":message_id,"digest":digest,"state":"reserved","created_at":time.time()}
    _ledger[message_id]=rec;return {"created":True,"same_payload":True,"record":rec}
def finalize(message_id:str,status:str):
    if message_id in _ledger:_ledger[message_id]["state"]=status;_ledger[message_id]["finalized_at"]=time.time()
    return _ledger.get(message_id)
def status(message_id:str):return _ledger.get(message_id)
