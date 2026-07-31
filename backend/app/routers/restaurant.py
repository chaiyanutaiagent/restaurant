from __future__ import annotations

from datetime import date, datetime, time, timezone
from decimal import Decimal
from typing import Any
import uuid
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy import distinct, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.database import get_db
from app.dependencies import (
    TokenData,
    get_current_user,
    require_any_permission,
    require_permission,
)
from app.models.branch import Branch
from app.models.product import Product
from app.models.pos import SaleOrder, SaleOrderItem
from app.models.stock import StockBalance, StockLocation
from app.models.user import User
from app.models.restaurant import (
    Brand, BrandBranch,
    BranchReplenishmentPolicy,
    DiningTable, DiningSession, DiningOrder, DiningOrderItem, KitchenTicket,
    Recipe, RecipeIngredient, WapShiftClosure, WapShiftClosureItem,
    CentralOrder, CentralOrderItem, CentralOrderShiftClosure, CreditAccount, CreditLedger,
    CreditTopupRequest as CreditTopupRequestModel,
    ProductionBatch, ProductionBatchLine,
)
from app.models.settings import BranchSettings
from app.schemas.restaurant import (
    RecipeCreate, RecipeUpdate, IngredientUsageReport, RawMaterialCreate,
    TableCreate, TableUpdate, FBSetupRequest, FBSettingsUpdate,
    SessionOpen, PlaceOrderRequest,
    CancelRequest, TicketStatusUpdate, SessionCheckoutRequest,
    WapPaidOrderRequest, WapOfflineSyncRequest, WapOfflineSyncItemRead,
    WapOfflineSyncRead, CentralOrderSubmitRequest, CentralOrderQtyUpdateRequest,
    CentralOrderReceiveRequest,
    CreditTopupRequest, CreditAdjustmentRequest, BrandBranchTypeUpdateRequest,
    BrandTransferConfigUpdateRequest, BrandCreateRequest, BrandUpdateRequest,
    BrandBranchUpdateRequest, CreditTopupReviewRequest, CentralProductionCompleteRequest,
    ProductionBatchCreate, ProductionBatchCompleteRequest,
    StoreStockAdjustmentRequest,
    ReplenishmentPolicyUpdateRequest,
    StockCutoverExecuteRequest,
)
from app.services.upload_service import UploadService
from app.services.brand_navigation_service import BrandNavigationService
from app.schemas.product import ProductCreate, ProductListItem
from app.schemas.stock import StockBalanceRead, StockMovementRead
from app.services.dining_service import DiningService
from app.services.fb_setup import (
    DiningTableZonePlan,
    plan_dining_table_zones,
    service_mode_for,
)
from app.services.admin_service import AdminService
from app.schemas.user_mgmt import BranchSettingsRead, BranchSettingsUpdate
from app.services.product_service import ProductService
from app.services.recipe_service import RecipeService
from app.services.production_service import ProductionService, calculate_production_required
from app.services.stock_service import StockService
from app.services.store_inventory_service import StoreInventoryService
from app.services.replenishment_service import ReplenishmentService, serialize_replenishment_policy
from app.services.stock_cutover_service import StockCutoverService
from app.services.transfer_service import TransferService
from app.utils.promptpay import generate_promptpay_payload
from app.schemas.transfer import (
    ApproveTORequest,
    CreateTORequest,
    ShipTORequest,
    ReceiveTORequest,
    TOItemApprove,
    TOItemReceive,
    TOItemCreate,
)

router = APIRouter(prefix="/api/v1/restaurant", tags=["restaurant"])
public_router = APIRouter(prefix="/api/public/menu", tags=["restaurant-public"])
qs_router = APIRouter(prefix="/api/public/qs", tags=["restaurant-qs"])
MIN_CREDIT_TOPUP_AMOUNT = Decimal("500.00")
FB_WORKSPACE_PERMISSIONS = (
    "fb.menu.view",
    "fb.table.manage",
    "fb.order.create",
    "fb.kitchen.manage",
    "fb.recipe.manage",
    "fb.report.view",
    "fb.settings.manage",
)


def ok(data: Any, meta: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"data": data, "meta": {"version": settings.app_version, **(meta or {})}, "error": None}


def _to_float(value: Decimal | int | float | None) -> float:
    return float(value or 0)


def _recipe_purchase_key(product_id: uuid.UUID, unit: str) -> str:
    return f"{product_id}:{unit}"


def _serialize_central_order(order: CentralOrder, branch_name: str | None = None) -> dict[str, Any]:
    linked_closures = [
        link.shift_closure
        for link in order.shift_closure_links
        if link.shift_closure is not None
    ]
    return {
        "id": str(order.id),
        "order_number": order.order_number,
        "status": order.status,
        "branch_id": str(order.branch_id),
        "branch_name": branch_name,
        "shift_closure_id": str(order.shift_closure_id),
        "transfer_order_id": str(order.transfer_order_id) if order.transfer_order_id else None,
        "transfer_order_number": order.transfer_order.to_number if order.transfer_order else None,
        "transfer_order_status": order.transfer_order.status if order.transfer_order else None,
        "transfer_has_discrepancy": order.transfer_order.has_discrepancy if order.transfer_order else False,
        "transfer_discrepancy_note": order.transfer_order.discrepancy_note if order.transfer_order else None,
        "business_date": order.business_date,
        "submitted_by": str(order.submitted_by),
        "approved_by": str(order.approved_by) if order.approved_by else None,
        "packed_by": str(order.packed_by) if order.packed_by else None,
        "shipped_by": str(order.shipped_by) if order.shipped_by else None,
        "received_by": str(order.received_by) if order.received_by else None,
        "submitted_at": order.submitted_at.isoformat() if order.submitted_at else None,
        "approved_at": order.approved_at.isoformat() if order.approved_at else None,
        "packed_at": order.packed_at.isoformat() if order.packed_at else None,
        "shipped_at": order.shipped_at.isoformat() if order.shipped_at else None,
        "received_at": order.received_at.isoformat() if order.received_at else None,
        "credit_reserved_amount": _to_float(order.credit_reserved_amount),
        "credit_captured_amount": _to_float(order.credit_captured_amount),
        "credit_released_amount": _to_float(order.credit_released_amount),
        "note": order.note,
        "closure_count": len(linked_closures) or 1,
        "closure_ids": [str(closure.id) for closure in linked_closures] or [str(order.shift_closure_id)],
        "closure_rounds": [
            {
                "id": str(closure.id),
                "round_no": closure.round_no,
                "total_orders": closure.total_orders,
                "total_amount": _to_float(closure.total_amount),
                "closed_at": closure.closed_at.isoformat() if closure.closed_at else None,
            }
            for closure in linked_closures
        ],
        "items": [
            {
                "id": str(item.id),
                "product_id": str(item.product_id) if item.product_id else None,
                "sku": item.sku,
                "product_name": item.product_name,
                "unit": item.unit,
                "unit_cost": _to_float(item.unit_cost),
                "system_qty": _to_float(item.system_qty),
                "requested_qty": _to_float(item.requested_qty),
                "approved_qty": _to_float(item.approved_qty),
                "shipped_qty": _to_float(item.shipped_qty),
                "received_qty": _to_float(item.received_qty),
                "in_transit_qty": (
                    _to_float(max(Decimal(item.shipped_qty or 0) - Decimal(item.received_qty or 0), Decimal("0")))
                    if order.status in {"shipped", "partially_received"}
                    else 0.0
                ),
                "discrepancy_qty": (
                    _to_float(max(Decimal(item.shipped_qty or 0) - Decimal(item.received_qty or 0), Decimal("0")))
                    if order.status == "received"
                    else 0.0
                ),
                "requested_amount": _to_float(item.requested_amount),
                "approved_amount": _to_float(item.approved_amount),
                "shipped_amount": _to_float(item.shipped_amount),
                "source": item.source,
            }
            for item in order.items
        ],
    }


def _serialize_shift_closure(
    closure: WapShiftClosure,
    closed_by_name: str | None = None,
    include_items: bool = False,
) -> dict[str, Any]:
    central_order = closure.central_orders[0] if closure.central_orders else None
    if not central_order and closure.central_order_links:
        central_order = closure.central_order_links[0].central_order
    data: dict[str, Any] = {
        "id": str(closure.id),
        "brand_id": str(closure.brand_id) if closure.brand_id else None,
        "branch_id": str(closure.branch_id),
        "business_date": closure.business_date,
        "round_no": closure.round_no,
        "closed_by": str(closure.closed_by),
        "closed_by_name": closed_by_name,
        "closed_at": closure.closed_at.isoformat() if closure.closed_at else None,
        "total_orders": closure.total_orders,
        "total_amount": _to_float(closure.total_amount),
        "central_order_id": str(central_order.id) if central_order else None,
        "central_order_number": central_order.order_number if central_order else None,
        "central_order_status": central_order.status if central_order else None,
    }
    if include_items:
        data["items"] = [
            {
                "id": str(item.id),
                "item_type": item.item_type,
                "product_id": str(item.product_id) if item.product_id else None,
                "sku": item.sku,
                "product_name": item.product_name,
                "qty": _to_float(item.qty),
                "unit": item.unit,
                "amount": _to_float(item.amount),
                "source": item.source,
            }
            for item in closure.items
        ]
    return data


async def _load_central_order(
    db: AsyncSession,
    order_id: uuid.UUID,
    company_id: uuid.UUID,
    *,
    lock: bool = False,
) -> CentralOrder:
    statement = (
        select(CentralOrder)
        .options(
            selectinload(CentralOrder.items),
            selectinload(CentralOrder.transfer_order),
            selectinload(CentralOrder.shift_closure_links).selectinload(CentralOrderShiftClosure.shift_closure),
        )
        .where(CentralOrder.id == order_id, CentralOrder.company_id == company_id)
    )
    if lock:
        statement = statement.with_for_update()
    order = await db.scalar(statement)
    if not order:
        raise HTTPException(status_code=404, detail="ไม่พบใบสั่งสินค้า")
    return order


def _require_central_status(order: CentralOrder, allowed: list[str]) -> None:
    if order.status not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"สถานะปัจจุบัน {order.status} ไม่สามารถทำรายการนี้ได้",
        )


async def _load_brand_for_slug(
    db: AsyncSession,
    company_id: uuid.UUID,
    slug: str | None,
) -> Brand | None:
    if not slug:
        return None
    brand = await db.scalar(
        select(Brand).where(
            Brand.company_id == company_id,
            Brand.slug == slug,
            Brand.is_active.is_(True),
        )
    )
    if not brand:
        raise HTTPException(status_code=404, detail="ไม่พบแบรนด์")
    return brand


def _require_brand_assignment(current: TokenData, brand: Brand | None) -> None:
    if (
        brand is not None
        and current.brand_id is not None
        and brand.id != current.brand_id
    ):
        raise HTTPException(status_code=404, detail="ไม่พบแบรนด์")


async def _ensure_brand_branch(
    db: AsyncSession,
    company_id: uuid.UUID,
    branch_id: uuid.UUID,
    brand: Brand | None,
) -> BrandBranch | None:
    if not brand:
        return None
    brand_branch = await db.scalar(
        select(BrandBranch).where(
            BrandBranch.company_id == company_id,
            BrandBranch.brand_id == brand.id,
            BrandBranch.branch_id == branch_id,
            BrandBranch.is_active.is_(True),
        ).limit(1)
    )
    if not brand_branch:
        raise HTTPException(status_code=403, detail="สาขานี้ไม่ได้เปิดใช้แบรนด์นี้")
    return brand_branch


def _money(value: Decimal | int | float | None) -> Decimal:
    return Decimal(str(value or 0)).quantize(Decimal("0.01"))


async def _get_or_create_credit_account(
    db: AsyncSession,
    company_id: uuid.UUID,
    brand_id: uuid.UUID,
    branch_id: uuid.UUID,
) -> CreditAccount:
    account = await db.scalar(
        select(CreditAccount).where(
            CreditAccount.company_id == company_id,
            CreditAccount.brand_id == brand_id,
            CreditAccount.branch_id == branch_id,
        )
    )
    if account:
        return account
    account = CreditAccount(
        company_id=company_id,
        brand_id=brand_id,
        branch_id=branch_id,
        credit_limit=Decimal("0"),
        balance=Decimal("0"),
        reserved_amount=Decimal("0"),
        is_active=True,
    )
    db.add(account)
    await db.flush()
    return account


def _available_credit(account: CreditAccount) -> Decimal:
    return _money(account.balance) - _money(account.reserved_amount)


def _add_credit_ledger(
    db: AsyncSession,
    account: CreditAccount,
    entry_type: str,
    amount: Decimal,
    user_id: uuid.UUID,
    reference_type: str | None = None,
    reference_id: str | None = None,
    note: str | None = None,
) -> None:
    db.add(CreditLedger(
        account_id=account.id,
        company_id=account.company_id,
        brand_id=account.brand_id,
        branch_id=account.branch_id,
        entry_type=entry_type,
        amount=_money(amount),
        balance_after=_money(account.balance),
        reserved_after=_money(account.reserved_amount),
        reference_type=reference_type,
        reference_id=reference_id,
        note=note,
        created_by=user_id,
    ))


def _serialize_credit_account(account: CreditAccount, branch_name: str | None = None) -> dict[str, Any]:
    return {
        "id": str(account.id),
        "brand_id": str(account.brand_id),
        "branch_id": str(account.branch_id),
        "branch_name": branch_name,
        "credit_limit": _to_float(account.credit_limit),
        "balance": _to_float(account.balance),
        "reserved_amount": _to_float(account.reserved_amount),
        "available_credit": _to_float(_available_credit(account)),
        "is_active": account.is_active,
    }


def _serialize_credit_topup_request(
    request: CreditTopupRequestModel,
    branch_name: str | None = None,
) -> dict[str, Any]:
    return {
        "id": str(request.id),
        "brand_id": str(request.brand_id),
        "branch_id": str(request.branch_id),
        "branch_name": branch_name,
        "account_id": str(request.account_id),
        "amount": _to_float(request.amount),
        "status": request.status,
        "slip_url": request.slip_url,
        "note": request.note,
        "requested_by": str(request.requested_by),
        "reviewed_by": str(request.reviewed_by) if request.reviewed_by else None,
        "reviewed_at": request.reviewed_at.isoformat() if request.reviewed_at else None,
        "review_note": request.review_note,
        "created_at": request.created_at.isoformat() if request.created_at else None,
    }


def _serialize_brand_transfer_config(brand: Brand) -> dict[str, Any]:
    return {
        "central_branch_id": str(brand.central_branch_id) if brand.central_branch_id else None,
        "central_location_id": str(brand.central_location_id) if brand.central_location_id else None,
        "central_ready_location_id": (
            str(brand.central_ready_location_id) if brand.central_ready_location_id else None
        ),
    }


def _serialize_stock_area_location(
    location: StockLocation | None,
    *,
    branch_id: uuid.UUID | None = None,
    branch_code: str | None = None,
    branch_name: str | None = None,
) -> dict[str, Any]:
    return {
        "branch_id": str(branch_id or location.branch_id) if (branch_id or location) else None,
        "branch_code": branch_code,
        "branch_name": branch_name,
        "location_id": str(location.id) if location else None,
        "location_code": location.code if location else None,
        "location_name": location.name if location else None,
        "is_configured": bool(
            location
            and location.is_active
            and location.deleted_at is None
            and (branch_id is None or location.branch_id == branch_id)
        ),
    }


async def _resolve_brand_stock_area_location(
    db: AsyncSession,
    company_id: uuid.UUID,
    brand: Brand,
    area: str,
    branch_id: uuid.UUID | None = None,
) -> StockLocation:
    if area == "production":
        location_id = brand.central_location_id
    elif area == "backoffice":
        location_id = brand.central_ready_location_id
    elif area == "storefront":
        if branch_id is None:
            raise HTTPException(status_code=400, detail="กรุณาเลือกสาขาหน้าร้าน")
        location_id = await db.scalar(
            select(BrandBranch.store_location_id).where(
                BrandBranch.company_id == company_id,
                BrandBranch.brand_id == brand.id,
                BrandBranch.branch_id == branch_id,
                BrandBranch.is_active.is_(True),
            )
        )
    else:
        raise HTTPException(status_code=400, detail="พื้นที่สต็อกไม่ถูกต้อง")

    location = await db.get(StockLocation, location_id) if location_id else None
    if (
        location is None
        or location.company_id != company_id
        or location.deleted_at is not None
        or not location.is_active
    ):
        raise HTTPException(status_code=409, detail="ยังไม่ได้ตั้งค่าคลังสำหรับพื้นที่นี้")
    if area == "storefront" and location.branch_id != branch_id:
        raise HTTPException(status_code=409, detail="คลังหน้าร้านไม่ตรงกับสาขาที่เลือก")
    return location


def _serialize_brand_credit_payment_config(brand: Brand) -> dict[str, Any]:
    theme_config = brand.theme_config or {}
    return {
        "credit_topup_qr_url": theme_config.get("credit_topup_qr_url"),
    }


def _serialize_brand(brand: Brand, branches: list[BrandBranch] | None = None) -> dict[str, Any]:
    return {
        "id": str(brand.id),
        "company_id": str(brand.company_id),
        "slug": brand.slug,
        "name": brand.name,
        "storefront_mode": brand.storefront_mode,
        "theme_config": brand.theme_config or {},
        "is_active": brand.is_active,
        "central_branch_id": str(brand.central_branch_id) if brand.central_branch_id else None,
        "central_location_id": str(brand.central_location_id) if brand.central_location_id else None,
        "central_ready_location_id": (
            str(brand.central_ready_location_id) if brand.central_ready_location_id else None
        ),
        "branches": [
            {
                "id": str(item.id),
                "branch_id": str(item.branch_id),
                "branch_name": item.branch.name if item.branch else "",
                "branch_type": item.branch_type,
                "store_location_id": str(item.store_location_id) if item.store_location_id else None,
                "is_active": item.is_active,
            }
            for item in (branches if branches is not None else brand.branches)
        ],
        "created_at": brand.created_at.isoformat() if brand.created_at else None,
        "updated_at": brand.updated_at.isoformat() if brand.updated_at else None,
    }


async def _get_brand_transfer_config(
    db: AsyncSession,
    company_id: uuid.UUID,
    brand: Brand,
    branch_id: uuid.UUID,
) -> tuple[BrandBranch | None, uuid.UUID | None, uuid.UUID | None, uuid.UUID | None]:
    brand_branch = await db.scalar(
        select(BrandBranch).where(
            BrandBranch.company_id == company_id,
            BrandBranch.brand_id == brand.id,
            BrandBranch.branch_id == branch_id,
            BrandBranch.is_active.is_(True),
        )
    )
    return (
        brand_branch,
        brand.central_branch_id,
        brand.central_ready_location_id,
        brand_branch.store_location_id if brand_branch else None,
    )


async def _create_transfer_for_central_order(
    db: AsyncSession,
    order: CentralOrder,
    user_id: uuid.UUID,
) -> uuid.UUID | None:
    if not order.brand_id:
        return None
    if order.transfer_order_id:
        return order.transfer_order_id
    brand = await db.get(Brand, order.brand_id)
    if not brand:
        raise HTTPException(status_code=409, detail="ไม่พบแบรนด์ของใบสั่งสินค้า")
    _brand_branch, from_branch_id, from_location_id, to_location_id = await _get_brand_transfer_config(
        db,
        order.company_id,
        brand,
        order.branch_id,
    )
    if not from_branch_id or not from_location_id or not to_location_id:
        raise HTTPException(
            status_code=409,
            detail="กรุณาตั้งค่าสาขากลาง คลังพร้อมส่ง (READY) และคลังร้านก่อนจัดส่ง",
        )
    if from_location_id == to_location_id:
        raise HTTPException(status_code=409, detail="คลัง READY และคลังร้านต้องเป็นคนละคลัง")
    transfer_items = [
        TOItemCreate(product_id=item.product_id, qty_requested=item.shipped_qty)
        for item in order.items
        if item.product_id and Decimal(item.shipped_qty or 0) > 0
    ]
    if any(not item.product_id and Decimal(item.shipped_qty or 0) > 0 for item in order.items):
        raise HTTPException(status_code=400, detail="สินค้าที่จัดส่งทุกบรรทัดต้องผูกกับ Product ใน stock")
    if not transfer_items:
        raise HTTPException(status_code=400, detail="ไม่มีสินค้าที่ส่งจริงสำหรับสร้าง Transfer")

    service = TransferService(db)
    transfer = await service.create_to(
        order.company_id,
        user_id,
        CreateTORequest(
            from_branch_id=from_branch_id,
            to_branch_id=order.branch_id,
            from_location_id=from_location_id,
            to_location_id=to_location_id,
            note=f"Auto-created from central order {order.order_number}",
            items=transfer_items,
        ),
        commit=False,
    )
    order.transfer_order_id = transfer.id
    order.transfer_order = transfer
    transfer = await service.submit_to(
        transfer.id,
        order.company_id,
        user_id,
        commit=False,
    )
    approved = [
        TOItemApprove(item_id=item.id, qty_approved=item.qty_requested)
        for item in transfer.items
    ]
    transfer = await service.approve_to(
        transfer.id,
        order.company_id,
        user_id,
        ApproveTORequest(items=approved, note=f"Auto-approved from {order.order_number}"),
        commit=False,
    )
    transfer = await service.ship_to(
        transfer.id,
        order.company_id,
        user_id,
        ShipTORequest(note=f"Auto-shipped from {order.order_number}"),
        commit=False,
    )
    order.transfer_order = transfer
    return transfer.id


async def _receive_transfer_for_central_order(
    db: AsyncSession,
    order: CentralOrder,
    user_id: uuid.UUID,
    payload: CentralOrderReceiveRequest | None = None,
) -> None:
    if not order.transfer_order_id:
        if order.brand_id is None:
            requested_by_id = {
                item.item_id: Decimal(str(item.qty_received))
                for item in (payload.items if payload else [])
            }
            for item in order.items:
                item.received_qty = requested_by_id.get(item.id, Decimal(str(item.shipped_qty or 0)))
            order.received_by = user_id
            order.status = "received" if payload is None or payload.finalize else "partially_received"
            order.received_at = datetime.now(timezone.utc) if order.status == "received" else None
            return
        raise HTTPException(status_code=409, detail="ใบสั่งนี้ยังไม่มี Transfer ที่จัดส่ง")
    service = TransferService(db)
    transfer = await service.get_to(order.transfer_order_id, order.company_id)
    if transfer.status not in {"in_transit", "partially_received"}:
        raise HTTPException(status_code=409, detail="Transfer นี้ไม่อยู่ระหว่างจัดส่งหรือรับบางส่วน")

    order_items_by_id = {item.id: item for item in order.items}
    if payload and payload.items:
        requested_by_id = {item.item_id: item for item in payload.items}
        if len(requested_by_id) != len(payload.items) or set(requested_by_id) != set(order_items_by_id):
            raise HTTPException(status_code=400, detail="รายการรับสินค้าต้องตรงกับใบสั่งทุกบรรทัดและห้ามซ้ำ")
        target_by_product = {
            item.product_id: Decimal(str(requested_by_id[item.id].qty_received))
            for item in order.items
            if item.product_id is not None
        }
    else:
        target_by_product = {
            item.product_id: Decimal(str(item.shipped_qty or 0))
            for item in order.items
            if item.product_id is not None
        }
    transfer_products = [item.product_id for item in transfer.items]
    if len(set(transfer_products)) != len(transfer_products):
        raise HTTPException(status_code=409, detail="Transfer มีสินค้าซ้ำ ไม่สามารถจับคู่ยอดรับอัตโนมัติได้")
    if set(transfer_products) != set(target_by_product):
        raise HTTPException(status_code=409, detail="รายการสินค้าใน Transfer ไม่ตรงกับใบสั่ง")

    received_transfer = await service.receive_to(
        transfer.id,
        order.company_id,
        user_id,
        ReceiveTORequest(
            items=[
                TOItemReceive(
                    item_id=item.id,
                    qty_received=target_by_product[item.product_id],
                )
                for item in transfer.items
            ],
            finalize=payload.finalize if payload else True,
            note=payload.note if payload else f"รับสินค้าจาก {order.order_number}",
        ),
        commit=False,
    )
    received_by_product = {
        item.product_id: Decimal(str(item.qty_received or 0))
        for item in received_transfer.items
    }
    for item in order.items:
        if item.product_id is not None:
            item.received_qty = received_by_product[item.product_id]
    order.received_by = user_id
    if received_transfer.status == "completed":
        order.status = "received"
        order.received_at = datetime.now(timezone.utc)
    else:
        order.status = "partially_received"
        order.received_at = None


# ── Brand Admin ───────────────────────────────────────────────────────────────

@router.get("/me/brand-navigation")
async def get_my_brand_navigation(
    current: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    return ok(await BrandNavigationService(db).list_for_user(current))


@router.get("/brands")
async def list_brands(
    include_inactive: bool = Query(default=True),
    current: TokenData = Depends(require_permission("fb.settings.manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    q = (
        select(Brand)
        .options(selectinload(Brand.branches).selectinload(BrandBranch.branch))
        .where(Brand.company_id == current.company_id)
        .order_by(Brand.name)
    )
    if not include_inactive:
        q = q.where(Brand.is_active.is_(True))
    brands = (await db.scalars(q)).all()
    return ok([_serialize_brand(brand) for brand in brands])


@router.post("/brands", status_code=status.HTTP_201_CREATED)
async def create_brand(
    payload: BrandCreateRequest,
    current: TokenData = Depends(require_permission("fb.settings.manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    slug = payload.slug.strip().lower()
    name = payload.name.strip()
    if not slug or not name:
        raise HTTPException(status_code=400, detail="กรุณาระบุ slug และชื่อแบรนด์")
    exists = await db.scalar(
        select(Brand.id).where(Brand.company_id == current.company_id, Brand.slug == slug).limit(1)
    )
    if exists:
        raise HTTPException(status_code=400, detail="slug นี้ถูกใช้แล้ว")
    brand = Brand(
        company_id=current.company_id,
        slug=slug,
        name=name,
        storefront_mode=payload.storefront_mode,
        theme_config=payload.theme_config or {},
        is_active=payload.is_active,
    )
    db.add(brand)
    await db.commit()
    await db.refresh(brand)
    return ok(_serialize_brand(brand, []))


@router.patch("/brands/{brand_id}")
async def update_brand(
    brand_id: uuid.UUID,
    payload: BrandUpdateRequest,
    current: TokenData = Depends(require_permission("fb.settings.manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    brand = await db.scalar(
        select(Brand)
        .options(selectinload(Brand.branches).selectinload(BrandBranch.branch))
        .where(Brand.id == brand_id, Brand.company_id == current.company_id)
    )
    if not brand:
        raise HTTPException(status_code=404, detail="ไม่พบแบรนด์")
    if payload.slug is not None:
        slug = payload.slug.strip().lower()
        if not slug:
            raise HTTPException(status_code=400, detail="slug ไม่ถูกต้อง")
        exists = await db.scalar(
            select(Brand.id)
            .where(Brand.company_id == current.company_id, Brand.slug == slug, Brand.id != brand.id)
            .limit(1)
        )
        if exists:
            raise HTTPException(status_code=400, detail="slug นี้ถูกใช้แล้ว")
        brand.slug = slug
    if payload.name is not None:
        name = payload.name.strip()
        if not name:
            raise HTTPException(status_code=400, detail="ชื่อแบรนด์ไม่ถูกต้อง")
        brand.name = name
    if payload.storefront_mode is not None:
        brand.storefront_mode = payload.storefront_mode
    if payload.theme_config is not None:
        brand.theme_config = payload.theme_config
    if payload.is_active is not None:
        brand.is_active = payload.is_active
    await db.commit()
    await db.refresh(brand)
    return ok(_serialize_brand(brand))


@router.post("/brands/{brand_id}/branches")
async def upsert_brand_branch(
    brand_id: uuid.UUID,
    payload: BrandBranchUpdateRequest,
    current: TokenData = Depends(require_permission("fb.settings.manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    if payload.branch_type not in ["company_owned", "franchise"]:
        raise HTTPException(status_code=400, detail="ประเภทสาขาไม่ถูกต้อง")
    brand = await db.scalar(
        select(Brand)
        .options(selectinload(Brand.branches).selectinload(BrandBranch.branch))
        .where(Brand.id == brand_id, Brand.company_id == current.company_id)
    )
    if not brand:
        raise HTTPException(status_code=404, detail="ไม่พบแบรนด์")
    branch = await db.get(Branch, payload.branch_id)
    if not branch or branch.company_id != current.company_id:
        raise HTTPException(status_code=404, detail="ไม่พบสาขา")
    brand_branch = await db.scalar(
        select(BrandBranch).where(
            BrandBranch.company_id == current.company_id,
            BrandBranch.brand_id == brand.id,
            BrandBranch.branch_id == branch.id,
        )
    )
    if not brand_branch:
        brand_branch = BrandBranch(
            company_id=current.company_id,
            brand_id=brand.id,
            branch_id=branch.id,
        )
        db.add(brand_branch)
    brand_branch.branch_type = payload.branch_type
    brand_branch.is_active = payload.is_active
    await db.commit()
    await db.refresh(brand)
    brand = await db.scalar(
        select(Brand)
        .options(selectinload(Brand.branches).selectinload(BrandBranch.branch))
        .where(Brand.id == brand_id, Brand.company_id == current.company_id)
    )
    assert brand is not None
    return ok(_serialize_brand(brand))


@router.delete("/brands/{brand_id}/branches/{branch_id}")
async def deactivate_brand_branch(
    brand_id: uuid.UUID,
    branch_id: uuid.UUID,
    current: TokenData = Depends(require_permission("fb.settings.manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    brand_branch = await db.scalar(
        select(BrandBranch).where(
            BrandBranch.company_id == current.company_id,
            BrandBranch.brand_id == brand_id,
            BrandBranch.branch_id == branch_id,
        )
    )
    if not brand_branch:
        raise HTTPException(status_code=404, detail="ไม่พบสาขาของแบรนด์")
    brand_branch.is_active = False
    await db.commit()
    brand = await db.scalar(
        select(Brand)
        .options(selectinload(Brand.branches).selectinload(BrandBranch.branch))
        .where(Brand.id == brand_id, Brand.company_id == current.company_id)
    )
    if not brand:
        raise HTTPException(status_code=404, detail="ไม่พบแบรนด์")
    return ok(_serialize_brand(brand))


# ── Recipes ───────────────────────────────────────────────────────────────────

@router.get("/recipes", response_model=None)
async def list_recipes(
    branch_id: uuid.UUID | None = Query(default=None),
    include_inactive: bool = Query(default=False),
    current: TokenData = Depends(require_permission("fb.menu.view")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    svc = RecipeService(db)
    items = await svc.list_recipes(
        current.company_id,
        branch_id or current.branch_id,
        None,
        include_inactive,
    )
    return ok([item.model_dump() for item in items])


@router.post("/recipes", status_code=status.HTTP_201_CREATED)
async def create_recipe(
    payload: RecipeCreate,
    current: TokenData = Depends(require_permission("fb.recipe.manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    payload.brand_id = None
    svc = RecipeService(db)
    try:
        recipe, inventory_updates = await svc.create_recipe(
            current.company_id,
            payload,
            current.user_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    enriched = await svc._enrich_recipe(recipe, current.company_id, inventory_updates)
    return ok(enriched.model_dump())


@router.get("/recipes/{recipe_id}")
async def get_recipe(
    recipe_id: uuid.UUID,
    current: TokenData = Depends(require_permission("fb.menu.view")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    svc = RecipeService(db)
    recipe = await svc.get_recipe(recipe_id, current.company_id)
    if not recipe or recipe.brand_id is not None:
        raise HTTPException(status_code=404, detail="ไม่พบสูตร")
    enriched = await svc._enrich_recipe(recipe, current.company_id)
    return ok(enriched.model_dump())


@router.patch("/recipes/{recipe_id}")
async def update_recipe(
    recipe_id: uuid.UUID,
    payload: RecipeUpdate,
    current: TokenData = Depends(require_permission("fb.recipe.manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    svc = RecipeService(db)
    recipe = await svc.get_recipe(recipe_id, current.company_id)
    if not recipe or recipe.brand_id is not None:
        raise HTTPException(status_code=404, detail="ไม่พบสูตร")
    try:
        updated, inventory_updates = await svc.update_recipe(
            recipe,
            current.company_id,
            payload,
            current.user_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    enriched = await svc._enrich_recipe(updated, current.company_id, inventory_updates)
    return ok(enriched.model_dump())


@router.delete("/recipes/{recipe_id}")
async def delete_recipe(
    recipe_id: uuid.UUID,
    current: TokenData = Depends(require_permission("fb.recipe.manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    svc = RecipeService(db)
    recipe = await svc.get_recipe(recipe_id, current.company_id)
    if not recipe or recipe.brand_id is not None:
        raise HTTPException(status_code=404, detail="ไม่พบสูตร")
    await svc.delete_recipe(recipe)
    return ok({"deleted": True})


# ── Raw Materials ─────────────────────────────────────────────────────────────

@router.post("/raw-materials", status_code=status.HTTP_201_CREATED)
async def create_raw_material(
    payload: RawMaterialCreate,
    current: TokenData = Depends(require_permission("fb.recipe.manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    sku = payload.sku.strip()
    name = payload.name.strip()
    if not sku or not name:
        raise HTTPException(status_code=400, detail="กรุณาระบุ SKU และชื่อวัตถุดิบ")
    service = ProductService(db)
    product = await service.create_product(
        current.company_id,
        ProductCreate(
            sku=sku,
            name=name,
            description=f"Created from restaurant recipe setup ({payload.unit.strip() or 'unit'})",
            product_type="raw_material",
            inventory_role=payload.inventory_role,
            cost_price=payload.cost_price,
            selling_price=0,
            vat_type="included",
            vat_rate=7,
            is_active=True,
            is_for_sale=False,
            is_for_purchase=True,
        ),
    )
    return ok(ProductListItem.model_validate(product).model_dump())


@router.get("/central/{brand_slug}/recipe-products", response_model=None)
async def list_brand_recipe_products(
    brand_slug: str,
    product_type: str | None = Query(default=None),
    current: TokenData = Depends(require_any_permission("fb.menu.view", "fb.recipe.manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    brand = await _load_brand_for_slug(db, current.company_id, brand_slug)
    _require_brand_assignment(current, brand)
    assert brand is not None
    q = (
        select(Product)
        .options(selectinload(Product.unit))
        .where(
            Product.company_id == current.company_id,
            Product.deleted_at.is_(None),
            Product.is_active.is_(True),
            or_(Product.brand_id == brand.id, Product.brand_id.is_(None)),
        )
        .order_by(Product.name.asc())
    )
    if product_type:
        q = q.where(Product.product_type == product_type)
    q = q.limit(300)
    products = (await db.scalars(q)).all()
    return ok([ProductListItem.model_validate(product).model_dump() for product in products])


@router.get("/central/{brand_slug}/recipes", response_model=None)
async def list_brand_recipes(
    brand_slug: str,
    include_inactive: bool = Query(default=False),
    current: TokenData = Depends(require_any_permission("fb.menu.view", "fb.recipe.manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    brand = await _load_brand_for_slug(db, current.company_id, brand_slug)
    _require_brand_assignment(current, brand)
    assert brand is not None
    svc = RecipeService(db)
    items = await svc.list_recipes(current.company_id, None, brand.id, include_inactive)
    return ok([item.model_dump() for item in items])


@router.post("/central/{brand_slug}/recipes", status_code=status.HTTP_201_CREATED)
async def create_brand_recipe(
    brand_slug: str,
    payload: RecipeCreate,
    current: TokenData = Depends(require_permission("fb.recipe.manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    brand = await _load_brand_for_slug(db, current.company_id, brand_slug)
    _require_brand_assignment(current, brand)
    assert brand is not None
    payload.brand_id = brand.id
    payload.branch_id = None
    svc = RecipeService(db)
    try:
        recipe, inventory_updates = await svc.create_recipe(
            current.company_id,
            payload,
            current.user_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    enriched = await svc._enrich_recipe(recipe, current.company_id, inventory_updates)
    return ok(enriched.model_dump())


@router.get("/central/{brand_slug}/recipes/{recipe_id}")
async def get_brand_recipe(
    brand_slug: str,
    recipe_id: uuid.UUID,
    current: TokenData = Depends(require_any_permission("fb.menu.view", "fb.recipe.manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    brand = await _load_brand_for_slug(db, current.company_id, brand_slug)
    _require_brand_assignment(current, brand)
    assert brand is not None
    svc = RecipeService(db)
    recipe = await svc.get_recipe(recipe_id, current.company_id)
    if not recipe or recipe.brand_id != brand.id:
        raise HTTPException(status_code=404, detail="ไม่พบสูตร")
    enriched = await svc._enrich_recipe(recipe, current.company_id)
    return ok(enriched.model_dump())


@router.patch("/central/{brand_slug}/recipes/{recipe_id}")
async def update_brand_recipe(
    brand_slug: str,
    recipe_id: uuid.UUID,
    payload: RecipeUpdate,
    current: TokenData = Depends(require_permission("fb.recipe.manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    brand = await _load_brand_for_slug(db, current.company_id, brand_slug)
    _require_brand_assignment(current, brand)
    assert brand is not None
    svc = RecipeService(db)
    recipe = await svc.get_recipe(recipe_id, current.company_id)
    if not recipe or recipe.brand_id != brand.id:
        raise HTTPException(status_code=404, detail="ไม่พบสูตร")
    try:
        updated, inventory_updates = await svc.update_recipe(
            recipe,
            current.company_id,
            payload,
            current.user_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    enriched = await svc._enrich_recipe(updated, current.company_id, inventory_updates)
    return ok(enriched.model_dump())


@router.delete("/central/{brand_slug}/recipes/{recipe_id}")
async def delete_brand_recipe(
    brand_slug: str,
    recipe_id: uuid.UUID,
    current: TokenData = Depends(require_permission("fb.recipe.manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    brand = await _load_brand_for_slug(db, current.company_id, brand_slug)
    _require_brand_assignment(current, brand)
    assert brand is not None
    svc = RecipeService(db)
    recipe = await svc.get_recipe(recipe_id, current.company_id)
    if not recipe or recipe.brand_id != brand.id:
        raise HTTPException(status_code=404, detail="ไม่พบสูตร")
    await svc.delete_recipe(recipe)
    return ok({"deleted": True})


@router.post("/central/{brand_slug}/raw-materials", status_code=status.HTTP_201_CREATED)
async def create_brand_raw_material(
    brand_slug: str,
    payload: RawMaterialCreate,
    current: TokenData = Depends(require_permission("fb.recipe.manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    brand = await _load_brand_for_slug(db, current.company_id, brand_slug)
    _require_brand_assignment(current, brand)
    assert brand is not None
    sku = payload.sku.strip()
    name = payload.name.strip()
    if not sku or not name:
        raise HTTPException(status_code=400, detail="กรุณาระบุ SKU และชื่อวัตถุดิบ")
    service = ProductService(db)
    product = await service.create_product(
        current.company_id,
        ProductCreate(
            sku=sku,
            name=name,
            description=f"Created from {brand.slug} recipe setup ({payload.unit.strip() or 'unit'})",
            product_type="raw_material",
            inventory_role=payload.inventory_role,
            cost_price=payload.cost_price,
            selling_price=0,
            vat_type="included",
            vat_rate=7,
            is_active=True,
            is_for_sale=False,
            is_for_purchase=True,
        ),
    )
    product.brand_id = brand.id
    await db.commit()
    await db.refresh(product)
    return ok(ProductListItem.model_validate(product).model_dump())


# ── F&B Settings and Setup ──────────────────────────────────────────────────

@router.get("/settings")
async def get_fb_settings(
    current: TokenData = Depends(require_any_permission(*FB_WORKSPACE_PERMISSIONS)),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    if not current.branch_id:
        raise HTTPException(status_code=400, detail="Branch context required")
    settings_row = await AdminService(db).get_branch_settings(
        current.branch_id,
        current.company_id,
    )
    return ok(BranchSettingsRead.model_validate(settings_row).model_dump())


@router.patch("/settings")
async def update_fb_settings(
    payload: FBSettingsUpdate,
    current: TokenData = Depends(require_permission("fb.settings.manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    if not current.branch_id:
        raise HTTPException(status_code=400, detail="Branch context required")

    values = payload.model_dump(exclude_unset=True)
    has_tables = values.pop("has_tables", None)
    update_values: dict[str, Any] = {
        "fb_enabled": True,
        "fb_queue_enabled": True,
    }
    if has_tables is not None:
        update_values["fb_service_mode"] = service_mode_for(has_tables)
        if has_tables:
            update_values["fb_qs_qr_token"] = None
        else:
            update_values["fb_table_qr_enabled"] = False
            update_values["fb_bill_at_table"] = False
            update_values["fb_qs_qr_token"] = uuid.uuid4()

    field_mapping = {
        "table_qr_enabled": "fb_table_qr_enabled",
        "bill_at_table": "fb_bill_at_table",
        "queue_reset": "fb_queue_reset",
        "queue_prefix": "fb_queue_prefix",
        "pickup_display_enabled": "fb_pickup_display_enabled",
        "line_notify_token": "fb_line_notify_token",
        "kitchen_stations": "fb_kitchen_stations",
    }
    for source, target in field_mapping.items():
        if source in values:
            value = values[source]
            if source == "queue_prefix" and value is not None:
                value = value.strip()
            elif source == "kitchen_stations" and value is not None:
                value = list(
                    dict.fromkeys(
                        station.strip() for station in value if station.strip()
                    )
                )
            update_values[target] = value

    if has_tables is False:
        update_values["fb_table_qr_enabled"] = False
        update_values["fb_bill_at_table"] = False

    settings_row = await AdminService(db).update_branch_settings(
        current.branch_id,
        current.company_id,
        BranchSettingsUpdate(**update_values),
    )
    return ok(BranchSettingsRead.model_validate(settings_row).model_dump())


@router.post("/setup", status_code=status.HTTP_201_CREATED)
async def setup_fb_workspace(
    payload: FBSetupRequest,
    current: TokenData = Depends(require_permission("fb.settings.manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    if not current.branch_id:
        raise HTTPException(status_code=400, detail="Branch context required")

    planned_tables = []
    if payload.has_tables:
        zone_inputs = (
            [
                DiningTableZonePlan(
                    zone_name=zone.zone_name,
                    table_name_prefix=zone.table_name_prefix,
                    table_count=zone.table_count,
                    table_capacity=zone.table_capacity,
                )
                for zone in payload.table_zones
            ]
            if payload.table_zones
            else [
                DiningTableZonePlan(
                    zone_name="โซนทั่วไป",
                    table_name_prefix=payload.table_name_prefix,
                    table_count=payload.table_count,
                    table_capacity=payload.table_capacity,
                )
            ]
        )
        try:
            planned_tables = plan_dining_table_zones(zone_inputs)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    branch = await db.scalar(
        select(Branch).where(
            Branch.id == current.branch_id,
            Branch.company_id == current.company_id,
            Branch.deleted_at.is_(None),
        )
    )
    if branch is None:
        raise HTTPException(status_code=404, detail="ไม่พบสาขา")

    settings_row = await AdminService(db).get_branch_settings(
        current.branch_id,
        current.company_id,
    )
    settings_row.fb_enabled = True
    settings_row.fb_service_mode = service_mode_for(payload.has_tables)
    settings_row.fb_table_qr_enabled = (
        payload.table_qr_enabled if payload.has_tables else False
    )
    settings_row.fb_bill_at_table = (
        payload.bill_at_table if payload.has_tables else False
    )
    settings_row.fb_queue_enabled = True
    settings_row.fb_queue_reset = payload.queue_reset
    settings_row.fb_queue_prefix = payload.queue_prefix.strip()
    settings_row.fb_pickup_display_enabled = payload.pickup_display_enabled
    if payload.has_tables:
        settings_row.fb_qs_qr_token = None
    elif settings_row.fb_qs_qr_token is None:
        settings_row.fb_qs_qr_token = uuid.uuid4()
    settings_row.fb_kitchen_stations = list(
        dict.fromkeys(
            station.strip()
            for station in payload.kitchen_stations
            if station.strip()
        )
    )

    ready_tables: list[DiningTable] = []
    created_table_names: list[str] = []
    if payload.has_tables:
        existing_tables = (
            await db.scalars(
                select(DiningTable).where(
                    DiningTable.company_id == current.company_id,
                    DiningTable.branch_id == current.branch_id,
                )
            )
        ).all()
        existing_by_name = {
            table.name.strip().casefold(): table for table in existing_tables
        }
        for spec in planned_tables:
            existing = existing_by_name.get(spec.name.casefold())
            if existing is not None:
                if not existing.is_active:
                    existing.is_active = True
                    existing.status = "available"
                existing.zone = spec.zone
                existing.capacity = spec.capacity
                existing.sort_order = spec.sort_order
                ready_tables.append(existing)
                continue

            table = DiningTable(
                company_id=current.company_id,
                branch_id=current.branch_id,
                name=spec.name,
                zone=spec.zone,
                capacity=spec.capacity,
                table_type="dine_in",
                sort_order=spec.sort_order,
            )
            db.add(table)
            ready_tables.append(table)
            created_table_names.append(spec.name)

    settings_row.fb_setup_completed = True
    await db.commit()
    await db.refresh(settings_row)

    return ok(
        {
            "settings": BranchSettingsRead.model_validate(settings_row).model_dump(),
            "tables_ready": len(ready_tables),
            "tables_created": created_table_names,
        }
    )


# ── Tables ───────────────────────────────────────────────────────────────────

@router.get("/tables")
async def list_tables(
    current: TokenData = Depends(require_permission("fb.menu.view")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    if not current.branch_id:
        raise HTTPException(status_code=400, detail="Branch context required")
    svc = DiningService(db)
    return ok(await svc.list_tables(current.company_id, current.branch_id))


@router.post("/tables", status_code=status.HTTP_201_CREATED)
async def create_table(
    payload: TableCreate,
    current: TokenData = Depends(require_permission("fb.table.manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    if not current.branch_id:
        raise HTTPException(status_code=400, detail="Branch context required")
    svc = DiningService(db)
    table = await svc.create_table(
        current.company_id,
        current.branch_id,
        payload.name.strip(),
        payload.capacity,
        payload.table_type,
        payload.sort_order,
        payload.zone,
    )
    return ok(
        {
            "id": str(table.id),
            "name": table.name,
            "zone": table.zone,
        }
    )


@router.get("/tables/{table_id}")
async def get_table(
    table_id: uuid.UUID,
    current: TokenData = Depends(require_permission("fb.menu.view")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    svc = DiningService(db)
    if not current.branch_id:
        raise HTTPException(status_code=400, detail="Branch context required")
    tables = await svc.list_tables(current.company_id, current.branch_id)
    found = next((t for t in tables if str(t.id) == str(table_id)), None)
    if not found:
        raise HTTPException(status_code=404, detail="ไม่พบโต๊ะ")
    return ok(found)


@router.patch("/tables/{table_id}")
async def update_table(
    table_id: uuid.UUID,
    payload: TableUpdate,
    current: TokenData = Depends(require_permission("fb.table.manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    if not current.branch_id:
        raise HTTPException(status_code=400, detail="Branch context required")
    table = await db.get(DiningTable, table_id)
    if not table or table.company_id != current.company_id or table.branch_id != current.branch_id:
        raise HTTPException(status_code=404, detail="ไม่พบโต๊ะ")
    if payload.status == "available":
        active = await db.scalar(
            select(DiningSession.id).where(
                DiningSession.table_id == table_id,
                DiningSession.status.in_(["open", "bill_requested"]),
            ).limit(1)
        )
        if active:
            raise HTTPException(status_code=400, detail="โต๊ะนี้มี session ที่ยังเปิดอยู่")
    svc = DiningService(db)
    update_values = payload.model_dump(exclude_none=True)
    if "name" in update_values:
        update_values["name"] = update_values["name"].strip()
    if "zone" in update_values:
        update_values["zone"] = " ".join(update_values["zone"].split()) or "โซนทั่วไป"
    updated = await svc.update_table(table, **update_values)
    return ok(
        {
            "id": str(updated.id),
            "status": updated.status,
            "name": updated.name,
            "zone": updated.zone,
        }
    )


@router.delete("/tables/{table_id}")
async def delete_table(
    table_id: uuid.UUID,
    current: TokenData = Depends(require_permission("fb.table.manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    if not current.branch_id:
        raise HTTPException(status_code=400, detail="Branch context required")
    table = await db.get(DiningTable, table_id)
    if not table or table.company_id != current.company_id or table.branch_id != current.branch_id:
        raise HTTPException(status_code=404, detail="ไม่พบโต๊ะ")
    # ตรวจว่าไม่มี open session
    from sqlalchemy import select as sa_select
    active = await db.scalar(
        sa_select(DiningSession.id).where(
            DiningSession.table_id == table_id,
            DiningSession.status.in_(["open", "bill_requested"]),
        ).limit(1)
    )
    if active:
        raise HTTPException(status_code=400, detail="มี session ที่ยังเปิดอยู่ ปิดโต๊ะก่อนลบ")
    table.is_active = False
    await db.commit()
    return ok({"deleted": True, "id": str(table_id)})


# ── Sessions ──────────────────────────────────────────────────────────────────

@router.get("/sessions")
async def list_sessions(
    status_filter: str | None = Query(default=None, alias="status"),
    date_value: date | None = Query(default=None, alias="date", description="YYYY-MM-DD, default=today"),
    current: TokenData = Depends(require_permission("fb.menu.view")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    if not current.branch_id:
        raise HTTPException(status_code=400, detail="Branch context required")
    from sqlalchemy.orm import selectinload

    bkk = ZoneInfo("Asia/Bangkok")
    target_date = date_value or datetime.now(bkk).date()
    start_at = datetime.combine(target_date, time.min, tzinfo=bkk).astimezone(timezone.utc)
    end_at = datetime.combine(target_date, time.max, tzinfo=bkk).astimezone(timezone.utc)

    q = (
        select(DiningSession)
        .options(selectinload(DiningSession.orders).selectinload(DiningOrder.items))
        .where(
            DiningSession.company_id == current.company_id,
            DiningSession.branch_id == current.branch_id,
            DiningSession.opened_at >= start_at,
            DiningSession.opened_at <= end_at,
        )
        .order_by(DiningSession.opened_at.desc())
    )
    if status_filter:
        q = q.where(DiningSession.status == status_filter)

    sessions = list((await db.scalars(q)).all())
    result = []
    for s in sessions:
        table = await db.get(DiningTable, s.table_id) if s.table_id else None
        all_items = [i for o in s.orders if o.status != "cancelled" for i in o.items]
        total = sum(float(i.unit_price) * i.qty for i in all_items)
        result.append({
            "id": str(s.id),
            "status": s.status,
            "source_type": "dine_in" if s.table_id else "quick_service",
            "table_name": table.name if table else None,
            "queue_number": s.queue_number,
            "customer_name": s.customer_name,
            "customer_phone": s.customer_phone,
            "opened_at": s.opened_at.isoformat(),
            "closed_at": s.closed_at.isoformat() if s.closed_at else None,
            "item_count": len(all_items),
            "pending_count": sum(i.qty for i in all_items if i.status == "pending"),
            "cooking_count": sum(i.qty for i in all_items if i.status == "cooking"),
            "ready_count": sum(i.qty for i in all_items if i.status == "done"),
            "served_count": sum(i.qty for i in all_items if i.status == "served"),
            "total_amount": round(total, 2),
            "sale_order_id": str(s.sale_order_id) if s.sale_order_id else None,
        })
    return ok(result)


@router.post("/sessions", status_code=status.HTTP_201_CREATED)
async def open_session(
    payload: SessionOpen,
    current: TokenData = Depends(require_permission("fb.table.manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    if not current.branch_id:
        raise HTTPException(status_code=400, detail="Branch context required")
    branch_settings = await db.scalar(
        select(BranchSettings).where(BranchSettings.branch_id == current.branch_id)
    )
    svc = DiningService(db)
    try:
        session = await svc.open_session(current.company_id, current.branch_id, payload, current.user_id, branch_settings)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ok({
        "id": str(session.id),
        "qr_token": (
            str(session.qr_token)
            if branch_settings and branch_settings.fb_table_qr_enabled
            else None
        ),
        "queue_number": session.queue_number,
    })


@router.get("/sessions/{session_id}")
async def get_session(
    session_id: uuid.UUID,
    current: TokenData = Depends(require_permission("fb.menu.view")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    svc = DiningService(db)
    session = await svc.get_session(session_id)
    if not session or session.company_id != current.company_id:
        raise HTTPException(status_code=404, detail="ไม่พบ session")
    return ok({"id": str(session.id), "status": session.status, "queue_number": session.queue_number})


@router.get("/sessions/{session_id}/detail")
async def get_session_detail(
    session_id: uuid.UUID,
    current: TokenData = Depends(require_permission("fb.menu.view")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    svc = DiningService(db)
    session = await svc.get_session(session_id)
    if not session or session.company_id != current.company_id:
        raise HTTPException(status_code=404, detail="ไม่พบ session")
    table = await db.get(DiningTable, session.table_id) if session.table_id else None
    active_orders = [order for order in session.orders if order.status != "cancelled"]
    active_items = [item for order in active_orders for item in order.items if item.status != "cancelled"]
    return ok({
        "id": str(session.id),
        "status": session.status,
        "queue_number": session.queue_number,
        "table_name": table.name if table else None,
        "customer_name": session.customer_name,
        "customer_phone": session.customer_phone,
        "opened_at": session.opened_at.isoformat() if session.opened_at else None,
        "closed_at": session.closed_at.isoformat() if session.closed_at else None,
        "pending_count": sum(item.qty for item in active_items if item.status == "pending"),
        "cooking_count": sum(item.qty for item in active_items if item.status == "cooking"),
        "ready_count": sum(item.qty for item in active_items if item.status == "done"),
        "served_count": sum(item.qty for item in active_items if item.status == "served"),
        "qr_pending_count": sum(item.qty for order in active_orders if order.source == "qr_self" for item in order.items if item.status == "pending"),
        "orders": [
            {
                "id": str(o.id),
                "order_number": o.order_number,
                "status": o.status,
                "source": o.source,
                "note": o.note,
                "created_at": o.created_at.isoformat() if o.created_at else None,
                "items": [
                    {
                        "id": str(i.id),
                        "product_name": i.product_name,
                        "qty": i.qty,
                        "unit_price": float(i.unit_price),
                        "special_request": i.special_request,
                        "status": i.status,
                    }
                    for i in o.items
                ],
            }
            for o in session.orders
        ],
    })


@router.post("/sessions/{session_id}/orders", status_code=status.HTTP_201_CREATED)
async def place_order(
    session_id: uuid.UUID,
    payload: PlaceOrderRequest,
    current: TokenData = Depends(require_permission("fb.order.create")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    svc = DiningService(db)
    session = await db.get(DiningSession, session_id)
    if not session or session.company_id != current.company_id:
        raise HTTPException(status_code=404, detail="ไม่พบ session")
    if session.status == "closed":
        raise HTTPException(status_code=400, detail="Session ปิดแล้ว")
    if session.status == "bill_requested":
        raise HTTPException(status_code=400, detail="ลูกค้าเรียกบิลแล้ว ไม่สามารถสั่งเพิ่มได้")
    branch_settings = await db.scalar(
        select(BranchSettings).where(BranchSettings.branch_id == session.branch_id)
    )
    try:
        order = await svc.place_order(current.company_id, session.branch_id, session, payload, "staff", branch_settings)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ok({"id": str(order.id), "order_number": order.order_number})


@router.post("/orders/{order_id}/cancel")
async def cancel_order(
    order_id: uuid.UUID,
    payload: CancelRequest,
    current: TokenData = Depends(require_permission("fb.order.create")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    if not payload.reason.strip():
        raise HTTPException(status_code=400, detail="กรุณาระบุเหตุผลการยกเลิก")
    order = await db.get(DiningOrder, order_id)
    if not order or order.company_id != current.company_id:
        raise HTTPException(status_code=404, detail="ไม่พบออเดอร์")
    session = await db.get(DiningSession, order.session_id)
    if not session or session.status == "closed":
        raise HTTPException(status_code=400, detail="Session ปิดแล้ว")
    svc = DiningService(db)
    try:
        updated = await svc.cancel_order(order, payload.reason)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ok({"id": str(updated.id), "status": updated.status})


@router.post("/order-items/{item_id}/cancel")
async def cancel_order_item(
    item_id: uuid.UUID,
    payload: CancelRequest,
    current: TokenData = Depends(require_permission("fb.order.create")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    if not payload.reason.strip():
        raise HTTPException(status_code=400, detail="กรุณาระบุเหตุผลการยกเลิก")
    item = await db.get(DiningOrderItem, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="ไม่พบรายการ")
    order = await db.get(DiningOrder, item.order_id)
    if not order or order.company_id != current.company_id:
        raise HTTPException(status_code=404, detail="ไม่พบออเดอร์")
    session = await db.get(DiningSession, order.session_id)
    if not session or session.status == "closed":
        raise HTTPException(status_code=400, detail="Session ปิดแล้ว")
    svc = DiningService(db)
    try:
        updated = await svc.cancel_order_item(item, payload.reason)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ok({"id": str(updated.id), "status": updated.status})


@router.patch("/order-items/{item_id}/status")
async def update_order_item_status(
    item_id: uuid.UUID,
    payload: TicketStatusUpdate,
    current: TokenData = Depends(require_permission("fb.kitchen.manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    item = await db.get(DiningOrderItem, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="ไม่พบรายการ")
    order = await db.get(DiningOrder, item.order_id)
    if not order or order.company_id != current.company_id:
        raise HTTPException(status_code=404, detail="ไม่พบออเดอร์")
    session = await db.get(DiningSession, order.session_id)
    if not session or session.status == "closed":
        raise HTTPException(status_code=400, detail="Session ปิดแล้ว")
    if payload.status not in ["pending", "cooking", "done", "served"]:
        raise HTTPException(status_code=400, detail="status ไม่ถูกต้อง")
    svc = DiningService(db)
    try:
        updated = await svc.update_order_item_status(item, payload.status)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ok({"id": str(updated.id), "status": updated.status})


@router.post("/sessions/{session_id}/bill")
async def request_bill(
    session_id: uuid.UUID,
    current: TokenData = Depends(require_permission("fb.order.create")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    svc = DiningService(db)
    session = await db.get(DiningSession, session_id)
    if not session or session.company_id != current.company_id:
        raise HTTPException(status_code=404, detail="ไม่พบ session")
    updated = await svc.request_bill(session)
    return ok({"status": updated.status})


@router.post("/sessions/{session_id}/checkout")
async def checkout_session(
    session_id: uuid.UUID,
    payload: SessionCheckoutRequest,
    current: TokenData = Depends(require_permission("fb.order.create")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """รวมบิลโต๊ะ → สร้าง SaleOrder → ปิด session"""
    svc = DiningService(db)
    session = await db.get(DiningSession, session_id)
    if not session or session.company_id != current.company_id:
        raise HTTPException(status_code=404, detail="ไม่พบ session")
    if session.status == "closed":
        raise HTTPException(status_code=400, detail="Session ปิดแล้ว")
    if not current.branch_id:
        raise HTTPException(status_code=400, detail="Branch context required")
    try:
        result = await svc.checkout_session(
            session, current.company_id, current.branch_id, current.user_id, payload
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ok(result.model_dump())


@router.get("/sessions/{session_id}/payment-qr")
async def get_session_payment_qr(
    session_id: uuid.UUID,
    amount: Decimal = Query(gt=0),
    current: TokenData = Depends(require_permission("fb.order.create")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Create a branch-scoped PromptPay QR for the current bill amount."""
    if not current.branch_id:
        raise HTTPException(status_code=400, detail="Branch context required")

    session = await db.get(DiningSession, session_id)
    if (
        not session
        or session.company_id != current.company_id
        or session.branch_id != current.branch_id
        or session.status == "closed"
    ):
        raise HTTPException(status_code=404, detail="ไม่พบออเดอร์ที่ยังเปิดอยู่")

    settings_row = await db.scalar(
        select(BranchSettings).where(
            BranchSettings.branch_id == current.branch_id,
            BranchSettings.company_id == current.company_id,
        )
    )
    if not settings_row or not settings_row.promptpay_target:
        raise HTTPException(status_code=400, detail="สาขานี้ยังไม่ได้ตั้งค่าบัญชี PromptPay")

    qr_amount = Decimal(amount).quantize(Decimal("0.01"))
    try:
        payload = generate_promptpay_payload(settings_row.promptpay_target, qr_amount)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="ข้อมูล PromptPay ของสาขาไม่ถูกต้อง") from exc

    return ok({
        "payload": payload,
        "amount": f"{qr_amount:.2f}",
        "promptpay_name": settings_row.promptpay_name,
    })


@router.post("/sessions/{session_id}/close")
async def close_session(
    session_id: uuid.UUID,
    current: TokenData = Depends(require_permission("fb.table.manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    svc = DiningService(db)
    session = await db.get(DiningSession, session_id)
    if not session or session.company_id != current.company_id:
        raise HTTPException(status_code=404, detail="ไม่พบ session")
    updated = await svc.close_session(session)
    return ok({"status": updated.status})


# ── Kitchen ───────────────────────────────────────────────────────────────────

@router.get("/kitchen")
async def list_kitchen_tickets(
    station: str | None = Query(default=None),
    current: TokenData = Depends(require_permission("fb.kitchen.manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    if not current.branch_id:
        raise HTTPException(status_code=400, detail="Branch context required")
    svc = DiningService(db)
    tickets = await svc.list_kitchen_tickets(current.branch_id, station)
    return ok([{
        "id": str(t.id),
        "session_id": str(t.session_id),
        "product_name": t.product_name,
        "qty": t.qty,
        "special_request": t.special_request,
        "station": t.station,
        "queue_number": t.queue_number,
        "table_name": t.table_name,
        "source_type": "dine_in" if t.table_name else "quick_service",
        "status": t.status,
        "created_at": t.created_at.isoformat() if t.created_at else None,
        "done_at": t.done_at.isoformat() if t.done_at else None,
    } for t in tickets])


@router.patch("/kitchen/{ticket_id}")
async def update_ticket(
    ticket_id: uuid.UUID,
    payload: TicketStatusUpdate,
    current: TokenData = Depends(require_permission("fb.kitchen.manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    ticket = await db.get(KitchenTicket, ticket_id)
    if not ticket or ticket.company_id != current.company_id:
        raise HTTPException(status_code=404, detail="ไม่พบ ticket")
    valid = ["pending", "cooking", "done", "served"]
    if payload.status not in valid:
        raise HTTPException(status_code=400, detail=f"status ต้องเป็น {valid}")
    svc = DiningService(db)
    try:
        updated = await svc.update_ticket_status(ticket, payload.status)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ok({"id": str(updated.id), "status": updated.status})


@router.get("/pickup-queue")
async def get_pickup_queue(
    current: TokenData = Depends(require_permission("fb.menu.view")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    if not current.branch_id:
        raise HTTPException(status_code=400, detail="Branch context required")
    svc = DiningService(db)
    queues = await svc.get_ready_pickup_queues(current.branch_id)
    return ok(queues)


@router.post("/pickup-queue/{session_id}/served")
async def mark_pickup_queue_served(
    session_id: uuid.UUID,
    current: TokenData = Depends(require_any_permission("fb.order.create", "fb.kitchen.manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    if not current.branch_id:
        raise HTTPException(status_code=400, detail="Branch context required")
    svc = DiningService(db)
    try:
        result = await svc.mark_pickup_session_served(session_id, current.company_id, current.branch_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ok(result)


# ── Staff WAP Quick Service ──────────────────────────────────────────────────

def _branch_promptpay_payload(settings_row: BranchSettings | None) -> str | None:
    if not settings_row or not settings_row.promptpay_target:
        return None
    try:
        return generate_promptpay_payload(settings_row.promptpay_target)
    except ValueError:
        return None


async def _wap_get_menu_data(
    brand_slug: str | None,
    current: TokenData = Depends(require_permission("fb.order.create")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    if not current.branch_id:
        raise HTTPException(status_code=400, detail="Branch context required")
    from app.models.branch import Branch as BranchModel
    from app.models.product import Product, Category as CategoryModel

    branch = await db.get(BranchModel, current.branch_id)
    if not branch or branch.company_id != current.company_id:
        raise HTTPException(status_code=404, detail="ไม่พบสาขา")
    brand = await _load_brand_for_slug(db, current.company_id, brand_slug)
    _require_brand_assignment(current, brand)
    brand_branch = await _ensure_brand_branch(db, current.company_id, current.branch_id, brand)
    if brand is not None and (brand_branch is None or brand_branch.store_location_id is None):
        raise HTTPException(status_code=400, detail="กรุณาตั้งค่าคลัง STORE-STOCK ของสาขาก่อนขาย")
    settings = await db.scalar(select(BranchSettings).where(BranchSettings.branch_id == current.branch_id))
    shift_id: uuid.UUID | None = None
    location_id: uuid.UUID | None = brand_branch.store_location_id if brand_branch else None
    if brand is not None and location_id is not None:
        shift_id, location_id = await DiningService(db)._resolve_shift_and_location(
            current.company_id,
            current.branch_id,
            current.user_id,
            None,
            location_id,
            location_id,
        )
        await db.commit()
    product_filters = [
            Product.company_id == current.company_id,
            Product.product_type == "menu_item",
            Product.is_active.is_(True),
            Product.is_for_sale.is_(True),
    ]
    if brand:
        product_filters.append(Product.brand_id == brand.id)
    else:
        product_filters.append(Product.brand_id.is_(None))
    products = list((await db.scalars(
        select(Product).where(*product_filters).order_by(Product.sku)
    )).all())
    product_ids = [item.id for item in products]
    menu_recipes: dict[uuid.UUID, Recipe] = {}
    if product_ids:
        recipe_filters = [
            Recipe.company_id == current.company_id,
            Recipe.product_id.in_(product_ids),
            Recipe.recipe_type == "menu_recipe",
            Recipe.is_active.is_(True),
            or_(Recipe.branch_id == current.branch_id, Recipe.branch_id.is_(None)),
        ]
        if brand:
            recipe_filters.append(Recipe.brand_id == brand.id)
        else:
            recipe_filters.append(Recipe.brand_id.is_(None))
        recipe_rows = list((await db.scalars(
            select(Recipe)
            .options(selectinload(Recipe.ingredients).selectinload(RecipeIngredient.ingredient))
            .where(*recipe_filters)
            .order_by(
                Recipe.product_id,
                Recipe.branch_id.desc().nullslast(),
                Recipe.version_no.desc(),
                Recipe.effective_from.desc().nullslast(),
                Recipe.created_at.desc(),
            )
        )).all())
        for recipe in recipe_rows:
            if recipe.product_id not in menu_recipes:
                menu_recipes[recipe.product_id] = recipe
    categories = list((await db.scalars(
        select(CategoryModel).where(
            CategoryModel.company_id == current.company_id,
            CategoryModel.is_active.is_(True),
        ).order_by(CategoryModel.sort_order, CategoryModel.name)
    )).all())
    cat_map = {item.id: item.name for item in categories}

    def _serialize_store_menu_recipe(recipe: Recipe | None) -> dict[str, Any] | None:
        if not recipe:
            return None
        return {
            "id": str(recipe.id),
            "name": recipe.name,
            "recipe_type": recipe.recipe_type,
            "yield_qty": _to_float(recipe.yield_qty),
            "yield_unit": recipe.yield_unit,
            "ingredients": [
                {
                    "ingredient_id": str(ingredient.ingredient_id),
                    "ingredient_name": ingredient.ingredient.name if ingredient.ingredient else "",
                    "ingredient_sku": ingredient.ingredient.sku if ingredient.ingredient else "",
                    "quantity": _to_float(ingredient.quantity),
                    "unit": ingredient.unit,
                }
                for ingredient in recipe.ingredients
            ],
        }

    return ok({
        "brand_slug": brand.slug if brand else None,
        "brand_name": brand.name if brand else None,
        "branch_name": branch.name,
        "shift_id": str(shift_id) if shift_id else None,
        "location_id": str(location_id) if location_id else None,
        "queue_prefix": settings.fb_queue_prefix if settings else "",
        "promptpay_name": settings.promptpay_name if settings else None,
        "promptpay_payload": _branch_promptpay_payload(settings),
        "categories": [{"id": str(item.id), "name": item.name} for item in categories],
        "products": [
            {
                "id": str(item.id),
                "sku": item.sku,
                "name": item.name,
                "description": item.description,
                "selling_price": float(item.selling_price),
                "category_id": str(item.category_id) if item.category_id else None,
                "category_name": cat_map.get(item.category_id) if item.category_id else None,
                "image_url": item.image_url,
                "is_available": True,
                "menu_recipe": _serialize_store_menu_recipe(menu_recipes.get(item.id)),
            }
            for item in products
        ],
    })


@router.get("/wap/menu")
async def wap_get_menu(
    current: TokenData = Depends(require_permission("fb.order.create")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    return await _wap_get_menu_data(None, current, db)


@router.get("/store/{brand_slug}/menu")
async def store_get_menu(
    brand_slug: str,
    current: TokenData = Depends(require_permission("fb.order.create")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    return await _wap_get_menu_data(brand_slug, current, db)


@router.get("/store/{brand_slug}/stock/daily")
async def get_store_stock_daily(
    brand_slug: str,
    business_date: date | None = Query(default=None, alias="date"),
    current: TokenData = Depends(
        require_any_permission("brand.store.stock.view", "brand.store.stock.adjust")
    ),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    if not current.branch_id:
        raise HTTPException(status_code=400, detail="Branch context required")
    brand = await _load_brand_for_slug(db, current.company_id, brand_slug)
    _require_brand_assignment(current, brand)
    brand_branch = await _ensure_brand_branch(
        db, current.company_id, current.branch_id, brand
    )
    if brand_branch is None or brand_branch.store_location_id is None:
        raise HTTPException(status_code=400, detail="กรุณาตั้งค่าคลัง STORE-STOCK ของสาขาก่อน")
    summary = await StoreInventoryService(db).daily_summary(
        company_id=current.company_id,
        brand_id=brand.id,
        branch_id=current.branch_id,
        location_id=brand_branch.store_location_id,
        business_date=business_date or datetime.now(ZoneInfo("Asia/Bangkok")).date(),
    )
    return ok(summary)


@router.post("/store/{brand_slug}/stock/adjustments", status_code=status.HTTP_201_CREATED)
async def create_store_stock_adjustment(
    brand_slug: str,
    payload: StoreStockAdjustmentRequest,
    current: TokenData = Depends(require_permission("brand.store.stock.adjust")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    if not current.branch_id:
        raise HTTPException(status_code=400, detail="Branch context required")
    brand = await _load_brand_for_slug(db, current.company_id, brand_slug)
    _require_brand_assignment(current, brand)
    brand_branch = await _ensure_brand_branch(
        db, current.company_id, current.branch_id, brand
    )
    if brand_branch is None or brand_branch.store_location_id is None:
        raise HTTPException(status_code=400, detail="กรุณาตั้งค่าคลัง STORE-STOCK ของสาขาก่อน")
    try:
        movement = await StoreInventoryService(db).adjust_store_stock(
            company_id=current.company_id,
            brand_id=brand.id,
            branch_id=current.branch_id,
            location_id=brand_branch.store_location_id,
            user_id=current.user_id,
            payload=payload,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ok(
        {
            "id": str(movement.id),
            "product_id": str(movement.product_id),
            "location_id": str(movement.location_id),
            "movement_type": movement.movement_type,
            "qty": _to_float(movement.qty),
            "qty_before": _to_float(movement.qty_before),
            "qty_after": _to_float(movement.qty_after),
            "reason": payload.reason,
            "note": movement.note,
            "created_at": movement.created_at.isoformat() if movement.created_at else None,
        }
    )


@router.get("/store/{brand_slug}/replenishment-suggestion")
async def get_store_replenishment_suggestion(
    brand_slug: str,
    business_date: date | None = Query(default=None, alias="date"),
    current: TokenData = Depends(
        require_any_permission(
            "brand.store.replenishment.submit",
            "brand.store.shift.close",
            "brand.store.stock.view",
            "fb.order.create",
        )
    ),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    if not current.branch_id:
        raise HTTPException(status_code=400, detail="Branch context required")
    brand = await _load_brand_for_slug(db, current.company_id, brand_slug)
    _require_brand_assignment(current, brand)
    brand_branch = await _ensure_brand_branch(
        db, current.company_id, current.branch_id, brand
    )
    if brand_branch is None or brand_branch.store_location_id is None:
        raise HTTPException(status_code=400, detail="กรุณาตั้งค่าคลัง STORE-STOCK ของสาขาก่อน")
    summary = await ReplenishmentService(db).suggestion(
        company_id=current.company_id,
        brand_id=brand.id,
        branch_id=current.branch_id,
        location_id=brand_branch.store_location_id,
        business_date=business_date or datetime.now(ZoneInfo("Asia/Bangkok")).date(),
    )
    return ok(summary)


async def _load_recipe_for_product(
    db: AsyncSession,
    company_id: uuid.UUID,
    branch_id: uuid.UUID,
    product_id: uuid.UUID,
    brand_id: uuid.UUID | None = None,
    recipe_type: str = "menu_recipe",
) -> Recipe | None:
    filters = [
        Recipe.company_id == company_id,
        Recipe.product_id == product_id,
        Recipe.recipe_type == recipe_type,
        Recipe.is_active.is_(True),
    ]
    if brand_id:
        filters.append(Recipe.brand_id == brand_id)
    ordering = (Recipe.version_no.desc(), Recipe.effective_from.desc().nullslast(), Recipe.created_at.desc())
    branch_recipe = await db.scalar(select(Recipe).where(*filters, Recipe.branch_id == branch_id).order_by(*ordering).limit(1))
    if branch_recipe:
        return branch_recipe
    return await db.scalar(select(Recipe).where(*filters, Recipe.branch_id.is_(None)).order_by(*ordering).limit(1))


async def _expand_recipe_purchase_items(
    db: AsyncSession,
    company_id: uuid.UUID,
    branch_id: uuid.UUID,
    product_id: uuid.UUID,
    required_qty: Decimal,
    brand_id: uuid.UUID | None = None,
    visited: set[uuid.UUID] | None = None,
    recipe_type: str = "menu_recipe",
) -> list[dict[str, Any]]:
    visited = visited or set()
    if product_id in visited:
        product = await db.get(Product, product_id)
        return [{
            "product_id": str(product_id),
            "product_name": product.name if product else "ไม่พบสินค้า",
            "sku": product.sku if product else "",
            "qty": _to_float(required_qty),
            "unit": "ชิ้น",
            "amount": 0,
            "source": "cycle_guard",
        }]

    recipe = await _load_recipe_for_product(db, company_id, branch_id, product_id, brand_id, recipe_type)
    if not recipe:
        product = await db.get(Product, product_id)
        return [{
            "product_id": str(product_id),
            "product_name": product.name if product else "ไม่พบสินค้า",
            "sku": product.sku if product else "",
            "qty": _to_float(required_qty),
            "unit": "ชิ้น",
            "amount": 0,
            "source": "no_recipe",
        }]

    rows = (await db.execute(
        select(RecipeIngredient, Product)
        .join(Product, RecipeIngredient.ingredient_id == Product.id)
        .where(RecipeIngredient.recipe_id == recipe.id)
        .order_by(RecipeIngredient.sort_order)
    )).all()
    multiplier = required_qty / Decimal(str(recipe.yield_qty or 1))
    loss_rate = min(max(Decimal(str(recipe.loss_percent or 0)), Decimal("0")), Decimal("100"))
    if loss_rate > 0:
        multiplier = multiplier / (Decimal("1") - (loss_rate / Decimal("100")))
    expanded: list[dict[str, Any]] = []
    next_visited = {*visited, product_id}
    for ingredient, product in rows:
        needed_qty = Decimal(str(ingredient.quantity or 0)) * multiplier
        nested_recipe = await _load_recipe_for_product(db, company_id, branch_id, ingredient.ingredient_id, brand_id, "production_recipe")
        if nested_recipe:
            expanded.extend(await _expand_recipe_purchase_items(
                db,
                company_id,
                branch_id,
                ingredient.ingredient_id,
                needed_qty,
                brand_id,
                next_visited,
                "production_recipe",
            ))
            continue
        expanded.append({
            "product_id": str(ingredient.ingredient_id),
            "product_name": product.name,
            "sku": product.sku,
            "qty": _to_float(needed_qty),
            "unit": ingredient.unit,
            "amount": 0,
            "source": "recipe",
        })
    return expanded


async def _build_central_production_ingredients(
    db: AsyncSession,
    company_id: uuid.UUID,
    brand_id: uuid.UUID | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    status_filter: str | None = None,
) -> list[dict[str, Any]]:
    active_statuses = ["submitted", "reserved_credit", "approved", "packed"]
    filters = [
        CentralOrder.company_id == company_id,
    ]
    if status_filter:
        filters.append(CentralOrder.status == status_filter)
    else:
        filters.append(CentralOrder.status.in_(active_statuses))
    if brand_id:
        filters.append(CentralOrder.brand_id == brand_id)
    if date_from:
        filters.append(CentralOrder.business_date >= date_from.isoformat())
    if date_to:
        filters.append(CentralOrder.business_date <= date_to.isoformat())
    orders = list((await db.scalars(
        select(CentralOrder)
        .options(
            selectinload(CentralOrder.items),
            selectinload(CentralOrder.shift_closure_links).selectinload(CentralOrderShiftClosure.shift_closure),
        )
        .where(*filters)
        .order_by(CentralOrder.submitted_at.desc())
    )).all())
    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    order_sets: dict[tuple[str, str], set[uuid.UUID]] = {}

    for order in orders:
        for item in order.items:
            required_qty = Decimal(str(item.requested_qty or 0))
            if required_qty <= 0:
                continue
            rows: list[dict[str, Any]]
            if item.product_id:
                rows = await _expand_recipe_purchase_items(
                    db,
                    company_id,
                    order.branch_id,
                    item.product_id,
                    required_qty,
                    order.brand_id,
                    recipe_type="production_recipe",
                )
            else:
                rows = [{
                    "product_id": None,
                    "product_name": item.product_name,
                    "sku": item.sku,
                    "qty": _to_float(required_qty),
                    "unit": item.unit,
                    "amount": 0,
                    "source": item.source or "central_order",
                }]
            for row in rows:
                product_key = row.get("product_id") or row.get("sku") or row.get("product_name") or ""
                unit = row.get("unit") or item.unit
                key = (str(product_key), str(unit))
                if key not in grouped:
                    grouped[key] = {
                        "product_id": row.get("product_id"),
                        "sku": row.get("sku") or "",
                        "product_name": row.get("product_name") or "",
                        "unit": unit,
                        "required_qty": Decimal("0"),
                        "sources": set(),
                    }
                    order_sets[key] = set()
                grouped[key]["required_qty"] += Decimal(str(row.get("qty") or 0))
                grouped[key]["sources"].add(row.get("source") or "recipe")
                order_sets[key].add(order.id)

    result = []
    for key, data in grouped.items():
        result.append({
            "product_id": data["product_id"],
            "sku": data["sku"],
            "product_name": data["product_name"],
            "unit": data["unit"],
            "required_qty": _to_float(data["required_qty"]),
            "order_count": len(order_sets.get(key, set())),
            "sources": sorted(data["sources"]),
        })
    result.sort(key=lambda item: (item["product_name"], item["unit"]))
    return result


async def _load_wap_shift_closure(
    db: AsyncSession,
    company_id: uuid.UUID,
    branch_id: uuid.UUID,
    business_date: str,
    brand_id: uuid.UUID | None = None,
    include_items: bool = False,
) -> WapShiftClosure | None:
    filters = [
        WapShiftClosure.company_id == company_id,
        WapShiftClosure.branch_id == branch_id,
        WapShiftClosure.business_date == business_date,
    ]
    if brand_id:
        filters.append(WapShiftClosure.brand_id == brand_id)
    else:
        filters.append(WapShiftClosure.brand_id.is_(None))
    query = select(WapShiftClosure).where(*filters).order_by(WapShiftClosure.closed_at.desc())
    if include_items:
        query = query.options(
            selectinload(WapShiftClosure.items),
            selectinload(WapShiftClosure.central_orders),
            selectinload(WapShiftClosure.central_order_links).selectinload(CentralOrderShiftClosure.central_order),
        )
    return await db.scalar(query.limit(1))


async def _next_wap_shift_round_no(
    db: AsyncSession,
    company_id: uuid.UUID,
    branch_id: uuid.UUID,
    business_date: str,
    brand_id: uuid.UUID | None = None,
) -> int:
    filters = [
        WapShiftClosure.company_id == company_id,
        WapShiftClosure.branch_id == branch_id,
        WapShiftClosure.business_date == business_date,
    ]
    if brand_id:
        filters.append(WapShiftClosure.brand_id == brand_id)
    else:
        filters.append(WapShiftClosure.brand_id.is_(None))
    latest_round = await db.scalar(select(func.coalesce(func.max(WapShiftClosure.round_no), 0)).where(*filters))
    return int(latest_round or 0) + 1


async def _build_wap_cashier_sales_report(
    db: AsyncSession,
    company_id: uuid.UUID,
    branch_id: uuid.UUID,
    date_value: date,
    brand_id: uuid.UUID | None = None,
    start_at: datetime | None = None,
    end_at: datetime | None = None,
) -> list[dict[str, Any]]:
    bkk = ZoneInfo("Asia/Bangkok")
    start_at = start_at or datetime.combine(date_value, time.min, tzinfo=bkk).astimezone(timezone.utc)
    end_at = end_at or datetime.combine(date_value, time.max, tzinfo=bkk).astimezone(timezone.utc)
    filters = [
        SaleOrder.company_id == company_id,
        SaleOrder.branch_id == branch_id,
        SaleOrder.status.in_(["completed", "partially_refunded"]),
        SaleOrder.created_at >= start_at,
        SaleOrder.created_at <= end_at,
    ]
    if brand_id:
        filters.append(Product.brand_id == brand_id)
    else:
        filters.append(Product.brand_id.is_(None))
    rows = (await db.execute(
        select(
            SaleOrder.user_id,
            User.username,
            User.display_name,
            User.first_name,
            User.last_name,
            func.count(distinct(SaleOrder.id)).label("order_count"),
            func.coalesce(func.sum(SaleOrderItem.subtotal), 0).label("total_amount"),
        )
        .join(SaleOrderItem, SaleOrderItem.order_id == SaleOrder.id)
        .join(Product, SaleOrderItem.product_id == Product.id)
        .join(User, SaleOrder.user_id == User.id)
        .where(*filters)
        .group_by(SaleOrder.user_id, User.username, User.display_name, User.first_name, User.last_name)
        .order_by(func.sum(SaleOrderItem.subtotal).desc())
    )).all()
    return [
        {
            "user_id": str(row.user_id),
            "employee_name": row.display_name or " ".join(filter(None, [row.first_name, row.last_name])) or row.username,
            "username": row.username,
            "order_count": int(row.order_count or 0),
            "total_amount": _to_float(row.total_amount),
        }
        for row in rows
    ]


async def _build_wap_shift_close_summary(
    db: AsyncSession,
    company_id: uuid.UUID,
    branch_id: uuid.UUID,
    date_value: date | None = None,
    brand_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    bkk = ZoneInfo("Asia/Bangkok")
    target_date = date_value or datetime.now(bkk).date()
    start_at = datetime.combine(target_date, time.min, tzinfo=bkk).astimezone(timezone.utc)
    end_at = datetime.combine(target_date, time.max, tzinfo=bkk).astimezone(timezone.utc)
    existing_closure = await _load_wap_shift_closure(
        db,
        company_id,
        branch_id,
        target_date.isoformat(),
        brand_id,
        include_items=True,
    )
    if existing_closure:
        start_at = max(start_at, existing_closure.closed_at)
    cashier_sales = await _build_wap_cashier_sales_report(db, company_id, branch_id, target_date, brand_id, start_at, end_at)
    statuses = ["completed", "partially_refunded"]

    item_filters = [
        SaleOrder.company_id == company_id,
        SaleOrder.branch_id == branch_id,
        SaleOrder.status.in_(statuses),
        SaleOrder.created_at >= start_at,
        SaleOrder.created_at <= end_at,
    ]
    if brand_id:
        item_filters.append(Product.brand_id == brand_id)
    else:
        item_filters.append(Product.brand_id.is_(None))

    summary_row = (await db.execute(
        select(
            func.count(distinct(SaleOrder.id)).label("total_orders"),
            func.coalesce(func.sum(SaleOrderItem.subtotal), 0).label("total_amount"),
        )
        .join(SaleOrderItem, SaleOrderItem.order_id == SaleOrder.id)
        .join(Product, SaleOrderItem.product_id == Product.id)
        .where(
            *item_filters,
        )
    )).one()

    if existing_closure and int(summary_row.total_orders or 0) == 0:
        sold_items = [item for item in existing_closure.items if item.item_type == "sold_product"]
        purchase_items = [item for item in existing_closure.items if item.item_type == "purchase_item"]
        return {
            "date": existing_closure.business_date,
            "total_orders": existing_closure.total_orders,
            "total_amount": _to_float(existing_closure.total_amount),
            "products": [
                {
                    "product_id": str(item.product_id) if item.product_id else None,
                    "product_name": item.product_name,
                    "sku": item.sku,
                    "qty": _to_float(item.qty),
                    "unit": item.unit,
                    "amount": _to_float(item.amount),
                    "source": item.source,
                }
                for item in sold_items
            ],
            "purchase_items": [
                {
                    "product_id": str(item.product_id) if item.product_id else None,
                    "product_name": item.product_name,
                    "sku": item.sku,
                    "qty": _to_float(item.qty),
                    "unit": item.unit,
                    "amount": _to_float(item.amount),
                    "source": item.source,
                }
                for item in purchase_items
            ],
            "cashier_sales": cashier_sales,
            "closure_id": str(existing_closure.id),
            "closed_at": existing_closure.closed_at.isoformat() if existing_closure.closed_at else None,
            "existing_closure": _serialize_shift_closure(existing_closure),
            "current_round_no": existing_closure.round_no,
        }

    product_rows = (await db.execute(
        select(
            SaleOrderItem.product_id,
            SaleOrderItem.product_name,
            SaleOrderItem.sku,
            func.coalesce(func.sum(SaleOrderItem.qty), 0).label("qty"),
            func.coalesce(func.sum(SaleOrderItem.subtotal), 0).label("amount"),
        )
        .join(SaleOrder, SaleOrderItem.order_id == SaleOrder.id)
        .join(Product, SaleOrderItem.product_id == Product.id)
        .where(
            *item_filters,
        )
        .group_by(SaleOrderItem.product_id, SaleOrderItem.product_name, SaleOrderItem.sku)
        .order_by(func.sum(SaleOrderItem.subtotal).desc())
    )).all()

    products = [
        {
            "product_id": str(row.product_id),
            "product_name": row.product_name,
            "sku": row.sku,
            "qty": _to_float(row.qty),
            "unit": "ชิ้น",
            "amount": _to_float(row.amount),
        }
        for row in product_rows
    ]

    purchase_by_key: dict[str, dict[str, Any]] = {}
    for row in product_rows:
        expanded_items = await _expand_recipe_purchase_items(
            db,
            company_id,
            branch_id,
            row.product_id,
            Decimal(str(row.qty or 0)),
            brand_id,
        )
        for item in expanded_items:
            key = _recipe_purchase_key(uuid.UUID(item["product_id"]), item["unit"])
            if key not in purchase_by_key:
                purchase_by_key[key] = {**item, "qty": 0}
            purchase_by_key[key]["qty"] += item["qty"]
            if item["source"] == "recipe":
                purchase_by_key[key]["source"] = "recipe"

    purchase_items = sorted(
        purchase_by_key.values(),
        key=lambda item: (item.get("source") != "recipe", item["product_name"]),
    )

    return {
        "date": target_date.isoformat(),
        "total_orders": int(summary_row.total_orders or 0),
        "total_amount": _to_float(summary_row.total_amount),
        "products": products,
        "purchase_items": purchase_items,
        "cashier_sales": cashier_sales,
        "existing_closure": None,
        "previous_closure": _serialize_shift_closure(existing_closure) if existing_closure else None,
        "current_round_no": (existing_closure.round_no + 1) if existing_closure else 1,
    }


@router.get("/wap/shift-close-summary")
async def wap_shift_close_summary(
    date_value: date | None = Query(default=None, alias="date"),
    current: TokenData = Depends(require_permission("fb.order.create")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    if not current.branch_id:
        raise HTTPException(status_code=400, detail="Branch context required")
    return ok(await _build_wap_shift_close_summary(db, current.company_id, current.branch_id, date_value))


async def _close_shift_for_brand(
    brand_slug: str | None,
    current: TokenData = Depends(require_permission("fb.order.create")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    if not current.branch_id:
        raise HTTPException(status_code=400, detail="Branch context required")
    brand = await _load_brand_for_slug(db, current.company_id, brand_slug)
    await _ensure_brand_branch(db, current.company_id, current.branch_id, brand)
    summary = await _build_wap_shift_close_summary(
        db,
        current.company_id,
        current.branch_id,
        brand_id=brand.id if brand else None,
    )
    if summary.get("closure_id"):
        raise HTTPException(status_code=409, detail="วันนี้ปิดกะไปแล้ว กรุณาดูประวัติปิดกะหรือใช้เอกสารเดิม")
    closed_at = datetime.now(timezone.utc)
    closure = WapShiftClosure(
        company_id=current.company_id,
        brand_id=brand.id if brand else None,
        branch_id=current.branch_id,
        closed_by=current.user_id,
        business_date=summary["date"],
        round_no=await _next_wap_shift_round_no(db, current.company_id, current.branch_id, summary["date"], brand.id if brand else None),
        closed_at=closed_at,
        total_orders=summary["total_orders"],
        total_amount=Decimal(str(summary["total_amount"])),
    )
    db.add(closure)
    await db.flush()

    sort_order = 0
    for item_type, rows in (("sold_product", summary["products"]), ("purchase_item", summary["purchase_items"])):
        for row in rows:
            db.add(WapShiftClosureItem(
                closure_id=closure.id,
                company_id=current.company_id,
                branch_id=current.branch_id,
                item_type=item_type,
                product_id=uuid.UUID(row["product_id"]) if row.get("product_id") else None,
                sku=row.get("sku") or "",
                product_name=row.get("product_name") or "",
                qty=Decimal(str(row.get("qty") or 0)),
                unit=row.get("unit") or "ชิ้น",
                amount=Decimal(str(row.get("amount") or 0)),
                source=row.get("source"),
                sort_order=sort_order,
            ))
            sort_order += 1
    await db.commit()
    summary["closure_id"] = str(closure.id)
    summary["closed_at"] = closed_at.isoformat()
    return ok(summary)


@router.post("/wap/shift-close")
async def wap_close_shift(
    current: TokenData = Depends(require_permission("fb.order.create")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    return await _close_shift_for_brand(None, current, db)


@router.get("/store/{brand_slug}/shift-close-summary")
async def store_shift_close_summary(
    brand_slug: str,
    date_value: date | None = Query(default=None, alias="date"),
    current: TokenData = Depends(require_any_permission("brand.store.shift.close", "fb.order.create")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    if not current.branch_id:
        raise HTTPException(status_code=400, detail="Branch context required")
    brand = await _load_brand_for_slug(db, current.company_id, brand_slug)
    await _ensure_brand_branch(db, current.company_id, current.branch_id, brand)
    return ok(await _build_wap_shift_close_summary(
        db,
        current.company_id,
        current.branch_id,
        date_value,
        brand.id if brand else None,
    ))


@router.post("/store/{brand_slug}/shift-close")
async def store_close_shift(
    brand_slug: str,
    current: TokenData = Depends(require_any_permission("brand.store.shift.close", "fb.order.create")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    return await _close_shift_for_brand(brand_slug, current, db)


async def _list_shift_closures_for_brand(
    brand_slug: str | None,
    current: TokenData,
    db: AsyncSession,
    limit: int = 30,
) -> dict[str, Any]:
    if not current.branch_id:
        raise HTTPException(status_code=400, detail="Branch context required")
    brand = await _load_brand_for_slug(db, current.company_id, brand_slug)
    await _ensure_brand_branch(db, current.company_id, current.branch_id, brand)
    filters = [
        WapShiftClosure.company_id == current.company_id,
        WapShiftClosure.branch_id == current.branch_id,
    ]
    if brand:
        filters.append(WapShiftClosure.brand_id == brand.id)
    else:
        filters.append(WapShiftClosure.brand_id.is_(None))
    rows = (await db.execute(
        select(WapShiftClosure, User.display_name, User.first_name, User.last_name, User.username)
        .outerjoin(User, WapShiftClosure.closed_by == User.id)
        .options(
            selectinload(WapShiftClosure.items),
            selectinload(WapShiftClosure.central_orders),
            selectinload(WapShiftClosure.central_order_links).selectinload(CentralOrderShiftClosure.central_order),
        )
        .where(*filters)
        .order_by(WapShiftClosure.closed_at.desc())
        .limit(max(1, min(limit, 100)))
    )).all()
    return ok([
        _serialize_shift_closure(
            closure,
            closed_by_name=display_name or " ".join(filter(None, [first_name, last_name])) or username,
            include_items=True,
        )
        for closure, display_name, first_name, last_name, username in rows
    ])


@router.get("/wap/shift-closures")
async def list_wap_shift_closures(
    limit: int = Query(default=30, ge=1, le=100),
    current: TokenData = Depends(require_permission("fb.order.create")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    return await _list_shift_closures_for_brand(None, current, db, limit)


@router.get("/store/{brand_slug}/shift-closures")
async def list_store_shift_closures(
    brand_slug: str,
    limit: int = Query(default=30, ge=1, le=100),
    current: TokenData = Depends(require_any_permission("brand.store.shift.close", "brand.store.replenishment.submit", "brand.store.delivery.receive", "fb.order.create")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    return await _list_shift_closures_for_brand(brand_slug, current, db, limit)


@router.get("/wap/reports/cashiers")
async def wap_cashier_sales_report(
    date_value: date | None = Query(default=None, alias="date"),
    current: TokenData = Depends(require_permission("fb.order.create")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    if not current.branch_id:
        raise HTTPException(status_code=400, detail="Branch context required")
    target_date = date_value or datetime.now(ZoneInfo("Asia/Bangkok")).date()
    return ok(await _build_wap_cashier_sales_report(db, current.company_id, current.branch_id, target_date, None))


@router.get("/store/{brand_slug}/reports/cashiers")
async def store_cashier_sales_report(
    brand_slug: str,
    date_value: date | None = Query(default=None, alias="date"),
    current: TokenData = Depends(require_any_permission("brand.store.shift.close", "brand.store.order.create", "fb.order.create")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    if not current.branch_id:
        raise HTTPException(status_code=400, detail="Branch context required")
    brand = await _load_brand_for_slug(db, current.company_id, brand_slug)
    await _ensure_brand_branch(db, current.company_id, current.branch_id, brand)
    target_date = date_value or datetime.now(ZoneInfo("Asia/Bangkok")).date()
    return ok(await _build_wap_cashier_sales_report(db, current.company_id, current.branch_id, target_date, brand.id if brand else None))


async def _next_central_order_number(db: AsyncSession, company_id: uuid.UUID, business_date: str) -> str:
    compact_date = business_date.replace("-", "")
    prefix = f"CO-{compact_date}-"
    count = await db.scalar(
        select(func.count(CentralOrder.id)).where(
            CentralOrder.company_id == company_id,
            CentralOrder.order_number.like(f"{prefix}%"),
        )
    )
    return f"{prefix}{int(count or 0) + 1:03d}"


async def _load_daily_central_order(
    db: AsyncSession,
    company_id: uuid.UUID,
    branch_id: uuid.UUID,
    business_date: str,
    brand_id: uuid.UUID | None,
) -> CentralOrder | None:
    filters = [
        CentralOrder.company_id == company_id,
        CentralOrder.branch_id == branch_id,
        CentralOrder.business_date == business_date,
    ]
    if brand_id:
        filters.append(CentralOrder.brand_id == brand_id)
    else:
        filters.append(CentralOrder.brand_id.is_(None))
    return await db.scalar(
        select(CentralOrder)
        .options(
            selectinload(CentralOrder.items),
            selectinload(CentralOrder.transfer_order),
            selectinload(CentralOrder.shift_closure_links).selectinload(CentralOrderShiftClosure.shift_closure),
        )
        .where(*filters)
        .order_by(CentralOrder.submitted_at.asc())
        .limit(1)
    )


async def _load_closed_shift_closures_for_day(
    db: AsyncSession,
    company_id: uuid.UUID,
    branch_id: uuid.UUID,
    business_date: str,
    brand_id: uuid.UUID | None,
) -> list[WapShiftClosure]:
    filters = [
        WapShiftClosure.company_id == company_id,
        WapShiftClosure.branch_id == branch_id,
        WapShiftClosure.business_date == business_date,
    ]
    if brand_id:
        filters.append(WapShiftClosure.brand_id == brand_id)
    else:
        filters.append(WapShiftClosure.brand_id.is_(None))
    return list((await db.scalars(
        select(WapShiftClosure)
        .options(
            selectinload(WapShiftClosure.items),
            selectinload(WapShiftClosure.central_orders),
            selectinload(WapShiftClosure.central_order_links).selectinload(CentralOrderShiftClosure.central_order),
        )
        .where(*filters)
        .order_by(WapShiftClosure.round_no.asc(), WapShiftClosure.closed_at.asc())
    )).all())


def _aggregate_purchase_items_from_closures(closures: list[WapShiftClosure]) -> list[dict[str, Any]]:
    purchase_by_key: dict[str, dict[str, Any]] = {}
    for closure in closures:
        for item in closure.items:
            if item.item_type != "purchase_item":
                continue
            key = _recipe_purchase_key(item.product_id, item.unit) if item.product_id else f"{item.sku}:{item.unit}"
            if key not in purchase_by_key:
                purchase_by_key[key] = {
                    "product_id": str(item.product_id) if item.product_id else None,
                    "product_name": item.product_name,
                    "sku": item.sku,
                    "qty": Decimal("0"),
                    "unit": item.unit,
                    "amount": Decimal("0"),
                    "source": item.source,
                }
            purchase_by_key[key]["qty"] += Decimal(str(item.qty or 0))
            purchase_by_key[key]["amount"] += Decimal(str(item.amount or 0))
            if item.source == "recipe":
                purchase_by_key[key]["source"] = "recipe"
    return [
        {**item, "qty": _to_float(item["qty"]), "amount": _to_float(item["amount"])}
        for item in sorted(purchase_by_key.values(), key=lambda row: (row.get("source") != "recipe", row["product_name"]))
    ]


def _serialize_daily_central_order_summary(
    business_date: str,
    closures: list[WapShiftClosure],
    purchase_items: list[dict[str, Any]],
    existing_order: CentralOrder | None,
    branch_name: str | None = None,
) -> dict[str, Any]:
    return {
        "date": business_date,
        "branch_name": branch_name,
        "closure_count": len(closures),
        "total_orders": sum(int(closure.total_orders or 0) for closure in closures),
        "total_amount": _to_float(sum((closure.total_amount for closure in closures), Decimal("0"))),
        "purchase_items": purchase_items,
        "closures": [_serialize_shift_closure(closure) for closure in closures],
        "existing_order": _serialize_central_order(existing_order, branch_name) if existing_order else None,
    }


async def _build_daily_central_order_summary(
    db: AsyncSession,
    company_id: uuid.UUID,
    branch_id: uuid.UUID,
    business_date: str,
    brand_id: uuid.UUID | None,
) -> dict[str, Any]:
    closures = await _load_closed_shift_closures_for_day(db, company_id, branch_id, business_date, brand_id)
    existing_order = await _load_daily_central_order(db, company_id, branch_id, business_date, brand_id)
    branch = await db.get(Branch, branch_id)
    return _serialize_daily_central_order_summary(
        business_date,
        closures,
        _aggregate_purchase_items_from_closures(closures),
        existing_order,
        branch.name if branch else None,
    )


async def _submit_daily_central_order(
    brand_slug: str | None,
    payload: CentralOrderSubmitRequest,
    current: TokenData,
    db: AsyncSession,
    date_value: date | None = None,
) -> dict[str, Any]:
    if not current.branch_id:
        raise HTTPException(status_code=400, detail="Branch context required")
    brand = await _load_brand_for_slug(db, current.company_id, brand_slug)
    brand_branch = None
    if brand:
        brand_branch = await _ensure_brand_branch(db, current.company_id, current.branch_id, brand)
    business_date = (date_value or datetime.now(ZoneInfo("Asia/Bangkok")).date()).isoformat()
    existing = await _load_daily_central_order(db, current.company_id, current.branch_id, business_date, brand.id if brand else None)
    branch = await db.get(Branch, current.branch_id)
    if existing:
        return ok(_serialize_central_order(existing, branch.name if branch else None))

    closures = await _load_closed_shift_closures_for_day(db, current.company_id, current.branch_id, business_date, brand.id if brand else None)
    if not closures:
        raise HTTPException(status_code=400, detail="ยังไม่มีรอบปิดกะสำหรับวันนี้")

    replenishment_by_product: dict[uuid.UUID, dict[str, Any]] = {}
    if brand:
        if brand_branch is None or brand_branch.store_location_id is None:
            raise HTTPException(status_code=400, detail="กรุณาตั้งค่าคลัง STORE-STOCK ของสาขาก่อน")
        replenishment = await ReplenishmentService(db).suggestion(
            company_id=current.company_id,
            brand_id=brand.id,
            branch_id=current.branch_id,
            location_id=brand_branch.store_location_id,
            business_date=date.fromisoformat(business_date),
        )
        replenishment_by_product = {
            uuid.UUID(item["product_id"]): item
            for item in replenishment["items"]
        }

    source_items = payload.items or []
    if not source_items:
        aggregate_items = (
            list(replenishment_by_product.values())
            if brand
            else _aggregate_purchase_items_from_closures(closures)
        )
        source_items = [
            type("DailyCentralOrderItem", (), {
                "product_id": uuid.UUID(item["product_id"]) if item.get("product_id") else None,
                "sku": item["sku"],
                "product_name": item["product_name"],
                "unit": item["unit"],
                "system_qty": item.get("suggested_qty", item.get("qty", 0)),
                "requested_qty": item.get("suggested_qty", item.get("qty", 0)),
                "source": item.get("source"),
            })()
            for item in aggregate_items
            if Decimal(str(item.get("suggested_qty", item.get("qty", 0)))) > 0
        ]
    if not source_items:
        raise HTTPException(status_code=400, detail="ไม่มีรายการสั่งสินค้า")

    product_ids = [item.product_id for item in source_items if item.product_id]
    products_by_id = {
        product.id: product
        for product in (await db.scalars(
            select(Product).where(Product.company_id == current.company_id, Product.id.in_(product_ids))
        )).all()
    } if product_ids else {}
    request_total = Decimal("0")
    prepared_items: list[dict[str, Any]] = []
    for item in source_items:
        requested_qty = max(Decimal(str(item.requested_qty or 0)), Decimal("0"))
        recommendation = replenishment_by_product.get(item.product_id) if item.product_id else None
        if brand and recommendation is None:
            raise HTTPException(
                status_code=400,
                detail=f"สินค้า {item.product_name} ไม่อยู่ในรายการ replenishment ของสาขานี้",
            )
        system_qty = max(
            Decimal(str(recommendation["suggested_qty"] if recommendation else item.system_qty or 0)),
            Decimal("0"),
        )
        product = products_by_id.get(item.product_id) if item.product_id else None
        unit_cost = Decimal(str(product.cost_price or 0)) if product else Decimal("0")
        requested_amount = _money(unit_cost * requested_qty)
        request_total += requested_amount
        prepared_items.append({
            "payload": item,
            "system_qty": system_qty,
            "requested_qty": requested_qty,
            "unit_cost": unit_cost,
            "requested_amount": requested_amount,
            "source": recommendation["source"] if recommendation else item.source,
        })

    primary_closure = closures[0]
    order = CentralOrder(
        company_id=current.company_id,
        brand_id=brand.id if brand else primary_closure.brand_id,
        branch_id=current.branch_id,
        shift_closure_id=primary_closure.id,
        order_number=await _next_central_order_number(db, current.company_id, business_date),
        status="submitted",
        business_date=business_date,
        submitted_by=current.user_id,
        submitted_at=datetime.now(timezone.utc),
        note=payload.note,
    )
    db.add(order)
    await db.flush()

    for closure in closures:
        db.add(CentralOrderShiftClosure(
            central_order_id=order.id,
            shift_closure_id=closure.id,
            company_id=current.company_id,
            brand_id=brand.id if brand else closure.brand_id,
            branch_id=current.branch_id,
            business_date=business_date,
        ))

    for index, prepared in enumerate(prepared_items):
        item = prepared["payload"]
        db.add(CentralOrderItem(
            order_id=order.id,
            company_id=current.company_id,
            branch_id=current.branch_id,
            product_id=item.product_id,
            sku=item.sku.strip(),
            product_name=item.product_name.strip(),
            unit=item.unit.strip() or "ชิ้น",
            unit_cost=prepared["unit_cost"],
            system_qty=prepared["system_qty"],
            requested_qty=prepared["requested_qty"],
            requested_amount=prepared["requested_amount"],
            source=prepared["source"],
            sort_order=index,
        ))

    if brand and brand_branch and brand_branch.branch_type == "franchise" and request_total > 0:
        account = await _get_or_create_credit_account(db, current.company_id, brand.id, current.branch_id)
        if not account.is_active:
            raise HTTPException(status_code=400, detail="บัญชีเครดิตสาขานี้ถูกปิดใช้งาน")
        if _available_credit(account) < _money(request_total):
            raise HTTPException(status_code=400, detail="เครดิตไม่พอสำหรับส่งใบสั่งสินค้า")
        account.reserved_amount = _money(account.reserved_amount + request_total)
        order.status = "reserved_credit"
        order.credit_reserved_amount = _money(request_total)
        _add_credit_ledger(
            db,
            account,
            "reserve",
            request_total,
            current.user_id,
            "central_order",
            str(order.id),
            f"Reserve credit for {order.order_number}",
        )

    await db.commit()
    saved = await _load_daily_central_order(db, current.company_id, current.branch_id, business_date, brand.id if brand else None)
    return ok(_serialize_central_order(saved or order, branch.name if branch else None))


async def _submit_central_order_for_closure(
    closure_id: uuid.UUID,
    payload: CentralOrderSubmitRequest,
    brand_slug: str | None,
    current: TokenData = Depends(require_permission("fb.order.create")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    if not current.branch_id:
        raise HTTPException(status_code=400, detail="Branch context required")
    closure = await db.get(WapShiftClosure, closure_id)
    if not closure or closure.company_id != current.company_id or closure.branch_id != current.branch_id:
        raise HTTPException(status_code=404, detail="ไม่พบเอกสารปิดกะ")
    brand = await _load_brand_for_slug(db, current.company_id, brand_slug)
    await _ensure_brand_branch(db, current.company_id, current.branch_id, brand)
    if brand and closure.brand_id and closure.brand_id != brand.id:
        raise HTTPException(status_code=400, detail="เอกสารปิดกะไม่ตรงกับแบรนด์")
    brand_branch = None
    if brand:
        brand_branch = await _ensure_brand_branch(db, current.company_id, current.branch_id, brand)
    daily_existing = await _load_daily_central_order(
        db,
        current.company_id,
        current.branch_id,
        closure.business_date,
        brand.id if brand else closure.brand_id,
    )
    if daily_existing:
        branch = await db.get(Branch, daily_existing.branch_id)
        return ok(_serialize_central_order(daily_existing, branch.name if branch else None))
    existing = await db.scalar(
        select(CentralOrder)
        .options(
            selectinload(CentralOrder.items),
            selectinload(CentralOrder.transfer_order),
            selectinload(CentralOrder.shift_closure_links).selectinload(CentralOrderShiftClosure.shift_closure),
        )
        .where(
            CentralOrder.company_id == current.company_id,
            CentralOrder.shift_closure_id == closure_id,
        )
    )
    if existing:
        branch = await db.get(Branch, existing.branch_id)
        return ok(_serialize_central_order(existing, branch.name if branch else None))
    if not payload.items:
        raise HTTPException(status_code=400, detail="ไม่มีรายการสั่งสินค้า")

    product_ids = [item.product_id for item in payload.items if item.product_id]
    products_by_id = {
        product.id: product
        for product in (await db.scalars(
            select(Product).where(Product.company_id == current.company_id, Product.id.in_(product_ids))
        )).all()
    } if product_ids else {}
    request_total = Decimal("0")
    prepared_items: list[dict[str, Any]] = []
    for item in payload.items:
        requested_qty = max(Decimal(str(item.requested_qty or 0)), Decimal("0"))
        system_qty = max(Decimal(str(item.system_qty or 0)), Decimal("0"))
        product = products_by_id.get(item.product_id) if item.product_id else None
        unit_cost = Decimal(str(product.cost_price or 0)) if product else Decimal("0")
        requested_amount = _money(unit_cost * requested_qty)
        request_total += requested_amount
        prepared_items.append({
            "payload": item,
            "system_qty": system_qty,
            "requested_qty": requested_qty,
            "unit_cost": unit_cost,
            "requested_amount": requested_amount,
        })

    order = CentralOrder(
        company_id=current.company_id,
        brand_id=brand.id if brand else closure.brand_id,
        branch_id=current.branch_id,
        shift_closure_id=closure.id,
        order_number=await _next_central_order_number(db, current.company_id, closure.business_date),
        status="submitted",
        business_date=closure.business_date,
        submitted_by=current.user_id,
        submitted_at=datetime.now(timezone.utc),
        note=payload.note,
    )
    db.add(order)
    await db.flush()
    db.add(CentralOrderShiftClosure(
        central_order_id=order.id,
        shift_closure_id=closure.id,
        company_id=current.company_id,
        brand_id=brand.id if brand else closure.brand_id,
        branch_id=current.branch_id,
        business_date=closure.business_date,
    ))

    for index, prepared in enumerate(prepared_items):
        item = prepared["payload"]
        db.add(CentralOrderItem(
            order_id=order.id,
            company_id=current.company_id,
            branch_id=current.branch_id,
            product_id=item.product_id,
            sku=item.sku.strip(),
            product_name=item.product_name.strip(),
            unit=item.unit.strip() or "ชิ้น",
            unit_cost=prepared["unit_cost"],
            system_qty=prepared["system_qty"],
            requested_qty=prepared["requested_qty"],
            requested_amount=prepared["requested_amount"],
            source=item.source,
            sort_order=index,
        ))

    if brand and brand_branch and brand_branch.branch_type == "franchise" and request_total > 0:
        account = await _get_or_create_credit_account(db, current.company_id, brand.id, current.branch_id)
        if not account.is_active:
            raise HTTPException(status_code=400, detail="บัญชีเครดิตสาขานี้ถูกปิดใช้งาน")
        if _available_credit(account) < _money(request_total):
            raise HTTPException(status_code=400, detail="เครดิตไม่พอสำหรับส่งใบสั่งสินค้า")
        account.reserved_amount = _money(account.reserved_amount + request_total)
        order.status = "reserved_credit"
        order.credit_reserved_amount = _money(request_total)
        _add_credit_ledger(
            db,
            account,
            "reserve",
            request_total,
            current.user_id,
            "central_order",
            str(order.id),
            f"Reserve credit for {order.order_number}",
        )

    await db.commit()
    saved = await db.scalar(
        select(CentralOrder)
        .options(
            selectinload(CentralOrder.items),
            selectinload(CentralOrder.transfer_order),
            selectinload(CentralOrder.shift_closure_links).selectinload(CentralOrderShiftClosure.shift_closure),
        )
        .where(CentralOrder.id == order.id)
    )
    branch = await db.get(Branch, current.branch_id)
    return ok(_serialize_central_order(saved or order, branch.name if branch else None))


@router.post("/wap/shift-closures/{closure_id}/central-order", status_code=status.HTTP_201_CREATED)
async def wap_submit_central_order(
    closure_id: uuid.UUID,
    payload: CentralOrderSubmitRequest,
    current: TokenData = Depends(require_permission("fb.order.create")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    return await _submit_central_order_for_closure(closure_id, payload, None, current, db)


@router.post("/store/{brand_slug}/shift-closures/{closure_id}/central-order", status_code=status.HTTP_201_CREATED)
async def store_submit_central_order(
    brand_slug: str,
    closure_id: uuid.UUID,
    payload: CentralOrderSubmitRequest,
    current: TokenData = Depends(require_any_permission("brand.store.replenishment.submit", "fb.order.create")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    return await _submit_central_order_for_closure(closure_id, payload, brand_slug, current, db)


@router.get("/wap/daily-central-order-summary")
async def wap_daily_central_order_summary(
    date_value: date | None = Query(default=None, alias="date"),
    current: TokenData = Depends(require_permission("fb.order.create")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    if not current.branch_id:
        raise HTTPException(status_code=400, detail="Branch context required")
    business_date = (date_value or datetime.now(ZoneInfo("Asia/Bangkok")).date()).isoformat()
    return ok(await _build_daily_central_order_summary(db, current.company_id, current.branch_id, business_date, None))


@router.post("/wap/daily-central-order", status_code=status.HTTP_201_CREATED)
async def wap_submit_daily_central_order(
    payload: CentralOrderSubmitRequest,
    date_value: date | None = Query(default=None, alias="date"),
    current: TokenData = Depends(require_permission("fb.order.create")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    return await _submit_daily_central_order(None, payload, current, db, date_value)


@router.get("/store/{brand_slug}/daily-central-order-summary")
async def store_daily_central_order_summary(
    brand_slug: str,
    date_value: date | None = Query(default=None, alias="date"),
    current: TokenData = Depends(require_any_permission("brand.store.replenishment.submit", "brand.store.shift.close", "fb.order.create")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    if not current.branch_id:
        raise HTTPException(status_code=400, detail="Branch context required")
    brand = await _load_brand_for_slug(db, current.company_id, brand_slug)
    await _ensure_brand_branch(db, current.company_id, current.branch_id, brand)
    business_date = (date_value or datetime.now(ZoneInfo("Asia/Bangkok")).date()).isoformat()
    return ok(await _build_daily_central_order_summary(db, current.company_id, current.branch_id, business_date, brand.id))


@router.post("/store/{brand_slug}/daily-central-order", status_code=status.HTTP_201_CREATED)
async def store_submit_daily_central_order(
    brand_slug: str,
    payload: CentralOrderSubmitRequest,
    date_value: date | None = Query(default=None, alias="date"),
    current: TokenData = Depends(require_any_permission("brand.store.replenishment.submit", "fb.order.create")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    return await _submit_daily_central_order(brand_slug, payload, current, db, date_value)


@router.get("/central/orders")
async def list_central_orders(
    status_filter: str | None = Query(default=None, alias="status"),
    current: TokenData = Depends(require_permission("fb.kitchen.manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    q = (
        select(CentralOrder, Branch.name.label("branch_name"))
        .join(Branch, CentralOrder.branch_id == Branch.id)
        .where(CentralOrder.company_id == current.company_id)
        .order_by(CentralOrder.submitted_at.desc())
    )
    if status_filter:
        q = q.where(CentralOrder.status == status_filter)
    rows = (await db.execute(q)).all()
    return ok([
        {
            "id": str(order.id),
            "order_number": order.order_number,
            "status": order.status,
            "branch_id": str(order.branch_id),
            "branch_name": branch_name,
            "business_date": order.business_date,
            "submitted_at": order.submitted_at.isoformat() if order.submitted_at else None,
            "item_count": await db.scalar(
                select(func.count(CentralOrderItem.id)).where(CentralOrderItem.order_id == order.id)
            ),
        }
        for order, branch_name in rows
    ])


@router.get("/central/{brand_slug}/orders")
async def list_brand_central_orders(
    brand_slug: str,
    status_filter: str | None = Query(default=None, alias="status"),
    current: TokenData = Depends(require_permission("fb.kitchen.manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    brand = await _load_brand_for_slug(db, current.company_id, brand_slug)
    q = (
        select(CentralOrder, Branch.name.label("branch_name"))
        .join(Branch, CentralOrder.branch_id == Branch.id)
        .where(CentralOrder.company_id == current.company_id, CentralOrder.brand_id == brand.id)
        .order_by(CentralOrder.submitted_at.desc())
    )
    if status_filter:
        q = q.where(CentralOrder.status == status_filter)
    rows = (await db.execute(q)).all()
    return ok([
        {
            "id": str(order.id),
            "order_number": order.order_number,
            "status": order.status,
            "branch_id": str(order.branch_id),
            "branch_name": branch_name,
            "business_date": order.business_date,
            "submitted_at": order.submitted_at.isoformat() if order.submitted_at else None,
            "item_count": await db.scalar(
                select(func.count(CentralOrderItem.id)).where(CentralOrderItem.order_id == order.id)
            ),
        }
        for order, branch_name in rows
    ])


@router.get("/central/orders/{order_id}")
async def get_central_order(
    order_id: uuid.UUID,
    current: TokenData = Depends(require_permission("fb.kitchen.manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    order = await db.scalar(
        select(CentralOrder)
        .options(
            selectinload(CentralOrder.items),
            selectinload(CentralOrder.transfer_order),
            selectinload(CentralOrder.shift_closure_links).selectinload(CentralOrderShiftClosure.shift_closure),
        )
        .where(CentralOrder.id == order_id, CentralOrder.company_id == current.company_id)
    )
    if not order:
        raise HTTPException(status_code=404, detail="ไม่พบใบสั่งสินค้า")
    branch = await db.get(Branch, order.branch_id)
    return ok(_serialize_central_order(order, branch.name if branch else None))


@router.get("/central/{brand_slug}/orders/{order_id}")
async def get_brand_central_order(
    brand_slug: str,
    order_id: uuid.UUID,
    current: TokenData = Depends(require_permission("fb.kitchen.manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    brand = await _load_brand_for_slug(db, current.company_id, brand_slug)
    order = await _load_central_order(db, order_id, current.company_id)
    if order.brand_id != brand.id:
        raise HTTPException(status_code=404, detail="ไม่พบใบสั่งสินค้าของแบรนด์นี้")
    branch = await db.get(Branch, order.branch_id)
    return ok(_serialize_central_order(order, branch.name if branch else None))


@router.post("/central/orders/{order_id}/approve")
async def approve_central_order(
    order_id: uuid.UUID,
    payload: CentralOrderQtyUpdateRequest | None = None,
    current: TokenData = Depends(require_permission("fb.kitchen.manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    order = await _load_central_order(db, order_id, current.company_id)
    _require_central_status(order, ["submitted", "reserved_credit"])
    qty_by_item = {item.item_id: max(Decimal(str(item.qty or 0)), Decimal("0")) for item in (payload.items if payload else [])}
    for item in order.items:
        item.approved_qty = qty_by_item.get(item.id, item.requested_qty)
        item.approved_amount = _money(item.unit_cost * item.approved_qty)
    order.status = "approved"
    order.approved_by = current.user_id
    order.approved_at = datetime.now(timezone.utc)
    await db.commit()
    branch = await db.get(Branch, order.branch_id)
    return ok(_serialize_central_order(order, branch.name if branch else None))


@router.post("/central/orders/{order_id}/pack")
async def pack_central_order(
    order_id: uuid.UUID,
    payload: CentralOrderQtyUpdateRequest | None = None,
    current: TokenData = Depends(require_permission("fb.kitchen.manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    order = await _load_central_order(db, order_id, current.company_id)
    _require_central_status(order, ["approved"])
    qty_by_item = {item.item_id: max(Decimal(str(item.qty or 0)), Decimal("0")) for item in (payload.items if payload else [])}
    for item in order.items:
        default_qty = item.approved_qty if item.approved_qty > 0 else item.requested_qty
        item.shipped_qty = qty_by_item.get(item.id, default_qty)
        item.shipped_amount = _money(item.unit_cost * item.shipped_qty)
    order.status = "packed"
    order.packed_by = current.user_id
    order.packed_at = datetime.now(timezone.utc)
    await db.commit()
    branch = await db.get(Branch, order.branch_id)
    return ok(_serialize_central_order(order, branch.name if branch else None))


@router.post("/central/orders/{order_id}/ship")
async def ship_central_order(
    order_id: uuid.UUID,
    current: TokenData = Depends(require_permission("fb.kitchen.manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    try:
        order = await _load_central_order(db, order_id, current.company_id, lock=True)
        _require_central_status(order, ["packed"])
        shipped_amount = _money(sum((item.shipped_amount for item in order.items), Decimal("0")))
        if order.brand_id and order.credit_reserved_amount > 0:
            account = await _get_or_create_credit_account(db, current.company_id, order.brand_id, order.branch_id)
            reserved = _money(order.credit_reserved_amount)
            extra_needed = max(shipped_amount - reserved, Decimal("0"))
            if extra_needed > 0:
                if _available_credit(account) < extra_needed:
                    raise HTTPException(status_code=400, detail="เครดิตไม่พอสำหรับยอดส่งจริง")
                account.reserved_amount = _money(account.reserved_amount + extra_needed)
                order.credit_reserved_amount = _money(order.credit_reserved_amount + extra_needed)
                reserved = _money(order.credit_reserved_amount)
                _add_credit_ledger(
                    db,
                    account,
                    "reserve",
                    extra_needed,
                    current.user_id,
                    "central_order",
                    str(order.id),
                    f"Reserve extra credit for {order.order_number}",
                )
            capture_amount = min(shipped_amount, reserved)
            release_amount = max(reserved - capture_amount, Decimal("0"))
            if capture_amount > 0:
                account.balance = _money(account.balance - capture_amount)
                account.reserved_amount = _money(max(account.reserved_amount - capture_amount, Decimal("0")))
                order.credit_captured_amount = capture_amount
                _add_credit_ledger(
                    db,
                    account,
                    "capture",
                    capture_amount,
                    current.user_id,
                    "central_order",
                    str(order.id),
                    f"Capture credit for {order.order_number}",
                )
            if release_amount > 0:
                account.reserved_amount = _money(max(account.reserved_amount - release_amount, Decimal("0")))
                order.credit_released_amount = release_amount
                _add_credit_ledger(
                    db,
                    account,
                    "release",
                    release_amount,
                    current.user_id,
                    "central_order",
                    str(order.id),
                    f"Release unused credit for {order.order_number}",
                )
        order.status = "shipped"
        order.shipped_by = current.user_id
        order.shipped_at = datetime.now(timezone.utc)
        await _create_transfer_for_central_order(db, order, current.user_id)
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    branch = await db.get(Branch, order.branch_id)
    return ok(_serialize_central_order(order, branch.name if branch else None))


@router.post("/central/orders/{order_id}/cancel")
async def cancel_central_order(
    order_id: uuid.UUID,
    payload: CancelRequest,
    current: TokenData = Depends(require_permission("fb.kitchen.manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    order = await _load_central_order(db, order_id, current.company_id)
    _require_central_status(order, ["submitted", "reserved_credit", "approved", "packed"])
    release_amount = _money(
        max(
            Decimal(str(order.credit_reserved_amount or 0))
            - Decimal(str(order.credit_captured_amount or 0))
            - Decimal(str(order.credit_released_amount or 0)),
            Decimal("0"),
        )
    )
    if order.brand_id and release_amount > 0:
        account = await _get_or_create_credit_account(db, current.company_id, order.brand_id, order.branch_id)
        account.reserved_amount = _money(max(account.reserved_amount - release_amount, Decimal("0")))
        order.credit_released_amount = _money(order.credit_released_amount + release_amount)
        _add_credit_ledger(
            db,
            account,
            "release",
            release_amount,
            current.user_id,
            "central_order",
            str(order.id),
            f"Cancel {order.order_number}: {payload.reason}",
        )
    order.status = "cancelled"
    order.note = f"{order.note or ''}\nCancelled: {payload.reason}".strip()
    await db.commit()
    branch = await db.get(Branch, order.branch_id)
    return ok(_serialize_central_order(order, branch.name if branch else None))


@router.get("/wap/central-orders")
async def list_wap_central_orders(
    current: TokenData = Depends(require_permission("fb.order.create")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    if not current.branch_id:
        raise HTTPException(status_code=400, detail="Branch context required")
    orders = list((await db.scalars(
        select(CentralOrder)
        .options(
            selectinload(CentralOrder.items),
            selectinload(CentralOrder.transfer_order),
            selectinload(CentralOrder.shift_closure_links).selectinload(CentralOrderShiftClosure.shift_closure),
        )
        .where(
            CentralOrder.company_id == current.company_id,
            CentralOrder.branch_id == current.branch_id,
        )
        .order_by(CentralOrder.submitted_at.desc())
    )).all())
    branch = await db.get(Branch, current.branch_id)
    return ok([_serialize_central_order(order, branch.name if branch else None) for order in orders])


@router.get("/store/{brand_slug}/central-orders")
async def list_store_central_orders(
    brand_slug: str,
    current: TokenData = Depends(require_any_permission("brand.store.replenishment.submit", "brand.store.delivery.receive", "fb.order.create")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    if not current.branch_id:
        raise HTTPException(status_code=400, detail="Branch context required")
    brand = await _load_brand_for_slug(db, current.company_id, brand_slug)
    await _ensure_brand_branch(db, current.company_id, current.branch_id, brand)
    orders = list((await db.scalars(
        select(CentralOrder)
        .options(
            selectinload(CentralOrder.items),
            selectinload(CentralOrder.transfer_order),
            selectinload(CentralOrder.shift_closure_links).selectinload(CentralOrderShiftClosure.shift_closure),
        )
        .where(
            CentralOrder.company_id == current.company_id,
            CentralOrder.branch_id == current.branch_id,
            CentralOrder.brand_id == brand.id,
        )
        .order_by(CentralOrder.submitted_at.desc())
    )).all())
    branch = await db.get(Branch, current.branch_id)
    return ok([_serialize_central_order(order, branch.name if branch else None) for order in orders])


@router.post("/wap/central-orders/{order_id}/receive")
async def receive_wap_central_order(
    order_id: uuid.UUID,
    payload: CentralOrderReceiveRequest | None = None,
    current: TokenData = Depends(require_permission("fb.order.create")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    if not current.branch_id:
        raise HTTPException(status_code=400, detail="Branch context required")
    try:
        order = await _load_central_order(db, order_id, current.company_id, lock=True)
        if order.branch_id != current.branch_id:
            raise HTTPException(status_code=404, detail="ไม่พบใบสั่งสินค้าของสาขานี้")
        _require_central_status(order, ["shipped", "partially_received"])
        await _receive_transfer_for_central_order(db, order, current.user_id, payload)
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    branch = await db.get(Branch, order.branch_id)
    return ok(_serialize_central_order(order, branch.name if branch else None))


@router.post("/store/{brand_slug}/central-orders/{order_id}/receive")
async def receive_store_central_order(
    brand_slug: str,
    order_id: uuid.UUID,
    payload: CentralOrderReceiveRequest | None = None,
    current: TokenData = Depends(require_any_permission("brand.store.delivery.receive", "fb.order.create")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    if not current.branch_id:
        raise HTTPException(status_code=400, detail="Branch context required")
    brand = await _load_brand_for_slug(db, current.company_id, brand_slug)
    await _ensure_brand_branch(db, current.company_id, current.branch_id, brand)
    try:
        order = await _load_central_order(db, order_id, current.company_id, lock=True)
        if order.branch_id != current.branch_id or order.brand_id != brand.id:
            raise HTTPException(status_code=404, detail="ไม่พบใบสั่งสินค้าของแบรนด์นี้")
        _require_central_status(order, ["shipped", "partially_received"])
        await _receive_transfer_for_central_order(db, order, current.user_id, payload)
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    branch = await db.get(Branch, order.branch_id)
    return ok(_serialize_central_order(order, branch.name if branch else None))


@router.get("/central/production-summary")
async def get_central_production_summary(
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    current: TokenData = Depends(require_permission("fb.kitchen.manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    active_statuses = ["submitted", "reserved_credit", "approved", "packed"]
    filters = [
        CentralOrder.company_id == current.company_id,
    ]
    if status_filter:
        filters.append(CentralOrder.status == status_filter)
    else:
        filters.append(CentralOrder.status.in_(active_statuses))
    if date_from:
        filters.append(CentralOrder.business_date >= date_from.isoformat())
    if date_to:
        filters.append(CentralOrder.business_date <= date_to.isoformat())
    rows = (await db.execute(
        select(
            CentralOrderItem.product_id,
            CentralOrderItem.sku,
            CentralOrderItem.product_name,
            CentralOrderItem.unit,
            func.coalesce(func.sum(CentralOrderItem.requested_qty), 0).label("requested_qty"),
            func.count(distinct(CentralOrder.id)).label("order_count"),
        )
        .join(CentralOrder, CentralOrderItem.order_id == CentralOrder.id)
        .where(*filters)
        .group_by(
            CentralOrderItem.product_id,
            CentralOrderItem.sku,
            CentralOrderItem.product_name,
            CentralOrderItem.unit,
        )
        .order_by(CentralOrderItem.product_name)
    )).all()
    return ok([
        {
            "product_id": str(row.product_id) if row.product_id else None,
            "sku": row.sku,
            "product_name": row.product_name,
            "unit": row.unit,
            "requested_qty": _to_float(row.requested_qty),
            "order_count": int(row.order_count or 0),
        }
        for row in rows
    ])


@router.get("/central/production-ingredients")
async def get_central_production_ingredients(
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    current: TokenData = Depends(require_permission("fb.kitchen.manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    return ok(await _build_central_production_ingredients(db, current.company_id, None, date_from, date_to, status_filter))


async def _enrich_brand_production_summary(
    db: AsyncSession,
    company_id: uuid.UUID,
    brand: Brand,
    rows: list[Any],
) -> list[dict[str, Any]]:
    product_ids = [row.product_id for row in rows if row.product_id is not None]
    ready_by_product: dict[uuid.UUID, Decimal] = {}
    pipeline_by_product: dict[uuid.UUID, Decimal] = {}
    if brand.central_ready_location_id is not None and product_ids:
        ready_rows = (
            await db.execute(
                select(
                    StockBalance.product_id,
                    func.coalesce(
                        func.sum(StockBalance.qty_on_hand - StockBalance.qty_reserved),
                        0,
                    ).label("available_qty"),
                )
                .where(
                    StockBalance.company_id == company_id,
                    StockBalance.location_id == brand.central_ready_location_id,
                    StockBalance.product_id.in_(product_ids),
                    StockBalance.variant_id.is_(None),
                )
                .group_by(StockBalance.product_id)
            )
        ).all()
        ready_by_product = {
            item.product_id: Decimal(str(item.available_qty or 0)) for item in ready_rows
        }
        pipeline_rows = (
            await db.execute(
                select(
                    ProductionBatchLine.product_id,
                    func.coalesce(func.sum(ProductionBatchLine.planned_qty), 0).label(
                        "pipeline_qty"
                    ),
                )
                .join(
                    ProductionBatch,
                    ProductionBatchLine.batch_id == ProductionBatch.id,
                )
                .where(
                    ProductionBatch.company_id == company_id,
                    ProductionBatch.brand_id == brand.id,
                    ProductionBatch.status.in_(["draft", "planned", "in_progress"]),
                    ProductionBatchLine.line_type == "output",
                    ProductionBatchLine.product_id.in_(product_ids),
                )
                .group_by(ProductionBatchLine.product_id)
            )
        ).all()
        pipeline_by_product = {
            item.product_id: Decimal(str(item.pipeline_qty or 0)) for item in pipeline_rows
        }
    return [
        {
            "product_id": str(row.product_id) if row.product_id else None,
            "sku": row.sku,
            "product_name": row.product_name,
            "unit": row.unit,
            "requested_qty": _to_float(row.requested_qty),
            "ready_available": _to_float(
                ready_by_product.get(row.product_id, Decimal("0"))
            ),
            "in_production_qty": _to_float(
                pipeline_by_product.get(row.product_id, Decimal("0"))
            ),
            "production_required": _to_float(
                calculate_production_required(
                    Decimal(str(row.requested_qty or 0)),
                    ready_by_product.get(row.product_id, Decimal("0")),
                    pipeline_by_product.get(row.product_id, Decimal("0")),
                )
            ),
            "order_count": int(row.order_count or 0),
        }
        for row in rows
    ]


@router.get("/central/{brand_slug}/production-summary")
async def get_brand_central_production_summary(
    brand_slug: str,
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    current: TokenData = Depends(
        require_any_permission(
            "brand.central.production.view",
            "brand.central.production.manage",
            "fb.kitchen.manage",
        )
    ),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    brand = await _load_brand_for_slug(db, current.company_id, brand_slug)
    _require_brand_assignment(current, brand)
    active_statuses = ["submitted", "reserved_credit", "approved", "packed"]
    filters = [
        CentralOrder.company_id == current.company_id,
        CentralOrder.brand_id == brand.id,
    ]
    if status_filter:
        filters.append(CentralOrder.status == status_filter)
    else:
        filters.append(CentralOrder.status.in_(active_statuses))
    if date_from:
        filters.append(CentralOrder.business_date >= date_from.isoformat())
    if date_to:
        filters.append(CentralOrder.business_date <= date_to.isoformat())
    rows = (await db.execute(
        select(
            CentralOrderItem.product_id,
            CentralOrderItem.sku,
            CentralOrderItem.product_name,
            CentralOrderItem.unit,
            func.coalesce(func.sum(CentralOrderItem.requested_qty), 0).label("requested_qty"),
            func.count(distinct(CentralOrder.id)).label("order_count"),
        )
        .join(CentralOrder, CentralOrderItem.order_id == CentralOrder.id)
        .where(*filters)
        .group_by(
            CentralOrderItem.product_id,
            CentralOrderItem.sku,
            CentralOrderItem.product_name,
            CentralOrderItem.unit,
        )
        .order_by(CentralOrderItem.product_name)
    )).all()
    return ok(
        await _enrich_brand_production_summary(
            db,
            current.company_id,
            brand,
            list(rows),
        )
    )


@router.get("/central/{brand_slug}/production-ingredients")
async def get_brand_central_production_ingredients(
    brand_slug: str,
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    current: TokenData = Depends(
        require_any_permission(
            "brand.central.production.view",
            "brand.central.production.manage",
            "fb.kitchen.manage",
        )
    ),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    brand = await _load_brand_for_slug(db, current.company_id, brand_slug)
    _require_brand_assignment(current, brand)
    return ok(await _build_central_production_ingredients(db, current.company_id, brand.id, date_from, date_to, status_filter))


@router.get("/central/{brand_slug}/production-batches")
async def list_brand_production_batches(
    brand_slug: str,
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    current: TokenData = Depends(
        require_any_permission(
            "brand.central.production.view",
            "brand.central.production.manage",
            "fb.kitchen.manage",
        )
    ),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    brand = await _load_brand_for_slug(db, current.company_id, brand_slug)
    _require_brand_assignment(current, brand)
    rows = await ProductionService(db).list_batches(
        current.company_id,
        brand.id,
        date_from=date_from,
        date_to=date_to,
        status_filter=status_filter,
    )
    return ok([row.model_dump(mode="json") for row in rows])


@router.post("/central/{brand_slug}/production-batches", status_code=201)
async def create_brand_production_batch(
    brand_slug: str,
    payload: ProductionBatchCreate,
    current: TokenData = Depends(
        require_any_permission("brand.central.production.manage", "fb.kitchen.manage")
    ),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    brand = await _load_brand_for_slug(db, current.company_id, brand_slug)
    _require_brand_assignment(current, brand)
    batch = await ProductionService(db).create_batch(
        current.company_id,
        brand.id,
        current.user_id,
        payload,
    )
    return ok(batch.model_dump(mode="json"))


@router.get("/central/{brand_slug}/production-batches/{batch_id}")
async def get_brand_production_batch(
    brand_slug: str,
    batch_id: uuid.UUID,
    current: TokenData = Depends(
        require_any_permission(
            "brand.central.production.view",
            "brand.central.production.manage",
            "fb.kitchen.manage",
        )
    ),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    brand = await _load_brand_for_slug(db, current.company_id, brand_slug)
    _require_brand_assignment(current, brand)
    batch = await ProductionService(db)._load_batch(
        current.company_id,
        brand.id,
        batch_id,
    )
    return ok(ProductionService.serialize(batch).model_dump(mode="json"))


@router.post("/central/{brand_slug}/production-batches/{batch_id}/start")
async def start_brand_production_batch(
    brand_slug: str,
    batch_id: uuid.UUID,
    current: TokenData = Depends(
        require_any_permission("brand.central.production.manage", "fb.kitchen.manage")
    ),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    brand = await _load_brand_for_slug(db, current.company_id, brand_slug)
    _require_brand_assignment(current, brand)
    batch = await ProductionService(db).start_batch(
        current.company_id,
        brand.id,
        batch_id,
        current.user_id,
    )
    return ok(batch.model_dump(mode="json"))


@router.post("/central/{brand_slug}/production-batches/{batch_id}/complete")
async def complete_brand_production_batch(
    brand_slug: str,
    batch_id: uuid.UUID,
    payload: ProductionBatchCompleteRequest,
    current: TokenData = Depends(
        require_any_permission("brand.central.production.manage", "fb.kitchen.manage")
    ),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    brand = await _load_brand_for_slug(db, current.company_id, brand_slug)
    _require_brand_assignment(current, brand)
    batch = await ProductionService(db).complete_batch(
        current.company_id,
        brand.id,
        batch_id,
        current.user_id,
        payload,
    )
    return ok(batch.model_dump(mode="json"))


@router.post("/central/{brand_slug}/production-batches/{batch_id}/cancel")
async def cancel_brand_production_batch(
    brand_slug: str,
    batch_id: uuid.UUID,
    payload: CancelRequest,
    current: TokenData = Depends(
        require_any_permission("brand.central.production.manage", "fb.kitchen.manage")
    ),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    brand = await _load_brand_for_slug(db, current.company_id, brand_slug)
    _require_brand_assignment(current, brand)
    batch = await ProductionService(db).cancel_batch(
        current.company_id,
        brand.id,
        batch_id,
        current.user_id,
        payload.reason,
    )
    return ok(batch.model_dump(mode="json"))


@router.post("/central/{brand_slug}/production-complete")
async def complete_brand_central_production(
    brand_slug: str,
    payload: CentralProductionCompleteRequest,
    current: TokenData = Depends(
        require_any_permission("brand.central.production.manage", "fb.kitchen.manage")
    ),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    brand = await _load_brand_for_slug(db, current.company_id, brand_slug)
    _require_brand_assignment(current, brand)
    if brand.central_ready_location_id is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="ระบบแยก RAW/READY แล้ว กรุณาใช้ Production Batch",
        )
    if not brand.central_location_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Central stock location is not configured")
    if payload.location_id != brand.central_location_id:
        location = await db.get(StockLocation, payload.location_id)
        if location is None or location.company_id != current.company_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Stock location not found")

    inputs = [
        {"product_id": item.product_id, "qty": item.qty, "cost_per_unit": item.cost_per_unit}
        for item in payload.inputs
        if item.qty > 0
    ]
    outputs = [
        {"product_id": item.product_id, "qty": item.qty, "cost_per_unit": item.cost_per_unit}
        for item in payload.outputs
        if item.qty > 0
    ]
    if not inputs and not outputs:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No production quantities to complete")

    label_from = payload.date_from.isoformat() if payload.date_from else "-"
    label_to = payload.date_to.isoformat() if payload.date_to else "-"
    note = payload.note or f"Central production completed for {brand.slug} {label_from}..{label_to}"
    movements = await StockService(db).produce(
        company_id=current.company_id,
        user_id=current.user_id,
        location_id=payload.location_id,
        inputs=inputs,
        outputs=outputs,
        note=note,
        reference_type="central_production",
        reference_id=f"{brand.slug}:{label_from}:{label_to}:{payload.status or 'active'}",
    )
    return ok({
        "input_count": len(inputs),
        "output_count": len(outputs),
        "movement_count": len(movements),
    })


@router.get("/central/{brand_slug}/stock-dashboard")
async def get_brand_stock_dashboard(
    brand_slug: str,
    current: TokenData = Depends(
        require_any_permission(
            "brand.central.raw_stock.view",
            "brand.central.ready_stock.view",
            "fb.kitchen.manage",
        )
    ),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    brand = await _load_brand_for_slug(db, current.company_id, brand_slug)
    _require_brand_assignment(current, brand)
    return ok(await StockCutoverService(db).dashboard(current.company_id, brand.id))


@router.get("/central/{brand_slug}/cutover/preview")
async def preview_brand_stock_cutover(
    brand_slug: str,
    current: TokenData = Depends(
        require_any_permission(
            "brand.central.raw_stock.view",
            "brand.central.ready_stock.view",
            "fb.kitchen.manage",
        )
    ),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    brand = await _load_brand_for_slug(db, current.company_id, brand_slug)
    _require_brand_assignment(current, brand)
    return ok(
        await StockCutoverService(db).preview(
            company_id=current.company_id,
            brand_id=brand.id,
        )
    )


@router.post("/central/{brand_slug}/cutover/execute")
async def execute_brand_stock_cutover(
    brand_slug: str,
    payload: StockCutoverExecuteRequest,
    current: TokenData = Depends(
        require_any_permission(
            "brand.central.raw_stock.manage",
            "brand.central.ready_stock.manage",
            "fb.kitchen.manage",
        )
    ),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    brand = await _load_brand_for_slug(db, current.company_id, brand_slug)
    _require_brand_assignment(current, brand)
    run = await StockCutoverService(db).execute(
        company_id=current.company_id,
        brand_id=brand.id,
        user_id=current.user_id,
        preview_token=payload.preview_token,
        confirmation_text=payload.confirmation_text,
        note=payload.note,
    )
    return ok(run)


@router.get("/central/{brand_slug}/cutover/runs")
async def list_brand_stock_cutover_runs(
    brand_slug: str,
    current: TokenData = Depends(
        require_any_permission(
            "brand.central.raw_stock.view",
            "brand.central.ready_stock.view",
            "fb.kitchen.manage",
        )
    ),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    brand = await _load_brand_for_slug(db, current.company_id, brand_slug)
    _require_brand_assignment(current, brand)
    return ok(await StockCutoverService(db).list_runs(current.company_id, brand.id))


@router.get("/central/{brand_slug}/reports/operations")
async def get_brand_operations_report(
    brand_slug: str,
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    current: TokenData = Depends(require_permission("fb.kitchen.manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    brand = await _load_brand_for_slug(db, current.company_id, brand_slug)
    _require_brand_assignment(current, brand)
    today = datetime.now(ZoneInfo("Asia/Bangkok")).date()
    from_value = date_from or today.replace(day=1)
    to_value = date_to or today

    sales_filters = [
        SaleOrder.company_id == current.company_id,
        SaleOrder.status.in_(["completed", "partially_refunded"]),
        Product.brand_id == brand.id,
        func.date(SaleOrder.created_at) >= from_value,
        func.date(SaleOrder.created_at) <= to_value,
    ]
    sales_rows = (await db.execute(
        select(
            Branch.id.label("branch_id"),
            Branch.name.label("branch_name"),
            func.count(distinct(SaleOrder.id)).label("order_count"),
            func.coalesce(func.sum(SaleOrderItem.subtotal), 0).label("total_amount"),
        )
        .join(SaleOrderItem, SaleOrderItem.order_id == SaleOrder.id)
        .join(Product, SaleOrderItem.product_id == Product.id)
        .join(Branch, SaleOrder.branch_id == Branch.id)
        .where(*sales_filters)
        .group_by(Branch.id, Branch.name)
        .order_by(Branch.name)
    )).all()
    sales_by_cashier_rows = (await db.execute(
        select(
            User.id.label("user_id"),
            User.display_name,
            User.first_name,
            User.last_name,
            User.username,
            func.count(distinct(SaleOrder.id)).label("order_count"),
            func.coalesce(func.sum(SaleOrderItem.subtotal), 0).label("total_amount"),
        )
        .join(SaleOrderItem, SaleOrderItem.order_id == SaleOrder.id)
        .join(Product, SaleOrderItem.product_id == Product.id)
        .join(User, SaleOrder.user_id == User.id)
        .where(*sales_filters)
        .group_by(User.id, User.display_name, User.first_name, User.last_name, User.username)
        .order_by(func.coalesce(func.sum(SaleOrderItem.subtotal), 0).desc())
    )).all()

    central_filters = [
        CentralOrder.company_id == current.company_id,
        CentralOrder.brand_id == brand.id,
        CentralOrder.business_date >= from_value.isoformat(),
        CentralOrder.business_date <= to_value.isoformat(),
    ]
    order_rows = (await db.execute(
        select(
            CentralOrder.status,
            func.count(CentralOrder.id).label("order_count"),
            func.coalesce(func.sum(CentralOrder.credit_reserved_amount), 0).label("reserved_amount"),
            func.coalesce(func.sum(CentralOrder.credit_captured_amount), 0).label("captured_amount"),
            func.coalesce(func.sum(CentralOrder.credit_released_amount), 0).label("released_amount"),
        )
        .where(*central_filters)
        .group_by(CentralOrder.status)
        .order_by(CentralOrder.status)
    )).all()
    production_rows = (await db.execute(
        select(
            CentralOrder.business_date,
            func.count(distinct(CentralOrder.id)).label("order_count"),
            func.coalesce(func.sum(CentralOrderItem.requested_qty), 0).label("requested_qty"),
            func.coalesce(func.sum(CentralOrderItem.shipped_qty), 0).label("shipped_qty"),
        )
        .join(CentralOrderItem, CentralOrderItem.order_id == CentralOrder.id)
        .where(*central_filters)
        .group_by(CentralOrder.business_date)
        .order_by(CentralOrder.business_date)
    )).all()
    shift_closure_rows = (await db.execute(
        select(
            Branch.id.label("branch_id"),
            Branch.name.label("branch_name"),
            func.count(WapShiftClosure.id).label("closure_count"),
            func.coalesce(func.sum(WapShiftClosure.total_orders), 0).label("order_count"),
            func.coalesce(func.sum(WapShiftClosure.total_amount), 0).label("total_amount"),
        )
        .join(Branch, WapShiftClosure.branch_id == Branch.id)
        .where(
            WapShiftClosure.company_id == current.company_id,
            WapShiftClosure.brand_id == brand.id,
            WapShiftClosure.business_date >= from_value.isoformat(),
            WapShiftClosure.business_date <= to_value.isoformat(),
        )
        .group_by(Branch.id, Branch.name)
        .order_by(Branch.name)
    )).all()
    shipped_rows = (await db.execute(
        select(
            Branch.id.label("branch_id"),
            Branch.name.label("branch_name"),
            func.count(distinct(CentralOrder.id)).label("shipped_order_count"),
            func.coalesce(func.sum(CentralOrderItem.shipped_amount), 0).label("shipped_amount"),
        )
        .select_from(CentralOrder)
        .join(CentralOrderItem, CentralOrderItem.order_id == CentralOrder.id)
        .join(Branch, CentralOrder.branch_id == Branch.id)
        .where(*central_filters, CentralOrder.status.in_(["shipped", "received"]))
        .group_by(Branch.id, Branch.name)
        .order_by(Branch.name)
    )).all()
    received_rows = (await db.execute(
        select(
            Branch.id.label("branch_id"),
            Branch.name.label("branch_name"),
            func.count(distinct(CentralOrder.id)).label("received_order_count"),
            func.coalesce(func.sum(CentralOrderItem.received_qty), 0).label("received_qty"),
        )
        .select_from(CentralOrder)
        .join(CentralOrderItem, CentralOrderItem.order_id == CentralOrder.id)
        .join(Branch, CentralOrder.branch_id == Branch.id)
        .where(*central_filters, CentralOrder.status == "received")
        .group_by(Branch.id, Branch.name)
        .order_by(Branch.name)
    )).all()
    replenishment_rows = (await db.execute(
        select(
            Branch.id.label("branch_id"),
            Branch.name.label("branch_name"),
            func.coalesce(func.sum(CentralOrderItem.requested_amount), 0).label("requested_amount"),
            func.coalesce(func.sum(CentralOrderItem.shipped_amount), 0).label("shipped_amount"),
        )
        .select_from(CentralOrder)
        .join(CentralOrderItem, CentralOrderItem.order_id == CentralOrder.id)
        .join(Branch, CentralOrder.branch_id == Branch.id)
        .where(*central_filters)
        .group_by(Branch.id, Branch.name)
        .order_by(Branch.name)
    )).all()
    credit_rows = (await db.execute(
        select(
            Branch.id.label("branch_id"),
            Branch.name.label("branch_name"),
            CreditAccount.balance,
            CreditAccount.reserved_amount,
        )
        .join(Branch, CreditAccount.branch_id == Branch.id)
        .where(
            CreditAccount.company_id == current.company_id,
            CreditAccount.brand_id == brand.id,
            CreditAccount.is_active.is_(True),
        )
        .order_by(Branch.name)
    )).all()
    recipe_rows = await RecipeService(db).list_recipes(current.company_id, brand_id=brand.id)

    sales_by_branch_map = {
        str(row.branch_id): {
            "branch_id": str(row.branch_id),
            "branch_name": row.branch_name,
            "sales_amount": _to_float(row.total_amount),
        }
        for row in sales_rows
    }
    replenishment_by_branch_map = {
        str(row.branch_id): {
            "branch_id": str(row.branch_id),
            "branch_name": row.branch_name,
            "requested_amount": _to_float(row.requested_amount),
            "shipped_amount": _to_float(row.shipped_amount),
        }
        for row in replenishment_rows
    }
    shipped_by_branch_map = {
        str(row.branch_id): {
            "branch_id": str(row.branch_id),
            "branch_name": row.branch_name,
            "shipped_order_count": int(row.shipped_order_count or 0),
            "shipped_amount": _to_float(row.shipped_amount),
            "received_order_count": 0,
            "received_qty": 0.0,
        }
        for row in shipped_rows
    }
    for row in received_rows:
        branch_key = str(row.branch_id)
        delivery_item = shipped_by_branch_map.setdefault(branch_key, {
            "branch_id": branch_key,
            "branch_name": row.branch_name,
            "shipped_order_count": 0,
            "shipped_amount": 0.0,
            "received_order_count": 0,
            "received_qty": 0.0,
        })
        delivery_item["received_order_count"] = int(row.received_order_count or 0)
        delivery_item["received_qty"] = _to_float(row.received_qty)

    return ok({
        "brand_id": str(brand.id),
        "brand_slug": brand.slug,
        "date_from": from_value.isoformat(),
        "date_to": to_value.isoformat(),
        "sales_by_branch": [
            {
                "branch_id": str(row.branch_id),
                "branch_name": row.branch_name,
                "order_count": int(row.order_count or 0),
                "total_amount": _to_float(row.total_amount),
            }
            for row in sales_rows
        ],
        "sales_by_cashier": [
            {
                "user_id": str(row.user_id),
                "cashier_name": (
                    row.display_name
                    or " ".join(part for part in [row.first_name, row.last_name] if part).strip()
                    or row.username
                ),
                "order_count": int(row.order_count or 0),
                "total_amount": _to_float(row.total_amount),
            }
            for row in sales_by_cashier_rows
        ],
        "central_orders_by_status": [
            {
                "status": row.status,
                "order_count": int(row.order_count or 0),
                "reserved_amount": _to_float(row.reserved_amount),
                "captured_amount": _to_float(row.captured_amount),
                "released_amount": _to_float(row.released_amount),
            }
            for row in order_rows
        ],
        "production_by_date": [
            {
                "business_date": row.business_date,
                "order_count": int(row.order_count or 0),
                "requested_qty": _to_float(row.requested_qty),
                "shipped_qty": _to_float(row.shipped_qty),
            }
            for row in production_rows
        ],
        "shift_closures_by_branch": [
            {
                "branch_id": str(row.branch_id),
                "branch_name": row.branch_name,
                "closure_count": int(row.closure_count or 0),
                "order_count": int(row.order_count or 0),
                "total_amount": _to_float(row.total_amount),
            }
            for row in shift_closure_rows
        ],
        "delivery_by_branch": sorted(shipped_by_branch_map.values(), key=lambda item: item["branch_name"]),
        "sales_vs_replenishment": [
            {
                "branch_id": branch_id,
                "branch_name": item.get("branch_name") or replenishment_by_branch_map.get(branch_id, {}).get("branch_name"),
                "sales_amount": item.get("sales_amount", 0.0),
                "requested_amount": replenishment_by_branch_map.get(branch_id, {}).get("requested_amount", 0.0),
                "shipped_amount": replenishment_by_branch_map.get(branch_id, {}).get("shipped_amount", 0.0),
                "delta_amount": item.get("sales_amount", 0.0) - replenishment_by_branch_map.get(branch_id, {}).get("requested_amount", 0.0),
            }
            for branch_id, item in sorted(
                (sales_by_branch_map | replenishment_by_branch_map).items(),
                key=lambda pair: pair[1].get("branch_name") or "",
            )
        ],
        "recipe_costs": [
            {
                "recipe_id": str(row.id),
                "product_id": str(row.product_id),
                "product_name": row.product_name,
                "recipe_name": row.name,
                "recipe_type": row.recipe_type,
                "total_cost": _to_float(row.total_cost),
                "cost_per_yield": _to_float(row.cost_per_yield),
                "selling_price": _to_float(row.selling_price),
                "gross_margin_pct": _to_float(row.gross_margin_pct),
            }
            for row in recipe_rows
        ],
        "credit_balances": [
            {
                "branch_id": str(row.branch_id),
                "branch_name": row.branch_name,
                "balance": _to_float(row.balance),
                "reserved_amount": _to_float(row.reserved_amount),
                "available_credit": _to_float(Decimal(str(row.balance or 0)) - Decimal(str(row.reserved_amount or 0))),
            }
            for row in credit_rows
        ],
    })


@router.get("/central/{brand_slug}/credits")
async def list_brand_credit_accounts(
    brand_slug: str,
    current: TokenData = Depends(require_permission("fb.kitchen.manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    brand = await _load_brand_for_slug(db, current.company_id, brand_slug)
    rows = (await db.execute(
        select(BrandBranch, Branch, CreditAccount)
        .join(Branch, BrandBranch.branch_id == Branch.id)
        .outerjoin(
            CreditAccount,
            (CreditAccount.brand_id == BrandBranch.brand_id)
            & (CreditAccount.branch_id == BrandBranch.branch_id),
        )
        .where(
            BrandBranch.company_id == current.company_id,
            BrandBranch.brand_id == brand.id,
            BrandBranch.is_active.is_(True),
        )
        .order_by(Branch.name)
    )).all()
    data = []
    for brand_branch, branch, account in rows:
        if not account:
            account = await _get_or_create_credit_account(db, current.company_id, brand.id, branch.id)
        item = _serialize_credit_account(account, branch.name)
        item["branch_type"] = brand_branch.branch_type
        item["store_location_id"] = str(brand_branch.store_location_id) if brand_branch.store_location_id else None
        data.append(item)
    await db.commit()
    return ok(data)


@router.get("/store/{brand_slug}/credits/payment-config")
async def get_store_credit_payment_config(
    brand_slug: str,
    current: TokenData = Depends(require_any_permission("brand.store.replenishment.submit", "brand.store.order.create", "fb.order.create")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    if not current.branch_id:
        raise HTTPException(status_code=400, detail="Branch context required")
    brand = await _load_brand_for_slug(db, current.company_id, brand_slug)
    await _ensure_brand_branch(db, current.company_id, current.branch_id, brand)
    return ok(_serialize_brand_credit_payment_config(brand))


@router.get("/central/{brand_slug}/credits/payment-config")
async def get_central_credit_payment_config(
    brand_slug: str,
    current: TokenData = Depends(require_permission("fb.kitchen.manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    brand = await _load_brand_for_slug(db, current.company_id, brand_slug)
    return ok(_serialize_brand_credit_payment_config(brand))


@router.post("/central/{brand_slug}/credits/payment-config/qr")
async def upload_central_credit_payment_qr(
    brand_slug: str,
    qr: UploadFile = File(...),
    current: TokenData = Depends(require_permission("fb.kitchen.manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    brand = await _load_brand_for_slug(db, current.company_id, brand_slug)
    qr_url = await UploadService().save_image(qr, "credit-qr", str(current.company_id))
    next_config = {**(brand.theme_config or {}), "credit_topup_qr_url": qr_url}
    brand.theme_config = next_config
    await db.commit()
    return ok(_serialize_brand_credit_payment_config(brand))


@router.post("/store/{brand_slug}/credits/topup-requests", status_code=status.HTTP_201_CREATED)
async def create_store_credit_topup_request(
    brand_slug: str,
    amount: Decimal = Form(...),
    note: str | None = Form(default=None),
    slip: UploadFile = File(...),
    current: TokenData = Depends(require_any_permission("brand.store.replenishment.submit", "brand.store.order.create", "fb.order.create")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    if not current.branch_id:
        raise HTTPException(status_code=400, detail="Branch context required")
    amount_value = _money(amount)
    if amount_value < MIN_CREDIT_TOPUP_AMOUNT:
        raise HTTPException(status_code=400, detail="ยอดเติมเครดิตขั้นต่ำ 500 บาท")
    brand = await _load_brand_for_slug(db, current.company_id, brand_slug)
    await _ensure_brand_branch(db, current.company_id, current.branch_id, brand)
    account = await _get_or_create_credit_account(db, current.company_id, brand.id, current.branch_id)
    slip_url = await UploadService().save_image(slip, "credit-slips", str(current.company_id))
    request = CreditTopupRequestModel(
        company_id=current.company_id,
        brand_id=brand.id,
        branch_id=current.branch_id,
        account_id=account.id,
        amount=amount_value,
        status="pending",
        slip_url=slip_url,
        note=note.strip() if note else None,
        requested_by=current.user_id,
    )
    db.add(request)
    await db.commit()
    await db.refresh(request)
    branch = await db.get(Branch, current.branch_id)
    return ok(_serialize_credit_topup_request(request, branch.name if branch else None))


@router.get("/store/{brand_slug}/credits/topup-requests")
async def list_store_credit_topup_requests(
    brand_slug: str,
    current: TokenData = Depends(require_any_permission("brand.store.replenishment.submit", "brand.store.order.create", "fb.order.create")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    if not current.branch_id:
        raise HTTPException(status_code=400, detail="Branch context required")
    brand = await _load_brand_for_slug(db, current.company_id, brand_slug)
    await _ensure_brand_branch(db, current.company_id, current.branch_id, brand)
    rows = list((await db.scalars(
        select(CreditTopupRequestModel)
        .where(
            CreditTopupRequestModel.company_id == current.company_id,
            CreditTopupRequestModel.brand_id == brand.id,
            CreditTopupRequestModel.branch_id == current.branch_id,
        )
        .order_by(CreditTopupRequestModel.created_at.desc())
        .limit(50)
    )).all())
    branch = await db.get(Branch, current.branch_id)
    return ok([_serialize_credit_topup_request(row, branch.name if branch else None) for row in rows])


@router.get("/central/{brand_slug}/credits/topup-requests")
async def list_central_credit_topup_requests(
    brand_slug: str,
    status_filter: str | None = Query(default=None, alias="status"),
    current: TokenData = Depends(require_permission("fb.kitchen.manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    brand = await _load_brand_for_slug(db, current.company_id, brand_slug)
    filters = [
        CreditTopupRequestModel.company_id == current.company_id,
        CreditTopupRequestModel.brand_id == brand.id,
    ]
    if status_filter:
        filters.append(CreditTopupRequestModel.status == status_filter)
    rows = (await db.execute(
        select(CreditTopupRequestModel, Branch.name)
        .join(Branch, CreditTopupRequestModel.branch_id == Branch.id)
        .where(*filters)
        .order_by(CreditTopupRequestModel.created_at.desc())
        .limit(100)
    )).all()
    return ok([_serialize_credit_topup_request(row, branch_name) for row, branch_name in rows])


@router.post("/central/{brand_slug}/credits/topup-requests/{request_id}/approve")
async def approve_credit_topup_request(
    brand_slug: str,
    request_id: uuid.UUID,
    payload: CreditTopupReviewRequest,
    current: TokenData = Depends(require_permission("fb.kitchen.manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    brand = await _load_brand_for_slug(db, current.company_id, brand_slug)
    request = await db.get(CreditTopupRequestModel, request_id)
    if not request or request.company_id != current.company_id or request.brand_id != brand.id:
        raise HTTPException(status_code=404, detail="ไม่พบคำขอเติมเครดิต")
    if request.status != "pending":
        raise HTTPException(status_code=400, detail="คำขอนี้ถูกตรวจแล้ว")
    account = await _get_or_create_credit_account(db, current.company_id, brand.id, request.branch_id)
    account.balance = _money(account.balance + request.amount)
    request.status = "approved"
    request.reviewed_by = current.user_id
    request.reviewed_at = datetime.now(timezone.utc)
    request.review_note = payload.note
    _add_credit_ledger(
        db,
        account,
        "topup",
        _money(request.amount),
        current.user_id,
        "credit_topup_request",
        str(request.id),
        payload.note or f"อนุมัติเติมเครดิตจากสลิป {request.id}",
    )
    await db.commit()
    branch = await db.get(Branch, request.branch_id)
    return ok(_serialize_credit_topup_request(request, branch.name if branch else None))


@router.post("/central/{brand_slug}/credits/topup-requests/{request_id}/reject")
async def reject_credit_topup_request(
    brand_slug: str,
    request_id: uuid.UUID,
    payload: CreditTopupReviewRequest,
    current: TokenData = Depends(require_permission("fb.kitchen.manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    brand = await _load_brand_for_slug(db, current.company_id, brand_slug)
    request = await db.get(CreditTopupRequestModel, request_id)
    if not request or request.company_id != current.company_id or request.brand_id != brand.id:
        raise HTTPException(status_code=404, detail="ไม่พบคำขอเติมเครดิต")
    if request.status != "pending":
        raise HTTPException(status_code=400, detail="คำขอนี้ถูกตรวจแล้ว")
    request.status = "rejected"
    request.reviewed_by = current.user_id
    request.reviewed_at = datetime.now(timezone.utc)
    request.review_note = payload.note
    await db.commit()
    branch = await db.get(Branch, request.branch_id)
    return ok(_serialize_credit_topup_request(request, branch.name if branch else None))


@router.patch("/central/{brand_slug}/branches/{branch_id}")
async def update_brand_branch_type(
    brand_slug: str,
    branch_id: uuid.UUID,
    payload: BrandBranchTypeUpdateRequest,
    current: TokenData = Depends(require_permission("fb.kitchen.manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    if payload.branch_type not in ["company_owned", "franchise"]:
        raise HTTPException(status_code=400, detail="ประเภทสาขาไม่ถูกต้อง")
    brand = await _load_brand_for_slug(db, current.company_id, brand_slug)
    brand_branch = await _ensure_brand_branch(db, current.company_id, branch_id, brand)
    if not brand_branch:
        raise HTTPException(status_code=404, detail="ไม่พบสาขาของแบรนด์")
    brand_branch.branch_type = payload.branch_type
    account = await _get_or_create_credit_account(db, current.company_id, brand.id, branch_id)
    await db.commit()
    branch = await db.get(Branch, branch_id)
    data = _serialize_credit_account(account, branch.name if branch else None)
    data["branch_type"] = brand_branch.branch_type
    return ok(data)


@router.get("/central/{brand_slug}/branches/{branch_id}/replenishment-policies")
async def get_branch_replenishment_policies(
    brand_slug: str,
    branch_id: uuid.UUID,
    business_date: date | None = Query(default=None, alias="date"),
    current: TokenData = Depends(
        require_any_permission("brand.central.production.manage", "fb.kitchen.manage")
    ),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    brand = await _load_brand_for_slug(db, current.company_id, brand_slug)
    _require_brand_assignment(current, brand)
    brand_branch = await _ensure_brand_branch(db, current.company_id, branch_id, brand)
    if brand_branch is None or brand_branch.store_location_id is None:
        raise HTTPException(status_code=400, detail="กรุณาตั้งค่าคลัง STORE-STOCK ของสาขาก่อน")
    summary = await ReplenishmentService(db).suggestion(
        company_id=current.company_id,
        brand_id=brand.id,
        branch_id=branch_id,
        location_id=brand_branch.store_location_id,
        business_date=business_date or datetime.now(ZoneInfo("Asia/Bangkok")).date(),
        include_disabled=True,
    )
    return ok(summary)


@router.put("/central/{brand_slug}/branches/{branch_id}/replenishment-policies/{product_id}")
async def upsert_branch_replenishment_policy(
    brand_slug: str,
    branch_id: uuid.UUID,
    product_id: uuid.UUID,
    payload: ReplenishmentPolicyUpdateRequest,
    current: TokenData = Depends(
        require_any_permission("brand.central.production.manage", "fb.kitchen.manage")
    ),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    brand = await _load_brand_for_slug(db, current.company_id, brand_slug)
    _require_brand_assignment(current, brand)
    await _ensure_brand_branch(db, current.company_id, branch_id, brand)
    product = await db.scalar(
        select(Product).where(
            Product.id == product_id,
            Product.company_id == current.company_id,
            Product.inventory_role == "central_ready",
            Product.deleted_at.is_(None),
            Product.is_active.is_(True),
        )
    )
    if product is None or product.brand_id not in {None, brand.id}:
        raise HTTPException(status_code=404, detail="ไม่พบสินค้า READY ของแบรนด์นี้")
    policy = await db.scalar(
        select(BranchReplenishmentPolicy)
        .where(
            BranchReplenishmentPolicy.company_id == current.company_id,
            BranchReplenishmentPolicy.brand_id == brand.id,
            BranchReplenishmentPolicy.branch_id == branch_id,
            BranchReplenishmentPolicy.product_id == product.id,
        )
        .with_for_update()
    )
    if policy is None:
        policy = BranchReplenishmentPolicy(
            company_id=current.company_id,
            brand_id=brand.id,
            branch_id=branch_id,
            product_id=product.id,
        )
        db.add(policy)
    policy.is_enabled = payload.is_enabled
    policy.safety_stock_percent = payload.safety_stock_percent
    policy.safety_stock_qty = payload.safety_stock_qty
    policy.pack_size = payload.pack_size
    policy.lead_time_days = payload.lead_time_days
    policy.forecast_method = payload.forecast_method
    policy.minimum_order_qty = payload.minimum_order_qty
    await db.commit()
    await db.refresh(policy)
    return ok(serialize_replenishment_policy(policy))


@router.patch("/central/{brand_slug}/transfer-config")
async def update_brand_transfer_config(
    brand_slug: str,
    payload: BrandTransferConfigUpdateRequest,
    current: TokenData = Depends(require_permission("fb.kitchen.manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    brand = await _load_brand_for_slug(db, current.company_id, brand_slug)
    _require_brand_assignment(current, brand)
    fields = payload.model_fields_set
    central_branch_id = (
        payload.central_branch_id
        if "central_branch_id" in fields
        else brand.central_branch_id
    )
    raw_location_id = (
        payload.central_location_id
        if "central_location_id" in fields
        else brand.central_location_id
    )
    ready_location_id = (
        payload.central_ready_location_id
        if "central_ready_location_id" in fields
        else brand.central_ready_location_id
    )

    if central_branch_id is not None:
        branch = await db.get(Branch, central_branch_id)
        if (
            not branch
            or branch.company_id != current.company_id
            or branch.deleted_at is not None
            or not branch.is_active
        ):
            raise HTTPException(status_code=404, detail="ไม่พบสาขาครัวกลาง")
    elif raw_location_id is not None or ready_location_id is not None:
        raise HTTPException(status_code=400, detail="ต้องเลือกสาขาครัวกลางก่อนเลือกคลัง")

    if raw_location_id is not None and raw_location_id == ready_location_id:
        raise HTTPException(status_code=400, detail="คลังวัตถุดิบและคลังพร้อมส่งต้องเป็นคนละคลัง")

    for location_id, not_found_message, branch_message in (
        (raw_location_id, "ไม่พบคลังวัตถุดิบ", "คลังวัตถุดิบไม่อยู่ในสาขาครัวกลาง"),
        (ready_location_id, "ไม่พบคลังสินค้าพร้อมส่ง", "คลังพร้อมส่งไม่อยู่ในสาขาครัวกลาง"),
    ):
        if location_id is None:
            continue
        location = await db.get(StockLocation, location_id)
        if (
            not location
            or location.company_id != current.company_id
            or location.deleted_at is not None
            or not location.is_active
        ):
            raise HTTPException(status_code=404, detail=not_found_message)
        if location.branch_id != central_branch_id:
            raise HTTPException(status_code=400, detail=branch_message)
        store_mapping = await db.scalar(
            select(BrandBranch.id).where(
                BrandBranch.company_id == current.company_id,
                BrandBranch.brand_id == brand.id,
                BrandBranch.store_location_id == location.id,
                BrandBranch.is_active.is_(True),
            )
        )
        if store_mapping:
            raise HTTPException(status_code=400, detail="คลังส่วนกลางต้องไม่ใช้ร่วมกับคลังหน้าร้าน")

    brand.central_branch_id = central_branch_id
    brand.central_location_id = raw_location_id
    brand.central_ready_location_id = ready_location_id
    await db.commit()
    return ok(_serialize_brand_transfer_config(brand))


@router.get("/central/{brand_slug}/transfer-config")
async def get_brand_transfer_config(
    brand_slug: str,
    current: TokenData = Depends(require_permission("fb.kitchen.manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    brand = await _load_brand_for_slug(db, current.company_id, brand_slug)
    _require_brand_assignment(current, brand)
    return ok(_serialize_brand_transfer_config(brand))


@router.get("/central/{brand_slug}/stock-areas")
async def get_brand_stock_areas(
    brand_slug: str,
    current: TokenData = Depends(
        require_any_permission(
            "brand.central.raw_stock.view",
            "brand.central.ready_stock.view",
            "fb.kitchen.manage",
        )
    ),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    brand = await _load_brand_for_slug(db, current.company_id, brand_slug)
    _require_brand_assignment(current, brand)
    central_branch = await db.get(Branch, brand.central_branch_id) if brand.central_branch_id else None
    raw_location = await db.get(StockLocation, brand.central_location_id) if brand.central_location_id else None
    ready_location = (
        await db.get(StockLocation, brand.central_ready_location_id)
        if brand.central_ready_location_id
        else None
    )
    store_rows = (
        await db.execute(
            select(BrandBranch, Branch, StockLocation)
            .join(Branch, BrandBranch.branch_id == Branch.id)
            .outerjoin(StockLocation, BrandBranch.store_location_id == StockLocation.id)
            .where(
                BrandBranch.company_id == current.company_id,
                BrandBranch.brand_id == brand.id,
                BrandBranch.is_active.is_(True),
            )
            .order_by(Branch.sort_order.asc(), Branch.code.asc())
        )
    ).all()
    stores = [
        _serialize_stock_area_location(
            location,
            branch_id=branch.id,
            branch_code=branch.code,
            branch_name=branch.name,
        )
        for _, branch, location in store_rows
    ]
    central_ids = {brand.central_location_id, brand.central_ready_location_id} - {None}
    store_ids = {item.store_location_id for item, _, _ in store_rows if item.store_location_id}
    return ok(
        {
            "production": _serialize_stock_area_location(
                raw_location,
                branch_id=brand.central_branch_id,
                branch_code=central_branch.code if central_branch else None,
                branch_name=central_branch.name if central_branch else None,
            ),
            "backoffice": _serialize_stock_area_location(
                ready_location,
                branch_id=brand.central_branch_id,
                branch_code=central_branch.code if central_branch else None,
                branch_name=central_branch.name if central_branch else None,
            ),
            "storefronts": stores,
            "is_separated": bool(
                raw_location
                and ready_location
                and raw_location.id != ready_location.id
                and central_ids.isdisjoint(store_ids)
                and all(item["is_configured"] for item in stores)
            ),
        }
    )


@router.get("/central/{brand_slug}/stock-balances")
async def get_brand_stock_area_balances(
    brand_slug: str,
    area: str = Query(...),
    branch_id: uuid.UUID | None = Query(default=None),
    current: TokenData = Depends(
        require_any_permission(
            "brand.central.raw_stock.view",
            "brand.central.ready_stock.view",
            "fb.kitchen.manage",
        )
    ),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    brand = await _load_brand_for_slug(db, current.company_id, brand_slug)
    _require_brand_assignment(current, brand)
    location = await _resolve_brand_stock_area_location(
        db,
        current.company_id,
        brand,
        area,
        branch_id,
    )
    balances = await StockService(db).list_balances(
        company_id=current.company_id,
        branch_id=location.branch_id,
        location_id=location.id,
        location_ids=(location.id,),
    )
    return ok([StockBalanceRead.model_validate(item).model_dump() for item in balances])


@router.get("/central/{brand_slug}/stock-movements")
async def get_brand_stock_area_movements(
    brand_slug: str,
    area: str = Query(...),
    branch_id: uuid.UUID | None = Query(default=None),
    product_id: uuid.UUID | None = Query(default=None),
    limit: int = Query(default=30, ge=1, le=100),
    current: TokenData = Depends(
        require_any_permission(
            "brand.central.raw_stock.view",
            "brand.central.ready_stock.view",
            "fb.kitchen.manage",
        )
    ),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    brand = await _load_brand_for_slug(db, current.company_id, brand_slug)
    _require_brand_assignment(current, brand)
    location = await _resolve_brand_stock_area_location(
        db,
        current.company_id,
        brand,
        area,
        branch_id,
    )
    movements, total = await StockService(db).list_movements(
        company_id=current.company_id,
        product_id=product_id,
        branch_id=location.branch_id,
        location_id=location.id,
        location_ids=(location.id,),
        page=1,
        limit=limit,
    )
    return ok(
        [StockMovementRead.model_validate(item).model_dump() for item in movements],
        {"total": total},
    )


@router.patch("/central/{brand_slug}/branches/{branch_id}/transfer-config")
async def update_brand_branch_transfer_config(
    brand_slug: str,
    branch_id: uuid.UUID,
    payload: BrandTransferConfigUpdateRequest,
    current: TokenData = Depends(require_permission("fb.kitchen.manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    brand = await _load_brand_for_slug(db, current.company_id, brand_slug)
    _require_brand_assignment(current, brand)
    brand_branch = await _ensure_brand_branch(db, current.company_id, branch_id, brand)
    if not brand_branch:
        raise HTTPException(status_code=404, detail="ไม่พบสาขาของแบรนด์")
    if "store_location_id" in payload.model_fields_set and payload.store_location_id:
        location = await db.get(StockLocation, payload.store_location_id)
        if (
            not location
            or location.company_id != current.company_id
            or location.branch_id != branch_id
            or location.deleted_at is not None
            or not location.is_active
        ):
            raise HTTPException(status_code=400, detail="คลังสาขาไม่ถูกต้อง")
        if location.id in {brand.central_location_id, brand.central_ready_location_id}:
            raise HTTPException(status_code=400, detail="คลังหน้าร้านต้องไม่ใช้ร่วมกับคลังส่วนกลาง")
        brand_branch.store_location_id = location.id
    elif "store_location_id" in payload.model_fields_set:
        brand_branch.store_location_id = None
    await db.commit()
    account = await _get_or_create_credit_account(db, current.company_id, brand.id, branch_id)
    branch = await db.get(Branch, branch_id)
    data = _serialize_credit_account(account, branch.name if branch else None)
    data["branch_type"] = brand_branch.branch_type
    data["store_location_id"] = str(brand_branch.store_location_id) if brand_branch.store_location_id else None
    return ok(data)


@router.post("/central/{brand_slug}/credits/topup")
async def topup_brand_credit(
    brand_slug: str,
    payload: CreditTopupRequest,
    current: TokenData = Depends(require_permission("fb.kitchen.manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    brand = await _load_brand_for_slug(db, current.company_id, brand_slug)
    await _ensure_brand_branch(db, current.company_id, payload.branch_id, brand)
    amount = _money(payload.amount)
    if amount <= 0:
        raise HTTPException(status_code=400, detail="ยอดเติมเครดิตต้องมากกว่า 0")
    account = await _get_or_create_credit_account(db, current.company_id, brand.id, payload.branch_id)
    account.balance = _money(account.balance + amount)
    _add_credit_ledger(db, account, "topup", amount, current.user_id, "credit_account", str(account.id), payload.note)
    await db.commit()
    branch = await db.get(Branch, payload.branch_id)
    return ok(_serialize_credit_account(account, branch.name if branch else None))


@router.post("/central/{brand_slug}/credits/adjust")
async def adjust_brand_credit(
    brand_slug: str,
    payload: CreditAdjustmentRequest,
    current: TokenData = Depends(require_permission("fb.kitchen.manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    brand = await _load_brand_for_slug(db, current.company_id, brand_slug)
    await _ensure_brand_branch(db, current.company_id, payload.branch_id, brand)
    amount = _money(payload.amount)
    if amount == 0:
        raise HTTPException(status_code=400, detail="ยอดปรับเครดิตต้องไม่เป็น 0")
    account = await _get_or_create_credit_account(db, current.company_id, brand.id, payload.branch_id)
    next_balance = _money(account.balance + amount)
    if next_balance < account.reserved_amount:
        raise HTTPException(status_code=400, detail="ปรับเครดิตแล้วจะต่ำกว่ายอดที่กันไว้")
    account.balance = next_balance
    _add_credit_ledger(db, account, "adjustment", amount, current.user_id, "credit_account", str(account.id), payload.note)
    await db.commit()
    branch = await db.get(Branch, payload.branch_id)
    return ok(_serialize_credit_account(account, branch.name if branch else None))


@router.post("/central/{brand_slug}/credits/refund")
async def refund_brand_credit(
    brand_slug: str,
    payload: CreditAdjustmentRequest,
    current: TokenData = Depends(require_permission("fb.kitchen.manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    brand = await _load_brand_for_slug(db, current.company_id, brand_slug)
    await _ensure_brand_branch(db, current.company_id, payload.branch_id, brand)
    amount = _money(payload.amount)
    if amount <= 0:
        raise HTTPException(status_code=400, detail="ยอดคืนเครดิตต้องมากกว่า 0")
    account = await _get_or_create_credit_account(db, current.company_id, brand.id, payload.branch_id)
    account.balance = _money(account.balance + amount)
    _add_credit_ledger(db, account, "refund", amount, current.user_id, "credit_account", str(account.id), payload.note)
    await db.commit()
    branch = await db.get(Branch, payload.branch_id)
    return ok(_serialize_credit_account(account, branch.name if branch else None))


@router.get("/central/{brand_slug}/credits/{account_id}/ledger")
async def get_brand_credit_ledger(
    brand_slug: str,
    account_id: uuid.UUID,
    current: TokenData = Depends(require_permission("fb.kitchen.manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    brand = await _load_brand_for_slug(db, current.company_id, brand_slug)
    account = await db.get(CreditAccount, account_id)
    if not account or account.company_id != current.company_id or account.brand_id != brand.id:
        raise HTTPException(status_code=404, detail="ไม่พบบัญชีเครดิต")
    rows = list((await db.scalars(
        select(CreditLedger)
        .where(CreditLedger.account_id == account.id)
        .order_by(CreditLedger.created_at.desc())
        .limit(100)
    )).all())
    return ok([
        {
            "id": str(row.id),
            "entry_type": row.entry_type,
            "amount": _to_float(row.amount),
            "balance_after": _to_float(row.balance_after),
            "reserved_after": _to_float(row.reserved_after),
            "reference_type": row.reference_type,
            "reference_id": row.reference_id,
            "note": row.note,
            "created_by": str(row.created_by),
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }
        for row in rows
    ])


@router.post("/wap/orders", status_code=status.HTTP_201_CREATED)
async def wap_create_paid_order(
    payload: WapPaidOrderRequest,
    current: TokenData = Depends(require_permission("fb.order.create")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    if not current.branch_id:
        raise HTTPException(status_code=400, detail="Branch context required")
    svc = DiningService(db)
    try:
        result = await svc.create_wap_paid_order(current.company_id, current.branch_id, current.user_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ok(result.model_dump())


@router.post("/store/{brand_slug}/orders", status_code=status.HTTP_201_CREATED)
async def store_create_paid_order(
    brand_slug: str,
    payload: WapPaidOrderRequest,
    current: TokenData = Depends(require_any_permission("brand.store.order.create", "fb.order.create")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    if not current.branch_id:
        raise HTTPException(status_code=400, detail="Branch context required")
    brand = await _load_brand_for_slug(db, current.company_id, brand_slug)
    _require_brand_assignment(current, brand)
    brand_branch = await _ensure_brand_branch(db, current.company_id, current.branch_id, brand)
    if brand_branch is None or brand_branch.store_location_id is None:
        raise HTTPException(status_code=400, detail="กรุณาตั้งค่าคลัง STORE-STOCK ของสาขาก่อนขาย")
    product_ids = [item.product_id for item in payload.items]
    if product_ids:
        count = await db.scalar(
            select(func.count(Product.id)).where(
                Product.company_id == current.company_id,
                Product.brand_id == brand.id,
                Product.id.in_(product_ids),
            )
        )
        if int(count or 0) != len(set(product_ids)):
            raise HTTPException(status_code=400, detail="พบสินค้าที่ไม่อยู่ในแบรนด์นี้")
    svc = DiningService(db)
    try:
        result = await svc.create_wap_paid_order(
            current.company_id,
            current.branch_id,
            current.user_id,
            payload,
            brand_id=brand.id,
            required_location_id=brand_branch.store_location_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ok(result.model_dump())


@router.post("/store/{brand_slug}/orders/sync")
async def store_sync_offline_orders(
    brand_slug: str,
    payload: WapOfflineSyncRequest,
    current: TokenData = Depends(require_any_permission("brand.store.order.create", "fb.order.create")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    if not current.branch_id:
        raise HTTPException(status_code=400, detail="Branch context required")
    brand = await _load_brand_for_slug(db, current.company_id, brand_slug)
    _require_brand_assignment(current, brand)
    brand_branch = await _ensure_brand_branch(db, current.company_id, current.branch_id, brand)
    if brand_branch is None or brand_branch.store_location_id is None:
        raise HTTPException(status_code=400, detail="กรุณาตั้งค่าคลัง STORE-STOCK ของสาขาก่อนขาย")

    product_ids = {
        item.product_id
        for offline_order in payload.orders
        for item in offline_order.items
    }
    valid_product_ids: set[uuid.UUID] = set()
    if product_ids:
        valid_product_ids = set((await db.scalars(
            select(Product.id).where(
                Product.company_id == current.company_id,
                Product.brand_id == brand.id,
                Product.id.in_(product_ids),
            )
        )).all())

    svc = DiningService(db)
    results: list[WapOfflineSyncItemRead] = []
    for offline_order in payload.orders:
        order_product_ids = {item.product_id for item in offline_order.items}
        if not order_product_ids.issubset(valid_product_ids):
            results.append(WapOfflineSyncItemRead(
                client_order_id=offline_order.client_order_id,
                status="needs_review",
                error="พบสินค้าที่ไม่อยู่ในแบรนด์นี้ กรุณาโหลดเมนูใหม่",
            ))
            continue
        try:
            result = await svc.create_wap_paid_order(
                current.company_id,
                current.branch_id,
                current.user_id,
                offline_order.model_copy(update={"is_offline": True}),
                brand_id=brand.id,
                required_location_id=brand_branch.store_location_id,
            )
        except HTTPException as exc:
            if exc.status_code >= 500:
                raise
            await db.rollback()
            results.append(WapOfflineSyncItemRead(
                client_order_id=offline_order.client_order_id,
                status="needs_review",
                error=str(exc.detail),
            ))
            continue
        except ValueError as exc:
            await db.rollback()
            results.append(WapOfflineSyncItemRead(
                client_order_id=offline_order.client_order_id,
                status="needs_review",
                error=str(exc),
            ))
            continue
        results.append(WapOfflineSyncItemRead(
            client_order_id=offline_order.client_order_id,
            status="synced",
            order=result,
        ))
    return ok(WapOfflineSyncRead(results=results).model_dump())


@router.post("/wap/orders/sync")
async def wap_sync_offline_orders(
    payload: WapOfflineSyncRequest,
    current: TokenData = Depends(require_permission("fb.order.create")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    if not current.branch_id:
        raise HTTPException(status_code=400, detail="Branch context required")

    product_ids = {
        item.product_id
        for offline_order in payload.orders
        for item in offline_order.items
    }
    valid_product_ids: set[uuid.UUID] = set()
    if product_ids:
        valid_product_ids = set((await db.scalars(
            select(Product.id).where(
                Product.company_id == current.company_id,
                Product.brand_id.is_(None),
                Product.product_type == "menu_item",
                Product.id.in_(product_ids),
            )
        )).all())

    svc = DiningService(db)
    results: list[WapOfflineSyncItemRead] = []
    for offline_order in payload.orders:
        order_product_ids = {item.product_id for item in offline_order.items}
        if not order_product_ids.issubset(valid_product_ids):
            results.append(WapOfflineSyncItemRead(
                client_order_id=offline_order.client_order_id,
                status="needs_review",
                error="พบสินค้าที่ไม่อยู่ในเมนูร้านอาหาร กรุณาโหลดเมนูใหม่",
            ))
            continue
        try:
            result = await svc.create_wap_paid_order(
                current.company_id,
                current.branch_id,
                current.user_id,
                offline_order.model_copy(update={"is_offline": True}),
            )
        except HTTPException as exc:
            if exc.status_code >= 500:
                raise
            await db.rollback()
            results.append(WapOfflineSyncItemRead(
                client_order_id=offline_order.client_order_id,
                status="needs_review",
                error=str(exc.detail),
            ))
            continue
        except ValueError as exc:
            await db.rollback()
            results.append(WapOfflineSyncItemRead(
                client_order_id=offline_order.client_order_id,
                status="needs_review",
                error=str(exc),
            ))
            continue
        results.append(WapOfflineSyncItemRead(
            client_order_id=offline_order.client_order_id,
            status="synced",
            order=result,
        ))
    return ok(WapOfflineSyncRead(results=results).model_dump())


@router.get("/wap/orders/{session_id}")
async def wap_get_order(
    session_id: uuid.UUID,
    current: TokenData = Depends(require_permission("fb.order.create")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    svc = DiningService(db)
    try:
        result = await svc.get_wap_order(session_id, current.company_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return ok(result.model_dump())


@router.post("/wap/orders/{session_id}/customer-slip")
async def wap_mark_customer_slip(
    session_id: uuid.UUID,
    current: TokenData = Depends(require_permission("fb.order.create")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    svc = DiningService(db)
    try:
        result = await svc.mark_customer_slip_printed(session_id, current.company_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ok(result.model_dump())


@router.post("/wap/orders/{session_id}/kitchen-slip")
async def wap_mark_kitchen_slip(
    session_id: uuid.UUID,
    current: TokenData = Depends(require_permission("fb.order.create")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    svc = DiningService(db)
    try:
        result = await svc.mark_kitchen_slip_printed(session_id, current.company_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ok(result.model_dump())


# ── Ingredient Usage Report ───────────────────────────────────────────────────

# ── Quick Service QR ─────────────────────────────────────────────────────────

@router.post("/qs-qr/generate")
async def generate_qs_qr(
    current: TokenData = Depends(require_permission("fb.settings.manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """สร้างหรือดึง QR token สำหรับ Quick Service ของสาขา"""
    if not current.branch_id:
        raise HTTPException(status_code=400, detail="Branch context required")
    branch_settings = await db.scalar(
        select(BranchSettings).where(BranchSettings.branch_id == current.branch_id)
    )
    if not branch_settings:
        raise HTTPException(status_code=404, detail="ไม่พบ settings สาขา")
    if branch_settings.fb_service_mode != "quick_service":
        raise HTTPException(
            status_code=400,
            detail="ร้านที่มีโต๊ะต้องออก QR รับกลับจากการเปิดคิวที่เคาน์เตอร์",
        )
    if not branch_settings.fb_qs_qr_token:
        import uuid as _uuid
        branch_settings.fb_qs_qr_token = _uuid.uuid4()
        await db.commit()
        await db.refresh(branch_settings)
    return ok({"qs_qr_token": str(branch_settings.fb_qs_qr_token)})


# ── Line Notify Test ──────────────────────────────────────────────────────────

@router.post("/line-notify/test")
async def test_fb_line_notify(
    current: TokenData = Depends(require_permission("fb.settings.manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """ทดสอบส่ง Line Notify ด้วย token ที่ตั้งไว้ใน F&B settings"""
    if not current.branch_id:
        raise HTTPException(status_code=400, detail="Branch context required")

    branch_settings = await db.scalar(
        select(BranchSettings).where(BranchSettings.branch_id == current.branch_id)
    )
    if not branch_settings or not branch_settings.fb_line_notify_token:
        raise HTTPException(status_code=400, detail="ยังไม่ได้ตั้งค่า Line Notify Token สำหรับ F&B")

    from app.services.notification_service import NotificationService
    from app.models.branch import Branch as BranchModel
    branch = await db.get(BranchModel, current.branch_id)
    if not branch:
        raise HTTPException(status_code=404, detail="ไม่พบสาขา")

    svc = NotificationService(db)
    success = await svc.send_line_notify(
        token=branch_settings.fb_line_notify_token,
        message=f"\n✅ ทดสอบระบบ F&B แจ้งเตือน\nสาขา: {branch.name}\nLine Notify ทำงานปกติครับ 🎉",
        company_id=current.company_id,
        event_type="fb_test",
    )
    if not success:
        raise HTTPException(status_code=502, detail="ส่ง Line Notify ไม่สำเร็จ — ตรวจสอบ Token อีกครั้ง")
    return ok({"sent": True})


# ── Public QR Routes ─────────────────────────────────────────────────────────

@public_router.get("/{qr_token}")
async def public_get_menu(
    qr_token: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    svc = DiningService(db)
    menu = await svc.get_public_menu(qr_token)
    if not menu:
        raise HTTPException(status_code=404, detail="ไม่พบ QR นี้")
    return ok(menu.model_dump())


@public_router.post("/{qr_token}/orders", status_code=status.HTTP_201_CREATED)
async def public_place_order(
    qr_token: uuid.UUID,
    payload: PlaceOrderRequest,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    svc = DiningService(db)
    session = await svc.get_session_by_token(qr_token)
    if not session:
        raise HTTPException(status_code=404, detail="ไม่พบ QR นี้")
    if session.status == "bill_requested":
        raise HTTPException(status_code=400, detail="มีการเรียกบิลแล้ว กรุณารอพนักงาน")

    if session.table_id:
        table = await db.get(DiningTable, session.table_id)
        if not table or not table.is_active:
            raise HTTPException(status_code=404, detail="ไม่พบโต๊ะ")

    branch_settings = await db.scalar(
        select(BranchSettings).where(BranchSettings.branch_id == session.branch_id)
    )

    try:
        order = await svc.place_order(
            session.company_id, session.branch_id, session, payload, "qr_self", branch_settings,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ok({
        "order_id": str(order.id),
        "order_number": order.order_number,
        "session_id": str(session.id),
        "queue_number": session.queue_number,
    })


@public_router.get("/{qr_token}/status")
async def public_order_status(
    qr_token: uuid.UUID,
    session_id: uuid.UUID | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    svc = DiningService(db)
    session = await svc.get_session_by_token(qr_token)
    if not session:
        raise HTTPException(status_code=404, detail="ไม่พบ QR นี้")
    if session_id is not None and session.id != session_id:
        raise HTTPException(status_code=404, detail="ไม่พบ session")
    result = await svc.get_public_order_status(session.id)
    if not result:
        raise HTTPException(status_code=404, detail="ไม่พบ session")
    return ok(result.model_dump())


@public_router.post("/{qr_token}/bill")
async def public_request_bill(
    qr_token: uuid.UUID,
    session_id: uuid.UUID | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    svc = DiningService(db)
    session = await svc.get_session_by_token(qr_token)
    if not session:
        raise HTTPException(status_code=404, detail="ไม่พบ QR นี้")
    if session_id is not None and session.id != session_id:
        raise HTTPException(status_code=404, detail="ไม่พบ session")
    if session.table_id is None:
        raise HTTPException(status_code=403, detail="ออเดอร์รับกลับไม่รองรับการเรียกบิลจาก QR")
    settings = await db.scalar(
        select(BranchSettings).where(BranchSettings.branch_id == session.branch_id)
    )
    if not settings or not settings.fb_bill_at_table:
        raise HTTPException(status_code=403, detail="สาขานี้ยังไม่เปิดบริการเรียกบิลจาก QR")
    updated = await svc.request_bill(session)
    return ok({"status": updated.status})


@router.get("/reports/ingredients")
async def ingredient_usage_report(
    branch_id: uuid.UUID = Query(...),
    date_from: date = Query(...),
    date_to: date = Query(...),
    current: TokenData = Depends(require_permission("fb.report.view")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    svc = RecipeService(db)
    report = await svc.get_ingredient_usage_report(
        current.company_id, branch_id, date_from, date_to
    )
    return ok(report.model_dump())


# ── Quick Service Public Routes ───────────────────────────────────────────────

async def _get_qs_settings(db: AsyncSession, qs_token: uuid.UUID) -> BranchSettings | None:
    return await db.scalar(
        select(BranchSettings).where(
            BranchSettings.fb_qs_qr_token == qs_token,
            BranchSettings.fb_service_mode == "quick_service",
        )
    )


@qs_router.get("/{qs_token}")
async def qs_get_menu(
    qs_token: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    settings = await _get_qs_settings(db, qs_token)
    if not settings:
        raise HTTPException(status_code=404, detail="ไม่พบ QR นี้")

    from app.models.branch import Branch as BranchModel
    from app.models.product import Product, Category as CategoryModel
    branch = await db.get(BranchModel, settings.branch_id)
    if not branch:
        raise HTTPException(status_code=404, detail="ไม่พบสาขา")

    products = list((await db.scalars(
        select(Product).where(
            Product.company_id == branch.company_id,
            Product.product_type == "menu_item",
            Product.is_active.is_(True),
            Product.is_for_sale.is_(True),
        ).order_by(Product.name)
    )).all())

    cats = list((await db.scalars(
        select(CategoryModel).where(
            CategoryModel.company_id == branch.company_id,
            CategoryModel.is_active.is_(True),
        )
    )).all())
    cat_map = {c.id: c.name for c in cats}
    prefix = settings.fb_queue_prefix or ""

    return ok({
        "branch_name": branch.name,
        "fb_service_mode": settings.fb_service_mode,
        "queue_prefix": prefix,
        "categories": [{"id": str(c.id), "name": c.name} for c in cats],
        "products": [
            {
                "id": str(p.id),
                "name": p.name,
                "description": p.description,
                "selling_price": float(p.selling_price),
                "category_id": str(p.category_id) if p.category_id else None,
                "category_name": cat_map.get(p.category_id) if p.category_id else None,
                "image_url": p.image_url,
                "is_available": True,
            }
            for p in products
        ],
    })


@qs_router.post("/{qs_token}/orders", status_code=201)
async def qs_place_order(
    qs_token: uuid.UUID,
    payload: PlaceOrderRequest,
    customer_name: str | None = Query(default=None),
    customer_phone: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    settings = await _get_qs_settings(db, qs_token)
    if not settings:
        raise HTTPException(status_code=404, detail="ไม่พบ QR นี้")

    from app.models.branch import Branch as BranchModel
    branch = await db.get(BranchModel, settings.branch_id)
    if not branch:
        raise HTTPException(status_code=404, detail="ไม่พบสาขา")

    svc = DiningService(db)
    # สร้าง session ใหม่เสมอสำหรับ Quick Service (ไม่แชร์กัน)
    session = await svc.open_session(
        company_id=branch.company_id,
        branch_id=settings.branch_id,
        payload=SessionOpen(table_id=None, guest_count=1, customer_name=customer_name, customer_phone=customer_phone),
        opened_by=None,
        settings=settings,
    )

    try:
        order = await svc.place_order(
            branch.company_id, settings.branch_id, session, payload, "qr_self", settings,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    prefix = settings.fb_queue_prefix or ""
    return ok({
        "order_id": str(order.id),
        "order_number": order.order_number,
        "session_id": str(session.id),
        "queue_number": session.queue_number,
        "queue_display": f"{prefix}{str(session.queue_number).zfill(3)}" if session.queue_number else None,
    })


@qs_router.get("/{qs_token}/status")
async def qs_order_status(
    qs_token: uuid.UUID,
    session_id: uuid.UUID = Query(...),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    settings = await _get_qs_settings(db, qs_token)
    if not settings:
        raise HTTPException(status_code=404, detail="ไม่พบ QR นี้")
    session = await db.get(DiningSession, session_id)
    if not session or session.branch_id != settings.branch_id or session.table_id is not None:
        raise HTTPException(status_code=404, detail="ไม่พบ session")
    svc = DiningService(db)
    result = await svc.get_public_order_status(session_id)
    if not result:
        raise HTTPException(status_code=404, detail="ไม่พบ session")
    return ok(result.model_dump())
