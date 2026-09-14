from __future__ import annotations

from datetime import date, timedelta
from typing import Any
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
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
            detail="Company Kitchen write path ยังไม่เปิดใช้งาน กรุณาผ่าน rollout sign-off ก่อน",
        )


class CancelRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


@router.get("/dashboard")
async def dashboard(
    current: TokenData = VIEW_PERMISSION,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    data = await SharedKitchenService(db).dashboard(current.company_id)
    data["write_enabled"] = settings.company_kitchen_writes_enabled
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
