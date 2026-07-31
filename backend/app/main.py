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
from app.database import (
    AsyncSessionLocal,
    PlatformSessionLocal,
    RestaurantSessionLocal,
    current_database_name,
    init_db,
    validate_runtime_database_names,
)
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
from app.services.reference_projector_worker import (
    reference_projector_state,
    run_reference_projector,
)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    await init_db()
    legacy_database_name, platform_database_name, restaurant_database_name = await asyncio.gather(
        current_database_name(AsyncSessionLocal),
        current_database_name(PlatformSessionLocal),
        current_database_name(RestaurantSessionLocal),
    )
    validate_runtime_database_names(
        identity_database=settings.identity_database,
        restaurant_service_database=settings.restaurant_service_database,
        reference_projector_enabled=settings.reference_projector_enabled,
        legacy_database_name=legacy_database_name,
        platform_database_name=platform_database_name,
        restaurant_database_name=restaurant_database_name,
    )
    async with AsyncSessionLocal() as db:
        permissions_table_exists = await db.scalar(
            text("SELECT 1 FROM information_schema.tables WHERE table_name = 'permissions' LIMIT 1")
        )
        if permissions_table_exists:
            await seed_default_permissions(db)
            # FIX S3-D-verify: bootstrap the documented company/admin seed so source-based docker compose matches the verification environment
            await ensure_default_company_seed_in_session(db)
            await db.commit()

    projector_stop: asyncio.Event | None = None
    projector_task: asyncio.Task[None] | None = None
    if settings.reference_projector_enabled:
        projector_stop = asyncio.Event()
        projector_task = asyncio.create_task(
            run_reference_projector(
                projector_stop,
                poll_seconds=settings.reference_projector_poll_seconds,
                batch_size=settings.reference_projector_batch_size,
            ),
            name="platform-reference-projector",
        )

    try:
        yield
    finally:
        if projector_stop is not None:
            projector_stop.set()
        if projector_task is not None:
            try:
                await asyncio.wait_for(projector_task, timeout=5)
            except TimeoutError:  # pragma: no cover - shutdown timeout path
                projector_task.cancel()
                await asyncio.gather(projector_task, return_exceptions=True)


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


async def _check_database(session_factory) -> str:
    async with session_factory() as db:
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
        ("database", lambda: _check_database(AsyncSessionLocal)),
        ("platform_database", lambda: _check_database(PlatformSessionLocal)),
        ("restaurant_database", lambda: _check_database(RestaurantSessionLocal)),
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

    if settings.reference_projector_enabled:
        checks["reference_projector"] = {
            "status": "ok" if reference_projector_state.running else "error"
        }

    ready = all(check["status"] == "ok" for check in checks.values())
    status_code = status.HTTP_200_OK if ready else status.HTTP_503_SERVICE_UNAVAILABLE
    return JSONResponse(
        status_code=status_code,
        content={
            "status": "ok" if ready else "error",
            "checks": checks,
            "runtime": {
                "identity_database": settings.identity_database,
                "restaurant_service_database": settings.restaurant_service_database,
                "reference_projector_enabled": settings.reference_projector_enabled,
                "reference_projector_running": reference_projector_state.running,
                "reference_projector_failed_events": reference_projector_state.failed,
                "reference_projector_loop_errors": reference_projector_state.loop_errors,
                "reference_projector_last_error_type": reference_projector_state.last_error_type,
            },
            "version": settings.app_version,
        },
    )


@app.get("/")
async def root() -> dict[str, str]:
    return {"message": "Restaurant POS API", "docs": "/docs"}
