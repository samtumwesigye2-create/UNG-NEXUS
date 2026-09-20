import os
def enforce(principal,payload,risk):
    if not principal: return False,"principal_required"
    if not principal.get("id"): return False,"principal_identity_required"
    if os.getenv("GOVBRIDGE_REQUIRE_DEVICE_POSTURE","true").lower()=="true":
        posture=payload.get("_device_posture") or {}
        if posture.get("trusted") is not True:return False,"trusted_device_posture_required"
    if risk.get("tier")==1:
        assurance=str(principal.get("assurance_level") or payload.get("_assurance_level") or "").upper()
        if assurance not in ("AAL3","HARDWARE"):return False,"high_assurance_hardware_auth_required"
    return True,"authorized"
