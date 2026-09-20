import time
from collections import deque
_queue=deque(maxlen=50000); _reconcile=deque(maxlen=10000)
def enqueue(direction:str,envelope:dict):
    item={"direction":direction,"message_id":envelope.get("message_id"),"envelope":envelope,"queued_at":time.time(),"status":"queued"}
    _queue.append(item); return item
def queue_status():return {"queued":sum(1 for x in _queue if x["status"]=="queued"),"total":len(_queue)}
def reconcile(left:dict,right:dict,key:str):
    keys=set(left)|set(right); diffs=[]
    for k in keys:
        if left.get(k)!=right.get(k):diffs.append({"record":k,"legacy":left.get(k),"modern":right.get(k)})
    result={"key":key,"checked_at":time.time(),"differences":diffs,"match":not diffs}
    _reconcile.append(result); return result
def reconciliation_tail(limit=100):return list(_reconcile)[-max(1,min(limit,1000)):]
