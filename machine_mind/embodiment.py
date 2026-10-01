from __future__ import annotations
from time import time
from typing import Any

class Embodiment:
    def __init__(self):
        self.sensors={}
        self.actuators={}
        self.body_state={}
        self.last_update=None
    def register_sensor(self,sensor_id:str,kind:str,metadata:dict|None=None):
        self.sensors[sensor_id]={"sensor_id":sensor_id,"kind":kind,"metadata":metadata or {}}
        return self.sensors[sensor_id]
    def register_actuator(self,actuator_id:str,kind:str,metadata:dict|None=None):
        self.actuators[actuator_id]={"actuator_id":actuator_id,"kind":kind,"metadata":metadata or {}}
        return self.actuators[actuator_id]
    def observe(self,sensor_id:str,value:Any,quality:float=1.0,timestamp:float|None=None):
        ts=float(timestamp or time());self.last_update=ts
        self.body_state[sensor_id]={"value":value,"quality":max(0.0,min(1.0,float(quality))),"timestamp":ts}
        return self.body_state[sensor_id]
    def status(self):
        return {"sensor_count":len(self.sensors),"actuator_count":len(self.actuators),
                "body_state":self.body_state,"last_update":self.last_update}
