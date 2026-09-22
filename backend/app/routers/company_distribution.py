from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
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
            detail={
                "code": "company_distribution_write_hold",
                "message": "Company Distribution writes remain closed until Kitchen, QC, receiver and rollout sign-off gates pass",
                "release_stage": "read_only",
            },
        )


async def require_distribution_release_gate(request: Request) -> None:
    if request.method.upper() not in {"GET", "HEAD", "OPTIONS"}:
        require_write_activation()


router.dependencies.append(Depends(require_distribution_release_gate))


def release_status(data: dict[str, Any]) -> dict[str, Any]:
    writes_enabled = settings.company_distribution_writes_enabled
    demand_count = len(data.get("demands", []))
    shipment_count = len(data.get("shipments", []))
    return {
        "release_stage": "uat_canary" if writes_enabled else "read_only",
        "writes_enabled": writes_enabled,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "stale_after_seconds": 300,
        "hard_holds": [
            "kitchen_write_canary",
            "ready_stock_reconciliation",
            "quality_control_release",
            "branch_receiver_physical_uat",
            "stock_owner_signoff",
        ],
        "checks": [
            {
                "key": "company_context",
                "label": "Company context",
                "state": "pass",
                "detail": "Company scope comes from the signed session",
            },
            {
                "key": "normalized_demand",
                "label": "Normalized demand queue",
                "state": "pass",
                "detail": f"{demand_count} scoped demand records are visible",
            },
            {
                "key": "shipment_reconciliation",
                "label": "Shipment reconciliation",
                "state": "pass" if shipment_count > 0 else "pending",
                "detail": f"{shipment_count} shipment records use the existing Transfer/Stock ledger",
            },
            {
                "key": "kitchen_write_canary",
                "label": "Kitchen write canary",
                "state": "hold",
                "detail": "Kitchen must pass its limited write wave before Distribution can open",
            },
            {
                "key": "quality_control_release",
                "label": "QC release before dispatch",
                "state": "hold",
                "detail": "Held or quarantined lots cannot yet be enforced in dispatch",
            },
            {
                "key": "branch_receiver_physical_uat",
                "label": "Branch receiving UAT",
                "state": "hold",
                "detail": "Partial receive, reject, return and device evidence is not accepted yet",
            },
        ],
    }


@router.get("/dashboard")
async def dashboard(
    current: TokenData = VIEW_PERMISSION,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    data = await DistributionService(db).dashboard(current.company_id)
    data["write_enabled"] = settings.company_distribution_writes_enabled
    data["release"] = release_status(data)
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
