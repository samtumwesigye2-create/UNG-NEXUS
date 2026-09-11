import hashlib
import hmac
import json
import os
import time
import urllib.error
import urllib.request
import uuid

LAGRANGE_BASE_URL = os.getenv("LAGRANGE_BASE_URL", "").rstrip("/")
LAGRANGE_SERVICE_NAME = os.getenv("LAGRANGE_SERVICE_NAME", "UNG-NEXUS")
LAGRANGE_KEY_ID = os.getenv("LAGRANGE_KEY_ID", "primary")
LAGRANGE_SECRET = os.getenv("LAGRANGE_SECRET", "")
DELIVERY_TIMEOUT = float(os.getenv("NEXUS_DELIVERY_TIMEOUT", "8"))
DELIVERY_RETRIES = max(1, min(5, int(os.getenv("NEXUS_DELIVERY_RETRIES", "3"))))
RELAY_PATH = "/v1/relay"


def _signature(secret: str, canonical: str) -> str:
    return hmac.new(secret.encode(), canonical.encode(), hashlib.sha256).hexdigest()


def build_request(envelope: dict, *, timestamp: str | None = None, nonce: str | None = None):
    if not LAGRANGE_SECRET:
        raise RuntimeError("LAGRANGE_SECRET is required")
    ts = timestamp or str(int(time.time()))
    request_nonce = nonce or uuid.uuid4().hex
    message_id = str(envelope.get("message_id") or uuid.uuid4())
    payload = {
        "from": LAGRANGE_SERVICE_NAME,
        "to": "UNG-PULSAR",
        "payload": envelope,
        "idempotency_key": message_id,
    }
    body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode()
    body_hash = hashlib.sha256(body).hexdigest()
    canonical = "\n".join(("POST", RELAY_PATH, ts, request_nonce, body_hash))
    headers = {
        "Content-Type": "application/json",
        "X-Lagrange-Service": LAGRANGE_SERVICE_NAME,
        "X-Lagrange-Key-ID": LAGRANGE_KEY_ID,
        "X-Lagrange-Timestamp": ts,
        "X-Lagrange-Nonce": request_nonce,
        "X-Lagrange-Signature": _signature(LAGRANGE_SECRET, canonical),
        "User-Agent": "UNG-NEXUS/0.6.0",
    }
    return body, headers


def relay(envelope: dict):
    if not LAGRANGE_BASE_URL:
        return False, 0, None, "lagrange_not_configured", None
    try:
        body, headers = build_request(envelope)
    except RuntimeError as exc:
        return False, 0, None, str(exc), None

    last_error = None
    last_code = None
    last_result = None
    for attempt in range(1, DELIVERY_RETRIES + 1):
        req = urllib.request.Request(
            LAGRANGE_BASE_URL + RELAY_PATH,
            data=body,
            method="POST",
            headers=headers,
        )
        try:
            with urllib.request.urlopen(req, timeout=DELIVERY_TIMEOUT) as response:
                last_code = int(response.status)
                last_result = json.loads(response.read().decode() or "{}")
                if 200 <= last_code < 300:
                    return True, attempt, last_code, None, last_result
                last_error = f"http_{last_code}"
        except urllib.error.HTTPError as exc:
            last_code = int(exc.code)
            last_error = f"http_{exc.code}"
            if 400 <= exc.code < 500 and exc.code not in (408, 429):
                break
        except Exception as exc:
            last_error = type(exc).__name__

        if attempt < DELIVERY_RETRIES:
            time.sleep(min(0.25 * (2 ** (attempt - 1)), 1.0))

    return False, attempt, last_code, last_error, last_result
