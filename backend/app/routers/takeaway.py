from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any
import uuid

from fastapi import APIRouter, Depends, Query, status
from fastapi.encoders import jsonable_encoder
from sqlalchemy.ext.asyncio import AsyncSession

from app.business_context import TAKEAWAY
from app.config import settings
from app.dependencies import (
    TokenData,
    get_takeaway_operational_db,
    require_business_type,
    require_company_feature,
    require_permission,
)
from app.schemas.takeaway import (
    TakeawayBranchAvailabilityUpdate,
    TakeawayCatalogItemCreate,
    TakeawayCategoryCreate,
    TakeawayCentralOrderCreate,
    TakeawayCentralOrderStatusUpdate,
    TakeawayCentralRoundCreate,
    TakeawayCreditEntryCreate,
    TakeawayCreditLimitUpdate,
    TakeawayImportDryRun,
    TakeawayProductionBatchCreate,
    TakeawayProductionComplete,
    TakeawayRefundCreate,
    TakeawaySaleCreate,
    TakeawayShiftClose,
    TakeawayShiftOpen,
    TakeawayStockMovementCreate,
    TakeawayTransferCreate,
    TakeawayTransferStatusUpdate,
)
from app.services.takeaway_service import TakeawayService
from app.services.takeaway_import_service import (
    TakeawayImportService,
    validate_takeaway_import_package,
)


router = APIRouter(
    prefix="/api/v1/takeaway",
    tags=["takeaway"],
    dependencies=[
        Depends(require_business_type(TAKEAWAY)),
        Depends(require_company_feature("takeaway")),
    ],
)


def ok(data: Any, meta: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "data": jsonable_encoder(data),
        "meta": {
            "version": settings.app_version,
            "business_type": TAKEAWAY,
            "target_database": "takeaway",
            **(meta or {}),
        },
        "error": None,
    }


@router.get("/status")
async def takeaway_status(
    current: TokenData = Depends(require_permission("takeaway.catalog.view")),
) -> dict[str, Any]:
    return ok(
        {
            "enabled": settings.takeaway_feature_enabled,
            "company_id": current.company_id,
            "brand_id": current.brand_id,
            "branch_id": current.branch_id,
        }
    )


@router.post("/catalog/categories", status_code=status.HTTP_201_CREATED)
async def create_category(
    payload: TakeawayCategoryCreate,
    current: TokenData = Depends(require_permission("takeaway.catalog.manage")),
    db: AsyncSession = Depends(get_takeaway_operational_db),
) -> dict[str, Any]:
    return ok(await TakeawayService(db, current).create_category(payload))


@router.get("/catalog/categories")
async def list_categories(
    brand_id: uuid.UUID,
    current: TokenData = Depends(require_permission("takeaway.catalog.view")),
    db: AsyncSession = Depends(get_takeaway_operational_db),
) -> dict[str, Any]:
    return ok(await TakeawayService(db, current).list_categories(brand_id))


@router.post("/catalog/items", status_code=status.HTTP_201_CREATED)
async def create_catalog_item(
    payload: TakeawayCatalogItemCreate,
    current: TokenData = Depends(require_permission("takeaway.catalog.manage")),
    db: AsyncSession = Depends(get_takeaway_operational_db),
) -> dict[str, Any]:
    return ok(await TakeawayService(db, current).create_catalog_item(payload))


@router.get("/catalog/items")
async def list_catalog(
    brand_id: uuid.UUID,
    branch_id: uuid.UUID | None = None,
    current: TokenData = Depends(require_permission("takeaway.catalog.view")),
    db: AsyncSession = Depends(get_takeaway_operational_db),
) -> dict[str, Any]:
    rows = await TakeawayService(db, current).list_catalog(brand_id, branch_id)
    return ok(
        [
            {
                "item": item,
                "effective_price": price_override if price_override is not None else item.price,
                "is_available": is_available,
            }
            for item, price_override, is_available in rows
        ]
    )


@router.put("/catalog/items/{item_id}/branches/{branch_id}")
async def set_branch_availability(
    item_id: uuid.UUID,
    branch_id: uuid.UUID,
    brand_id: uuid.UUID,
    payload: TakeawayBranchAvailabilityUpdate,
    current: TokenData = Depends(require_permission("takeaway.catalog.manage")),
    db: AsyncSession = Depends(get_takeaway_operational_db),
) -> dict[str, Any]:
    return ok(
        await TakeawayService(db, current).set_branch_availability(
            brand_id=brand_id,
            branch_id=branch_id,
            item_id=item_id,
            price_override=payload.price_override,
            is_available=payload.is_available,
        )
    )


@router.post("/shifts/open", status_code=status.HTTP_201_CREATED)
async def open_shift(
    payload: TakeawayShiftOpen,
    current: TokenData = Depends(require_permission("takeaway.shift.manage")),
    db: AsyncSession = Depends(get_takeaway_operational_db),
) -> dict[str, Any]:
    return ok(await TakeawayService(db, current).open_shift(payload))


@router.post("/shifts/{shift_id}/close")
async def close_shift(
    shift_id: uuid.UUID,
    payload: TakeawayShiftClose,
    current: TokenData = Depends(require_permission("takeaway.shift.manage")),
    db: AsyncSession = Depends(get_takeaway_operational_db),
) -> dict[str, Any]:
    return ok(await TakeawayService(db, current).close_shift(shift_id, payload))


@router.post("/sales", status_code=status.HTTP_201_CREATED)
async def create_sale(
    payload: TakeawaySaleCreate,
    current: TokenData = Depends(require_permission("takeaway.sale.create")),
    db: AsyncSession = Depends(get_takeaway_operational_db),
) -> dict[str, Any]:
    order, pickup_token, replayed = await TakeawayService(db, current).create_sale(payload)
    return ok(
        {"order": order, "pickup_token": pickup_token},
        {"idempotent_replay": replayed},
    )


@router.post("/sales/offline-sync", status_code=status.HTTP_201_CREATED)
async def sync_offline_sale(
    payload: TakeawaySaleCreate,
    current: TokenData = Depends(require_permission("takeaway.sale.create")),
    db: AsyncSession = Depends(get_takeaway_operational_db),
) -> dict[str, Any]:
    order, pickup_token, replayed = await TakeawayService(db, current).create_sale(payload)
    return ok(
        {"order": order, "pickup_token": pickup_token},
        {"idempotent_replay": replayed, "offline": True},
    )


@router.get("/orders")
async def list_orders(
    branch_id: uuid.UUID | None = None,
    fulfillment_status: str | None = Query(default=None, max_length=30),
    limit: int = Query(default=100, ge=1, le=500),
    current: TokenData = Depends(require_permission("takeaway.sale.view")),
    db: AsyncSession = Depends(get_takeaway_operational_db),
) -> dict[str, Any]:
    return ok(
        await TakeawayService(db, current).list_orders(
            branch_id=branch_id,
            fulfillment_status=fulfillment_status,
            limit=limit,
        )
    )


@router.post("/orders/{order_id}/refund")
async def refund_order(
    order_id: uuid.UUID,
    payload: TakeawayRefundCreate,
    current: TokenData = Depends(require_permission("takeaway.sale.refund")),
    db: AsyncSession = Depends(get_takeaway_operational_db),
) -> dict[str, Any]:
    return ok(
        await TakeawayService(db, current).refund_order(
            order_id,
            payload.idempotency_key,
            payload.reason,
        )
    )


@router.post("/kitchen/tickets/{ticket_id}/{next_status}")
async def update_kitchen_ticket(
    ticket_id: uuid.UUID,
    next_status: str,
    current: TokenData = Depends(require_permission("takeaway.kitchen.manage")),
    db: AsyncSession = Depends(get_takeaway_operational_db),
) -> dict[str, Any]:
    return ok(await TakeawayService(db, current).update_kitchen_ticket(ticket_id, next_status))


@router.post("/orders/{order_id}/picked-up")
async def mark_picked_up(
    order_id: uuid.UUID,
    current: TokenData = Depends(require_permission("takeaway.pickup.manage")),
    db: AsyncSession = Depends(get_takeaway_operational_db),
) -> dict[str, Any]:
    return ok(await TakeawayService(db, current).mark_picked_up(order_id))


@router.post("/central/rounds", status_code=status.HTTP_201_CREATED)
async def create_central_round(
    payload: TakeawayCentralRoundCreate,
    current: TokenData = Depends(require_permission("takeaway.central_order.manage")),
    db: AsyncSession = Depends(get_takeaway_operational_db),
) -> dict[str, Any]:
    return ok(
        await TakeawayService(db, current).create_central_round(
            payload.brand_id,
            payload.business_date,
            payload.round_no,
        )
    )


@router.post("/central/orders", status_code=status.HTTP_201_CREATED)
async def create_central_order(
    payload: TakeawayCentralOrderCreate,
    current: TokenData = Depends(require_permission("takeaway.central_order.create")),
    db: AsyncSession = Depends(get_takeaway_operational_db),
) -> dict[str, Any]:
    return ok(await TakeawayService(db, current).create_central_order(payload))


@router.post("/central/orders/{order_id}/status")
async def update_central_order_status(
    order_id: uuid.UUID,
    payload: TakeawayCentralOrderStatusUpdate,
    current: TokenData = Depends(require_permission("takeaway.central_order.manage")),
    db: AsyncSession = Depends(get_takeaway_operational_db),
) -> dict[str, Any]:
    return ok(
        await TakeawayService(db, current).update_central_order_status(order_id, payload.status)
    )


@router.post("/production/batches", status_code=status.HTTP_201_CREATED)
async def create_production_batch(
    payload: TakeawayProductionBatchCreate,
    current: TokenData = Depends(require_permission("takeaway.production.manage")),
    db: AsyncSession = Depends(get_takeaway_operational_db),
) -> dict[str, Any]:
    return ok(await TakeawayService(db, current).create_production_batch(payload))


@router.post("/production/batches/{batch_id}/complete")
async def complete_production_batch(
    batch_id: uuid.UUID,
    payload: TakeawayProductionComplete,
    current: TokenData = Depends(require_permission("takeaway.production.manage")),
    db: AsyncSession = Depends(get_takeaway_operational_db),
) -> dict[str, Any]:
    return ok(
        await TakeawayService(db, current).complete_production_batch(batch_id, payload)
    )


@router.get("/stock")
async def list_stock(
    location_id: uuid.UUID | None = None,
    current: TokenData = Depends(require_permission("takeaway.stock.view")),
    db: AsyncSession = Depends(get_takeaway_operational_db),
) -> dict[str, Any]:
    return ok(await TakeawayService(db, current).list_stock(location_id=location_id))


@router.post("/stock/movements", status_code=status.HTTP_201_CREATED)
async def create_stock_movement(
    payload: TakeawayStockMovementCreate,
    current: TokenData = Depends(require_permission("takeaway.stock.manage")),
    db: AsyncSession = Depends(get_takeaway_operational_db),
) -> dict[str, Any]:
    return ok(await TakeawayService(db, current).create_stock_movement(payload))


@router.post("/transfers", status_code=status.HTTP_201_CREATED)
async def create_transfer(
    payload: TakeawayTransferCreate,
    current: TokenData = Depends(require_permission("takeaway.transfer.manage")),
    db: AsyncSession = Depends(get_takeaway_operational_db),
) -> dict[str, Any]:
    return ok(await TakeawayService(db, current).create_transfer(payload))


@router.post("/transfers/{transfer_id}/status")
async def update_transfer(
    transfer_id: uuid.UUID,
    payload: TakeawayTransferStatusUpdate,
    current: TokenData = Depends(require_permission("takeaway.transfer.manage")),
    db: AsyncSession = Depends(get_takeaway_operational_db),
) -> dict[str, Any]:
    return ok(await TakeawayService(db, current).update_transfer(transfer_id, payload))


@router.put("/credit/accounts")
async def set_credit_limit(
    payload: TakeawayCreditLimitUpdate,
    current: TokenData = Depends(require_permission("takeaway.credit.manage")),
    db: AsyncSession = Depends(get_takeaway_operational_db),
) -> dict[str, Any]:
    return ok(await TakeawayService(db, current).set_credit_limit(payload))


@router.post("/credit/accounts/{account_id}/entries", status_code=status.HTTP_201_CREATED)
async def create_credit_entry(
    account_id: uuid.UUID,
    payload: TakeawayCreditEntryCreate,
    current: TokenData = Depends(require_permission("takeaway.credit.manage")),
    db: AsyncSession = Depends(get_takeaway_operational_db),
) -> dict[str, Any]:
    return ok(await TakeawayService(db, current).create_credit_entry(account_id, payload))


@router.get("/reports/sales-summary")
async def sales_summary(
    date_from: date,
    date_to: date,
    brand_id: uuid.UUID | None = None,
    branch_id: uuid.UUID | None = None,
    current: TokenData = Depends(require_permission("takeaway.report.view")),
    db: AsyncSession = Depends(get_takeaway_operational_db),
) -> dict[str, Any]:
    return ok(
        await TakeawayService(db, current).sales_summary(
            date_from=date_from,
            date_to=date_to,
            brand_id=brand_id,
            branch_id=branch_id,
        )
    )


@router.post("/imports/dry-run")
async def validate_import(
    payload: TakeawayImportDryRun,
    current: TokenData = Depends(require_permission("takeaway.import.dry_run")),
) -> dict[str, Any]:
    report = validate_takeaway_import_package(
        manifest=payload.manifest,
        mapping=payload.mapping,
        records=payload.records,
        expected_company_id=current.company_id,
        expected_brand_id=current.brand_id,
    )
    return ok(report.as_dict())


@router.post("/imports/synthetic-apply", status_code=status.HTTP_201_CREATED)
async def apply_synthetic_import(
    payload: TakeawayImportDryRun,
    current: TokenData = Depends(require_permission("takeaway.import.apply")),
    db: AsyncSession = Depends(get_takeaway_operational_db),
) -> dict[str, Any]:
    batch, replayed = await TakeawayImportService(db, current).apply_synthetic(
        manifest=payload.manifest,
        mapping=payload.mapping,
        records=payload.records,
    )
    return ok(batch, {"idempotent_replay": replayed, "synthetic_only": True})
