from __future__ import annotations

from typing import Any
import uuid

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_identity_db, get_restaurant_service_db
from app.dependencies import DeviceTokenData, TokenData, get_current_device, require_permission
from app.schemas.device import (
    DeviceActionReason,
    DeviceContextRead,
    DeviceCreate,
    DevicePairRequest,
    DeviceRenewRequest,
)
from app.services.device_service import DeviceService


router = APIRouter(prefix="/api/v1/system/devices", tags=["devices"])
auth_router = APIRouter(prefix="/api/v1/device-auth", tags=["device-auth"])


def ok(data: Any) -> dict[str, Any]:
    return {
        "data": data,
        "meta": {
            "version": settings.app_version,
            "identity_database": settings.identity_database,
        },
        "error": None,
    }


@router.get("")
async def list_devices(
    branch_id: uuid.UUID | None = Query(default=None),
    current: TokenData = Depends(require_permission("system.device.view")),
    db: AsyncSession = Depends(get_identity_db),
) -> dict[str, Any]:
    rows = await DeviceService(db).list_devices(current, branch_id=branch_id)
    return ok([row.model_dump() for row in rows])


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_device(
    payload: DeviceCreate,
    request: Request,
    current: TokenData = Depends(require_permission("system.device.manage")),
    db: AsyncSession = Depends(get_identity_db),
    restaurant_db: AsyncSession = Depends(get_restaurant_service_db),
) -> dict[str, Any]:
    result = await DeviceService(db, restaurant_db=restaurant_db).create_device(
        current,
        payload,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    return ok(result.model_dump())


@router.post("/{device_id}/pairing-code")
async def rotate_device_pairing_code(
    device_id: uuid.UUID,
    payload: DeviceActionReason,
    request: Request,
    current: TokenData = Depends(require_permission("system.device.manage")),
    db: AsyncSession = Depends(get_identity_db),
    restaurant_db: AsyncSession = Depends(get_restaurant_service_db),
) -> dict[str, Any]:
    result = await DeviceService(db, restaurant_db=restaurant_db).rotate_pairing_code(
        current,
        device_id,
        payload,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    return ok(result.model_dump())


@router.post("/{device_id}/revoke")
async def revoke_device(
    device_id: uuid.UUID,
    payload: DeviceActionReason,
    request: Request,
    current: TokenData = Depends(require_permission("system.device.manage")),
    db: AsyncSession = Depends(get_identity_db),
) -> dict[str, Any]:
    result = await DeviceService(db).revoke_device(
        current,
        device_id,
        payload,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    return ok(result.model_dump())


@auth_router.post("/pair")
async def pair_device(
    payload: DevicePairRequest,
    request: Request,
    db: AsyncSession = Depends(get_identity_db),
    restaurant_db: AsyncSession = Depends(get_restaurant_service_db),
) -> dict[str, Any]:
    result = await DeviceService(db, restaurant_db=restaurant_db).pair_device(
        payload,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    return ok(result.model_dump())


@auth_router.post("/renew")
async def renew_device(
    payload: DeviceRenewRequest,
    request: Request,
    db: AsyncSession = Depends(get_identity_db),
    restaurant_db: AsyncSession = Depends(get_restaurant_service_db),
) -> dict[str, Any]:
    result = await DeviceService(db, restaurant_db=restaurant_db).renew_device(
        payload,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    return ok(result.model_dump())


@auth_router.get("/me")
async def get_device_context(
    current: DeviceTokenData = Depends(get_current_device),
) -> dict[str, Any]:
    result = DeviceContextRead(
        device_id=current.device_id,
        company_id=current.company_id,
        brand_id=current.brand_id,
        branch_id=current.branch_id,
        device_code=current.device_code,
        name=current.name,
        device_type=current.device_type,
        station_key=current.station_key,
        business_type="restaurant",
        target_database="restaurant",
        credential_version=current.credential_version,
        paired_at=current.paired_at,
        last_seen_at=current.last_seen_at,
    )
    return ok(result.model_dump())
