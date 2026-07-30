from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import asyncio
import os
import tempfile
from pathlib import Path

from fastapi import FastAPI
from fastapi import status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from app.config import settings
from app.database import AsyncSessionLocal, init_db
from app.middleware.branch_context import BranchContextMiddleware
from app.middleware.request_id import RequestIDMiddleware
from app.routers import accounting as accounting_router
from app.routers import api_mgmt, incoming_webhook, public_api, storefront
from app.routers import crm as crm_router
from app.routers import etax as etax_router
from app.routers import hr as hr_router
from app.routers import logistics as logistics_router
from app.routers import payment_gateway as payment_gw_router
from app.routers import restaurant as restaurant_router
from app.routers import payable as payable_router
from app.routers import auth, pos, products, purchase, reports, stock, stock_count as stock_count_router, system, transfer
from app.routers import router
from app.utils.create_superuser import ensure_default_company_seed_in_session
from app.utils.seed_permissions import seed_default_permissions


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    await init_db()
    async with AsyncSessionLocal() as db:
        permissions_table_exists = await db.scalar(
            text("SELECT 1 FROM information_schema.tables WHERE table_name = 'permissions' LIMIT 1")
        )
        if permissions_table_exists:
            await seed_default_permissions(db)
            # FIX S3-D-verify: bootstrap the documented company/admin seed so source-based docker compose matches the verification environment
            await ensure_default_company_seed_in_session(db)
            await db.commit()
    yield


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(BranchContextMiddleware)
app.add_middleware(RequestIDMiddleware)

os.makedirs(settings.upload_dir, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=settings.upload_dir), name="uploads")

app.include_router(router)
app.include_router(auth.router)
app.include_router(system.router)
app.include_router(products.router)
app.include_router(stock.router)
app.include_router(stock_count_router.router)
app.include_router(pos.router)
app.include_router(reports.router)
app.include_router(purchase.router)
app.include_router(transfer.router)
app.include_router(accounting_router.router)
app.include_router(etax_router.router)
app.include_router(payable_router.router)
app.include_router(hr_router.router)
app.include_router(crm_router.router)
app.include_router(api_mgmt.router)
app.include_router(public_api.router)
app.include_router(storefront.router)
app.include_router(incoming_webhook.router)
app.include_router(logistics_router.router)
app.include_router(payment_gw_router.router)
app.include_router(restaurant_router.router)
app.include_router(restaurant_router.public_router)
app.include_router(restaurant_router.qs_router)


@app.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "ok", "version": settings.app_version}


@app.get("/health/live")
async def health_live() -> dict[str, str]:
    return {"status": "ok", "version": settings.app_version}


async def _check_database() -> str:
    async with AsyncSessionLocal() as db:
        await asyncio.wait_for(db.execute(text("SELECT 1")), timeout=5)
    return "ok"


async def _check_redis() -> str:
    import redis.asyncio as aioredis

    redis = aioredis.from_url(settings.redis_url, decode_responses=True)
    try:
        await asyncio.wait_for(redis.ping(), timeout=5)
    finally:
        await redis.aclose()
    return "ok"


def _check_uploads() -> str:
    upload_path = Path(settings.upload_dir)
    upload_path.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=upload_path, prefix=".health-", delete=True):
        pass
    return "ok"


@app.get("/health/ready")
async def health_ready() -> JSONResponse:
    checks: dict[str, dict[str, str]] = {}

    for name, check in (
        ("database", _check_database),
        ("redis", _check_redis),
    ):
        try:
            await check()
            checks[name] = {"status": "ok"}
        except Exception:  # pragma: no cover - runtime dependency failure path
            checks[name] = {"status": "error"}

    try:
        _check_uploads()
        checks["uploads"] = {"status": "ok"}
    except Exception:  # pragma: no cover - runtime dependency failure path
        checks["uploads"] = {"status": "error"}

    ready = all(check["status"] == "ok" for check in checks.values())
    status_code = status.HTTP_200_OK if ready else status.HTTP_503_SERVICE_UNAVAILABLE
    return JSONResponse(
        status_code=status_code,
        content={
            "status": "ok" if ready else "error",
            "checks": checks,
            "version": settings.app_version,
        },
    )


@app.get("/")
async def root() -> dict[str, str]:
    return {"message": "Restaurant POS API", "docs": "/docs"}
