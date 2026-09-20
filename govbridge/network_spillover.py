import time,uuid
_queue=[]
def route(segment,envelope,backbone_available):
    if backbone_available:return {"route":"private-backbone","queued":False}
    if segment=="atomic":return {"route":"blocked","queued":False,"fail_closed":True}
    if segment=="sandbox":return {"route":"sandbox-only","queued":False}
    item={"id":str(uuid.uuid4()),"envelope":envelope,"state":"pending","created_at":time.time()}
    _queue.append(item);return {"route":"spillover-dlq","queued":True,"id":item["id"]}
def items():return list(_queue)
