from __future__ import annotations

from datetime import datetime, timezone
import secrets

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.api_integration import APIKey
from app.utils.rate_limiter import is_api_key_rate_limited
from app.utils.security import hash_password, verify_password


def generate_api_key() -> tuple[str, str, str]:
    random_part = secrets.token_hex(20).upper()
    prefix = random_part[:8]
    full_key = f"erppos_{prefix}_{random_part[8:40]}"
    key_hash = hash_password(full_key)
    return full_key, prefix, key_hash


async def verify_api_key(full_key: str, db: AsyncSession) -> APIKey | None:
    if not full_key.startswith("erppos_"):
        return None

    parts = full_key.split("_")
    if len(parts) < 3:
        return None

    prefix = parts[1]
    candidates = list((await db.scalars(
        select(APIKey).where(
            APIKey.key_prefix == prefix,
            APIKey.is_active.is_(True),
            APIKey.revoked_at.is_(None),
        )
    )).all())
    for api_key in candidates:
        if not verify_password(full_key, api_key.key_hash):
            continue
        # Legacy unowned or non-expiring keys must be rotated before use.
        if not api_key.expires_at or api_key.owner_contact.strip().lower() == "unassigned":
            return None
        if api_key.expires_at < datetime.now(timezone.utc):
            return None
        return api_key
    return None


async def get_api_key_auth(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> APIKey:
    key = request.headers.get("X-API-Key")
    if not key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="API key required")

    api_key = await verify_api_key(key, db)
    if api_key is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired API key")

    is_limited, _remaining = await is_api_key_rate_limited(api_key.key_prefix)
    if is_limited:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Rate limit exceeded")

    api_key.last_used_at = datetime.now(timezone.utc)
    await db.commit()
    return api_key


def require_scope(scope: str):
    async def checker(api_key: APIKey = Depends(get_api_key_auth)) -> APIKey:
        # Legacy wildcard keys fail closed. They must be rotated into an
        # explicitly-owned, expiring key before they can call an API.
        if "*" in (api_key.scopes or []) or scope not in (api_key.scopes or []):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"Scope required: {scope}")
        return api_key

    return checker
