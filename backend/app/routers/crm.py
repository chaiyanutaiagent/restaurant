from __future__ import annotations

from typing import Any
import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.dependencies import TokenData, require_permission
from app.schemas.crm import (
    AdjustPointsRequest,
    CustomerCreate,
    CustomerListItem,
    CustomerPurchaseHistory,
    CustomerRead,
    CustomerSearchResult,
    CustomerTagCreate,
    CustomerTagRead,
    CustomerTierRead,
    CustomerUpdate,
    EarnPointsRequest,
    LoyaltySettingsRead,
    LoyaltySettingsUpdate,
    PointsTransactionRead,
    RedeemPointsRequest,
    RedeemPointsResponse,
)
from app.services.crm_service import CRMService, resolve_public_company_id

router = APIRouter(prefix="/api/v1/crm", tags=["crm"])


def ok(data: Any, meta: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"data": data, "meta": {"version": settings.app_version, **(meta or {})}, "error": None}


@router.get("/settings")
async def get_settings(
    current: TokenData = Depends(require_permission("pos.sale.view")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    row = await CRMService(db).get_loyalty_settings(current.company_id)
    return ok(LoyaltySettingsRead.model_validate(row).model_dump())


@router.patch("/settings")
async def update_settings(
    payload: LoyaltySettingsUpdate,
    current: TokenData = Depends(require_permission("system.company.edit")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    row = await CRMService(db).update_loyalty_settings(current.company_id, payload)
    return ok(LoyaltySettingsRead.model_validate(row).model_dump())


@router.get("/tiers")
async def list_tiers(
    current: TokenData = Depends(require_permission("pos.sale.view")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    rows = await CRMService(db).list_tiers(current.company_id)
    return ok([CustomerTierRead.model_validate(row).model_dump() for row in rows])


@router.get("/tags")
async def list_tags(
    current: TokenData = Depends(require_permission("pos.sale.view")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    rows = await CRMService(db).list_tags(current.company_id)
    return ok([CustomerTagRead.model_validate(row).model_dump() for row in rows])


@router.post("/tags", status_code=status.HTTP_201_CREATED)
async def create_tag(
    payload: CustomerTagCreate,
    current: TokenData = Depends(require_permission("system.user.create")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    row = await CRMService(db).create_tag(current.company_id, payload)
    return ok(CustomerTagRead.model_validate(row).model_dump())


@router.get("/customers/search")
async def search_customers(
    q: str = Query(..., min_length=3),
    limit: int = Query(default=10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    company_id = await resolve_public_company_id(db)
    rows = await CRMService(db).search_customers(company_id, q, limit)
    return ok([CustomerSearchResult.model_validate(row).model_dump() for row in rows])


@router.get("/customers")
async def list_customers(
    tier_id: uuid.UUID | None = Query(default=None),
    tag_id: uuid.UUID | None = Query(default=None),
    is_active: bool | None = Query(default=None),
    search: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    current: TokenData = Depends(require_permission("pos.sale.view")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    rows, total = await CRMService(db).list_customers(
        current.company_id,
        tier_id=tier_id,
        tag_id=tag_id,
        is_active=is_active,
        search=search,
        page=page,
        limit=limit,
    )
    return ok([CustomerListItem.model_validate(row).model_dump() for row in rows], meta={"total": total, "page": page, "limit": limit})


@router.post("/customers", status_code=status.HTTP_201_CREATED)
async def create_customer(
    payload: CustomerCreate,
    current: TokenData = Depends(require_permission("pos.sale.create")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    row = await CRMService(db).create_customer(current.company_id, current.user_id, payload)
    return ok(CustomerRead.model_validate(row).model_dump())


@router.get("/customers/{customer_id}")
async def get_customer(
    customer_id: uuid.UUID,
    current: TokenData = Depends(require_permission("pos.sale.view")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    row = await CRMService(db).get_customer(customer_id, current.company_id)
    return ok(CustomerRead.model_validate(row).model_dump())


@router.patch("/customers/{customer_id}")
async def update_customer(
    customer_id: uuid.UUID,
    payload: CustomerUpdate,
    current: TokenData = Depends(require_permission("pos.sale.create")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    row = await CRMService(db).update_customer(customer_id, current.company_id, payload)
    return ok(CustomerRead.model_validate(row).model_dump())


@router.get("/customers/{customer_id}/history")
async def get_purchase_history(
    customer_id: uuid.UUID,
    current: TokenData = Depends(require_permission("pos.sale.view")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    row = await CRMService(db).get_purchase_history(customer_id, current.company_id)
    return ok(CustomerPurchaseHistory.model_validate(row).model_dump())


@router.get("/customers/{customer_id}/points")
async def get_points_history(
    customer_id: uuid.UUID,
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    current: TokenData = Depends(require_permission("pos.sale.view")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    rows, total = await CRMService(db).get_points_history(customer_id, current.company_id, page=page, limit=limit)
    return ok([PointsTransactionRead.model_validate(row).model_dump() for row in rows], meta={"total": total, "page": page, "limit": limit})


@router.post("/points/earn", status_code=status.HTTP_201_CREATED)
async def earn_points(
    payload: EarnPointsRequest,
    current: TokenData = Depends(require_permission("pos.sale.create")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    row = await CRMService(db).earn_points(current.company_id, current.user_id, payload)
    return ok(PointsTransactionRead.model_validate(row).model_dump() if row is not None else None)


@router.post("/points/redeem")
async def redeem_points(
    payload: RedeemPointsRequest,
    current: TokenData = Depends(require_permission("pos.sale.create")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    row = await CRMService(db).redeem_points(current.company_id, current.user_id, payload)
    return ok(RedeemPointsResponse.model_validate(row).model_dump())


@router.post("/points/adjust")
async def adjust_points(
    payload: AdjustPointsRequest,
    current: TokenData = Depends(require_permission("system.user.edit")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    row = await CRMService(db).adjust_points(
        current.company_id,
        current.user_id,
        payload.customer_id,
        payload.points,
        payload.note,
    )
    return ok(PointsTransactionRead.model_validate(row).model_dump())
