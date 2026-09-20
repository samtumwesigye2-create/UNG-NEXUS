import os,time
_paths={}
def configure_path(name,kind,priority,private=True):
    allowed={"mpls","dark-fiber","private-cross-connect","private-wan"}
    if kind not in allowed:raise ValueError("unsupported_backbone_kind")
    _paths[name]={"name":name,"kind":kind,"priority":int(priority),"private":bool(private),"state":"configured","updated_at":time.time()}
    return _paths[name]
def health(name,state,latency_ms=None):
    p=_paths[name];p.update({"state":state,"latency_ms":latency_ms,"updated_at":time.time()});return p
def selected():
    healthy=[p for p in _paths.values() if p["state"]=="healthy" and p["private"]]
    return sorted(healthy,key=lambda x:(x["priority"],x.get("latency_ms") or 999999))[0] if healthy else None
def posture():
    return {"mtls_required":True,"tls_min":"1.3","public_mainframe_route":False,
      "ipsec_required":True,"hsm_required":True,
      "fips_provider_configured":bool(os.getenv("GOVBRIDGE_FIPS_CRYPTO_PROVIDER")),
      "hsm_uri_configured":bool(os.getenv("GOVBRIDGE_HSM_KEY_URI")),
      "pqc_profile":os.getenv("GOVBRIDGE_PQC_PROFILE") or None,
      "note":"configuration target only; cryptographic validation and carrier routing are external controls"}
