from __future__ import annotations

import time

import redis.asyncio as aioredis

from app.config import settings


async def get_redis() -> aioredis.Redis:
    return aioredis.from_url(settings.redis_url, decode_responses=True)


async def check_rate_limit(
    key: str,
    limit: int,
    window_seconds: int,
) -> tuple[bool, int, int]:
    redis = await get_redis()
    window_key = f"rl:{key}:{int(time.time()) // window_seconds}"
    count = await redis.incr(window_key)
    if count == 1:
        await redis.expire(window_key, window_seconds)
    remaining = max(0, limit - count)
    return count <= limit, count, remaining


async def is_api_key_rate_limited(api_key_prefix: str) -> tuple[bool, int]:
    allowed, _, remaining = await check_rate_limit(f"apikey:{api_key_prefix}", 1000, 3600)
    return not allowed, remaining


async def is_webhook_rate_limited(source_ip: str) -> tuple[bool, int]:
    allowed, _, remaining = await check_rate_limit(f"webhook:{source_ip}", 100, 60)
    return not allowed, remaining
