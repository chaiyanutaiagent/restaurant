from __future__ import annotations

import asyncio
import json
import os
from statistics import median
from time import perf_counter

import httpx
from app.main import app


REQUESTS = 120
CONCURRENCY = 10
P95_LIMIT_MS = 3000.0
MAX_LIMIT_MS = 10000.0
USERNAME = "privacy.platform.owner"
PASSWORD = "Privacy-Platform-Password!"
ENDPOINTS = (
    "/api/v1/platform/dashboard",
    "/api/v1/platform/operations/summary",
    "/api/v1/platform/billing/overview",
    "/api/v1/platform/privacy/requests",
    "/api/v1/platform/support/tickets",
)


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(len(ordered) * fraction) - 1))
    return ordered[index]


async def probe() -> dict[str, object]:
    semaphore = asyncio.Semaphore(CONCURRENCY)
    latencies: list[float] = []
    errors: list[dict[str, object]] = []
    transport = httpx.ASGITransport(app=app)
    async with app.router.lifespan_context(app), httpx.AsyncClient(
        transport=transport,
        base_url="http://beta.local",
        timeout=15.0,
    ) as client:
        login = await client.post(
            "/api/v1/platform/auth/login",
            json={"username": USERNAME, "password": PASSWORD},
        )
        if login.status_code != 200:
            raise RuntimeError(f"Beta load login failed: {login.status_code} {login.text}")
        token = login.json()["data"]["access_token"]

        async def one(index: int) -> None:
            endpoint = ENDPOINTS[index % len(ENDPOINTS)]
            async with semaphore:
                started = perf_counter()
                response = await client.get(endpoint, headers={"Authorization": f"Bearer {token}"})
                elapsed_ms = (perf_counter() - started) * 1000
                latencies.append(elapsed_ms)
                if response.status_code != 200:
                    errors.append({"endpoint": endpoint, "status": response.status_code})

        started = perf_counter()
        await asyncio.gather(*(one(index) for index in range(REQUESTS)))
        total_seconds = perf_counter() - started
    result = {
        "requests": REQUESTS,
        "concurrency": CONCURRENCY,
        "endpoints": list(ENDPOINTS),
        "errors": len(errors),
        "p50_ms": round(median(latencies), 2),
        "p95_ms": round(percentile(latencies, 0.95), 2),
        "max_ms": round(max(latencies), 2),
        "throughput_requests_per_second": round(REQUESTS / total_seconds, 2),
        "thresholds": {"p95_ms": P95_LIMIT_MS, "max_ms": MAX_LIMIT_MS, "errors": 0},
    }
    if errors or result["p95_ms"] > P95_LIMIT_MS or result["max_ms"] > MAX_LIMIT_MS:
        raise RuntimeError(json.dumps({**result, "sample_errors": errors[:5]}, sort_keys=True))
    return result


def main() -> None:
    configured = os.environ.get("SAAS_BETA_DATABASE_NAME", "")
    if not configured.startswith("restaurant_saas_beta_"):
        raise RuntimeError("Beta load probe refuses to run outside an isolated beta database")
    print(json.dumps(asyncio.run(probe()), sort_keys=True))


if __name__ == "__main__":
    main()
