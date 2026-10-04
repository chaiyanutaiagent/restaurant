from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.dependencies import TokenData, require_any_permission
from app.schemas.shared_kitchen import (
    CompanyIngredientAliasCreateRequest,
    CompanyIngredientCreateRequest,
    CompanyIngredientReceiptRequest,
    CompanyKitchenConfigureRequest,
    CompanyProductionCompleteRequest,
    CompanyProductionDemandCreateRequest,
    CompanyProductionOrderCreateRequest,
    CompanyProductionReverseRequest,
)
from app.services.shared_kitchen_service import SharedKitchenService


router = APIRouter(prefix="/api/v1/company-kitchen", tags=["company-kitchen"])
VIEW_PERMISSION = Depends(
    require_any_permission("company.kitchen.view", "company.kitchen.manage", "system.company.edit")
)
MANAGE_PERMISSION = Depends(
    require_any_permission("company.kitchen.manage", "system.company.edit")
)


def ok(data: Any) -> dict[str, Any]:
    return {"data": data, "meta": {"version": settings.app_version}, "error": None}


def require_write_activation() -> None:
    if not settings.company_kitchen_writes_enabled:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "company_kitchen_write_hold",
                "message": "Company Kitchen writes remain closed until opening-lot, QC, owner and rollout sign-off gates pass",
                "release_stage": "read_only",
            },
        )


async def require_kitchen_release_gate(request: Request) -> None:
    if request.method.upper() not in {"GET", "HEAD", "OPTIONS"}:
        require_write_activation()


router.dependencies.append(Depends(require_kitchen_release_gate))


def release_status(data: dict[str, Any]) -> dict[str, Any]:
    writes_enabled = settings.company_kitchen_writes_enabled
    kitchen_configured = data.get("kitchen") is not None
    ingredient_count = len(data.get("ingredients", []))
    alias_count = len(data.get("aliases", []))
    return {
        "release_stage": "uat_canary" if writes_enabled else "read_only",
        "writes_enabled": writes_enabled,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "stale_after_seconds": 300,
        "hard_holds": [
            "opening_lot_physical_count",
            "stock_owner_signoff",
            "quality_control_release",
            "recall_traceability",
            "physical_device_uat",
        ],
        "checks": [
            {
                "key": "company_context",
                "label": "Company context",
                "state": "pass",
                "detail": "Company scope comes from the signed session",
            },
            {
                "key": "kitchen_configuration",
                "label": "Kitchen and RAW location",
                "state": "pass" if kitchen_configured else "pending",
                "detail": "Configured" if kitchen_configured else "Kitchen/RAW location is not configured",
            },
            {
                "key": "canonical_ingredients",
                "label": "Canonical ingredients",
                "state": "pass" if ingredient_count > 0 else "pending",
                "detail": f"{ingredient_count} canonical ingredient records",
            },
            {
                "key": "brand_alias_mapping",
                "label": "Brand alias mapping",
                "state": "pass" if alias_count > 0 else "pending",
                "detail": f"{alias_count} approved mapping candidates; owner sign-off remains required",
            },
            {
                "key": "opening_lot_physical_count",
                "label": "Opening lot and physical count",
                "state": "hold",
                "detail": "Two-person count, cost, expiry and location evidence is not accepted yet",
            },
            {
                "key": "quality_control_release",
                "label": "QC hold and release",
                "state": "hold",
                "detail": "QC inspection, quarantine and release workflow is not active",
            },
            {
                "key": "recall_traceability",
                "label": "Traceability and recall",
                "state": "hold",
                "detail": "Immutable recall case workflow is not active",
            },
        ],
    }


class CancelRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


@router.get("/dashboard")
async def dashboard(
    current: TokenData = VIEW_PERMISSION,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    data = await SharedKitchenService(db).dashboard(current.company_id)
    data["write_enabled"] = settings.company_kitchen_writes_enabled
    data["release"] = release_status(data)
    return ok(data)


@router.get("/report")
async def report(
    date_from: date = Query(default_factory=lambda: date.today() - timedelta(days=6)),
    date_to: date = Query(default_factory=date.today),
    current: TokenData = VIEW_PERMISSION,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    return ok(await SharedKitchenService(db).report(current.company_id, date_from, date_to))


@router.put("/configuration")
async def configure(
    payload: CompanyKitchenConfigureRequest,
    current: TokenData = MANAGE_PERMISSION,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    require_write_activation()
    return ok(await SharedKitchenService(db).configure(current.company_id, current.user_id, payload))


@router.post("/ingredients", status_code=status.HTTP_201_CREATED)
async def create_ingredient(
    payload: CompanyIngredientCreateRequest,
    current: TokenData = MANAGE_PERMISSION,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    require_write_activation()
    return ok(await SharedKitchenService(db).create_ingredient(current.company_id, current.user_id, payload))


@router.post("/ingredient-aliases", status_code=status.HTTP_201_CREATED)
async def create_alias(
    payload: CompanyIngredientAliasCreateRequest,
    current: TokenData = MANAGE_PERMISSION,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    require_write_activation()
    return ok(await SharedKitchenService(db).create_alias(current.company_id, current.user_id, payload))


@router.post("/receipts", status_code=status.HTTP_201_CREATED)
async def receive(
    payload: CompanyIngredientReceiptRequest,
    current: TokenData = MANAGE_PERMISSION,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    require_write_activation()
    return ok(await SharedKitchenService(db).receive(current.company_id, current.user_id, payload))


@router.post("/demands", status_code=status.HTTP_201_CREATED)
async def create_demand(
    payload: CompanyProductionDemandCreateRequest,
    current: TokenData = MANAGE_PERMISSION,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    require_write_activation()
    return ok(await SharedKitchenService(db).create_demand(current.company_id, current.user_id, payload))


@router.post("/production-orders", status_code=status.HTTP_201_CREATED)
async def create_order(
    payload: CompanyProductionOrderCreateRequest,
    current: TokenData = MANAGE_PERMISSION,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    require_write_activation()
    return ok(await SharedKitchenService(db).create_order(current.company_id, current.user_id, payload))


@router.post("/production-orders/{order_id}/start")
async def start_order(
    order_id: uuid.UUID,
    current: TokenData = MANAGE_PERMISSION,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    require_write_activation()
    return ok(await SharedKitchenService(db).start_order(current.company_id, current.user_id, order_id))


@router.post("/production-orders/{order_id}/complete")
async def complete_order(
    order_id: uuid.UUID,
    payload: CompanyProductionCompleteRequest,
    current: TokenData = MANAGE_PERMISSION,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    require_write_activation()
    return ok(
        await SharedKitchenService(db).complete_order(
            current.company_id, current.user_id, order_id, payload
        )
    )


@router.post("/production-orders/{order_id}/reverse")
async def reverse_order(
    order_id: uuid.UUID,
    payload: CompanyProductionReverseRequest,
    current: TokenData = MANAGE_PERMISSION,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    require_write_activation()
    return ok(
        await SharedKitchenService(db).reverse_order(
            current.company_id,
            current.user_id,
            order_id,
            payload.reversal_key,
            payload.reason,
        )
    )


@router.post("/production-orders/{order_id}/cancel")
async def cancel_order(
    order_id: uuid.UUID,
    payload: CancelRequest,
    current: TokenData = MANAGE_PERMISSION,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    require_write_activation()
    return ok(
        await SharedKitchenService(db).cancel_order(
            current.company_id, current.user_id, order_id, payload.reason
        )
    )
