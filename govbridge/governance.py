import os,time
SECTOR_PROFILES={
 "financial":{"priority":90,"rate":250,"classification":"restricted","finality":True},
 "identity":{"priority":85,"rate":180,"classification":"restricted","conflict":"authoritative-source"},
 "health":{"priority":85,"rate":160,"classification":"restricted","conflict":"authoritative-source"},
 "land":{"priority":80,"rate":140,"classification":"confidential","conflict":"authoritative-source"},
 "civilian":{"priority":50,"rate":600,"classification":"internal"},
 "emergency":{"priority":100,"rate":1000,"classification":"restricted","latency":"low"},
 "critical-infrastructure":{"priority":100,"rate":1000,"classification":"restricted","latency":"low"},
 "national-security":{"priority":100,"rate":100,"classification":"restricted","cross_domain":"deny-by-default"},
}
def sector_for(message_type:str,payload:dict):
    explicit=str(payload.get("_sector","")).lower()
    if explicit in SECTOR_PROFILES:return explicit
    mt=message_type.lower()
    if any(x in mt for x in ("tax","payment","customs","treasury","revenue")):return "financial"
    if any(x in mt for x in ("identity","citizen","civil-registry")):return "identity"
    if "health" in mt:return "health"
    if "land" in mt or "title" in mt:return "land"
    if any(x in mt for x in ("emergency","incident","dispatch")):return "emergency"
    return "civilian"
def profile(sector):return SECTOR_PROFILES.get(sector,SECTOR_PROFILES["civilian"])
def cross_domain_allowed(sector,payload):
    if sector!="national-security":return True
    # No software-only claim of an air gap: classified transfer requires an approved external guard.
    return bool(os.getenv("GOVBRIDGE_APPROVED_CROSS_DOMAIN_GUARD_URL")) and payload.get("_cross_domain_approved") is True
