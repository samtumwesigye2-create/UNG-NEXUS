PHASES={
 1:{"name":"high-stakes-core","target_range":"1-2M","failure_mode":"fail-closed","preferred_access":"supervised-hubs"},
 2:{"name":"high-volume-operational","target_range":"10-15M","failure_mode":"degrade-gracefully","preferred_access":"hybrid"},
 3:{"name":"ubiquitous-civilian","target_range":"30M+","failure_mode":"degrade-gracefully","preferred_access":"cloud-first"},
}
_current=1
def set_phase(n):
    global _current
    n=int(n)
    if n not in PHASES:raise ValueError("invalid_rollout_phase")
    _current=n;return current()
def current():return {"phase":_current,**PHASES[_current]}
