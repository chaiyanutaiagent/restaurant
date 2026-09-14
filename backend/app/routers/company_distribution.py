from __future__ import annotations

from datetime import date, timedelta
from typing import Any
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.dependencies import TokenData, require_any_permission
from app.schemas.distribution import (
    DistributionActionRequest,
    DistributionDemandCreateRequest,
    DistributionReceiveRequest,
    DistributionRejectRequest,
    DistributionReturnRequest,
    DistributionShipmentPlanRequest,
)
from app.services.distribution_service import DistributionService


router = APIRouter(prefix="/api/v1/company-distribution", tags=["company-distribution"])
VIEW_PERMISSION = Depends(require_any_permission(
    "company.distribution.view", "company.distribution.manage", "system.company.edit"
))
MANAGE_PERMISSION = Depends(require_any_permission("company.distribution.manage", "system.company.edit"))


def ok(data: Any) -> dict[str, Any]:
    return {"data": data, "meta": {"version": settings.app_version}, "error": None}


def require_write_activation() -> None:
    if not settings.company_distribution_writes_enabled:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Company Distribution write path ยังไม่เปิดใช้งาน กรุณาผ่าน rollout sign-off ก่อน",
        )


@router.get("/dashboard")
async def dashboard(
    current: TokenData = VIEW_PERMISSION,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    data = await DistributionService(db).dashboard(current.company_id)
    data["write_enabled"] = settings.company_distribution_writes_enabled
    return ok(data)


@router.get("/report")
async def report(
    date_from: date = Query(default_factory=lambda: date.today() - timedelta(days=6)),
    date_to: date = Query(default_factory=date.today),
    current: TokenData = VIEW_PERMISSION,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    return ok(await DistributionService(db).report(current.company_id, date_from, date_to))


@router.post("/demands", status_code=status.HTTP_201_CREATED)
async def create_demand(
    payload: DistributionDemandCreateRequest,
    current: TokenData = MANAGE_PERMISSION,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    require_write_activation()
    return ok(await DistributionService(db).create_demand(current.company_id, current.user_id, payload))


@router.post("/shipments", status_code=status.HTTP_201_CREATED)
async def plan_shipment(
    payload: DistributionShipmentPlanRequest,
    current: TokenData = MANAGE_PERMISSION,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    require_write_activation()
    return ok(await DistributionService(db).plan_shipment(current.company_id, current.user_id, payload))


@router.post("/shipments/{shipment_id}/dispatch")
async def dispatch(
    shipment_id: uuid.UUID,
    payload: DistributionActionRequest,
    current: TokenData = MANAGE_PERMISSION,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    require_write_activation()
    return ok(await DistributionService(db).dispatch(current.company_id, current.user_id, shipment_id, payload))


@router.post("/shipments/{shipment_id}/receive")
async def receive(
    shipment_id: uuid.UUID,
    payload: DistributionReceiveRequest,
    current: TokenData = MANAGE_PERMISSION,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    require_write_activation()
    return ok(await DistributionService(db).receive(current.company_id, current.user_id, shipment_id, payload))


@router.post("/shipments/{shipment_id}/reject")
async def reject(
    shipment_id: uuid.UUID,
    payload: DistributionRejectRequest,
    current: TokenData = MANAGE_PERMISSION,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    require_write_activation()
    return ok(await DistributionService(db).reject(current.company_id, current.user_id, shipment_id, payload))


@router.post("/shipments/{shipment_id}/return")
async def return_goods(
    shipment_id: uuid.UUID,
    payload: DistributionReturnRequest,
    current: TokenData = MANAGE_PERMISSION,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    require_write_activation()
    return ok(await DistributionService(db).return_goods(current.company_id, current.user_id, shipment_id, payload))


@router.post("/shipments/{shipment_id}/cancel")
async def cancel(
    shipment_id: uuid.UUID,
    payload: DistributionRejectRequest,
    current: TokenData = MANAGE_PERMISSION,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    require_write_activation()
    return ok(await DistributionService(db).cancel(current.company_id, current.user_id, shipment_id, payload))
