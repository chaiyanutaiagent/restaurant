from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import asyncio
import os

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
    TakeawaySessionLocal,
    current_database_name,
    init_db,
    validate_runtime_database_names,
)
from app.middleware.branch_context import BranchContextMiddleware
from app.middleware.request_id import RequestIDMiddleware
from app.routers import accounting as accounting_router
from app.routers import platform as platform_router
from app.routers import api_mgmt, approvals, device_workspaces, devices, incoming_webhook, public_api, storefront
from app.routers import crm as crm_router
from app.routers import etax as etax_router
from app.routers import hr as hr_router
from app.routers import logistics as logistics_router
from app.routers import payment_gateway as payment_gw_router
from app.routers import takeaway as takeaway_router
from app.routers import restaurant as restaurant_router
from app.routers import payable as payable_router
from app.routers import auth, membership, pos, privacy_support, products, purchase, reports, stock, stock_count as stock_count_router, system, transfer
from app.routers import router
from app.utils.create_superuser import ensure_default_company_seed_in_session
from app.utils.seed_permissions import seed_default_permissions
from app.services.reference_projector_worker import (
    run_reference_projector,
)
from app.services.platform_operations_service import collect_runtime_state
from app.services.takeaway_reference_projector import run_takeaway_reference_projector


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    await init_db()
    legacy_database_name, platform_database_name, restaurant_database_name = await asyncio.gather(
        current_database_name(AsyncSessionLocal),
        current_database_name(PlatformSessionLocal),
        current_database_name(RestaurantSessionLocal),
    )
    takeaway_database_name = (
        await current_database_name(TakeawaySessionLocal)
        if settings.takeaway_feature_enabled and TakeawaySessionLocal is not None
        else None
    )
    validate_runtime_database_names(
        identity_database=settings.identity_database,
        restaurant_service_database=settings.restaurant_service_database,
        reference_projector_enabled=settings.reference_projector_enabled,
        legacy_database_name=legacy_database_name,
        platform_database_name=platform_database_name,
        restaurant_database_name=restaurant_database_name,
        takeaway_service_database=settings.takeaway_service_database,
        takeaway_feature_enabled=settings.takeaway_feature_enabled,
        takeaway_database_name=takeaway_database_name,
    )
    permission_catalog_factories = [AsyncSessionLocal]
    if platform_database_name != legacy_database_name:
        permission_catalog_factories.append(PlatformSessionLocal)
    for session_factory in permission_catalog_factories:
        async with session_factory() as db:
            permissions_table_exists = await db.scalar(
                text("SELECT 1 FROM information_schema.tables WHERE table_name = 'permissions' LIMIT 1")
            )
            if permissions_table_exists:
                await seed_default_permissions(db)
                if session_factory is AsyncSessionLocal:
                    # Keep the documented local company/admin bootstrap on the legacy source only.
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

    takeaway_projector_stop: asyncio.Event | None = None
    takeaway_projector_task: asyncio.Task[None] | None = None
    if settings.takeaway_feature_enabled:
        takeaway_projector_stop = asyncio.Event()
        takeaway_projector_task = asyncio.create_task(
            run_takeaway_reference_projector(
                takeaway_projector_stop,
                poll_seconds=settings.reference_projector_poll_seconds,
            ),
            name="takeaway-reference-projector",
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
        if takeaway_projector_stop is not None:
            takeaway_projector_stop.set()
        if takeaway_projector_task is not None:
            try:
                await asyncio.wait_for(takeaway_projector_task, timeout=5)
            except TimeoutError:  # pragma: no cover - shutdown timeout path
                takeaway_projector_task.cancel()
                await asyncio.gather(takeaway_projector_task, return_exceptions=True)


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    docs_url="/api/docs" if settings.api_docs_enabled else None,
    redoc_url="/api/redoc" if settings.api_docs_enabled else None,
    openapi_url="/api/openapi.json" if settings.api_docs_enabled else None,
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
app.include_router(membership.router)
app.include_router(privacy_support.router)
app.include_router(platform_router.router)
app.include_router(approvals.router)
app.include_router(devices.router)
app.include_router(devices.auth_router)
app.include_router(device_workspaces.router)
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
app.include_router(takeaway_router.router)


@app.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "ok", "version": settings.app_version}


@app.get("/health/live")
async def health_live() -> dict[str, str]:
    return {"status": "ok", "version": settings.app_version}


@app.get("/health/ready")
async def health_ready() -> JSONResponse:
    runtime = await collect_runtime_state()
    ready = runtime.status == "ok"
    status_code = status.HTTP_200_OK if ready else status.HTTP_503_SERVICE_UNAVAILABLE
    return JSONResponse(
        status_code=status_code,
        content={
            "status": "ok" if ready else "error",
            "version": settings.app_version,
        },
    )


@app.get("/")
async def root() -> dict[str, str]:
    return {"message": "Restaurant POS API", "docs": "/docs"}
