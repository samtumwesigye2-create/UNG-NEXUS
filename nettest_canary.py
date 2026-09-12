import json
import os
import time
import urllib.error
import urllib.request

NEXUS_URL = os.environ.get("NEXUS_URL", "https://ung-nexus-production.up.railway.app").rstrip("/")
TOKEN = os.environ["UNG_NETTEST_TOKEN"]

body = {
    "source_system": "UNG-NETTEST",
    "target_system": "UNG-NEXUS",
    "message_type": "acceptance.probe",
    "message_id": "00000000-0000-4000-8000-000000012000",
    "correlation_id": "UNG-NETTEST-12000",
    "payload": {
        "test_run_id": "UNG-NETTEST-12000",
        "sequence": 0,
        "synthetic": True,
        "probe": True,
    },
}

req = urllib.request.Request(
    NEXUS_URL + "/v1/inbound",
    data=json.dumps(body).encode(),
    method="POST",
    headers={
        "Authorization": "Bearer " + TOKEN,
        "Content-Type": "application/json",
        "User-Agent": "UNG-NETTEST-RUNNER/1.0",
    },
)
started = time.perf_counter()
try:
    with urllib.request.urlopen(req, timeout=15) as response:
        data = json.loads(response.read().decode() or "{}")
        message = data.get("message") or {}
        result = {
            "http_status": int(response.status),
            "accepted": data.get("accepted"),
            "duplicate": data.get("duplicate"),
            "message_id": str(message.get("id") or ""),
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
        }
except urllib.error.HTTPError as exc:
    result = {
        "http_status": int(exc.code),
        "error": exc.read().decode(errors="replace"),
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
    }
except Exception as exc:
    result = {
        "http_status": 0,
        "error": type(exc).__name__,
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
    }

print("NETTEST_CANARY " + json.dumps(result, sort_keys=True), flush=True)
time.sleep(3600)
