from __future__ import annotations

import os
import time
from collections import OrderedDict
from collections.abc import Callable

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import ValidationError

from .models import LagrangeEnvelope
from .security import canonical_request, verify_request

ADAPTER_VERSION = '1.0.0'
INBOUND_PATH = '/v1/lagrange/inbound'
CAPABILITIES_PATH = '/v1/lagrange/capabilities'
MAX_CLOCK_SKEW_SECONDS = 300
MAX_REPLAY_CACHE = 4096


class _ReplayCache:
    def __init__(self, max_size: int = MAX_REPLAY_CACHE):
        self.max_size = max_size
        self.nonces: OrderedDict[str, int] = OrderedDict()
        self.messages: OrderedDict[str, None] = OrderedDict()

    def _trim(self):
        while len(self.nonces) > self.max_size:
            self.nonces.popitem(last=False)
        while len(self.messages) > self.max_size:
            self.messages.popitem(last=False)

    def seen_nonce(self, nonce: str) -> bool:
        return nonce in self.nonces

    def remember_nonce(self, nonce: str, timestamp: int):
        self.nonces[nonce] = timestamp
        self.nonces.move_to_end(nonce)
        self._trim()

    def seen_message(self, message_id: str) -> bool:
        return message_id in self.messages

    def remember_message(self, message_id: str):
        self.messages[message_id] = None
        self.messages.move_to_end(message_id)
        self._trim()


def create_lagrange_router(system_name: str, capabilities: list[str] | None = None, *, secret: str | None = None, key_id: str | None = None, now: Callable[[], float] = time.time) -> APIRouter:
    configured_secret = secret if secret is not None else os.getenv('LAGRANGE_INBOUND_SECRET', '')
    configured_key_id = key_id if key_id is not None else os.getenv('LAGRANGE_INBOUND_KEY_ID', 'primary')
    declared = sorted({'lagrange_inbound', 'ung_system', *(capabilities or [])})
    replay = _ReplayCache()
    router = APIRouter()

    @router.get(CAPABILITIES_PATH)
    def capabilities_route():
        return {'system': system_name, 'adapter_version': ADAPTER_VERSION, 'schema_version': '1.0', 'capabilities': declared}

    @router.post(INBOUND_PATH, status_code=status.HTTP_202_ACCEPTED)
    async def inbound(request: Request):
        body = await request.body()
        service = request.headers.get('X-Lagrange-Service')
        received_key_id = request.headers.get('X-Lagrange-Key-ID')
        timestamp = request.headers.get('X-Lagrange-Timestamp')
        nonce = request.headers.get('X-Lagrange-Nonce')
        signature = request.headers.get('X-Lagrange-Signature')
        if not configured_secret:
            raise HTTPException(503, 'lagrange_inbound_secret_not_configured')
        if not all((service, received_key_id, timestamp, nonce, signature)):
            raise HTTPException(401, 'lagrange_auth_required')
        if service != 'UNG-LAGRANGE' or received_key_id != configured_key_id:
            raise HTTPException(401, 'lagrange_identity_invalid')
        try:
            timestamp_value = int(timestamp)
        except (TypeError, ValueError):
            raise HTTPException(401, 'lagrange_timestamp_invalid') from None
        if abs(int(now()) - timestamp_value) > MAX_CLOCK_SKEW_SECONDS:
            raise HTTPException(401, 'lagrange_timestamp_stale')
        canonical = canonical_request('POST', INBOUND_PATH, timestamp, nonce, body)
        if not verify_request(configured_secret, canonical, signature):
            raise HTTPException(401, 'lagrange_signature_invalid')
        if replay.seen_nonce(nonce):
            raise HTTPException(409, 'lagrange_nonce_replay')
        replay.remember_nonce(nonce, timestamp_value)
        try:
            envelope = LagrangeEnvelope.model_validate_json(body)
        except ValidationError as exc:
            raise HTTPException(422, exc.errors()) from exc
        if envelope.schema_version != '1.0':
            raise HTTPException(422, 'unsupported_schema_version')
        if envelope.target_system != system_name:
            raise HTTPException(422, 'lagrange_target_mismatch')
        duplicate = replay.seen_message(envelope.message_id)
        if not duplicate:
            replay.remember_message(envelope.message_id)
        return {'accepted': True, 'duplicate': duplicate, 'message_id': envelope.message_id, 'system': system_name}

    return router
