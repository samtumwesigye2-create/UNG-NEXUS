import time
_profiles={}
def select(session_id,mbps=None,rtt_ms=None):
    mbps=float(mbps or 0);rtt=float(rtt_ms or 9999)
    constrained=mbps<10 or rtt>=150
    p={"mode":"compressed" if constrained else "high-fidelity","terminal":"headless-text-buffer" if constrained else "html5-emulator","sync":"batched-submit" if constrained else "interactive","client_cache":constrained,"measured_mbps":mbps,"rtt_ms":rtt,"selected_at":time.time()}
    _profiles[session_id]=p;return p
def profile(session_id):return _profiles.get(session_id)
def batch(changes):
    return {"encoding":"json-delta","changes":changes,"count":len(changes)}
