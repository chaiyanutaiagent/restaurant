from __future__ import annotations

import asyncio
import hashlib
import logging
import time

from fastapi import HTTPException, Request, status

from app.utils.rate_limiter import check_rate_limit


logger = logging.getLogger(__name__)
_fallback_counts: dict[str, tuple[int, int]] = {}
_fallback_lock = asyncio.Lock()


async def check_public_rate_limit(
    key: str,
    *,
    limit: int,
    window_seconds: int,
) -> bool:
    """Return True when allowed, with a bounded in-process fallback if Redis is down."""
    try:
        allowed, _, _ = await check_rate_limit(f"saas-public:{key}", limit, window_seconds)
        return allowed
    except Exception as exc:  # pragma: no cover - exact Redis failures vary
        logger.warning("public rate limiter using process fallback: %s", type(exc).__name__)

    window = int(time.time()) // window_seconds
    fallback_key = f"{key}:{window}"
    async with _fallback_lock:
        if len(_fallback_counts) > 10_000:
            _fallback_counts.clear()
        stored_window, count = _fallback_counts.get(fallback_key, (window, 0))
        count = count + 1 if stored_window == window else 1
        _fallback_counts[fallback_key] = (window, count)
    return count <= limit


def public_request_rate_key(request: Request, scope: str, subject: str | None = None) -> str:
    """Build a privacy-safe key without retaining an IP address or public token."""
    client = request.client.host if request.client else "unknown"
    material = f"{client}|{subject or '-'}"
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()[:24]
    return f"{scope}:{digest}"


async def require_public_rate_limit(
    request: Request,
    scope: str,
    *,
    subject: str | None = None,
    limit: int,
    window_seconds: int = 60,
) -> None:
    key = public_request_rate_key(request, scope, subject)
    if not await check_public_rate_limit(key, limit=limit, window_seconds=window_seconds):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests; try again later",
        )
