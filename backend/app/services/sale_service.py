from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
import logging
import uuid
from zoneinfo import ZoneInfo

from fastapi import HTTPException, status
from sqlalchemy import and_, func, or_, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.audit import AuditLog
from app.models.branch import Branch
from app.models.company import Company
from app.models.pos import CashierShift, Payment, SaleOrder, SaleOrderItem
from app.models.refund import RefundOperation
from app.models.pricing import PriceOverrideAudit
from app.models.product import Product, ProductVariant
from app.models.restaurant import BrandBranch
from app.models.settings import BranchSettings
from app.models.stock import StockBalance, StockLocation
from app.models.user import User
from app.schemas.pos import (
    CloseShiftRequest,
    CreateSaleRequest,
    OpenShiftRequest,
    PartialRefundRequest,
    PaymentCreateRequest,
    SyncSalesRequest,
    VoidRequest,
)
from app.schemas.pricing import PricingCalculateRequest, PricingLineRequest
from app.services.accounting_service import AccountingService
from app.services.approval_service import ApprovalEvidence
from app.services.crm_service import CRMService
from app.services.hold_draft_service import HoldDraftService, hold_error
from app.services.notification_service import NotificationService
from app.services.operational_handoff_service import (
    ensure_sale_completed_handoff,
    ensure_sale_state_changed_handoff,
)
from app.services.pricing_service import PricingResult, PricingService, canonical_hash, pricing_error
from app.services.stock_service import StockService
from app.utils.webhook_dispatcher import trigger_event
from app.schemas.crm import EarnPointsRequest

TWOPLACES = Decimal("0.01")
FOURPLACES = Decimal("0.0001")
BANGKOK = ZoneInfo("Asia/Bangkok")
logger = logging.getLogger(__name__)


def q2(value: Decimal) -> Decimal:
    return Decimal(value).quantize(TWOPLACES, rounding=ROUND_HALF_UP)


def q4(value: Decimal) -> Decimal:
    return Decimal(value).quantize(FOURPLACES, rounding=ROUND_HALF_UP)


def _discounted_value(
    base_price: Decimal,
    discount_amount: Decimal,
    discount_type: str,
) -> Decimal:
    if discount_type == "percent":
        discounted = base_price - (base_price * discount_amount / Decimal("100"))
    else:
        discounted = base_price - discount_amount
    return max(Decimal("0"), discounted)


def sale_discount_percentage(data: CreateSaleRequest) -> Decimal:
    gross = Decimal("0")
    subtotal = Decimal("0")
    for item in data.items:
        qty = Decimal(item.qty)
        original_price = Decimal(item.original_price)
        gross += original_price * qty
        effective_price = _discounted_value(
            original_price,
            Decimal(item.discount_amount),
            item.discount_type,
        )
        subtotal += q4(effective_price) * qty
    after_order_discount = _discounted_value(
        q2(subtotal),
        Decimal(data.discount_amount),
        data.discount_type,
    )
    if gross <= 0:
        return Decimal("0.00")
    total_discount = max(Decimal("0"), gross - after_order_discount)
    return q2(total_discount * Decimal("100") / gross)


def pricing_request_for_sale(data: CreateSaleRequest) -> PricingCalculateRequest:
    """Translate the untrusted checkout payload into the pricing input contract.

    Client price and VAT values are supplied only as expectations. The pricing
    engine resolves all authoritative monetary values from server-side data.
    """
    return PricingCalculateRequest(
        items=[
            PricingLineRequest(
                product_id=item.product_id,
                variant_id=item.variant_id,
                qty=item.qty,
                discount_amount=item.discount_amount,
                discount_type=item.discount_type,
                expected_unit_price=item.original_price,
                expected_price_version=item.expected_price_version,
                price_override=item.price_override,
            )
            for item in data.items
        ],
        discount_amount=data.discount_amount,
        discount_type=data.discount_type,
        channel=data.channel,
        currency=data.currency,
        customer_id=data.customer_id,
        idempotency_key=data.client_order_id or f"non-idempotent-{uuid.uuid4()}",
        cart_version=data.cart_version,
    )


def sale_request_hash(data: CreateSaleRequest) -> str:
    return canonical_hash(
        data.model_dump(
            mode="json",
            exclude={"approval_token", "price_override_approval_token"},
            exclude_none=True,
        )
    )


class SaleService:
    def __init__(
        self,
        db: AsyncSession,
        *,
        legacy_side_effects_enabled: bool = True,
    ):
        self.db = db
        self.stock_service = StockService(db)
        self.legacy_side_effects_enabled = legacy_side_effects_enabled

    async def open_shift(
        self,
        company_id: uuid.UUID,
        branch_id: uuid.UUID,
        user_id: uuid.UUID,
        data: OpenShiftRequest,
        *,
        device_id: uuid.UUID | None = None,
        device_code: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> CashierShift:
        existing = await self.get_open_shift(company_id, user_id, branch_id)
        if existing is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Shift already open")

        location = await self._get_location(company_id, data.location_id)
        if location.branch_id != branch_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Location not in current branch")

        now_local = datetime.now(BANGKOK)
        today_start = now_local.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)
        today_end = now_local.replace(hour=23, minute=59, second=59, microsecond=999999).astimezone(timezone.utc)
        count = await self.db.scalar(
            select(func.count(CashierShift.id)).where(
                CashierShift.company_id == company_id,
                CashierShift.branch_id == branch_id,
                CashierShift.opened_at >= today_start,
                CashierShift.opened_at <= today_end,
            )
        ) or 0
        shift = CashierShift(
            company_id=company_id,
            branch_id=branch_id,
            location_id=data.location_id,
            user_id=user_id,
            shift_number=f"S{now_local:%Y%m%d}-{int(count) + 1:03d}",
            opening_cash=q2(data.opening_cash),
        )
        self.db.add(shift)
        await self.db.flush()
        self.db.add(
            AuditLog(
                company_id=company_id,
                branch_id=branch_id,
                user_id=user_id,
                action="pos.shift.open",
                resource="CashierShift",
                resource_id=str(shift.id),
                new_value={
                    "shift_number": shift.shift_number,
                    "operator_user_id": str(user_id),
                    "location_id": str(data.location_id),
                    "opening_cash": str(q2(data.opening_cash)),
                    "device_id": str(device_id) if device_id else None,
                    "device_code": device_code,
                },
                ip_address=ip_address,
                user_agent=user_agent,
            )
        )
        await self.db.commit()
        await self.db.refresh(shift)
        return shift

    async def get_open_shift(
        self,
        company_id: uuid.UUID,
        user_id: uuid.UUID,
        branch_id: uuid.UUID,
    ) -> CashierShift | None:
        return await self.db.scalar(
            select(CashierShift).where(
                CashierShift.company_id == company_id,
                CashierShift.user_id == user_id,
                CashierShift.branch_id == branch_id,
                CashierShift.status == "open",
            )
        )

    async def close_shift(
        self,
        shift_id: uuid.UUID,
        company_id: uuid.UUID,
        user_id: uuid.UUID,
        data: CloseShiftRequest,
        *,
        device_id: uuid.UUID | None = None,
        device_code: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> CashierShift:
        shift = await self.db.scalar(
            select(CashierShift).where(
                CashierShift.id == shift_id,
                CashierShift.company_id == company_id,
                CashierShift.user_id == user_id,
            )
        )
        if shift is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shift not found")
        if shift.status != "open":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Shift already closed")

        pending_drafts = await HoldDraftService(self.db).count_pending_for_shift(shift.id)
        if pending_drafts:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "hold_drafts_pending",
                    "message": "Resolve, reassign or discard Hold Drafts before closing this shift",
                    "pending_count": pending_drafts,
                },
            )

        pending_refunds = await self.db.scalar(
            select(func.count(RefundOperation.id)).where(
                RefundOperation.shift_id == shift.id,
                RefundOperation.status.in_((
                    "requested", "processing", "cash_due", "unknown",
                    "needs_reconciliation", "tax_pending",
                )),
            )
        ) or 0
        if pending_refunds:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "refunds_pending",
                    "message": "Resolve pending or unknown refunds before closing this shift",
                    "pending_count": int(pending_refunds),
                },
            )

        cash_paid = await self.db.scalar(
            select(func.coalesce(func.sum(Payment.amount), 0))
            .join(SaleOrder, SaleOrder.id == Payment.order_id)
            .where(
                SaleOrder.shift_id == shift.id,
                SaleOrder.status.in_(("completed", "partially_refunded", "refunded")),
                Payment.payment_method == "cash",
            )
        ) or Decimal("0")
        cash_change = await self.db.scalar(
            select(func.coalesce(func.sum(SaleOrder.change_amount), 0)).where(
                SaleOrder.shift_id == shift.id,
                SaleOrder.status.in_(("completed", "partially_refunded", "refunded")),
            )
        ) or Decimal("0")
        expected_cash = q2(Decimal(shift.opening_cash or 0) + Decimal(cash_paid) - Decimal(cash_change))
        closing_cash = q2(data.closing_cash)
        shift.expected_cash = expected_cash
        shift.closing_cash = closing_cash
        shift.cash_difference = q2(closing_cash - expected_cash)
        shift.note = data.note
        shift.status = "closed"
        shift.closed_at = datetime.now(timezone.utc)
        self.db.add(
            AuditLog(
                company_id=company_id,
                branch_id=shift.branch_id,
                user_id=user_id,
                action="pos.shift.close",
                resource="CashierShift",
                resource_id=str(shift.id),
                old_value={
                    "status": "open",
                    "operator_user_id": str(shift.user_id),
                    "opening_cash": str(q2(shift.opening_cash)),
                    "total_sales": str(q2(shift.total_sales)),
                    "total_orders": shift.total_orders,
                },
                new_value={
                    "status": "closed",
                    "closed_by_user_id": str(user_id),
                    "closing_cash": str(closing_cash),
                    "expected_cash": str(expected_cash),
                    "cash_difference": str(shift.cash_difference),
                    "device_id": str(device_id) if device_id else None,
                    "device_code": device_code,
                    "note": data.note,
                },
                ip_address=ip_address,
                user_agent=user_agent,
            )
        )
        await self.db.commit()
        await self.db.refresh(shift)
        return shift

    async def list_shifts(
        self,
        company_id: uuid.UUID,
        branch_id: uuid.UUID | None,
        page: int = 1,
        limit: int = 20,
    ) -> tuple[list[CashierShift], int]:
        filters = [CashierShift.company_id == company_id]
        if branch_id is not None:
            filters.append(CashierShift.branch_id == branch_id)
        total = await self.db.scalar(select(func.count(CashierShift.id)).where(*filters)) or 0
        rows = await self.db.scalars(
            select(CashierShift)
            .where(*filters)
            .order_by(CashierShift.opened_at.desc())
            .offset((page - 1) * limit)
            .limit(limit)
        )
        return rows.all(), int(total)

    async def get_existing_sale_by_client_order_id(
        self,
        company_id: uuid.UUID,
        branch_id: uuid.UUID,
        client_order_id: str | None,
    ) -> SaleOrder | None:
        if not client_order_id:
            return None
        order = await self.db.scalar(
            select(SaleOrder)
            .where(
                SaleOrder.company_id == company_id,
                SaleOrder.branch_id == branch_id,
                SaleOrder.client_order_id == client_order_id,
            )
            .options(selectinload(SaleOrder.items), selectinload(SaleOrder.payments))
        )
        return order

    async def ensure_existing_sale_handoffs(
        self,
        order: SaleOrder,
        company_id: uuid.UUID,
        user_id: uuid.UUID,
        *,
        brand_id: uuid.UUID | None = None,
    ) -> SaleOrder:
        await ensure_sale_completed_handoff(
            self.db,
            company_id=company_id,
            brand_id=brand_id,
            branch_id=order.branch_id,
            order_id=order.id,
            order_number=order.order_number,
            total_amount=Decimal(order.total_amount),
            item_count=len(order.items),
            payment_methods=[payment.payment_method for payment in order.payments],
        )
        await self.db.commit()
        await self._ensure_accounting_handoff(order, company_id, user_id)
        return await self.get_sale(order.id, company_id)

    async def create_sale(
        self,
        company_id: uuid.UUID,
        branch_id: uuid.UUID,
        user_id: uuid.UUID,
        data: CreateSaleRequest,
        brand_id: uuid.UUID | None = None,
        recipe_inventory_location_id: uuid.UUID | None = None,
        approval_evidence: ApprovalEvidence | None = None,
        price_override_evidence: ApprovalEvidence | None = None,
        pricing_result: PricingResult | None = None,
    ) -> SaleOrder:
        if not data.items:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="At least one cart item is required")

        pricing = pricing_result or await PricingService(self.db).calculate(
            company_id=company_id,
            branch_id=branch_id,
            brand_id=brand_id,
            payload=pricing_request_for_sale(data),
            lock_prices=True,
        )
        request_hash = sale_request_hash(data)
        discount_percentage = pricing.discount_percentage
        branch_settings = await self.db.scalar(
            select(BranchSettings).where(
                BranchSettings.company_id == company_id,
                BranchSettings.branch_id == branch_id,
            )
        )
        allow_discount = branch_settings.pos_allow_discount if branch_settings else True
        hard_max = Decimal(
            branch_settings.pos_max_discount_pct if branch_settings else 100
        )
        cashier_limit = Decimal(
            branch_settings.pos_cashier_discount_limit_pct if branch_settings else 10
        )
        if discount_percentage > 0 and not allow_discount:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Discounts are disabled for this branch",
            )
        if discount_percentage > hard_max:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "discount_limit_exceeded",
                    "message": "Discount exceeds the branch maximum",
                    "discount_percentage": str(discount_percentage),
                    "maximum_percentage": str(hard_max),
                },
            )
        if discount_percentage > cashier_limit and approval_evidence is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "approval_required",
                    "action": "pos.discount.override",
                    "message": "Manager approval is required",
                    "discount_percentage": str(discount_percentage),
                    "cashier_limit_percentage": str(cashier_limit),
                },
            )
        if pricing.requires_price_override_approval and price_override_evidence is None:
            raise pricing_error(
                status.HTTP_403_FORBIDDEN,
                "approval_required",
                "Manager approval is required for this price override",
                action="pos.price.override",
            )

        quote = None
        if data.pricing_quote_id is not None or data.pricing_calculation_hash is not None:
            if data.pricing_quote_id is None or data.pricing_calculation_hash is None:
                raise pricing_error(
                    status.HTTP_409_CONFLICT,
                    "context_mismatch",
                    "Both pricing quote id and calculation hash are required",
                )
            quote = await PricingService(self.db).validate_quote(
                quote_id=data.pricing_quote_id,
                calculation_hash=data.pricing_calculation_hash,
                company_id=company_id,
                branch_id=branch_id,
                user_id=user_id,
                current_result=pricing,
            )
        elif pricing.has_price_discrepancy:
            raise pricing_error(
                status.HTTP_409_CONFLICT,
                "stale_price",
                "Displayed price differs from the server price; recalculate before checkout",
                calculation_hash=pricing.calculation_hash,
            )

        shift = await self._get_shift_for_sale(company_id, branch_id, user_id, data.shift_id)
        location = await self._get_location(company_id, data.location_id)
        if location.branch_id != branch_id or shift.location_id != data.location_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Shift and location mismatch")
        if recipe_inventory_location_id is not None and recipe_inventory_location_id != data.location_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Store stock location mismatch")

        stock_needs: dict[tuple[uuid.UUID, uuid.UUID | None], Decimal] = {}
        item_rows: list[dict[str, object]] = []
        for line in pricing.lines:
            product = line.product
            variant = line.variant
            key = (product.id, variant.id if variant else None)
            stock_needs[key] = stock_needs.get(key, Decimal("0")) + Decimal(line.request.qty)
            effective_unit_price = q4(
                line.applied_unit_price
                - (line.line_discount_amount / Decimal(line.request.qty))
            )
            item_rows.append(
                {
                    "product": product,
                    "variant": variant,
                    "qty": q4(line.request.qty),
                    "unit_price": effective_unit_price,
                    "original_price": line.applied_unit_price,
                    "discount_amount": q4(line.request.discount_amount),
                    "discount_type": line.request.discount_type,
                    "vat_type": line.vat_type,
                    "vat_rate": line.vat_rate,
                    "vat_amount": line.vat_amount,
                    "subtotal": line.line_subtotal,
                    "line_total": line.line_total,
                    "order_discount_share": line.order_discount_share,
                    "price_source": line.price_source,
                    "price_list_id": line.price_list_id,
                    "price_list_version": line.price_list_version,
                    "price_version": line.price_version,
                    "price_snapshot": line.snapshot(),
                    "price_override_applied": line.override_requested,
                    "price_override_reason": (
                        line.request.price_override.reason
                        if line.request.price_override is not None
                        else None
                    ),
                    "price_override_reason_code": (
                        line.request.price_override.reason_code
                        if line.request.price_override is not None
                        else None
                    ),
                    "override_deviation_pct": line.override_deviation_pct,
                    "override_requires_approval": line.override_requires_approval,
                }
            )

        await self._ensure_stock_available(company_id, branch_id, data.location_id, stock_needs)

        base_subtotal = pricing.subtotal
        actual_order_discount = pricing.order_discount_amount
        vat_total = pricing.vat_amount
        total_amount = pricing.total_amount
        payment_rows = self._prepare_payments(data, total_amount)
        paid_amount = q2(sum((Decimal(item.amount) for item in payment_rows), Decimal("0")))
        if paid_amount < total_amount:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Paid amount is insufficient")
        change_amount = q2(max(Decimal("0"), paid_amount - total_amount))

        now_local = datetime.now(BANGKOK)
        order_number = await self._generate_order_number(company_id, now_local.strftime("%Y%m%d"))

        order_values = {
            "id": uuid.uuid4(),
            "company_id": company_id,
            "branch_id": branch_id,
            "location_id": data.location_id,
            "shift_id": shift.id,
            "user_id": user_id,
            "order_number": order_number,
            "customer_name": data.customer_name,
            "customer_phone": data.customer_phone,
            "customer_tax_id": data.customer_tax_id,
            "subtotal": base_subtotal,
            "discount_amount": actual_order_discount,
            "discount_type": data.discount_type,
            "vat_amount": q2(vat_total),
            "vat_rate": Decimal("7.00"),
            "total_amount": total_amount,
            "paid_amount": paid_amount,
            "change_amount": change_amount,
            "is_offline": data.is_offline,
            "client_order_id": data.client_order_id,
            "synced_at": datetime.now(timezone.utc) if not data.is_offline else None,
            "note": data.note,
            "pricing_quote_id": data.pricing_quote_id,
            "pricing_request_hash": request_hash,
            "pricing_calculation_hash": pricing.calculation_hash,
            "pricing_calculation_version": pricing.calculation_version,
            "pricing_context": pricing.context(),
            "pricing_snapshot": pricing.snapshot(),
            "row_version": 1,
        }
        if data.client_order_id:
            inserted_id = (
                await self.db.execute(
                    insert(SaleOrder)
                    .values(**order_values)
                    .on_conflict_do_nothing(constraint="uq_sale_orders_client_order_id")
                    .returning(SaleOrder.id)
                )
            ).scalar_one_or_none()
            if inserted_id is None:
                await self.db.rollback()
                existing = await self.get_existing_sale_by_client_order_id(company_id, branch_id, data.client_order_id)
                if existing is None:
                    raise pricing_error(
                        status.HTTP_409_CONFLICT,
                        "duplicate_request",
                        "Idempotency key already exists in another checkout context",
                    )
                if existing.pricing_request_hash and existing.pricing_request_hash != request_hash:
                    raise pricing_error(
                        status.HTTP_409_CONFLICT,
                        "duplicate_request",
                        "Idempotency key was replayed with a different sale request",
                        client_order_id=data.client_order_id,
                    )
                if brand_id is not None and recipe_inventory_location_id is not None and existing.recipe_stock_posted_at is None:
                    from app.services.store_inventory_service import StoreInventoryService

                    await StoreInventoryService(self.db).post_sale(
                        order=existing,
                        company_id=company_id,
                        brand_id=brand_id,
                        branch_id=branch_id,
                        location_id=recipe_inventory_location_id,
                        user_id=user_id,
                        items=[
                            (row["product"], Decimal(row["qty"]))
                            for row in item_rows
                            if isinstance(row["product"], Product) and row["product"].product_type == "menu_item"
                        ],
                    )
                return await self.ensure_existing_sale_handoffs(
                    existing,
                    company_id,
                    user_id,
                    brand_id=brand_id,
                )
            order_id = inserted_id
        else:
            order = SaleOrder(**order_values)
            self.db.add(order)
            await self.db.flush()
            order_id = order.id

        if (data.source_hold_draft_id is None) != (data.source_hold_draft_version is None):
            raise hold_error(
                status.HTTP_409_CONFLICT,
                "context_mismatch",
                "Both source_hold_draft_id and source_hold_draft_version are required",
            )
        if data.source_hold_draft_id is not None and data.source_hold_draft_version is not None:
            await HoldDraftService(self.db).convert_into_sale(
                draft_id=data.source_hold_draft_id,
                expected_version=data.source_hold_draft_version,
                company_id=company_id,
                brand_id=brand_id,
                branch_id=branch_id,
                user_id=user_id,
                order_id=order_id,
            )

        for row in item_rows:
            product = row["product"]
            variant = row["variant"]
            assert isinstance(product, Product)
            assert variant is None or isinstance(variant, ProductVariant)
            order_item = SaleOrderItem(
                order_id=order_id,
                company_id=company_id,
                product_id=product.id,
                variant_id=variant.id if variant else None,
                product_name=product.name,
                variant_name=variant.name if variant else None,
                sku=variant.sku if variant else product.sku,
                unit_code=product.unit.code if product.unit else None,
                qty=row["qty"],
                unit_price=row["unit_price"],
                original_price=row["original_price"],
                discount_amount=row["discount_amount"],
                discount_type=row["discount_type"],
                vat_type=row["vat_type"],
                vat_rate=row["vat_rate"],
                vat_amount=row["vat_amount"],
                subtotal=row["subtotal"],
                line_total=row["line_total"],
                order_discount_share=row["order_discount_share"],
                price_source=row["price_source"],
                price_list_id=row["price_list_id"],
                price_list_version=row["price_list_version"],
                price_version=row["price_version"],
                price_snapshot=row["price_snapshot"],
                price_override_applied=row["price_override_applied"],
                price_override_reason=row["price_override_reason"],
            )
            self.db.add(order_item)
            await self.db.flush()
            if bool(row["price_override_applied"]):
                evidence = price_override_evidence or ApprovalEvidence(
                    action="pos.price.override",
                    requester_id=user_id,
                    approver_id=user_id,
                    reason=str(row["price_override_reason"]),
                    mode="policy_auto",
                )
                self.db.add(
                    PriceOverrideAudit(
                        company_id=company_id,
                        brand_id=brand_id,
                        branch_id=branch_id,
                        order_id=order_id,
                        order_item_id=order_item.id,
                        product_id=product.id,
                        requester_id=user_id,
                        approver_id=evidence.approver_id,
                        approval_grant_id=evidence.grant_id,
                        original_unit_price=row["price_snapshot"]["authoritative_unit_price"],
                        applied_unit_price=row["original_price"],
                        deviation_pct=row["override_deviation_pct"],
                        reason=str(row["price_override_reason"]),
                        reason_code=str(row["price_override_reason_code"] or "other"),
                        approval_mode=evidence.mode,
                        policy_snapshot={
                            "requires_approval": bool(row["override_requires_approval"]),
                            "auto_limit_pct": str(branch_settings.pos_price_override_auto_limit_pct if branch_settings else 10),
                            "auto_limit_amount": str(branch_settings.pos_price_override_auto_limit_amount if branch_settings else 100),
                            "max_deviation_pct": str(branch_settings.pos_price_override_max_deviation_pct if branch_settings else 50),
                            "minimum_margin_pct": str(branch_settings.pos_price_override_min_margin_pct if branch_settings else 0),
                            "self_approval": bool(branch_settings.pos_price_override_self_approval if branch_settings else False),
                        },
                        price_snapshot=row["price_snapshot"],
                    )
                )

        for payment in payment_rows:
            self.db.add(
                Payment(
                    order_id=order_id,
                    company_id=company_id,
                    payment_method=payment.payment_method,
                    amount=q2(Decimal(payment.amount)),
                    reference_no=payment.reference_no,
                    currency="THB",
                    settlement_state="settled" if payment.payment_method == "cash" else "unknown",
                    note=data.note,
                )
            )

        for row in item_rows:
            product = row["product"]
            variant = row["variant"]
            assert isinstance(product, Product)
            if product.product_type in ("menu_item", "raw_material"):
                continue
            balance = await self.stock_service._get_or_create_balance(
                company_id=company_id,
                branch_id=branch_id,
                location_id=data.location_id,
                product_id=product.id,
                variant_id=variant.id if variant else None,
            )
            await self.stock_service._record_movement(
                balance=balance,
                movement_type="sale",
                qty_delta=-Decimal(row["qty"]),
                user_id=user_id,
                cost_per_unit=Decimal(balance.cost_per_unit or 0),
                reference_type="SaleOrder",
                reference_id=str(order_id),
                note=data.note,
            )

        if brand_id is not None and recipe_inventory_location_id is not None:
            from app.services.store_inventory_service import StoreInventoryService

            sale_order = await self.db.get(SaleOrder, order_id)
            if sale_order is None:
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Sale order was not created")
            await StoreInventoryService(self.db).post_sale(
                order=sale_order,
                company_id=company_id,
                brand_id=brand_id,
                branch_id=branch_id,
                location_id=recipe_inventory_location_id,
                user_id=user_id,
                items=[
                    (row["product"], Decimal(row["qty"]))
                    for row in item_rows
                    if isinstance(row["product"], Product) and row["product"].product_type == "menu_item"
                ],
            )

        shift.total_sales = q2(Decimal(shift.total_sales or 0) + total_amount)
        shift.total_orders = int(shift.total_orders or 0) + 1
        self.db.add(
            AuditLog(
                company_id=company_id,
                branch_id=branch_id,
                user_id=user_id,
                action="pos.sale.create",
                resource="SaleOrder",
                resource_id=str(order_id),
                new_value={
                    "order_number": order_values["order_number"],
                    "total_amount": str(total_amount),
                    "discount_percentage": str(discount_percentage),
                    "pricing_calculation_hash": pricing.calculation_hash,
                    "approval": (
                        approval_evidence.as_audit_value()
                        if approval_evidence is not None
                        else None
                    ),
                    "price_override_approval": (
                        price_override_evidence.as_audit_value()
                        if price_override_evidence is not None
                        else None
                    ),
                },
            )
        )
        if self.legacy_side_effects_enabled:
            try:
                await trigger_event(
                    self.db,
                    company_id,
                    "sale.created",
                    {
                        "order_number": order_values["order_number"],
                        "total_amount": str(total_amount),
                        "branch_id": str(order_values["branch_id"]),
                        "items_count": len(item_rows),
                    },
                )
            except Exception:
                pass
            try:
                notif_svc = NotificationService(self.db)
                await notif_svc.notify_event(
                    company_id,
                    "sale.created",
                    context={
                        "order_number": order_values["order_number"],
                        "total_amount": f"{total_amount:,.2f}",
                        "branch_name": str(order_values["branch_id"]),
                    },
                    reference_type="SaleOrder",
                    reference_id=str(order_id),
                )
            except Exception:
                pass
        if quote is not None:
            PricingService.consume_quote(quote, order_id)
        await ensure_sale_completed_handoff(
            self.db,
            company_id=company_id,
            brand_id=brand_id,
            branch_id=branch_id,
            order_id=order_id,
            order_number=str(order_values["order_number"]),
            total_amount=total_amount,
            item_count=len(item_rows),
            payment_methods=[payment.payment_method for payment in payment_rows],
        )
        await self.db.commit()
        order = await self.get_sale(order_id, company_id)
        if data.customer_id and self.legacy_side_effects_enabled:
            try:
                crm_svc = CRMService(self.db)
                await crm_svc.earn_points(
                    company_id=company_id,
                    user_id=user_id,
                    data=EarnPointsRequest(
                        customer_id=data.customer_id,
                        sale_order_id=str(order.id),
                        spend_amount=order.total_amount,
                    ),
                )
                await self.db.commit()
            except Exception as e:
                logger.error(f"Points earn failed: {e}")
                await self.db.rollback()
        await self._ensure_accounting_handoff(order, company_id, user_id)
        return await self.get_sale(order_id, company_id)

    async def _ensure_accounting_handoff(
        self,
        order: SaleOrder,
        company_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> None:
        if not self.legacy_side_effects_enabled:
            return
        try:
            accounting_svc = AccountingService(self.db)
            await accounting_svc.post_sale(order, company_id, user_id)
            await self.db.commit()
        except Exception as exc:
            logger.error("Accounting post failed for %s: %s", order.order_number, exc)
            await self.db.rollback()

    async def _generate_order_number(self, company_id: uuid.UUID, date_str: str) -> str:
        lock_key = hash(str(company_id) + date_str + "SALE") % (2**31)
        await self.db.execute(text(f"SELECT pg_advisory_xact_lock({lock_key})"))
        count = (
            await self.db.scalar(
                select(func.count(SaleOrder.id)).where(
                    SaleOrder.company_id == company_id,
                    SaleOrder.order_number.like(f"SO{date_str}-%"),
                )
            )
        ) or 0
        return f"SO{date_str}-{int(count) + 1:04d}"

    async def void_sale(
        self,
        order_id: uuid.UUID,
        company_id: uuid.UUID,
        user_id: uuid.UUID,
        data: VoidRequest,
        approval_evidence: ApprovalEvidence | None = None,
    ) -> SaleOrder:
        order = await self.get_sale(order_id, company_id)
        if order.status != "completed":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Order cannot be voided")
        shift = await self.get_open_shift(company_id, user_id, order.branch_id)
        if shift is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Active shift required to void sale")
        unsafe_payment = next(
            (
                payment
                for payment in order.payments
                if Decimal(payment.amount) > 0
                and payment.settlement_state not in {"authorized", "pending"}
            ),
            None,
        )
        if unsafe_payment is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "settled_payment_requires_refund",
                    "message": "Settled or unknown payments cannot be voided; use the Refund workflow",
                    "payment_id": str(unsafe_payment.id),
                    "settlement_state": unsafe_payment.settlement_state,
                },
            )

        recipe_return_items: list[tuple[Product, Decimal]] = []
        for item in order.items:
            product = await self.db.get(Product, item.product_id)
            if product is not None and product.product_type in ("menu_item", "raw_material"):
                if product.product_type == "menu_item":
                    recipe_return_items.append((product, Decimal(item.qty)))
                continue
            balance = await self.stock_service._get_or_create_balance(
                company_id=company_id,
                branch_id=order.branch_id,
                location_id=order.location_id,
                product_id=item.product_id,
                variant_id=item.variant_id,
            )
            await self.stock_service._record_movement(
                balance=balance,
                movement_type="sale_return",
                qty_delta=Decimal(item.qty),
                user_id=user_id,
                cost_per_unit=Decimal(balance.cost_per_unit or 0),
                reference_type="SaleOrder",
                reference_id=str(order.id),
                note=data.void_reason,
            )

        if order.recipe_stock_posted_at is not None:
            brand_branch = await self._get_store_brand_context(order)
            if brand_branch is None:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Store stock mapping is missing")
            from app.services.store_inventory_service import StoreInventoryService

            await StoreInventoryService(self.db).reverse_items(
                order=order,
                company_id=company_id,
                brand_id=brand_branch.brand_id,
                branch_id=order.branch_id,
                location_id=order.location_id,
                user_id=user_id,
                items=recipe_return_items,
                reference_type="pos_sale_recipe_void",
                note=data.void_reason,
                mark_fully_reversed=True,
            )

        order.status = "voided"
        order.voided_at = datetime.now(timezone.utc)
        order.voided_by = user_id
        order.void_reason = data.void_reason
        order.shift.total_voids = int(order.shift.total_voids or 0) + 1
        order.shift.total_sales = q2(max(Decimal("0"), Decimal(order.shift.total_sales or 0) - Decimal(order.total_amount)))
        self.db.add(
            AuditLog(
                company_id=company_id,
                branch_id=order.branch_id,
                user_id=user_id,
                action="pos.sale.void",
                resource="SaleOrder",
                resource_id=str(order.id),
                old_value={
                    "status": "completed",
                    "total_amount": str(order.total_amount),
                },
                new_value={
                    "status": "voided",
                    "void_reason": data.void_reason,
                    "approval": (
                        approval_evidence.as_audit_value()
                        if approval_evidence is not None
                        else None
                    ),
                },
            )
        )
        if self.legacy_side_effects_enabled:
            try:
                crm_svc = CRMService(self.db)
                await crm_svc.void_earn(company_id, user_id, str(order.id))
            except Exception as e:
                logger.error(f"Points void failed: {e}")
        brand_context = await self._get_store_brand_context(order)
        await ensure_sale_state_changed_handoff(
            self.db,
            company_id=company_id,
            brand_id=brand_context.brand_id if brand_context is not None else None,
            branch_id=order.branch_id,
            order_id=order.id,
            order_number=order.order_number,
            source_status=order.status,
            total_amount=Decimal(order.total_amount),
            refund_amount=Decimal(order.refund_amount or 0),
        )
        await self.db.commit()
        return await self.get_sale(order.id, company_id)

    async def refund_sale(
        self,
        order_id: uuid.UUID,
        company_id: uuid.UUID,
        user_id: uuid.UUID,
        refund_reason: str,
        approval_evidence: ApprovalEvidence | None = None,
    ) -> SaleOrder:
        order = await self.get_sale(order_id, company_id)
        if order.status not in {"completed", "partially_refunded"}:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Order cannot be refunded")
        active_shift = await self.get_open_shift(company_id, user_id, order.branch_id)
        if active_shift is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Active shift required to refund sale")
        refundable_items = [
            (item, q4(Decimal(item.qty) - Decimal(item.refunded_qty or 0)))
            for item in order.items
            if q4(Decimal(item.qty) - Decimal(item.refunded_qty or 0)) > 0
        ]
        if not refundable_items:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Order has no refundable items left")
        refund_total = await self._apply_refund(
            order=order,
            company_id=company_id,
            user_id=user_id,
            active_shift=active_shift,
            refund_reason=refund_reason,
            refund_rows=refundable_items,
            audit_action="pos.sale.refund",
            approval_evidence=approval_evidence,
        )
        if (
            self.legacy_side_effects_enabled
            and q2(Decimal(order.refund_amount or 0))
            >= q2(Decimal(order.total_amount or 0))
        ):
            try:
                crm_svc = CRMService(self.db)
                await crm_svc.void_earn(company_id, user_id, str(order.id))
            except Exception as e:
                logger.error(f"Points refund failed: {e}")
        await self.db.commit()
        logger.info("Full refund processed for %s amount=%s", order.order_number, refund_total)
        return await self.get_sale(order.id, company_id)

    async def partial_refund_sale(
        self,
        order_id: uuid.UUID,
        company_id: uuid.UUID,
        user_id: uuid.UUID,
        payload: PartialRefundRequest,
        approval_evidence: ApprovalEvidence | None = None,
    ) -> SaleOrder:
        order = await self.get_sale(order_id, company_id)
        if order.status not in {"completed", "partially_refunded"}:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Order cannot be partially refunded")
        active_shift = await self.get_open_shift(company_id, user_id, order.branch_id)
        if active_shift is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Active shift required to refund sale")
        if not payload.items:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="At least one refund item is required")

        order_items = {item.id: item for item in order.items}
        refund_rows: list[tuple[SaleOrderItem, Decimal]] = []
        for entry in payload.items:
            item = order_items.get(entry.order_item_id)
            if item is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sale order item not found")
            qty = q4(Decimal(entry.qty))
            if qty <= 0:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Refund quantity must be positive")
            refundable_qty = q4(Decimal(item.qty) - Decimal(item.refunded_qty or 0))
            if qty > refundable_qty:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Refund quantity exceeds available balance")
            refund_rows.append((item, qty))

        await self._apply_refund(
            order=order,
            company_id=company_id,
            user_id=user_id,
            active_shift=active_shift,
            refund_reason=payload.refund_reason,
            refund_rows=refund_rows,
            audit_action="pos.sale.partial_refund",
            approval_evidence=approval_evidence,
        )
        await self.db.commit()
        return await self.get_sale(order.id, company_id)

    async def get_sale(self, order_id: uuid.UUID, company_id: uuid.UUID) -> SaleOrder:
        order = await self.db.scalar(
            select(SaleOrder)
            .where(SaleOrder.id == order_id, SaleOrder.company_id == company_id)
            .options(
                selectinload(SaleOrder.items),
                selectinload(SaleOrder.payments),
                selectinload(SaleOrder.shift),
            )
        )
        if order is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sale order not found")
        return order

    async def list_sales(
        self,
        company_id: uuid.UUID,
        shift_id: uuid.UUID | None = None,
        branch_id: uuid.UUID | None = None,
        status_value: str | None = None,
        page: int = 1,
        limit: int = 20,
    ) -> tuple[list[SaleOrder], int]:
        filters = [SaleOrder.company_id == company_id]
        if shift_id is not None:
            filters.append(SaleOrder.shift_id == shift_id)
        if branch_id is not None:
            filters.append(SaleOrder.branch_id == branch_id)
        if status_value is not None:
            filters.append(SaleOrder.status == status_value)

        total = await self.db.scalar(select(func.count(SaleOrder.id)).where(*filters)) or 0
        rows = await self.db.scalars(
            select(SaleOrder)
            .where(*filters)
            .options(selectinload(SaleOrder.items), selectinload(SaleOrder.payments))
            .order_by(SaleOrder.created_at.desc())
            .offset((page - 1) * limit)
            .limit(limit)
        )
        return rows.all(), int(total)

    async def sync_offline_sales(
        self,
        company_id: uuid.UUID,
        branch_id: uuid.UUID,
        user_id: uuid.UUID,
        orders: list[CreateSaleRequest],
    ) -> list[SaleOrder]:
        created: list[SaleOrder] = []
        for order in orders:
            existing = await self.get_existing_sale_by_client_order_id(company_id, branch_id, order.client_order_id)
            if existing is not None:
                created.append(
                    await self.ensure_existing_sale_handoffs(
                        existing,
                        company_id,
                        user_id,
                    )
                )
                continue
            created.append(await self.create_sale(company_id, branch_id, user_id, order))
        return created

    async def get_receipt_data(self, order_id: uuid.UUID, company_id: uuid.UUID) -> dict[str, str]:
        order = await self.get_sale(order_id, company_id)
        company = await self.db.get(Company, company_id)
        branch = await self.db.get(Branch, order.branch_id)
        cashier = await self.db.get(User, order.user_id)
        return {
            "company_name": company.name if company else "Restaurant POS",
            "branch_name": branch.name if branch else "-",
            "cashier_name": cashier.display_name or cashier.username if cashier else "-",
        }

    def _prepare_payments(self, data: CreateSaleRequest, total_amount: Decimal) -> list[PaymentCreateRequest]:
        if data.payments:
            rows = [item for item in data.payments if Decimal(item.amount) > 0]
            if not rows:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="At least one payment entry is required")
            return rows

        paid_amount = q2(Decimal(data.paid_amount))
        if data.payment_method != "cash" and paid_amount <= 0:
            paid_amount = q2(total_amount)
        return [
            PaymentCreateRequest(
                payment_method=data.payment_method,
                amount=paid_amount,
                reference_no=data.payment_reference,
            )
        ]

    async def _apply_refund(
        self,
        order: SaleOrder,
        company_id: uuid.UUID,
        user_id: uuid.UUID,
        active_shift: CashierShift,
        refund_reason: str,
        refund_rows: list[tuple[SaleOrderItem, Decimal]],
        audit_action: str,
        approval_evidence: ApprovalEvidence | None = None,
    ) -> Decimal:
        if not refund_reason.strip():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Refund reason is required")

        subtotal_refund = Decimal("0")
        excluded_vat_refund = Decimal("0")

        for item, qty in refund_rows:
            line_ratio = Decimal("0") if Decimal(item.qty) <= 0 else q4(qty / Decimal(item.qty))
            line_subtotal = q4(Decimal(item.subtotal) * line_ratio)
            subtotal_refund += line_subtotal
            if item.vat_type == "excluded":
                excluded_vat_refund += q2(Decimal(item.vat_amount) * line_ratio)

        order_subtotal = q4(Decimal(order.subtotal or 0))
        discount_share = Decimal("0")
        if order_subtotal > 0 and subtotal_refund > 0:
            discount_share = q2(Decimal(order.discount_amount or 0) * (subtotal_refund / order_subtotal))
        refund_total = q2(q2(subtotal_refund) - discount_share + excluded_vat_refund)
        remaining_refundable = q2(Decimal(order.total_amount or 0) - Decimal(order.refund_amount or 0))
        if refund_total <= 0:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Refund amount must be greater than zero")
        if refund_total > remaining_refundable:
            refund_total = remaining_refundable

        recipe_return_items: list[tuple[Product, Decimal]] = []
        for item, qty in refund_rows:
            product = await self.db.get(Product, item.product_id)
            if product is not None and product.product_type in ("menu_item", "raw_material"):
                if product.product_type == "menu_item":
                    recipe_return_items.append((product, qty))
                continue
            balance = await self.stock_service._get_or_create_balance(
                company_id=company_id,
                branch_id=order.branch_id,
                location_id=order.location_id,
                product_id=item.product_id,
                variant_id=item.variant_id,
            )
            await self.stock_service._record_movement(
                balance=balance,
                movement_type="sale_return",
                qty_delta=qty,
                user_id=user_id,
                cost_per_unit=Decimal(balance.cost_per_unit or 0),
                reference_type="SaleOrder",
                reference_id=str(order.id),
                note=refund_reason,
            )

        if order.recipe_stock_posted_at is not None and recipe_return_items:
            brand_branch = await self._get_store_brand_context(order)
            if brand_branch is None:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Store stock mapping is missing")
            from app.services.store_inventory_service import StoreInventoryService

            await StoreInventoryService(self.db).reverse_items(
                order=order,
                company_id=company_id,
                brand_id=brand_branch.brand_id,
                branch_id=order.branch_id,
                location_id=order.location_id,
                user_id=user_id,
                items=recipe_return_items,
                reference_type="pos_sale_recipe_refund",
                note=refund_reason,
            )

        refundable_allocations = self._allocate_refund_payments(order, refund_total)
        for item, qty in refund_rows:
            line_refund = self._calculate_item_refund_amount(order, item, qty)
            item.refunded_qty = q4(Decimal(item.refunded_qty or 0) + qty)
            item.refunded_amount = q2(Decimal(item.refunded_amount or 0) + line_refund)

        order.refund_amount = q2(Decimal(order.refund_amount or 0) + refund_total)
        order.refunded_at = datetime.now(timezone.utc)
        order.status = "refunded" if q2(Decimal(order.refund_amount or 0)) >= q2(Decimal(order.total_amount or 0)) else "partially_refunded"
        note_line = f"REFUND {datetime.now(BANGKOK).strftime('%d/%m/%Y %H:%M')} {refund_total:,.2f}: {refund_reason.strip()}"
        order.note = f"{order.note}\n{note_line}".strip() if order.note else note_line
        active_shift.total_sales = q2(max(Decimal("0"), Decimal(active_shift.total_sales or 0) - refund_total))

        for original_payment_id, payment_method, amount, reference_no in refundable_allocations:
            self.db.add(
                Payment(
                    order_id=order.id,
                    company_id=company_id,
                    payment_method=payment_method,
                    amount=-amount,
                    reference_no=reference_no,
                    original_payment_id=original_payment_id,
                    note=refund_reason.strip(),
                )
            )

        self.db.add(
            AuditLog(
                company_id=company_id,
                branch_id=order.branch_id,
                user_id=user_id,
                action=audit_action,
                resource="SaleOrder",
                resource_id=str(order.id),
                new_value={
                    "refund_reason": refund_reason.strip(),
                    "refund_amount": str(refund_total),
                    "original_payment_ids": [
                        str(payment_id)
                        for payment_id, _, _, _ in refundable_allocations
                    ],
                    "approval": (
                        approval_evidence.as_audit_value()
                        if approval_evidence is not None
                        else None
                    ),
                    "items": [
                        {
                            "order_item_id": str(item.id),
                            "product_name": item.product_name,
                            "qty": str(qty),
                        }
                        for item, qty in refund_rows
                    ],
                },
            )
        )
        brand_context = await self._get_store_brand_context(order)
        await ensure_sale_state_changed_handoff(
            self.db,
            company_id=company_id,
            brand_id=brand_context.brand_id if brand_context is not None else None,
            branch_id=order.branch_id,
            order_id=order.id,
            order_number=order.order_number,
            source_status=order.status,
            total_amount=Decimal(order.total_amount),
            refund_amount=Decimal(order.refund_amount or 0),
        )
        return refund_total

    def _calculate_item_refund_amount(self, order: SaleOrder, item: SaleOrderItem, qty: Decimal) -> Decimal:
        ratio = Decimal("0") if Decimal(item.qty) <= 0 else q4(qty / Decimal(item.qty))
        line_subtotal = q4(Decimal(item.subtotal) * ratio)
        order_discount_share = Decimal("0")
        if Decimal(order.subtotal or 0) > 0 and line_subtotal > 0:
            order_discount_share = q2(Decimal(order.discount_amount or 0) * (line_subtotal / Decimal(order.subtotal or 0)))
        excluded_vat = q2(Decimal(item.vat_amount) * ratio) if item.vat_type == "excluded" else Decimal("0")
        return q2(q2(line_subtotal) - order_discount_share + excluded_vat)

    def _allocate_refund_payments(
        self,
        order: SaleOrder,
        refund_total: Decimal,
    ) -> list[tuple[uuid.UUID, str, Decimal, str | None]]:
        positive_payments = [payment for payment in order.payments if Decimal(payment.amount) > 0]
        if not positive_payments:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Original payment data not found")

        total_paid = q2(sum((Decimal(payment.amount) for payment in positive_payments), Decimal("0")))
        remaining = q2(refund_total)
        rows: list[tuple[uuid.UUID, str, Decimal, str | None]] = []
        for index, payment in enumerate(positive_payments):
            if index == len(positive_payments) - 1:
                amount = remaining
            else:
                amount = q2(refund_total * (Decimal(payment.amount) / total_paid))
                remaining = q2(remaining - amount)
            if amount > 0:
                rows.append(
                    (
                        payment.id,
                        payment.payment_method,
                        amount,
                        payment.reference_no,
                    )
                )
        return rows

    async def _get_shift_for_sale(
        self,
        company_id: uuid.UUID,
        branch_id: uuid.UUID,
        user_id: uuid.UUID,
        shift_id: uuid.UUID,
    ) -> CashierShift:
        shift = await self.db.scalar(
            select(CashierShift).where(
                CashierShift.id == shift_id,
                CashierShift.company_id == company_id,
                CashierShift.branch_id == branch_id,
                CashierShift.user_id == user_id,
            )
        )
        if shift is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shift not found")
        if shift.status != "open":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Shift is not open")
        return shift

    async def _get_location(self, company_id: uuid.UUID, location_id: uuid.UUID) -> StockLocation:
        location = await self.db.scalar(
            select(StockLocation).where(
                StockLocation.id == location_id,
                StockLocation.company_id == company_id,
                StockLocation.deleted_at.is_(None),
                StockLocation.is_active.is_(True),
            )
        )
        if location is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Location not found")
        return location

    async def _get_product_snapshot(
        self,
        company_id: uuid.UUID,
        product_id: uuid.UUID,
        variant_id: uuid.UUID | None,
    ) -> tuple[Product, ProductVariant | None]:
        product = await self.db.scalar(
            select(Product)
            .where(
                Product.id == product_id,
                Product.company_id == company_id,
                Product.deleted_at.is_(None),
                Product.is_active.is_(True),
            )
            .options(selectinload(Product.unit))
        )
        if product is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
        variant = None
        if variant_id is not None:
            variant = await self.db.scalar(
                select(ProductVariant).where(
                    ProductVariant.id == variant_id,
                    ProductVariant.product_id == product_id,
                    ProductVariant.company_id == company_id,
                    ProductVariant.deleted_at.is_(None),
                    ProductVariant.is_active.is_(True),
                )
            )
            if variant is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Variant not found")
        return product, variant

    async def _ensure_stock_available(
        self,
        company_id: uuid.UUID,
        branch_id: uuid.UUID,
        location_id: uuid.UUID,
        stock_needs: dict[tuple[uuid.UUID, uuid.UUID | None], Decimal],
    ) -> None:
        for (product_id, variant_id), needed in stock_needs.items():
            # skip stock check for menu_item and raw_material — tracked via recipes
            product_type_row = await self.db.scalar(
                select(Product.product_type).where(Product.id == product_id)
            )
            if product_type_row in ("menu_item", "raw_material"):
                continue

            balance = await self.db.scalar(
                select(StockBalance).where(
                    StockBalance.company_id == company_id,
                    StockBalance.branch_id == branch_id,
                    StockBalance.location_id == location_id,
                    StockBalance.product_id == product_id,
                    StockBalance.variant_id.is_(None) if variant_id is None else StockBalance.variant_id == variant_id,
                )
            )
            available = Decimal(balance.qty_available if balance is not None else 0)
            if available < needed:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Insufficient stock for one or more items",
                )

    async def _get_store_brand_context(self, order: SaleOrder) -> BrandBranch | None:
        return await self.db.scalar(
            select(BrandBranch).where(
                BrandBranch.company_id == order.company_id,
                BrandBranch.branch_id == order.branch_id,
                BrandBranch.store_location_id == order.location_id,
            ).limit(1)
        )

    def _apply_discount(self, base_price: Decimal, discount_amount: Decimal, discount_type: str) -> Decimal:
        return _discounted_value(base_price, discount_amount, discount_type)

    def _calc_vat(self, subtotal: Decimal, vat_type: str, vat_rate: Decimal) -> Decimal:
        if vat_type == "excluded":
            return q4(subtotal * vat_rate / Decimal("100"))
        if vat_type == "included":
            return q4(subtotal * vat_rate / (Decimal("100") + vat_rate))
        return Decimal("0.0000")
