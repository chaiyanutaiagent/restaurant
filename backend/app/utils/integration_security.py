from __future__ import annotations

import base64
from datetime import datetime, timezone
import hashlib
import hmac

from cryptography.fernet import Fernet, InvalidToken

from app.config import settings


INTEGRATION_SECRET_PREFIX = "enc:v1:"
WEBHOOK_REPLAY_WINDOW_SECONDS = 300


def _fernet() -> Fernet:
    material = hashlib.sha256(
        f"integration-secret-v1:{settings.secret_key}".encode("utf-8")
    ).digest()
    return Fernet(base64.urlsafe_b64encode(material))


def encrypt_integration_secret(value: str) -> str:
    normalized = value.strip()
    if len(normalized) < 32:
        raise ValueError("Integration secret must be at least 32 characters")
    token = _fernet().encrypt(normalized.encode("utf-8")).decode("ascii")
    return f"{INTEGRATION_SECRET_PREFIX}{token}"


def decrypt_integration_secret(ciphertext: str | None) -> str | None:
    if not ciphertext:
        return None
    if not ciphertext.startswith(INTEGRATION_SECRET_PREFIX):
        raise ValueError("Integration secret is not encrypted; rotate it before use")
    try:
        return _fernet().decrypt(
            ciphertext.removeprefix(INTEGRATION_SECRET_PREFIX).encode("ascii")
        ).decode("utf-8")
    except (InvalidToken, UnicodeDecodeError) as exc:
        raise ValueError("Integration secret cannot be decrypted") from exc


def webhook_signature(secret: str, timestamp: int, body: bytes) -> str:
    signed = str(timestamp).encode("ascii") + b"." + body
    return hmac.new(secret.encode("utf-8"), signed, hashlib.sha256).hexdigest()


def verify_webhook_timestamp(raw_timestamp: str, *, now: datetime | None = None) -> int:
    try:
        timestamp = int(raw_timestamp)
    except (TypeError, ValueError) as exc:
        raise ValueError("Webhook timestamp is invalid") from exc
    current = int((now or datetime.now(timezone.utc)).timestamp())
    if abs(current - timestamp) > WEBHOOK_REPLAY_WINDOW_SECONDS:
        raise ValueError("Webhook timestamp is outside the replay window")
    return timestamp
