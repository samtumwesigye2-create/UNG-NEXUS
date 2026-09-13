import hashlib
import hmac


def canonical_request(method: str, path: str, timestamp: str, nonce: str, body: bytes) -> str:
    body_hash = hashlib.sha256(body).hexdigest()
    return '\n'.join((method.upper(), path, timestamp, nonce, body_hash))


def sign_request(secret: str, canonical: str) -> str:
    return hmac.new(secret.encode(), canonical.encode(), hashlib.sha256).hexdigest()


def verify_request(secret: str, canonical: str, signature: str) -> bool:
    return hmac.compare_digest(sign_request(secret, canonical), signature)
