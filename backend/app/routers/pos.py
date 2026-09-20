from __future__ import annotations

from decimal import Decimal
from typing import Any
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.dependencies import (
    DeviceTokenData,
    TokenData,
    get_optional_counter_device,
    get_scoped_operational_db as get_db,
    require_any_permission,
    require_permission,
)
from app.models.company import Company
from app.models.settings import BranchSettings
from app.schemas.pos import CloseShiftRequest, CreateSaleRequest, OpenShiftRequest, PartialRefundRequest, RefundRequest, SaleOrderRead, ShiftRead, SyncSalesRequest, VoidRequest
from app.schemas.pricing import PricingCalculateRequest
from app.services.approval_service import ApprovalEvidence, ApprovalService, has_permission
from app.services.pricing_service import PricingResult, PricingService, pricing_error
from app.services.sale_service import SaleService, pricing_request_for_sale, sale_request_hash
from app.utils.promptpay import generate_promptpay_payload

router = APIRouter(prefix="/api/v1/pos", tags=["pos"])


def ok(data: Any, meta: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"data": data, "meta": {"version": settings.app_version, **(meta or {})}, "error": None}


def _approval_payload(
    payload: CreateSaleRequest | VoidRequest | RefundRequest | PartialRefundRequest,
    *,
    order_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    value = payload.model_dump(
        mode="json",
        exclude={"approval_token", "price_override_approval_token"},
        exclude_none=True,
        exclude_unset=True,
    )
    if order_id is not None:
        value["order_id"] = str(order_id)
    return value


async def _authorize_sale_discount(
    db: AsyncSession,
    current: TokenData,
    payload: CreateSaleRequest,
    pricing: PricingResult,
) -> ApprovalEvidence | None:
    assert current.branch_id is not None
    percentage = pricing.discount_percentage
    branch_settings = await db.scalar(
        select(BranchSettings).where(
            BranchSettings.company_id == current.company_id,
            BranchSettings.branch_id == current.branch_id,
        )
    )
    cashier_limit = Decimal(
        branch_settings.pos_cashier_discount_limit_pct if branch_settings else 10
    )
    if percentage <= 0:
        return None
    if not (
        has_permission(current.permissions, "pos.discount.apply")
        or has_permission(current.permissions, "pos.discount.override")
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permission required: pos.discount.apply",
        )
    if percentage <= cashier_limit:
        return None
    return await ApprovalService(db).authorize_operation(
        current=current,
        action="pos.discount.override",
        request_payload=_approval_payload(payload),
        approval_token=payload.approval_token,
        reason=(
            f"Discount {percentage}% exceeds cashier limit {cashier_limit}%"
        ),
        resource_type="SaleOrder",
        resource_id=payload.client_order_id,
    )


async def _authorize_price_override(
    db: AsyncSession,
    current: TokenData,
    payload: CreateSaleRequest,
    pricing: PricingResult,
) -> ApprovalEvidence | None:
    overridden = [line for line in pricing.lines if line.override_requested]
    if not overridden:
        return None
    if not (
        has_permission(current.permissions, "pos.price.override")
        or has_permission(current.permissions, "pos.price.override.request")
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "permission_denied",
                "action": "pos.price.override",
                "message": "Permission required: pos.price.override.request",
            },
        )
    if not pricing.requires_price_override_approval:
        return None
    assert current.branch_id is not None
    branch_settings = await db.scalar(
        select(BranchSettings).where(
            BranchSettings.company_id == current.company_id,
            BranchSettings.branch_id == current.branch_id,
        )
    )
    allow_direct = bool(
        branch_settings.pos_price_override_self_approval
        if branch_settings else False
    )
    reasons = sorted(
        {
            line.request.price_override.reason
            for line in overridden
            if line.request.price_override is not None
        }
    )
    return await ApprovalService(db).authorize_operation(
        current=current,
        action="pos.price.override",
        request_payload=_approval_payload(payload),
        approval_token=payload.price_override_approval_token,
        reason="; ".join(reasons),
        resource_type="SaleOrder",
        resource_id=payload.client_order_id,
        allow_direct=allow_direct,
    )
def _require_current_order_branch(current: TokenData, branch_id: uuid.UUID) -> None:
    if current.branch_id is None or current.branch_id != branch_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sale order not found",
        )


def _require_matching_counter_device(
    current: TokenData,
    counter_device: DeviceTokenData | None,
) -> None:
    if counter_device is not None and (
        counter_device.company_id != current.company_id
        or counter_device.branch_id != current.branch_id
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Counter device Branch does not match staff Branch",
        )


def _sale_service(db: AsyncSession, current: TokenData) -> SaleService:
    retail_cutover = (
        current.target_database == "retail_pos"
        and settings.retail_service_database == "retail"
    )
    return SaleService(db, legacy_side_effects_enabled=not retail_cutover)


@router.post("/shifts/open", status_code=status.HTTP_201_CREATED)
async def open_shift(
    payload: OpenShiftRequest,
    request: Request,
    current: TokenData = Depends(require_permission("pos.cashier.open_shift")),
    db: AsyncSession = Depends(get_db),
    counter_device: DeviceTokenData | None = Depends(get_optional_counter_device),
) -> dict[str, Any]:
    if current.branch_id is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Branch context required")
    _require_matching_counter_device(current, counter_device)
    shift = await _sale_service(db, current).open_shift(
        current.company_id,
        current.branch_id,
        current.user_id,
        payload,
        device_id=counter_device.device_id if counter_device else None,
        device_code=counter_device.device_code if counter_device else None,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    return ok(ShiftRead.model_validate(shift).model_dump())


@router.get("/shifts/current")
async def get_current_shift(
    current: TokenData = Depends(require_permission("pos.cashier.open_shift")),
    db: AsyncSession = Depends(get_db),
    counter_device: DeviceTokenData | None = Depends(get_optional_counter_device),
) -> dict[str, Any]:
    if current.branch_id is None:
        return ok(None)
    _require_matching_counter_device(current, counter_device)
    shift = await _sale_service(db, current).get_open_shift(current.company_id, current.user_id, current.branch_id)
    return ok(ShiftRead.model_validate(shift).model_dump() if shift else None)


@router.post("/shifts/{shift_id}/close")
async def close_shift(
    shift_id: uuid.UUID,
    payload: CloseShiftRequest,
    request: Request,
    current: TokenData = Depends(require_permission("pos.cashier.close_shift")),
    db: AsyncSession = Depends(get_db),
    counter_device: DeviceTokenData | None = Depends(get_optional_counter_device),
) -> dict[str, Any]:
    _require_matching_counter_device(current, counter_device)
    shift = await _sale_service(db, current).close_shift(
        shift_id,
        current.company_id,
        current.user_id,
        payload,
        device_id=counter_device.device_id if counter_device else None,
        device_code=counter_device.device_code if counter_device else None,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    return ok(ShiftRead.model_validate(shift).model_dump())


@router.get("/shifts")
async def list_shifts(
    branch_id: uuid.UUID | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    current: TokenData = Depends(require_permission("pos.sale.view")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    shifts, total = await _sale_service(db, current).list_shifts(current.company_id, branch_id, page, limit)
    return ok([ShiftRead.model_validate(item).model_dump() for item in shifts], meta={"total": total, "page": page, "limit": limit})


@router.post("/pricing/calculate")
async def calculate_pricing(
    payload: PricingCalculateRequest,
    current: TokenData = Depends(require_permission("pos.sale.create")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    if current.branch_id is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Branch context required")
    quote = await PricingService(db).create_quote(
        company_id=current.company_id,
        branch_id=current.branch_id,
        brand_id=current.brand_id,
        user_id=current.user_id,
        payload=payload,
    )
    return ok(quote.model_dump(mode="json"))


@router.post("/sales", status_code=status.HTTP_201_CREATED)
async def create_sale(
    payload: CreateSaleRequest,
    response: Response,
    current: TokenData = Depends(require_permission("pos.sale.create")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    if current.branch_id is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Branch context required")
    if not payload.client_order_id:
        raise pricing_error(
            status.HTTP_400_BAD_REQUEST,
            "idempotency_key_required",
            "client_order_id is required for checkout",
        )
    service = _sale_service(db, current)
    existing = await service.get_existing_sale_by_client_order_id(current.company_id, current.branch_id, payload.client_order_id)
    if existing is not None:
        request_hash = sale_request_hash(payload)
        if existing.pricing_request_hash and existing.pricing_request_hash != request_hash:
            raise pricing_error(
                status.HTTP_409_CONFLICT,
                "duplicate_request",
                "client_order_id was already used with a different sale request",
                client_order_id=payload.client_order_id,
            )
        response.status_code = status.HTTP_200_OK
        repaired = await service.ensure_existing_sale_handoffs(
            existing,
            current.company_id,
            current.user_id,
            brand_id=current.brand_id,
        )
        return ok(SaleOrderRead.model_validate(repaired).model_dump())
    pricing = await PricingService(db).calculate(
        company_id=current.company_id,
        branch_id=current.branch_id,
        brand_id=current.brand_id,
        payload=pricing_request_for_sale(payload),
        lock_prices=True,
    )
    approval_evidence = await _authorize_sale_discount(db, current, payload, pricing)
    price_override_evidence = await _authorize_price_override(db, current, payload, pricing)
    order = await service.create_sale(
        current.company_id,
        current.branch_id,
        current.user_id,
        payload,
        brand_id=current.brand_id,
        approval_evidence=approval_evidence,
        price_override_evidence=price_override_evidence,
        pricing_result=pricing,
    )
    return ok(SaleOrderRead.model_validate(order).model_dump())


@router.post("/sales/sync")
async def sync_sales(
    payload: SyncSalesRequest,
    current: TokenData = Depends(require_permission("pos.sale.create")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    if current.branch_id is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Branch context required")
    service = _sale_service(db, current)
    orders = []
    for sale_payload in payload.orders:
        if not sale_payload.client_order_id:
            raise pricing_error(
                status.HTTP_400_BAD_REQUEST,
                "idempotency_key_required",
                "client_order_id is required for offline synchronization",
            )
        existing = await service.get_existing_sale_by_client_order_id(
            current.company_id,
            current.branch_id,
            sale_payload.client_order_id,
        )
        if existing is not None:
            request_hash = sale_request_hash(sale_payload)
            if existing.pricing_request_hash and existing.pricing_request_hash != request_hash:
                raise pricing_error(
                    status.HTTP_409_CONFLICT,
                    "duplicate_request",
                    "client_order_id was replayed with a different sale request",
                    client_order_id=sale_payload.client_order_id,
                )
            orders.append(
                await service.ensure_existing_sale_handoffs(
                    existing,
                    current.company_id,
                    current.user_id,
                    brand_id=current.brand_id,
                )
            )
            continue
        pricing = await PricingService(db).calculate(
            company_id=current.company_id,
            branch_id=current.branch_id,
            brand_id=current.brand_id,
            payload=pricing_request_for_sale(sale_payload),
            lock_prices=True,
        )
        if pricing.has_price_discrepancy:
            raise pricing_error(
                status.HTTP_409_CONFLICT,
                "stale_price",
                "Offline price is stale; refresh online before checkout",
                client_order_id=sale_payload.client_order_id,
            )
        approval_evidence = await _authorize_sale_discount(db, current, sale_payload, pricing)
        price_override_evidence = await _authorize_price_override(db, current, sale_payload, pricing)
        orders.append(
            await service.create_sale(
                current.company_id,
                current.branch_id,
                current.user_id,
                sale_payload,
                brand_id=current.brand_id,
                approval_evidence=approval_evidence,
                price_override_evidence=price_override_evidence,
                pricing_result=pricing,
            )
        )
    return ok([SaleOrderRead.model_validate(item).model_dump() for item in orders])


@router.get("/sales")
async def list_sales(
    shift_id: uuid.UUID | None = Query(default=None),
    branch_id: uuid.UUID | None = Query(default=None),
    status_value: str | None = Query(default=None, alias="status"),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    current: TokenData = Depends(require_permission("pos.sale.view")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    rows, total = await _sale_service(db, current).list_sales(
        current.company_id,
        shift_id=shift_id,
        branch_id=branch_id,
        status_value=status_value,
        page=page,
        limit=limit,
    )
    return ok([SaleOrderRead.model_validate(item).model_dump() for item in rows], meta={"total": total, "page": page, "limit": limit})


@router.get("/sales/{order_id}")
async def get_sale(
    order_id: uuid.UUID,
    current: TokenData = Depends(require_permission("pos.sale.view")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    order = await _sale_service(db, current).get_sale(order_id, current.company_id)
    return ok(SaleOrderRead.model_validate(order).model_dump())


@router.post("/sales/{order_id}/void")
async def void_sale(
    order_id: uuid.UUID,
    payload: VoidRequest,
    current: TokenData = Depends(
        require_any_permission("pos.sale.void", "pos.sale.void.request")
    ),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    service = _sale_service(db, current)
    existing = await service.get_sale(order_id, current.company_id)
    _require_current_order_branch(current, existing.branch_id)
    approval_evidence = await ApprovalService(db).authorize_operation(
        current=current,
        action="pos.sale.void",
        request_payload=_approval_payload(payload, order_id=order_id),
        approval_token=payload.approval_token,
        reason=payload.void_reason,
        resource_type="SaleOrder",
        resource_id=str(order_id),
    )
    order = await service.void_sale(
        order_id,
        current.company_id,
        current.user_id,
        payload,
        approval_evidence=approval_evidence,
    )
    return ok(SaleOrderRead.model_validate(order).model_dump())


@router.post("/sales/{order_id}/refund")
async def refund_sale(
    order_id: uuid.UUID,
    payload: RefundRequest,
    current: TokenData = Depends(
        require_any_permission("pos.refund.create", "pos.refund.request")
    ),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    service = _sale_service(db, current)
    existing = await service.get_sale(order_id, current.company_id)
    _require_current_order_branch(current, existing.branch_id)
    approval_evidence = await ApprovalService(db).authorize_operation(
        current=current,
        action="pos.refund.create",
        request_payload=_approval_payload(payload, order_id=order_id),
        approval_token=payload.approval_token,
        reason=payload.refund_reason,
        resource_type="SaleOrder",
        resource_id=str(order_id),
    )
    order = await service.refund_sale(
        order_id,
        current.company_id,
        current.user_id,
        payload.refund_reason,
        approval_evidence=approval_evidence,
    )
    return ok(SaleOrderRead.model_validate(order).model_dump())


@router.post("/sales/{order_id}/refund/partial")
async def partial_refund_sale(
    order_id: uuid.UUID,
    payload: PartialRefundRequest,
    current: TokenData = Depends(
        require_any_permission("pos.refund.create", "pos.refund.request")
    ),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    service = _sale_service(db, current)
    existing = await service.get_sale(order_id, current.company_id)
    _require_current_order_branch(current, existing.branch_id)
    approval_evidence = await ApprovalService(db).authorize_operation(
        current=current,
        action="pos.refund.create",
        request_payload=_approval_payload(payload, order_id=order_id),
        approval_token=payload.approval_token,
        reason=payload.refund_reason,
        resource_type="SaleOrder",
        resource_id=str(order_id),
    )
    order = await service.partial_refund_sale(
        order_id,
        current.company_id,
        current.user_id,
        payload,
        approval_evidence=approval_evidence,
    )
    return ok(SaleOrderRead.model_validate(order).model_dump())


@router.get("/promptpay/qr")
async def get_promptpay_qr(
    amount: Decimal | None = Query(default=None, gt=0),
    target: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    company_target = target
    if not company_target:
        company = await db.scalar(select(Company).where(Company.is_active.is_(True)).order_by(Company.created_at.asc()))
        company_target = (company.phone if company and company.phone else None) or (company.tax_id if company and company.tax_id else None) or "0812345678"
    qr_amount = Decimal(amount).quantize(Decimal("0.01")) if amount is not None else None
    try:
        payload = generate_promptpay_payload(company_target, qr_amount)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="PromptPay ต้องเป็นเบอร์มือถือไทย 10 หลักหรือเลขผู้เสียภาษี 13 หลัก",
        ) from exc
    return ok({"payload": payload, "amount": f"{qr_amount:.2f}" if qr_amount is not None else None, "target": company_target})
