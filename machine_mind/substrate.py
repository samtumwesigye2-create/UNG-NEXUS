from __future__ import annotations
from collections import defaultdict, deque
from dataclasses import dataclass
from time import time
from typing import Any

@dataclass
class Spike:
    source:str
    channel:str
    value:float
    timestamp:float

class SparseEventFabric:
    def __init__(self,partitions:int=8,max_events:int=20000):
        self.partitions=max(1,int(partitions))
        per=max(1,max_events//self.partitions)
        self.queues=[deque(maxlen=per) for _ in range(self.partitions)]
        self.counts=defaultdict(int)
        self.last_event_at=None
    def partition(self,source:str,channel:str)->int:
        return hash((source,channel))%self.partitions
    def emit(self,source:str,channel:str,value:float=1.0,timestamp:float|None=None)->dict[str,Any]:
        ts=float(timestamp or time());p=self.partition(source,channel)
        spike=Spike(source,channel,float(value),ts)
        self.queues[p].append(spike)
        self.counts[channel]+=1
        self.last_event_at=ts
        return {"partition":p,"source":source,"channel":channel,"value":float(value),"timestamp":ts}
    def status(self)->dict[str,Any]:
        return {"mode":"sparse-event","partitions":self.partitions,
                "queued":sum(len(q) for q in self.queues),
                "channel_counts":dict(self.counts),"last_event_at":self.last_event_at}
