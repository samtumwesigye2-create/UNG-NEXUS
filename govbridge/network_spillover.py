import time,uuid
from persistent_state import enqueue_spillover,spillover as persisted_spillover,configured as persistence_configured
_queue=[]
def route(segment,envelope,backbone_available):
    if backbone_available:return {"route":"private-backbone","queued":False}
    if segment=="atomic":return {"route":"blocked","queued":False,"fail_closed":True}
    if segment=="sandbox":return {"route":"sandbox-only","queued":False}
    item={"id":str(uuid.uuid4()),"segment":segment,"envelope":envelope,"state":"pending","created_at":time.time()}
    durable=enqueue_spillover(item)
    if not durable:_queue.append(item)
    return {"route":"spillover-dlq","queued":True,"durable":durable,"id":item["id"]}
def items():
    return persisted_spillover() if persistence_configured() else list(_queue)
