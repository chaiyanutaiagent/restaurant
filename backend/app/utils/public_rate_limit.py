from __future__ import annotations

import asyncio
import logging
import time

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
