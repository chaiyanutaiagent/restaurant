from __future__ import annotations

import base64
from datetime import datetime, timezone
import hashlib
import hmac
import secrets
import struct
from urllib.parse import quote

from cryptography.fernet import Fernet, InvalidToken

from app.config import settings


TOTP_PERIOD_SECONDS = 30
TOTP_DIGITS = 6
RECOVERY_ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"


def generate_opaque_credential() -> str:
    return secrets.token_urlsafe(48)


def hash_opaque_credential(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def generate_totp_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


def _fernet() -> Fernet:
    material = hashlib.sha256(
        f"platform-mfa-v1:{settings.secret_key}".encode("utf-8")
    ).digest()
    return Fernet(base64.urlsafe_b64encode(material))


def encrypt_totp_secret(secret: str) -> str:
    return _fernet().encrypt(secret.encode("ascii")).decode("ascii")


def decrypt_totp_secret(ciphertext: str) -> str:
    try:
        return _fernet().decrypt(ciphertext.encode("ascii")).decode("ascii")
    except (InvalidToken, UnicodeDecodeError) as exc:
        raise ValueError("Platform MFA secret cannot be decrypted") from exc


def _totp_at(secret: str, counter: int) -> str:
    padding = "=" * ((8 - len(secret) % 8) % 8)
    key = base64.b32decode(f"{secret}{padding}", casefold=True)
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return str(value % (10**TOTP_DIGITS)).zfill(TOTP_DIGITS)


def verify_totp(secret: str, code: str, *, at: datetime | None = None) -> bool:
    return matching_totp_step(secret, code, at=at) is not None


def matching_totp_step(
    secret: str,
    code: str,
    *,
    at: datetime | None = None,
) -> int | None:
    normalized = "".join(character for character in code if character.isdigit())
    if len(normalized) != TOTP_DIGITS:
        return None
    instant = at or datetime.now(timezone.utc)
    counter = int(instant.timestamp()) // TOTP_PERIOD_SECONDS
    for drift in (-1, 0, 1):
        step = counter + drift
        if hmac.compare_digest(_totp_at(secret, step), normalized):
            return step
    return None


def totp_code(secret: str, *, at: datetime | None = None) -> str:
    instant = at or datetime.now(timezone.utc)
    return _totp_at(secret, int(instant.timestamp()) // TOTP_PERIOD_SECONDS)


def build_totp_uri(*, secret: str, username: str) -> str:
    issuer = settings.app_name or "Restaurant Platform"
    label = quote(f"{issuer}:{username}", safe="")
    return (
        f"otpauth://totp/{label}?secret={quote(secret)}"
        f"&issuer={quote(issuer)}&algorithm=SHA1&digits={TOTP_DIGITS}"
        f"&period={TOTP_PERIOD_SECONDS}"
    )


def generate_recovery_codes(count: int = 10) -> list[str]:
    return [
        "-".join(
            "".join(secrets.choice(RECOVERY_ALPHABET) for _ in range(4))
            for _ in range(3)
        )
        for _ in range(count)
    ]


def normalize_recovery_code(code: str) -> str:
    return "".join(character for character in code.upper() if character.isalnum())


def hash_recovery_code(code: str) -> str:
    normalized = normalize_recovery_code(code)
    return hmac.new(
        settings.secret_key.encode("utf-8"),
        f"platform-recovery-v1:{normalized}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
