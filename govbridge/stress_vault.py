import time,uuid
_runs={}
def create(target_concurrency,scenario="mixed-failure"):
    rid=str(uuid.uuid4());_runs[rid]={"run_id":rid,"target_concurrency":int(target_concurrency),"scenario":scenario,"state":"planned","created_at":time.time(),"production_access":False,"synthetic_only":True};return _runs[rid]
def update(rid,state,metrics=None):
    r=_runs[rid];r["state"]=state;r["metrics"]=metrics or {};r["updated_at"]=time.time();return r
def runs():return list(_runs.values())
