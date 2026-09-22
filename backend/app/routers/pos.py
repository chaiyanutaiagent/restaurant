from __future__ import annotations

from decimal import Decimal
from typing import Any
import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_restaurant_service_db
from app.dependencies import (
    DeviceTokenData,
    TokenData,
    get_optional_counter_device,
    get_scoped_operational_db as get_db,
    require_any_permission,
    require_permission,
)
from app.models.company import Company
from app.models.pos import CashierShift, PosCashMovement, PosHoldDraftAudit, SaleOrder
from app.models.refund import RefundOperation, RefundPaymentLeg, RefundTaxLink
from app.models.settings import BranchSettings
from app.models.stock import StockLocation
from app.models.user import User
from app.schemas.pos import (
    CashMovementCreateRequest,
    CashMovementRead,
    CloseShiftRequest,
    CreateSaleRequest,
    HoldDraftActionRequest,
    HoldDraftCreateRequest,
    HoldDraftRead,
    HoldDraftUpdateRequest,
    OpenShiftRequest,
    PartialRefundRequest,
    RefundRequest,
    RefundExecuteRequest,
    RefundOperationActionRequest,
    RefundProviderWebhookRequest,
    RefundQuoteCreateRequest,
    SaleOrderRead,
    ShiftRead,
    SyncSalesRequest,
    VoidRequest,
)
from app.schemas.pricing import PricingCalculateRequest
from app.services.approval_service import ApprovalEvidence, ApprovalService, has_permission
from app.services.hold_draft_service import HoldDraftService, hold_error
from app.services.pricing_service import PricingResult, PricingService, canonical_hash, pricing_error
from app.services.refund_service import RefundService, serialize_operation, serialize_quote
from app.services.sale_service import SaleService, pricing_request_for_sale, sale_request_hash
from app.utils.promptpay import generate_promptpay_payload

router = APIRouter(prefix="/api/v1/pos", tags=["pos"])


def ok(data: Any, meta: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"data": data, "meta": {"version": settings.app_version, **(meta or {})}, "error": None}


def _user_display(user: User | None) -> str | None:
    if user is None:
        return None
    return user.display_name or " ".join(part for part in [user.first_name, user.last_name] if part) or user.username


async def _enrich_hold_drafts(
    db: AsyncSession,
    rows: list[HoldDraftRead],
    *,
    company_id: uuid.UUID,
    branch_id: uuid.UUID,
) -> list[dict[str, Any]]:
    user_ids = {row.owner_user_id for row in rows}
    user_ids.update(row.assignee_user_id for row in rows if row.assignee_user_id)
    shift_ids = {row.origin_shift_id for row in rows}
    location_ids = {row.location_id for row in rows}
    users = (
        list(
            (
                await db.scalars(
                    select(User).where(User.company_id == company_id, User.id.in_(user_ids))
                )
            ).all()
        )
        if user_ids
        else []
    )
    shifts = (
        list(
            (
                await db.scalars(
                    select(CashierShift).where(
                        CashierShift.company_id == company_id,
                        CashierShift.branch_id == branch_id,
                        CashierShift.id.in_(shift_ids),
                    )
                )
            ).all()
        )
        if shift_ids
        else []
    )
    locations = (
        list(
            (
                await db.scalars(
                    select(StockLocation).where(
                        StockLocation.company_id == company_id,
                        StockLocation.branch_id == branch_id,
                        StockLocation.id.in_(location_ids),
                    )
                )
            ).all()
        )
        if location_ids
        else []
    )
    user_map = {row.id: row for row in users}
    shift_map = {row.id: row.shift_number for row in shifts}
    location_map = {row.id: row.name for row in locations}
    return [
        {
            **row.model_dump(mode="json"),
            "owner_display": _user_display(user_map.get(row.owner_user_id)),
            "assignee_display": _user_display(user_map.get(row.assignee_user_id)) if row.assignee_user_id else None,
            "origin_shift_number": shift_map.get(row.origin_shift_id),
            "location_name": location_map.get(row.location_id),
        }
        for row in rows
    ]


def _approval_payload(
    payload: CreateSaleRequest | VoidRequest | RefundRequest | PartialRefundRequest | RefundExecuteRequest,
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


def _shift_approval_payload(
    shift_id: uuid.UUID,
    payload: CashMovementCreateRequest | CloseShiftRequest,
) -> dict[str, Any]:
    value = payload.model_dump(
        mode="json",
        exclude={"approval_token"},
        exclude_none=True,
    )
    value["shift_id"] = str(shift_id)
    return value


def _shift_request_hash(payload: CashMovementCreateRequest | CloseShiftRequest) -> str:
    return canonical_hash(
        payload.model_dump(
            mode="json",
            exclude={"approval_token"},
            exclude_none=True,
        )
    )


async def _cash_movement_replay(
    db: AsyncSession,
    current: TokenData,
    shift_id: uuid.UUID,
    payload: CashMovementCreateRequest,
) -> PosCashMovement | None:
    if current.branch_id is None:
        return None
    row = await db.scalar(
        select(PosCashMovement).where(
            PosCashMovement.company_id == current.company_id,
            PosCashMovement.branch_id == current.branch_id,
            PosCashMovement.idempotency_key == payload.idempotency_key,
        )
    )
    if row is not None and (
        row.shift_id != shift_id or row.request_hash != _shift_request_hash(payload)
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "duplicate_request", "message": "Idempotency key belongs to another cash movement"},
        )
    return row


async def _closed_shift_replay(
    db: AsyncSession,
    current: TokenData,
    shift_id: uuid.UUID,
    payload: CloseShiftRequest,
) -> CashierShift | None:
    key = payload.idempotency_key or f"legacy-close:{shift_id}"
    row = await db.scalar(
        select(CashierShift).where(
            CashierShift.id == shift_id,
            CashierShift.company_id == current.company_id,
            CashierShift.user_id == current.user_id,
        )
    )
    if row is None or row.status == "open":
        return None
    if row.close_idempotency_key == key and row.close_request_hash == _shift_request_hash(payload):
        return row
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={"code": "shift_closed", "message": "Shift is already closed"},
    )


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


def _enforce_retail_payment_readiness(
    current: TokenData,
    payload: CreateSaleRequest,
    *,
    synchronized: bool = False,
) -> None:
    if current.business_type != "retail_pos":
        return
    if current.target_database != "retail_pos" or current.brand_id is None or current.branch_id is None:
        raise pricing_error(
            status.HTTP_403_FORBIDDEN,
            "retail_context_required",
            "Retail checkout requires a signed Retail Company, Brand and Branch context",
        )
    if synchronized or payload.is_offline:
        raise pricing_error(
            status.HTTP_409_CONFLICT,
            "retail_offline_not_authorized",
            "Retail offline checkout is disabled until a signed authorization lease is available",
        )
    methods = {payment.payment_method for payment in payload.payments}
    if not methods:
        methods = {payload.payment_method}
    if methods != {"cash"}:
        raise pricing_error(
            status.HTTP_409_CONFLICT,
            "retail_provider_not_ready",
            "Retail non-cash payment is disabled until Provider UAT and reconciliation are complete",
            payment_methods=sorted(methods),
        )


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


@router.get("/shifts/{shift_id}/summary")
async def get_shift_summary(
    shift_id: uuid.UUID,
    current: TokenData = Depends(require_permission("pos.cashier.open_shift")),
    db: AsyncSession = Depends(get_db),
    counter_device: DeviceTokenData | None = Depends(get_optional_counter_device),
) -> dict[str, Any]:
    _require_matching_counter_device(current, counter_device)
    summary = await _sale_service(db, current).get_shift_summary(
        shift_id,
        current.company_id,
        current.user_id,
        include_journal=current.target_database != "retail_pos",
    )
    return ok(summary)


@router.post("/shifts/{shift_id}/cash-movements", status_code=status.HTTP_201_CREATED)
async def create_cash_movement(
    shift_id: uuid.UUID,
    payload: CashMovementCreateRequest,
    request: Request,
    current: TokenData = Depends(require_permission("pos.cash_movement.create")),
    db: AsyncSession = Depends(get_db),
    counter_device: DeviceTokenData | None = Depends(get_optional_counter_device),
) -> dict[str, Any]:
    _require_matching_counter_device(current, counter_device)
    if current.target_database == "retail_pos":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "feature_not_enabled", "message": "Retail cash movement will be enabled in its Retail work package"},
        )
    replay = await _cash_movement_replay(db, current, shift_id, payload)
    if replay is not None:
        return ok(CashMovementRead.model_validate(replay).model_dump())
    if current.branch_id is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Branch context required")
    branch_settings = await db.scalar(
        select(BranchSettings).where(
            BranchSettings.company_id == current.company_id,
            BranchSettings.branch_id == current.branch_id,
        )
    )
    threshold = Decimal(
        branch_settings.pos_cash_movement_approval_threshold
        if branch_settings else 1000
    )
    approval_evidence = None
    if Decimal(payload.amount) >= threshold:
        approval_evidence = await ApprovalService(db).authorize_operation(
            current=current,
            action="pos.cash_movement.approve",
            request_payload=_shift_approval_payload(shift_id, payload),
            approval_token=payload.approval_token,
            reason=f"Cash movement {payload.amount} reaches approval threshold {threshold}",
            resource_type="CashierShift",
            resource_id=str(shift_id),
            allow_direct=False,
        )
    movement = await _sale_service(db, current).create_cash_movement(
        shift_id,
        current.company_id,
        current.user_id,
        payload,
        approval_evidence=approval_evidence,
        device_id=counter_device.device_id if counter_device else None,
        device_code=counter_device.device_code if counter_device else None,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    return ok(CashMovementRead.model_validate(movement).model_dump())


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
    replay = await _closed_shift_replay(db, current, shift_id, payload)
    if replay is not None:
        return ok(ShiftRead.model_validate(replay).model_dump())
    service = _sale_service(db, current)
    summary = await service.get_shift_summary(
        shift_id,
        current.company_id,
        current.user_id,
        include_journal=current.target_database != "retail_pos",
    )
    branch_settings = await db.scalar(
        select(BranchSettings).where(
            BranchSettings.company_id == current.company_id,
            BranchSettings.branch_id == current.branch_id,
        )
    ) if current.branch_id else None
    threshold = Decimal(
        branch_settings.pos_shift_variance_approval_threshold
        if branch_settings else 500
    )
    difference = Decimal(payload.closing_cash) - Decimal(str(summary["expected_cash"]))
    approval_evidence = None
    if abs(difference) >= threshold:
        approval_evidence = await ApprovalService(db).authorize_operation(
            current=current,
            action="pos.shift.variance.approve",
            request_payload=_shift_approval_payload(shift_id, payload),
            approval_token=payload.approval_token,
            reason=f"Shift cash variance {difference} reaches approval threshold {threshold}",
            resource_type="CashierShift",
            resource_id=str(shift_id),
            allow_direct=False,
        )
    shift = await service.close_shift(
        shift_id,
        current.company_id,
        current.user_id,
        payload,
        device_id=counter_device.device_id if counter_device else None,
        device_code=counter_device.device_code if counter_device else None,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        approval_evidence=approval_evidence,
        include_journal=current.target_database != "retail_pos",
    )
    return ok(ShiftRead.model_validate(shift).model_dump())


@router.post("/shifts/{shift_id}/handover")
async def handover_shift(
    shift_id: uuid.UUID,
    payload: CloseShiftRequest,
    request: Request,
    current: TokenData = Depends(require_permission("pos.cashier.handover")),
    db: AsyncSession = Depends(get_db),
    counter_device: DeviceTokenData | None = Depends(get_optional_counter_device),
) -> dict[str, Any]:
    if counter_device is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "counter_device_required", "message": "A paired Counter is required for handover"},
        )
    _require_matching_counter_device(current, counter_device)
    replay = await _closed_shift_replay(db, current, shift_id, payload)
    if replay is not None:
        return ok({
            "shift": ShiftRead.model_validate(replay).model_dump(),
            "device_code": counter_device.device_code,
            "staff_logout_required": True,
            "device_pairing_preserved": True,
        })
    service = _sale_service(db, current)
    summary = await service.get_shift_summary(
        shift_id,
        current.company_id,
        current.user_id,
        include_journal=current.target_database != "retail_pos",
    )
    branch_settings = await db.scalar(
        select(BranchSettings).where(
            BranchSettings.company_id == current.company_id,
            BranchSettings.branch_id == current.branch_id,
        )
    ) if current.branch_id else None
    threshold = Decimal(branch_settings.pos_shift_variance_approval_threshold if branch_settings else 500)
    difference = Decimal(payload.closing_cash) - Decimal(str(summary["expected_cash"]))
    approval_evidence = None
    if abs(difference) >= threshold:
        approval_evidence = await ApprovalService(db).authorize_operation(
            current=current,
            action="pos.shift.variance.approve",
            request_payload=_shift_approval_payload(shift_id, payload),
            approval_token=payload.approval_token,
            reason=f"Shift handover variance {difference} reaches approval threshold {threshold}",
            resource_type="CashierShift",
            resource_id=str(shift_id),
            allow_direct=False,
        )
    shift = await service.close_shift(
        shift_id,
        current.company_id,
        current.user_id,
        payload,
        device_id=counter_device.device_id,
        device_code=counter_device.device_code,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        approval_evidence=approval_evidence,
        include_journal=current.target_database != "retail_pos",
        handover=True,
    )
    return ok({
        "shift": ShiftRead.model_validate(shift).model_dump(),
        "device_code": counter_device.device_code,
        "staff_logout_required": True,
        "device_pairing_preserved": True,
    })


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


@router.post("/drafts", status_code=status.HTTP_201_CREATED)
async def create_hold_draft(
    payload: HoldDraftCreateRequest,
    current: TokenData = Depends(require_permission("pos.draft.create")),
    db: AsyncSession = Depends(get_db),
    counter_device: DeviceTokenData | None = Depends(get_optional_counter_device),
) -> dict[str, Any]:
    if current.branch_id is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Branch context required")
    _require_matching_counter_device(current, counter_device)
    draft = await HoldDraftService(db).create(
        company_id=current.company_id,
        brand_id=current.brand_id,
        branch_id=current.branch_id,
        user_id=current.user_id,
        device_id=counter_device.device_id if counter_device else None,
        device_code=counter_device.device_code if counter_device else None,
        payload=payload,
    )
    return ok(draft.model_dump(mode="json"))


@router.get("/drafts")
async def list_hold_drafts(
    status_value: str | None = Query(default=None, alias="status"),
    mine: bool = Query(default=False),
    this_counter: bool = Query(default=False),
    search: str | None = Query(default=None, max_length=160),
    include_history: bool = Query(default=False),
    current: TokenData = Depends(require_permission("pos.draft.view")),
    db: AsyncSession = Depends(get_db),
    counter_device: DeviceTokenData | None = Depends(get_optional_counter_device),
) -> dict[str, Any]:
    if current.branch_id is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Branch context required")
    _require_matching_counter_device(current, counter_device)
    if this_counter and counter_device is None:
        raise hold_error(
            status.HTTP_409_CONFLICT,
            "counter_device_required",
            "A paired Counter device is required for the this-counter filter",
        )
    rows = await HoldDraftService(db).list(
        company_id=current.company_id,
        brand_id=current.brand_id,
        branch_id=current.branch_id,
        status_value=status_value,
        owner_user_id=current.user_id if mine else None,
        device_id=counter_device.device_id if this_counter and counter_device else None,
        search=search,
        include_history=include_history,
    )
    return ok(
        await _enrich_hold_drafts(
            db,
            rows,
            company_id=current.company_id,
            branch_id=current.branch_id,
        ),
        meta={"total": len(rows)},
    )


@router.get("/drafts/{draft_id}")
async def get_hold_draft(
    draft_id: uuid.UUID,
    current: TokenData = Depends(require_permission("pos.draft.view")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    if current.branch_id is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Branch context required")
    draft = await HoldDraftService(db).get(
        draft_id=draft_id,
        company_id=current.company_id,
        brand_id=current.brand_id,
        branch_id=current.branch_id,
    )
    enriched = await _enrich_hold_drafts(
        db,
        [draft],
        company_id=current.company_id,
        branch_id=current.branch_id,
    )
    return ok(enriched[0])


@router.patch("/drafts/{draft_id}")
async def update_hold_draft(
    draft_id: uuid.UUID,
    payload: HoldDraftUpdateRequest,
    current: TokenData = Depends(require_permission("pos.draft.update")),
    db: AsyncSession = Depends(get_db),
    counter_device: DeviceTokenData | None = Depends(get_optional_counter_device),
) -> dict[str, Any]:
    if current.branch_id is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Branch context required")
    _require_matching_counter_device(current, counter_device)
    draft = await HoldDraftService(db).update(
        draft_id=draft_id,
        company_id=current.company_id,
        brand_id=current.brand_id,
        branch_id=current.branch_id,
        user_id=current.user_id,
        device_id=counter_device.device_id if counter_device else None,
        payload=payload,
        can_reassign=has_permission(current.permissions, "pos.draft.reassign"),
    )
    return ok(draft.model_dump(mode="json"))


@router.post("/drafts/{draft_id}/claim")
async def claim_hold_draft(
    draft_id: uuid.UUID,
    payload: HoldDraftActionRequest,
    current: TokenData = Depends(require_permission("pos.draft.resume")),
    db: AsyncSession = Depends(get_db),
    counter_device: DeviceTokenData | None = Depends(get_optional_counter_device),
) -> dict[str, Any]:
    if current.branch_id is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Branch context required")
    _require_matching_counter_device(current, counter_device)
    result = await HoldDraftService(db).claim(
        draft_id=draft_id,
        company_id=current.company_id,
        brand_id=current.brand_id,
        branch_id=current.branch_id,
        user_id=current.user_id,
        device_id=counter_device.device_id if counter_device else None,
        payload=payload,
    )
    return ok(result.model_dump(mode="json"))


@router.post("/drafts/{draft_id}/resume")
async def resume_hold_draft(
    draft_id: uuid.UUID,
    payload: HoldDraftActionRequest,
    current: TokenData = Depends(require_permission("pos.draft.resume")),
    db: AsyncSession = Depends(get_db),
    counter_device: DeviceTokenData | None = Depends(get_optional_counter_device),
) -> dict[str, Any]:
    if current.branch_id is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Branch context required")
    _require_matching_counter_device(current, counter_device)
    draft = await HoldDraftService(db).resume(
        draft_id=draft_id,
        company_id=current.company_id,
        brand_id=current.brand_id,
        branch_id=current.branch_id,
        user_id=current.user_id,
        device_id=counter_device.device_id if counter_device else None,
        payload=payload,
    )
    return ok(draft.model_dump(mode="json"))


@router.post("/drafts/{draft_id}/release")
async def release_hold_draft_claim(
    draft_id: uuid.UUID,
    payload: HoldDraftActionRequest,
    current: TokenData = Depends(require_permission("pos.draft.resume")),
    db: AsyncSession = Depends(get_db),
    counter_device: DeviceTokenData | None = Depends(get_optional_counter_device),
) -> dict[str, Any]:
    if current.branch_id is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Branch context required")
    _require_matching_counter_device(current, counter_device)
    draft = await HoldDraftService(db).release_claim(
        draft_id=draft_id,
        company_id=current.company_id,
        brand_id=current.brand_id,
        branch_id=current.branch_id,
        user_id=current.user_id,
        device_id=counter_device.device_id if counter_device else None,
        payload=payload,
    )
    return ok(draft.model_dump(mode="json"))


@router.post("/drafts/{draft_id}/discard")
async def discard_hold_draft(
    draft_id: uuid.UUID,
    payload: HoldDraftActionRequest,
    current: TokenData = Depends(require_permission("pos.draft.discard")),
    db: AsyncSession = Depends(get_db),
    counter_device: DeviceTokenData | None = Depends(get_optional_counter_device),
) -> dict[str, Any]:
    if current.branch_id is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Branch context required")
    _require_matching_counter_device(current, counter_device)
    draft = await HoldDraftService(db).discard(
        draft_id=draft_id,
        company_id=current.company_id,
        brand_id=current.brand_id,
        branch_id=current.branch_id,
        user_id=current.user_id,
        device_id=counter_device.device_id if counter_device else None,
        payload=payload,
    )
    return ok(draft.model_dump(mode="json"))


@router.post("/drafts/{draft_id}/reopen", status_code=status.HTTP_201_CREATED)
async def reopen_hold_draft(
    draft_id: uuid.UUID,
    payload: HoldDraftActionRequest,
    current: TokenData = Depends(require_permission("pos.draft.create")),
    db: AsyncSession = Depends(get_db),
    counter_device: DeviceTokenData | None = Depends(get_optional_counter_device),
) -> dict[str, Any]:
    if current.branch_id is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Branch context required")
    _require_matching_counter_device(current, counter_device)
    draft = await HoldDraftService(db).reopen(
        draft_id=draft_id,
        company_id=current.company_id,
        brand_id=current.brand_id,
        branch_id=current.branch_id,
        user_id=current.user_id,
        device_id=counter_device.device_id if counter_device else None,
        device_code=counter_device.device_code if counter_device else None,
        payload=payload,
    )
    return ok(draft.model_dump(mode="json"))


@router.get("/drafts/{draft_id}/audit")
async def list_hold_draft_audit(
    draft_id: uuid.UUID,
    current: TokenData = Depends(require_permission("pos.draft.view")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    if current.branch_id is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Branch context required")
    await HoldDraftService(db).get(
        draft_id=draft_id,
        company_id=current.company_id,
        brand_id=current.brand_id,
        branch_id=current.branch_id,
    )
    rows = list(
        (
            await db.scalars(
                select(PosHoldDraftAudit)
                .where(
                    PosHoldDraftAudit.draft_id == draft_id,
                    PosHoldDraftAudit.company_id == current.company_id,
                    PosHoldDraftAudit.branch_id == current.branch_id,
                )
                .order_by(PosHoldDraftAudit.created_at.asc())
            )
        ).all()
    )
    actor_ids = {row.actor_user_id for row in rows}
    actors = (
        list(
            (
                await db.scalars(
                    select(User).where(
                        User.company_id == current.company_id,
                        User.id.in_(actor_ids),
                    )
                )
            ).all()
        )
        if actor_ids
        else []
    )
    actor_map = {row.id: row for row in actors}
    return ok(
        [
            {
                "id": str(row.id),
                "action": row.action,
                "from_status": row.from_status,
                "to_status": row.to_status,
                "from_version": row.from_version,
                "to_version": row.to_version,
                "actor_user_id": str(row.actor_user_id),
                "actor_display": _user_display(actor_map.get(row.actor_user_id)),
                "device_id": str(row.device_id) if row.device_id else None,
                "shift_id": str(row.shift_id) if row.shift_id else None,
                "reason": row.reason,
                "metadata": row.metadata_json,
                "created_at": row.created_at.isoformat(),
            }
            for row in rows
        ]
    )


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
    _enforce_retail_payment_readiness(current, payload)
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
        _enforce_retail_payment_readiness(current, sale_payload, synchronized=True)
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
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail={"code": "legacy_refund_disabled", "message": "Create a Server refund quote and use /refunds"},
    )


@router.post("/sales/{order_id}/refund/partial")
async def partial_refund_sale(
    order_id: uuid.UUID,
    payload: PartialRefundRequest,
    current: TokenData = Depends(
        require_any_permission("pos.refund.create", "pos.refund.request")
    ),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail={"code": "legacy_refund_disabled", "message": "Create a Server refund quote and use /refunds"},
    )


@router.post("/refunds/quotes", status_code=status.HTTP_201_CREATED)
async def create_refund_quote(
    payload: RefundQuoteCreateRequest,
    current: TokenData = Depends(require_any_permission("pos.refund.create", "pos.refund.request")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    if current.branch_id is None:
        raise HTTPException(status_code=409, detail="Branch context required")
    quote = await RefundService(db).create_quote(
        company_id=current.company_id,
        branch_id=current.branch_id,
        user_id=current.user_id,
        data=payload,
    )
    return ok(serialize_quote(quote))


@router.post("/refunds", status_code=status.HTTP_201_CREATED)
async def execute_refund(
    payload: RefundExecuteRequest,
    current: TokenData = Depends(require_any_permission("pos.refund.create", "pos.refund.request")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    if current.branch_id is None:
        raise HTTPException(status_code=409, detail="Branch context required")
    service = RefundService(db)
    replay = await service.find_execute_replay(
        company_id=current.company_id,
        branch_id=current.branch_id,
        user_id=current.user_id,
        data=payload,
    )
    if replay is not None:
        return ok(await serialize_operation(service, replay))
    approval = await ApprovalService(db).authorize_operation(
        current=current,
        action="pos.refund.create",
        request_payload=_approval_payload(payload),
        approval_token=payload.approval_token,
        reason=payload.reason_note or payload.reason_code,
        resource_type="RefundQuote",
        resource_id=str(payload.quote_id),
        allow_direct=False,
    )
    operation = await service.execute(
        company_id=current.company_id,
        branch_id=current.branch_id,
        user_id=current.user_id,
        data=payload,
        approval=approval,
    )
    return ok(await serialize_operation(service, operation))


@router.get("/refunds")
async def list_refunds(
    order_id: uuid.UUID | None = Query(default=None),
    current: TokenData = Depends(require_permission("pos.sale.view")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    if current.branch_id is None:
        raise HTTPException(status_code=409, detail="Branch context required")
    service = RefundService(db)
    rows = await service.list_operations(current.company_id, current.branch_id, order_id)
    return ok([await serialize_operation(service, row) for row in rows])


@router.get("/refunds/reconciliation")
async def refund_reconciliation(
    shift_id: uuid.UUID | None = Query(default=None),
    current: TokenData = Depends(require_permission("pos.sale.view")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    if current.branch_id is None:
        raise HTTPException(status_code=409, detail="Branch context required")
    filters = [RefundOperation.company_id == current.company_id, RefundOperation.branch_id == current.branch_id]
    if shift_id:
        filters.append(RefundOperation.shift_id == shift_id)
    operations = list((await db.scalars(select(RefundOperation).where(*filters))).all())
    operation_ids = [row.id for row in operations]
    legs = list((await db.scalars(select(RefundPaymentLeg).where(RefundPaymentLeg.operation_id.in_(operation_ids)))).all()) if operation_ids else []
    tax_links = list((await db.scalars(select(RefundTaxLink).where(RefundTaxLink.operation_id.in_(operation_ids)))).all()) if operation_ids else []
    sale_filters = [SaleOrder.company_id == current.company_id, SaleOrder.branch_id == current.branch_id]
    if shift_id:
        sale_filters.append(SaleOrder.shift_id == shift_id)
    gross_sales = await db.scalar(select(func.coalesce(func.sum(SaleOrder.total_amount), 0)).where(
        *sale_filters, SaleOrder.status.in_(("completed", "partially_refunded", "refunded")),
    )) or Decimal("0")
    void_count = await db.scalar(select(func.count(SaleOrder.id)).where(*sale_filters, SaleOrder.status == "voided")) or 0
    void_amount = await db.scalar(select(func.coalesce(func.sum(SaleOrder.total_amount), 0)).where(*sale_filters, SaleOrder.status == "voided")) or Decimal("0")
    return ok({
        "gross_sales": str(gross_sales),
        "operation_count": len(operations),
        "status_counts": {state: sum(1 for row in operations if row.status == state) for state in sorted({row.status for row in operations})},
        "cash_refund_succeeded": str(sum((Decimal(leg.amount) for leg in legs if leg.leg_type == "cash" and leg.status == "succeeded"), Decimal("0"))),
        "provider_refund_succeeded": str(sum((Decimal(leg.amount) for leg in legs if leg.leg_type == "provider" and leg.status == "succeeded"), Decimal("0"))),
        "pending_or_unknown": sum(1 for row in operations if row.status in {"requested", "processing", "cash_due", "unknown", "needs_reconciliation", "tax_pending"}),
        "credit_note_status_counts": {state: sum(1 for row in tax_links if row.status == state) for state in sorted({row.status for row in tax_links})},
        "void_count": int(void_count),
        "void_amount": str(void_amount),
        "void_is_separate": True,
    })


@router.get("/refunds/{operation_id}")
async def get_refund(
    operation_id: uuid.UUID,
    current: TokenData = Depends(require_permission("pos.sale.view")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    if current.branch_id is None:
        raise HTTPException(status_code=409, detail="Branch context required")
    service = RefundService(db)
    row = await service.get_operation(operation_id, current.company_id, current.branch_id)
    return ok(await serialize_operation(service, row))


@router.post("/refunds/{operation_id}/cash-confirm")
async def confirm_cash_refund(
    operation_id: uuid.UUID,
    payload: RefundOperationActionRequest,
    current: TokenData = Depends(require_permission("pos.refund.create")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    if current.branch_id is None:
        raise HTTPException(status_code=409, detail="Branch context required")
    service = RefundService(db)
    row = await service.confirm_cash(operation_id, current.company_id, current.branch_id, current.user_id, payload)
    return ok(await serialize_operation(service, row))


@router.post("/refunds/{operation_id}/inquire")
async def inquire_refund(
    operation_id: uuid.UUID,
    payload: RefundOperationActionRequest,
    current: TokenData = Depends(require_any_permission("pos.refund.create", "pos.refund.request")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    if current.branch_id is None:
        raise HTTPException(status_code=409, detail="Branch context required")
    service = RefundService(db)
    row = await service.inquire(operation_id, current.company_id, current.branch_id, current.user_id, payload)
    return ok(await serialize_operation(service, row))


@router.post("/refunds/{operation_id}/retry")
async def retry_refund(
    operation_id: uuid.UUID,
    payload: RefundOperationActionRequest,
    current: TokenData = Depends(require_permission("pos.refund.create")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    if current.branch_id is None:
        raise HTTPException(status_code=409, detail="Branch context required")
    service = RefundService(db)
    row = await service.retry(operation_id, current.company_id, current.branch_id, current.user_id, payload)
    return ok(await serialize_operation(service, row))


@router.post("/refunds/{operation_id}/tax-retry")
async def retry_refund_tax(
    operation_id: uuid.UUID,
    payload: RefundOperationActionRequest,
    current: TokenData = Depends(require_any_permission("pos.refund.create", "accounting.etax.create")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    if current.branch_id is None:
        raise HTTPException(status_code=409, detail="Branch context required")
    service = RefundService(db)
    row = await service.retry_tax(operation_id, current.company_id, current.branch_id, current.user_id, payload)
    return ok(await serialize_operation(service, row))


@router.post("/refunds/provider/sandbox/webhook")
async def sandbox_refund_webhook(
    payload: RefundProviderWebhookRequest,
    x_refund_signature: str | None = Header(default=None),
    db: AsyncSession = Depends(get_restaurant_service_db),
) -> dict[str, Any]:
    if settings.refund_provider_mode != "sandbox":
        raise HTTPException(status_code=404, detail="Sandbox provider is disabled")
    service = RefundService(db)
    row = await service.apply_webhook(payload, x_refund_signature)
    return ok(await serialize_operation(service, row))


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
