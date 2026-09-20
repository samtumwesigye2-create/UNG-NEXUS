import os,time
_state={}
def circuit_allow(target:str):
    s=_state.get(target,{"failures":0,"opened_until":0})
    return time.time()>=s["opened_until"]
def circuit_success(target:str):
    _state[target]={"failures":0,"opened_until":0}
def circuit_failure(target:str):
    threshold=int(os.getenv("GOVBRIDGE_CIRCUIT_THRESHOLD","5"))
    cooldown=int(os.getenv("GOVBRIDGE_CIRCUIT_COOLDOWN","60"))
    s=_state.get(target,{"failures":0,"opened_until":0}); s["failures"]+=1
    if s["failures"]>=threshold:s["opened_until"]=time.time()+cooldown
    _state[target]=s
def circuit_state():return _state
