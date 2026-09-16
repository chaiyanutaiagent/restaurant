from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
import hashlib
from typing import Any
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.encoders import jsonable_encoder
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.business_context import TAKEAWAY
from app.config import settings
from app.dependencies import (
    TokenData,
    get_takeaway_operational_db,
    require_business_type,
    require_company_feature,
    require_any_permission,
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
    TakeawayErpEventAcknowledge,
    TakeawayImportDryRun,
    TakeawayOrderPaymentCapture,
    TakeawayOrderingLinkCreate,
    TakeawayProductionBatchCreate,
    TakeawayProductionComplete,
    TakeawayRefundCreate,
    TakeawaySaleCreate,
    TakeawayPublicOrderCreate,
    TakeawayShiftClose,
    TakeawayShiftOpen,
    TakeawayStockMovementCreate,
    TakeawayTransferCreate,
    TakeawayTransferStatusUpdate,
)
from app.services.takeaway_service import TakeawayService
from app.models.takeaway import (
    TakeawayOrder,
    TakeawayOrderingToken,
    TakeawayPickupToken,
    TakeawayReferenceProjection,
)
from app.services.takeaway_import_service import (
    TakeawayImportService,
    validate_takeaway_import_package,
)
from app.utils.public_rate_limit import check_public_rate_limit


router = APIRouter(
    prefix="/api/v1/takeaway",
    tags=["takeaway"],
    dependencies=[
        Depends(require_business_type(TAKEAWAY)),
        Depends(require_company_feature("takeaway")),
    ],
)
public_router = APIRouter(prefix="/api/public/takeaway", tags=["takeaway-public"])


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


async def _ordering_token(
    raw_token: str,
    db: AsyncSession,
) -> TakeawayOrderingToken:
    if not settings.takeaway_feature_enabled or len(raw_token) < 20 or len(raw_token) > 200:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ordering link not found")
    row = await db.scalar(
        select(TakeawayOrderingToken).where(
            TakeawayOrderingToken.token_hash == hashlib.sha256(raw_token.encode()).hexdigest(),
            TakeawayOrderingToken.revoked_at.is_(None),
        )
    )
    if row is None or row.expires_at <= datetime.now(timezone.utc):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ordering link not found")
    return row


def _public_current(row: TakeawayOrderingToken) -> TokenData:
    return TokenData(
        user_id=row.created_by,
        company_id=row.company_id,
        brand_id=row.brand_id,
        branch_id=row.branch_id,
        business_type="takeaway",
        target_database="takeaway",
        permissions=[],
        scope_types=["branch"],
    )


@public_router.get("/ordering/{ordering_token}")
async def public_ordering_menu(
    ordering_token: str,
    request: Request,
    db: AsyncSession = Depends(get_takeaway_operational_db),
) -> dict[str, Any]:
    client = request.client.host if request.client else "unknown"
    if not await check_public_rate_limit(
        f"takeaway-menu:{client}:{hashlib.sha256(ordering_token.encode()).hexdigest()[:16]}",
        limit=120,
        window_seconds=60,
    ):
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Too many requests")
    token_row = await _ordering_token(ordering_token, db)
    service = TakeawayService(db, _public_current(token_row))
    categories = await service.list_categories(token_row.brand_id)
    catalog = await service.list_catalog(token_row.brand_id, token_row.branch_id)
    branch_ref = await db.scalar(
        select(TakeawayReferenceProjection).where(
            TakeawayReferenceProjection.aggregate_type == "branch",
            TakeawayReferenceProjection.aggregate_id == token_row.branch_id,
            TakeawayReferenceProjection.company_id == token_row.company_id,
        )
    )
    return {
        "data": {
            "branch_name": (branch_ref.payload.get("name") if branch_ref else None) or "Takeaway",
            "expires_at": token_row.expires_at,
            "categories": categories,
            "items": [
                {
                    "item": item,
                    "effective_price": price_override if price_override is not None else item.price,
                    "is_available": is_available,
                }
                for item, price_override, is_available in catalog
            ],
        },
        "meta": {"version": settings.app_version},
        "error": None,
    }


@public_router.post("/ordering/{ordering_token}/orders", status_code=status.HTTP_201_CREATED)
async def public_create_order(
    ordering_token: str,
    payload: TakeawayPublicOrderCreate,
    request: Request,
    db: AsyncSession = Depends(get_takeaway_operational_db),
) -> dict[str, Any]:
    client = request.client.host if request.client else "unknown"
    if not await check_public_rate_limit(
        f"takeaway-order:{client}:{hashlib.sha256(ordering_token.encode()).hexdigest()[:16]}",
        limit=20,
        window_seconds=60,
    ):
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Too many requests")
    token_row = await _ordering_token(ordering_token, db)
    order, pickup_token, replayed = await TakeawayService(
        db,
        _public_current(token_row),
    ).create_public_order(payload)
    return {
        "data": {
            "order_number": order.order_number,
            "queue_number": order.queue_number,
            "total_amount": order.total_amount,
            "fulfillment_status": order.fulfillment_status,
            "pickup_token": pickup_token,
        },
        "meta": {"version": settings.app_version, "idempotent_replay": replayed},
        "error": None,
    }


@public_router.get("/pickup/{pickup_token}")
async def public_pickup_status(
    pickup_token: str,
    request: Request,
    db: AsyncSession = Depends(get_takeaway_operational_db),
) -> dict[str, Any]:
    if not settings.takeaway_feature_enabled or len(pickup_token) < 20 or len(pickup_token) > 200:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pickup order not found")
    token_hash = hashlib.sha256(pickup_token.encode()).hexdigest()
    client = request.client.host if request.client else "unknown"
    if not await check_public_rate_limit(
        f"takeaway-pickup:{client}",
        limit=300,
        window_seconds=60,
    ):
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Too many requests")
    token_row = await db.scalar(
        select(TakeawayPickupToken).where(TakeawayPickupToken.token_hash == token_hash)
    )
    if token_row is None or token_row.expires_at <= datetime.now(timezone.utc):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pickup order not found")
    order = await db.get(TakeawayOrder, token_row.order_id)
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pickup order not found")
    return {
        "data": {
            "order_number": order.order_number,
            "queue_number": order.queue_number,
            "total_amount": order.total_amount,
            "status": order.status,
            "fulfillment_status": order.fulfillment_status,
            "paid_at": order.paid_at,
            "picked_up_at": order.picked_up_at,
        },
        "meta": {"version": settings.app_version},
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


@router.get("/shifts")
async def list_shifts(
    limit: int = Query(default=100, ge=1, le=500),
    current: TokenData = Depends(require_permission("takeaway.shift.manage")),
    db: AsyncSession = Depends(get_takeaway_operational_db),
) -> dict[str, Any]:
    return ok(await TakeawayService(db, current).list_shifts(limit=limit))


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


@router.post("/ordering-links", status_code=status.HTTP_201_CREATED)
async def create_ordering_link(
    payload: TakeawayOrderingLinkCreate,
    current: TokenData = Depends(require_permission("takeaway.sale.create")),
    db: AsyncSession = Depends(get_takeaway_operational_db),
) -> dict[str, Any]:
    row, raw_token = await TakeawayService(db, current).create_ordering_link(payload)
    return ok({"token": raw_token, "expires_at": row.expires_at})


@router.post("/orders/{order_id}/capture-payment")
async def capture_order_payment(
    order_id: uuid.UUID,
    payload: TakeawayOrderPaymentCapture,
    current: TokenData = Depends(require_permission("takeaway.sale.create")),
    db: AsyncSession = Depends(get_takeaway_operational_db),
) -> dict[str, Any]:
    order, replayed = await TakeawayService(db, current).capture_order_payment(order_id, payload)
    return ok(order, {"idempotent_replay": replayed})


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


@router.get("/kitchen/tickets")
async def list_kitchen_tickets(
    branch_id: uuid.UUID | None = None,
    ticket_status: str | None = Query(default=None, alias="status", max_length=30),
    limit: int = Query(default=200, ge=1, le=500),
    current: TokenData = Depends(require_permission("takeaway.kitchen.manage")),
    db: AsyncSession = Depends(get_takeaway_operational_db),
) -> dict[str, Any]:
    return ok(
        await TakeawayService(db, current).list_kitchen_tickets(
            branch_id=branch_id, ticket_status=ticket_status, limit=limit
        )
    )


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


@router.get("/central/orders")
async def list_central_orders(
    brand_id: uuid.UUID | None = None,
    branch_id: uuid.UUID | None = None,
    limit: int = Query(default=200, ge=1, le=500),
    current: TokenData = Depends(
        require_any_permission("takeaway.central_order.create", "takeaway.central_order.manage")
    ),
    db: AsyncSession = Depends(get_takeaway_operational_db),
) -> dict[str, Any]:
    return ok(
        await TakeawayService(db, current).list_central_orders(
            brand_id=brand_id, branch_id=branch_id, limit=limit
        )
    )


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


@router.get("/production/batches")
async def list_production_batches(
    brand_id: uuid.UUID | None = None,
    limit: int = Query(default=200, ge=1, le=500),
    current: TokenData = Depends(require_permission("takeaway.production.manage")),
    db: AsyncSession = Depends(get_takeaway_operational_db),
) -> dict[str, Any]:
    return ok(
        await TakeawayService(db, current).list_production_batches(
            brand_id=brand_id, limit=limit
        )
    )


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


@router.get("/stock/locations")
async def list_stock_locations(
    current: TokenData = Depends(require_permission("takeaway.stock.view")),
    db: AsyncSession = Depends(get_takeaway_operational_db),
) -> dict[str, Any]:
    return ok(await TakeawayService(db, current).list_stock_locations())


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


@router.get("/transfers")
async def list_transfers(
    brand_id: uuid.UUID | None = None,
    limit: int = Query(default=200, ge=1, le=500),
    current: TokenData = Depends(require_permission("takeaway.transfer.manage")),
    db: AsyncSession = Depends(get_takeaway_operational_db),
) -> dict[str, Any]:
    return ok(await TakeawayService(db, current).list_transfers(brand_id=brand_id, limit=limit))


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


@router.get("/credit/accounts")
async def list_credit_accounts(
    brand_id: uuid.UUID | None = None,
    branch_id: uuid.UUID | None = None,
    current: TokenData = Depends(require_permission("takeaway.credit.manage")),
    db: AsyncSession = Depends(get_takeaway_operational_db),
) -> dict[str, Any]:
    return ok(
        await TakeawayService(db, current).list_credit_accounts(
            brand_id=brand_id, branch_id=branch_id
        )
    )


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


@router.get("/integrations/erp/events")
async def list_erp_events(
    event_status: str = Query(default="pending", alias="status", pattern="^(pending|processed|failed)$"),
    limit: int = Query(default=200, ge=1, le=500),
    current: TokenData = Depends(require_permission("takeaway.erp.export")),
    db: AsyncSession = Depends(get_takeaway_operational_db),
) -> dict[str, Any]:
    return ok(
        await TakeawayService(db, current).list_erp_events(
            event_status=event_status, limit=limit
        )
    )


@router.post("/integrations/erp/events/{event_id}/acknowledge")
async def acknowledge_erp_event(
    event_id: uuid.UUID,
    payload: TakeawayErpEventAcknowledge,
    current: TokenData = Depends(require_permission("takeaway.erp.acknowledge")),
    db: AsyncSession = Depends(get_takeaway_operational_db),
) -> dict[str, Any]:
    row, replayed = await TakeawayService(db, current).acknowledge_erp_event(event_id, payload)
    return ok(row, {"idempotent_replay": replayed})


@router.get("/integrations/erp/reconciliation")
async def erp_reconciliation(
    current: TokenData = Depends(require_permission("takeaway.erp.export")),
    db: AsyncSession = Depends(get_takeaway_operational_db),
) -> dict[str, Any]:
    return ok(await TakeawayService(db, current).erp_reconciliation())
