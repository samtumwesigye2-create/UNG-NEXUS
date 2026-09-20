import time
SEGMENTS={
 "sandbox":{"vlan":100,"profiles":["synthetic-training","emulator","browser"],"production_routes":False,"fail_mode":"isolated"},
 "async":{"vlan":200,"profiles":["event-stream","cdc","registry-update"],"production_routes":True,"fail_mode":"durable-queue"},
 "atomic":{"vlan":300,"profiles":["synchronous-transaction","two-phase-commit"],"production_routes":True,"fail_mode":"fail-closed"},
}
def classify(body):
    if body.get("_sandbox") is True:return "sandbox"
    tier=str(body.get("_criticality_tier") or "").lower()
    return "atomic" if tier in ("1","tier1","tier_1_atomic") else "async"
def enforce(segment,target):
    p=SEGMENTS.get(segment)
    if not p:raise ValueError("unknown_network_segment")
    if segment=="sandbox" and str(target).lower() not in ("sandbox","emulator","synthetic"):raise PermissionError("sandbox_production_route_blocked")
    return {"allowed":True,"segment":segment,"vlan":p["vlan"],"target":target,"policy":p}
def matrix():return SEGMENTS
