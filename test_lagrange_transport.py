import hashlib
import hmac
import json

import lagrange_transport
import pulsar_transport


def test_build_request_matches_lagrange_hmac_contract(monkeypatch):
    monkeypatch.setattr(lagrange_transport, "LAGRANGE_SERVICE_NAME", "UNG-NEXUS")
    monkeypatch.setattr(lagrange_transport, "LAGRANGE_KEY_ID", "primary")
    monkeypatch.setattr(lagrange_transport, "LAGRANGE_SECRET", "shared-secret")

    envelope = {
        "message_id": "msg-001",
        "source_system": "UGASHIP",
        "target_system": "UNG-PULSAR",
        "message_type": "shipment.updated",
        "payload": {"shipment_id": "S1"},
    }
    body, headers = lagrange_transport.build_request(
        envelope,
        timestamp="1700000000",
        nonce="nonce-001",
    )

    expected_payload = {
        "from": "UNG-NEXUS",
        "to": "UNG-PULSAR",
        "payload": envelope,
        "idempotency_key": "msg-001",
    }
    assert json.loads(body) == expected_payload
    body_hash = hashlib.sha256(body).hexdigest()
    canonical = "\n".join(("POST", "/v1/relay", "1700000000", "nonce-001", body_hash))
    expected_signature = hmac.new(
        b"shared-secret", canonical.encode(), hashlib.sha256
    ).hexdigest()

    assert headers["X-Lagrange-Service"] == "UNG-NEXUS"
    assert headers["X-Lagrange-Key-ID"] == "primary"
    assert headers["X-Lagrange-Timestamp"] == "1700000000"
    assert headers["X-Lagrange-Nonce"] == "nonce-001"
    assert headers["X-Lagrange-Signature"] == expected_signature


def test_pulsar_transport_prefers_lagrange(monkeypatch):
    envelope = {"message_id": "msg-002", "payload": {"probe": True}}
    expected = (True, 1, 202, None, {"status": "accepted"})
    seen = {}

    def fake_lagrange_relay(value):
        seen["envelope"] = value
        return expected

    monkeypatch.setattr(pulsar_transport, "LAGRANGE_BASE_URL", "https://lagrange.example")
    monkeypatch.setattr(pulsar_transport, "relay_to_lagrange", fake_lagrange_relay)

    result = pulsar_transport.relay(envelope, "Bearer janus-token")

    assert result == expected
    assert seen["envelope"] == envelope
