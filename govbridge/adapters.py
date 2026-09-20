import os, httpx

AGENCY_ENV = {
    "GOU-UGHUB": ("UGHUB_BASE_URL","UGHUB_API_TOKEN"),
    "GOU-NIRA": ("NIRA_BASE_URL","NIRA_API_TOKEN"),
    "GOU-URA": ("URA_BASE_URL","URA_API_TOKEN"),
    "GOU-URSB": ("URSB_BASE_URL","URSB_API_TOKEN"),
    "GOU-EGP": ("EGP_BASE_URL","EGP_API_TOKEN"),
    "GOU-IFMS": ("IFMS_BASE_URL","IFMS_API_TOKEN"),
    "GOU-UBOS": ("UBOS_BASE_URL","UBOS_API_TOKEN"),
}

def configured(target: str) -> bool:
    pair = AGENCY_ENV.get(target)
    return bool(pair and os.getenv(pair[0], "").strip())

async def send(target: str, envelope: dict):
    if target not in AGENCY_ENV:
        return False, None, None, "unknown_agency"
    base_key, token_key = AGENCY_ENV[target]
    base = os.getenv(base_key, "").rstrip("/")
    token = os.getenv(token_key, "").strip()
    if not base:
        return False, None, None, "adapter_not_configured"
    headers = {"Content-Type":"application/json","User-Agent":"UNG-GOVBRIDGE/1.0"}
    if token:
        headers["Authorization"] = "Bearer " + token
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.post(base + "/v1/ung/inbound", json=envelope, headers=headers)
        data = {}
        try:
            data = r.json()
        except Exception:
            data = {"body": r.text[:2000]}
        return 200 <= r.status_code < 300, r.status_code, data, None if 200 <= r.status_code < 300 else f"http_{r.status_code}"
    except Exception as exc:
        return False, None, None, type(exc).__name__
