from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_DOWN, ROUND_HALF_UP
import hashlib
import hmac
import json
import uuid
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.models.crm import Customer, PointsTransaction
from app.models.etax import TaxDocument, TaxDocumentItem
from app.models.pos import CashierShift, Payment, SaleOrder, SaleOrderItem
from app.models.product import Product
from app.models.refund import (
    ProviderRefundAttempt,
    ProviderRefundEvent,
    RefundOperation,
    RefundOperationAudit,
    RefundOperationItem,
    RefundPaymentLeg,
    RefundQuote,
    RefundTaxLink,
)
from app.schemas.pos import (
    RefundExecuteRequest,
    RefundOperationActionRequest,
    RefundProviderWebhookRequest,
    RefundQuoteCreateRequest,
)
from app.services.approval_service import ApprovalEvidence
from app.services.etax_service import ETaxService
from app.services.operational_handoff_service import ensure_sale_state_changed_handoff
from app.services.pricing_service import canonical_hash
from app.services.stock_service import StockService


TWOPLACES = Decimal("0.01")
FOURPLACES = Decimal("0.0001")
REFUND_QUOTE_TTL_SECONDS = 300
REFUND_POLICY_VERSION = "wp46-refund-v1"
FINAL_OPERATION_STATES = {"completed", "failed"}
BLOCKING_SHIFT_STATES = {
    "requested", "processing", "cash_due", "unknown", "needs_reconciliation", "tax_pending"
}


def q2(value: Decimal | str | int | float) -> Decimal:
    return Decimal(value).quantize(TWOPLACES, rounding=ROUND_HALF_UP)


def q4(value: Decimal | str | int | float) -> Decimal:
    return Decimal(value).quantize(FOURPLACES, rounding=ROUND_HALF_UP)


def refund_error(code: str, message: str, status_code: int = status.HTTP_409_CONFLICT, **extra: Any) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": message, **extra})


def provider_webhook_signature(payload: dict[str, Any], secret: str) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hmac.new(secret.encode("utf-8"), encoded, hashlib.sha256).hexdigest()


class SandboxRefundAdapter:
    """Deterministic, network-free adapter used only for UAT state-machine tests."""

    @staticmethod
    def result(scenario: str, attempt_no: int, *, inquiry: bool = False) -> str:
        if scenario == "succeeded":
            return "succeeded"
        if scenario == "failed":
            return "failed" if attempt_no <= 1 and not inquiry else "succeeded"
        if scenario == "processing_then_succeeded":
            return "succeeded" if inquiry else "processing"
        if scenario == "unknown_then_succeeded":
            return "succeeded" if inquiry else "unknown"
        if scenario == "unknown_persistent":
            return "unknown"
        raise refund_error("unsupported_provider_scenario", "Unsupported sandbox provider scenario", 400)


class RefundService:
    def __init__(self, db: AsyncSession, *, retail_cash_pilot: bool = False):
        self.db = db
        self.stock_service = StockService(db)
        self.retail_cash_pilot = retail_cash_pilot

    async def create_quote(
        self,
        *,
        company_id: uuid.UUID,
        branch_id: uuid.UUID,
        user_id: uuid.UUID,
        data: RefundQuoteCreateRequest,
    ) -> RefundQuote:
        request_hash = canonical_hash(data.model_dump(mode="json"))
        existing = await self.db.scalar(
            select(RefundQuote).where(
                RefundQuote.company_id == company_id,
                RefundQuote.branch_id == branch_id,
                RefundQuote.requester_id == user_id,
                RefundQuote.idempotency_key == data.idempotency_key,
            )
        )
        if existing is not None:
            if existing.request_hash != request_hash:
                raise refund_error("duplicate_request", "Idempotency key was used with another payload")
            return existing

        order = await self.db.scalar(
            select(SaleOrder)
            .where(
                SaleOrder.id == data.order_id,
                SaleOrder.company_id == company_id,
                SaleOrder.branch_id == branch_id,
            )
            .with_for_update()
        )
        if order is None:
            raise refund_error("sale_not_found", "Sale order not found", 404)
        if order.status not in {"completed", "partially_refunded"}:
            raise refund_error("sale_not_refundable", "Sale is not refundable")
        if data.currency.upper() != "THB":
            raise refund_error("currency_not_supported", "WP46 UAT supports THB refunds only", 400)

        shift = await self.db.scalar(
            select(CashierShift).where(
                CashierShift.id == data.shift_id,
                CashierShift.company_id == company_id,
                CashierShift.branch_id == branch_id,
                CashierShift.user_id == user_id,
                CashierShift.status == "open",
            )
        )
        if shift is None:
            raise refund_error("active_shift_required", "An open shift owned by the requester is required")

        order_items = list((await self.db.scalars(
            select(SaleOrderItem).where(SaleOrderItem.order_id == order.id).with_for_update()
        )).all())
        requested = {item.order_item_id: q4(item.qty) for item in data.items}
        if len(requested) != len(data.items):
            raise refund_error("duplicate_item", "Each sale item may be selected only once", 400)
        selected: list[tuple[SaleOrderItem, Decimal]] = []
        for item in order_items:
            remaining = q4(Decimal(item.qty) - Decimal(item.refunded_qty or 0))
            qty = requested.get(item.id, remaining if not data.items else Decimal("0"))
            if qty <= 0:
                continue
            if qty > remaining:
                raise refund_error("over_refund", "Requested quantity exceeds the refundable balance")
            selected.append((item, qty))
        if not selected or (data.items and len(selected) != len(data.items)):
            raise refund_error("refund_items_invalid", "No refundable items were selected", 400)

        if data.stock_disposition == "sellable":
            for item, _ in selected:
                product = await self.db.get(Product, item.product_id)
                if product is None or product.product_type not in {"simple", "variant", "raw_material"}:
                    raise refund_error(
                        "stock_disposition_unsupported",
                        "Sellable stock return is not supported for prepared food, bundles or services",
                    )

        if not self.retail_cash_pilot:
            redeemed = await self.db.scalar(
                select(PointsTransaction.id).where(
                    PointsTransaction.company_id == company_id,
                    PointsTransaction.reference_type == "SaleOrder",
                    PointsTransaction.reference_id == str(order.id),
                    PointsTransaction.transaction_type == "redeem",
                )
            )
            if redeemed is not None:
                raise refund_error(
                    "loyalty_restore_contract_required",
                    "This sale used redeemed points and requires manual review until reserve/restore is atomic",
                )

        items_snapshot: list[dict[str, Any]] = []
        subtotal = Decimal("0")
        discount = Decimal("0")
        vat = Decimal("0")
        total = Decimal("0")
        order_subtotal = Decimal(order.subtotal or 0)
        for item, qty in selected:
            ratio = Decimal("0") if Decimal(item.qty) <= 0 else q4(qty / Decimal(item.qty))
            line_base = q2(Decimal(item.subtotal) * ratio)
            line_discount = q2(Decimal(order.discount_amount or 0) * line_base / order_subtotal) if order_subtotal > 0 else Decimal("0")
            line_vat = q2(Decimal(item.vat_amount or 0) * ratio)
            line_total = q2(line_base - line_discount + (line_vat if item.vat_type == "excluded" else Decimal("0")))
            line_net = q2(line_total - line_vat) if item.vat_type in {"included", "excluded"} else line_total
            items_snapshot.append({
                "sale_order_item_id": str(item.id), "product_id": str(item.product_id),
                "variant_id": str(item.variant_id) if item.variant_id else None,
                "product_name": item.product_name, "quantity": str(qty),
                "subtotal_amount": str(line_net), "discount_amount": str(line_discount),
                "vat_amount": str(line_vat), "total_amount": str(line_total),
                "vat_type": item.vat_type, "vat_rate": str(item.vat_rate),
                "stock_disposition": data.stock_disposition,
            })
            subtotal += line_net
            discount += line_discount
            vat += line_vat
            total += line_total
        subtotal, discount, vat, total = map(q2, (subtotal, discount, vat, total))
        remaining_order = q2(Decimal(order.total_amount or 0) - Decimal(order.refund_amount or 0))
        if total <= 0 or total > remaining_order:
            raise refund_error("over_refund", "Quote exceeds the remaining refundable amount")

        payments = list((await self.db.scalars(
            select(Payment)
            .where(Payment.order_id == order.id, Payment.amount > 0)
            .order_by(Payment.paid_at.asc(), Payment.id.asc())
            .with_for_update()
        )).all())
        if not payments:
            raise refund_error("original_payment_missing", "Original payment data is missing")
        if self.retail_cash_pilot:
            unsupported = [payment for payment in payments if payment.payment_method != "cash"]
            if unsupported:
                raise refund_error(
                    "retail_provider_not_ready",
                    "Retail Pilot supports cash returns only; provider refunds remain disabled",
                )
            unsettled = [payment for payment in payments if payment.settlement_state != "settled"]
            if unsettled:
                raise refund_error(
                    "retail_payment_not_settled",
                    "Retail cash Return requires a settled original payment",
                )
        negative_rows = list((await self.db.scalars(
            select(Payment).where(Payment.order_id == order.id, Payment.amount < 0)
        )).all())
        used_by_payment: dict[uuid.UUID, Decimal] = {}
        for row in negative_rows:
            if row.original_payment_id:
                used_by_payment[row.original_payment_id] = q2(
                    used_by_payment.get(row.original_payment_id, Decimal("0")) + abs(Decimal(row.amount))
                )
        reserved = await self.db.execute(
            select(RefundPaymentLeg.original_payment_id, func.coalesce(func.sum(RefundPaymentLeg.amount), 0))
            .join(RefundOperation, RefundOperation.id == RefundPaymentLeg.operation_id)
            .where(
                RefundOperation.order_id == order.id,
                RefundOperation.status.in_(("requested", "processing", "cash_due", "unknown", "needs_reconciliation", "tax_pending")),
            )
            .group_by(RefundPaymentLeg.original_payment_id)
        )
        for payment_id, amount in reserved.all():
            used_by_payment[payment_id] = q2(used_by_payment.get(payment_id, Decimal("0")) + Decimal(amount))

        remaining_total = total
        allocations: list[dict[str, Any]] = []
        for payment in payments:
            available = q2(max(Decimal("0"), Decimal(payment.amount) - used_by_payment.get(payment.id, Decimal("0"))))
            amount = min(available, remaining_total)
            if amount <= 0:
                continue
            if payment.payment_method != "cash" and (
                payment.settlement_state not in {"captured", "settled"}
                or not payment.provider_payment_ref
            ):
                raise refund_error(
                    "provider_payment_link_unknown",
                    "Original provider payment is not safely linked or settled; manual review is required",
                )
            allocations.append({
                "original_payment_id": str(payment.id),
                "payment_method": payment.payment_method,
                "leg_type": "cash" if payment.payment_method == "cash" else "provider",
                "provider_name": payment.provider_name or (None if payment.payment_method == "cash" else payment.payment_method),
                "provider_payment_ref": payment.provider_payment_ref,
                "amount": str(q2(amount)), "currency": payment.currency or "THB",
            })
            remaining_total = q2(remaining_total - amount)
            if remaining_total <= 0:
                break
        if remaining_total > 0:
            raise refund_error("over_refund", "Original payments do not have enough refundable balance")

        totals = {
            "subtotal_amount": str(subtotal), "discount_amount": str(discount),
            "vat_amount": str(vat), "rounding_amount": "0.00", "total_amount": str(total),
            "remaining_refundable_before": str(remaining_order), "rounding_rule": "THB_HALF_UP_0.01",
        }
        policy = {
            "version": "wp57-retail-cash-v1" if self.retail_cash_pilot else REFUND_POLICY_VERSION,
            "maker_checker_required": True,
            "server_authoritative": True,
            "stock_disposition": data.stock_disposition,
            "credit_note": "not_available" if self.retail_cash_pilot else "uat_non_fiscal_only",
            "provider_refund": "disabled" if self.retail_cash_pilot else "sandbox_only",
            "loyalty": "not_available" if self.retail_cash_pilot else "reversed_when_applicable",
            "offline_allowed": False,
        }
        quote_payload = {
            "company_id": str(company_id), "branch_id": str(branch_id), "order_id": str(order.id),
            "order_version": order.row_version, "items": items_snapshot, "payments": allocations,
            "totals": totals, "policy": policy,
        }
        quote = RefundQuote(
            company_id=company_id, branch_id=branch_id, order_id=order.id, requester_id=user_id,
            shift_id=shift.id, currency="THB", order_version=order.row_version,
            idempotency_key=data.idempotency_key, request_hash=request_hash,
            quote_hash=canonical_hash(quote_payload), items_snapshot=items_snapshot,
            payment_snapshot=allocations, totals_snapshot=totals, policy_snapshot=policy,
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=REFUND_QUOTE_TTL_SECONDS),
        )
        self.db.add(quote)
        try:
            await self.db.commit()
        except IntegrityError as exc:
            await self.db.rollback()
            raise refund_error("duplicate_request", "Refund quote conflicts with another request") from exc
        await self.db.refresh(quote)
        return quote

    async def execute(
        self,
        *,
        company_id: uuid.UUID,
        branch_id: uuid.UUID,
        user_id: uuid.UUID,
        data: RefundExecuteRequest,
        approval: ApprovalEvidence,
    ) -> RefundOperation:
        request_hash = canonical_hash(data.model_dump(mode="json", exclude={"approval_token"}))
        existing = await self.db.scalar(select(RefundOperation).where(
            RefundOperation.company_id == company_id, RefundOperation.branch_id == branch_id,
            RefundOperation.requester_id == user_id, RefundOperation.idempotency_key == data.idempotency_key,
        ))
        if existing is not None:
            if existing.request_hash != request_hash:
                raise refund_error("duplicate_request", "Idempotency key was used with another payload")
            return await self.get_operation(existing.id, company_id, branch_id)
        if approval.requester_id != user_id or approval.approver_id == user_id:
            raise refund_error("maker_checker_required", "Refund requester and approver must be different", 403)

        quote = await self.db.scalar(select(RefundQuote).where(
            RefundQuote.id == data.quote_id, RefundQuote.company_id == company_id,
            RefundQuote.branch_id == branch_id, RefundQuote.requester_id == user_id,
        ).with_for_update())
        now = datetime.now(timezone.utc)
        if quote is None:
            raise refund_error("quote_not_found", "Refund quote not found", 404)
        if quote.status != "active" or quote.expires_at <= now:
            raise refund_error("stale_quote", "Refund quote expired or was already consumed")
        if quote.quote_hash != data.quote_hash or quote.order_id != data.order_id:
            raise refund_error("quote_mismatch", "Refund quote does not match this request")
        if quote.order_version != data.expected_order_version:
            raise refund_error("version_conflict", "Sale changed after the refund quote")
        if q2(data.total_amount) != q2(quote.totals_snapshot["total_amount"]):
            raise refund_error("quote_mismatch", "Refund total differs from the Server quote")
        if data.stock_disposition != quote.policy_snapshot["stock_disposition"]:
            raise refund_error("quote_mismatch", "Stock disposition differs from the Server quote")

        order = await self.db.scalar(select(SaleOrder).where(
            SaleOrder.id == quote.order_id, SaleOrder.company_id == company_id,
            SaleOrder.branch_id == branch_id,
        ).with_for_update())
        if order is None or order.row_version != quote.order_version:
            raise refund_error("version_conflict", "Sale changed after the refund quote")
        if self.retail_cash_pilot and any(row["leg_type"] != "cash" for row in quote.payment_snapshot):
            raise refund_error(
                "retail_provider_not_ready",
                "Retail Pilot supports cash returns only; provider refunds remain disabled",
            )
        if any(row["leg_type"] == "provider" for row in quote.payment_snapshot):
            if settings.refund_provider_mode != "sandbox":
                raise refund_error("provider_disabled", "Refund provider adapter is disabled")

        # Reserve the sale version while this operation is pending.  A refund may
        # remain in cash_due/processing/unknown for minutes, so waiting until
        # financial finalization to advance the version would allow two quotes
        # based on the same refundable balance to execute concurrently.
        order.row_version += 1

        totals = quote.totals_snapshot
        operation = RefundOperation(
            company_id=company_id, branch_id=branch_id, order_id=order.id, quote_id=quote.id,
            shift_id=quote.shift_id, requester_id=user_id, approver_id=approval.approver_id,
            approval_grant_id=approval.grant_id, status="requested", reason_code=data.reason_code,
            reason_note=data.reason_note, currency=quote.currency,
            subtotal_amount=q2(totals["subtotal_amount"]), discount_amount=q2(totals["discount_amount"]),
            vat_amount=q2(totals["vat_amount"]), rounding_amount=q2(totals["rounding_amount"]),
            total_amount=q2(totals["total_amount"]), stock_disposition=data.stock_disposition,
            provider_scenario=data.provider_scenario, approval_snapshot=approval.as_audit_value(),
            idempotency_key=data.idempotency_key, request_hash=request_hash,
        )
        self.db.add(operation)
        try:
            await self.db.flush()
        except IntegrityError as exc:
            await self.db.rollback()
            raise refund_error("quote_consumed", "Another refund request already consumed this quote") from exc
        for row in quote.items_snapshot:
            self.db.add(RefundOperationItem(
                operation_id=operation.id, sale_order_item_id=uuid.UUID(row["sale_order_item_id"]),
                product_id=uuid.UUID(row["product_id"]), variant_id=uuid.UUID(row["variant_id"]) if row["variant_id"] else None,
                product_name=row["product_name"], quantity=q4(row["quantity"]), subtotal_amount=q2(row["subtotal_amount"]),
                discount_amount=q2(row["discount_amount"]), vat_amount=q2(row["vat_amount"]), total_amount=q2(row["total_amount"]),
                vat_type=row["vat_type"], vat_rate=q2(row["vat_rate"]), stock_disposition=row["stock_disposition"],
            ))
        for row in quote.payment_snapshot:
            leg = RefundPaymentLeg(
                operation_id=operation.id, original_payment_id=uuid.UUID(row["original_payment_id"]),
                payment_method=row["payment_method"], leg_type=row["leg_type"], provider_name=row["provider_name"],
                provider_payment_ref=row["provider_payment_ref"], amount=q2(row["amount"]), currency=row["currency"],
                status="cash_due" if row["leg_type"] == "cash" else "requested",
            )
            self.db.add(leg)
            await self.db.flush()
            if leg.leg_type == "provider":
                await self._call_provider(leg, operation, kind="request", inquiry=False)
        quote.status = "consumed"
        quote.consumed_at = now
        await self._derive_and_finalize(operation, user_id, audit_key=f"execute:{data.idempotency_key}")
        await self.db.commit()
        return await self.get_operation(operation.id, company_id, branch_id)

    async def find_execute_replay(
        self,
        *,
        company_id: uuid.UUID,
        branch_id: uuid.UUID,
        user_id: uuid.UUID,
        data: RefundExecuteRequest,
    ) -> RefundOperation | None:
        existing = await self.db.scalar(select(RefundOperation).where(
            RefundOperation.company_id == company_id,
            RefundOperation.branch_id == branch_id,
            RefundOperation.requester_id == user_id,
            RefundOperation.idempotency_key == data.idempotency_key,
        ))
        if existing is None:
            return None
        request_hash = canonical_hash(data.model_dump(mode="json", exclude={"approval_token"}))
        if existing.request_hash != request_hash:
            raise refund_error("duplicate_request", "Idempotency key was used with another payload")
        return await self.get_operation(existing.id, company_id, branch_id)

    async def confirm_cash(self, operation_id: uuid.UUID, company_id: uuid.UUID, branch_id: uuid.UUID, user_id: uuid.UUID, data: RefundOperationActionRequest) -> RefundOperation:
        operation = await self._locked_operation(operation_id, company_id, branch_id)
        if await self._action_replayed(operation, "cash", data):
            return await self.get_operation(operation.id, company_id, branch_id)
        self._require_version(operation, data.expected_version)
        if operation.status == "completed":
            return await self.get_operation(operation.id, company_id, branch_id)
        legs = await self._load_legs(operation.id, lock=True)
        cash_legs = [leg for leg in legs if leg.leg_type == "cash"]
        if not cash_legs or any(leg.status not in {"cash_due", "succeeded"} for leg in cash_legs):
            raise refund_error("cash_not_due", "Cash refund is not ready for confirmation")
        if any(leg.leg_type == "provider" and leg.status != "succeeded" for leg in legs):
            raise refund_error("provider_not_succeeded", "Provider refund must succeed before cash is released")
        for leg in cash_legs:
            if leg.status != "succeeded":
                leg.status = "succeeded"
                leg.succeeded_at = datetime.now(timezone.utc)
        await self._derive_and_finalize(
            operation, user_id, audit_key=f"cash:{data.idempotency_key}",
            action_request_hash=canonical_hash(data.model_dump(mode="json")),
        )
        await self.db.commit()
        return await self.get_operation(operation.id, company_id, branch_id)

    async def inquire(self, operation_id: uuid.UUID, company_id: uuid.UUID, branch_id: uuid.UUID, user_id: uuid.UUID, data: RefundOperationActionRequest) -> RefundOperation:
        operation = await self._locked_operation(operation_id, company_id, branch_id)
        if await self._action_replayed(operation, "inquiry", data):
            return await self.get_operation(operation.id, company_id, branch_id)
        self._require_version(operation, data.expected_version)
        legs = await self._load_legs(operation.id, lock=True)
        queryable = [leg for leg in legs if leg.leg_type == "provider" and leg.status in {"processing", "unknown"}]
        if not queryable:
            raise refund_error("inquiry_not_available", "No provider leg is processing or unknown")
        for leg in queryable:
            await self._call_provider(leg, operation, kind="inquiry", inquiry=True)
        await self._derive_and_finalize(
            operation, user_id, audit_key=f"inquiry:{data.idempotency_key}",
            action_request_hash=canonical_hash(data.model_dump(mode="json")),
        )
        await self.db.commit()
        return await self.get_operation(operation.id, company_id, branch_id)

    async def retry(self, operation_id: uuid.UUID, company_id: uuid.UUID, branch_id: uuid.UUID, user_id: uuid.UUID, data: RefundOperationActionRequest) -> RefundOperation:
        operation = await self._locked_operation(operation_id, company_id, branch_id)
        if await self._action_replayed(operation, "retry", data):
            return await self.get_operation(operation.id, company_id, branch_id)
        self._require_version(operation, data.expected_version)
        legs = await self._load_legs(operation.id, lock=True)
        if any(leg.status == "unknown" for leg in legs):
            raise refund_error("inquiry_required", "Unknown provider results must be inquired before retry")
        retryable = [leg for leg in legs if leg.leg_type == "provider" and leg.status == "failed"]
        if not retryable or any(leg.status == "succeeded" for leg in legs):
            raise refund_error("retry_not_safe", "Retry is unavailable after a partial provider success")
        for leg in retryable:
            await self._call_provider(leg, operation, kind="retry", inquiry=False)
        await self._derive_and_finalize(
            operation, user_id, audit_key=f"retry:{data.idempotency_key}",
            action_request_hash=canonical_hash(data.model_dump(mode="json")),
        )
        await self.db.commit()
        return await self.get_operation(operation.id, company_id, branch_id)

    async def retry_tax(self, operation_id: uuid.UUID, company_id: uuid.UUID, branch_id: uuid.UUID, user_id: uuid.UUID, data: RefundOperationActionRequest) -> RefundOperation:
        operation = await self._locked_operation(operation_id, company_id, branch_id)
        if await self._action_replayed(operation, "tax-retry", data):
            return await self.get_operation(operation.id, company_id, branch_id)
        self._require_version(operation, data.expected_version)
        if operation.finalized_at is None or operation.status != "tax_pending":
            raise refund_error("tax_retry_not_available", "Credit Note retry is available only for a finalized refund with pending tax")
        link = await self.db.scalar(select(RefundTaxLink).where(RefundTaxLink.operation_id == operation.id).with_for_update())
        if link is None or link.original_document_id is None:
            raise refund_error("tax_retry_not_available", "Original tax document link is missing")
        link.retry_count += 1
        link.status = "pending"
        link.last_error = None
        order = await self.db.get(SaleOrder, operation.order_id)
        items = list((await self.db.scalars(select(RefundOperationItem).where(RefundOperationItem.operation_id == operation.id))).all())
        if order is None:
            raise refund_error("sale_not_found", "Sale order not found", 404)
        old = operation.status
        await self._create_credit_note(operation, order, user_id, items)
        operation.row_version += 1
        self.db.add(RefundOperationAudit(
            operation_id=operation.id, company_id=operation.company_id, branch_id=operation.branch_id,
            actor_user_id=user_id, action="tax-retry", from_state=old, to_state=operation.status,
            idempotency_key=f"tax-retry:{data.idempotency_key}",
            evidence={"request_hash": canonical_hash(data.model_dump(mode="json")), "retry_count": link.retry_count},
        ))
        await self.db.commit()
        return await self.get_operation(operation.id, company_id, branch_id)

    async def apply_webhook(self, data: RefundProviderWebhookRequest, signature: str | None) -> RefundOperation:
        secret = settings.refund_sandbox_webhook_secret or ""
        payload = data.model_dump(mode="json")
        expected = provider_webhook_signature(payload, secret) if secret else ""
        valid = bool(signature and expected and hmac.compare_digest(signature, expected))
        leg = await self.db.scalar(select(RefundPaymentLeg).where(RefundPaymentLeg.id == data.payment_leg_id).with_for_update())
        if leg is None:
            raise refund_error("refund_leg_not_found", "Refund payment leg not found", 404)
        operation = await self._locked_operation_by_id(leg.operation_id)
        existing = await self.db.scalar(select(ProviderRefundEvent).where(
            ProviderRefundEvent.provider_name == (leg.provider_name or "sandbox"),
            ProviderRefundEvent.provider_event_id == data.provider_event_id,
        ))
        if existing is not None:
            if existing.payment_leg_id != leg.id or existing.payload_hash != canonical_hash(payload):
                raise refund_error(
                    "provider_event_conflict",
                    "Provider event id was replayed with a different refund payload",
                )
            return await self.get_operation(operation.id, operation.company_id, operation.branch_id)
        applied = valid and data.sequence > leg.last_event_sequence
        ignored_reason = None if applied else ("invalid_signature" if not valid else "out_of_order")
        self.db.add(ProviderRefundEvent(
            payment_leg_id=leg.id, provider_name=leg.provider_name or "sandbox",
            provider_event_id=data.provider_event_id, event_sequence=data.sequence,
            event_type=f"refund.{data.state}", signature_valid=valid,
            payload_hash=canonical_hash(payload), payload_snapshot=payload,
            applied=applied, ignored_reason=ignored_reason,
        ))
        if not valid:
            await self.db.commit()
            raise refund_error("invalid_webhook_signature", "Webhook signature is invalid", 401)
        if applied:
            leg.last_event_sequence = data.sequence
            leg.status = data.state
            leg.provider_refund_ref = data.provider_refund_ref or leg.provider_refund_ref
            leg.last_error_code = data.error_code
            if data.state == "succeeded":
                leg.succeeded_at = datetime.now(timezone.utc)
            await self._derive_and_finalize(operation, None, audit_key=f"webhook:{data.provider_event_id}")
        await self.db.commit()
        return await self.get_operation(operation.id, operation.company_id, operation.branch_id)

    async def get_operation(self, operation_id: uuid.UUID, company_id: uuid.UUID, branch_id: uuid.UUID) -> RefundOperation:
        operation = await self.db.scalar(
            select(RefundOperation)
            .where(RefundOperation.id == operation_id, RefundOperation.company_id == company_id, RefundOperation.branch_id == branch_id)
            .options(selectinload(RefundOperation.items), selectinload(RefundOperation.payment_legs))
        )
        if operation is None:
            raise refund_error("refund_not_found", "Refund operation not found", 404)
        return operation

    async def list_operations(self, company_id: uuid.UUID, branch_id: uuid.UUID, order_id: uuid.UUID | None = None) -> list[RefundOperation]:
        query = select(RefundOperation).where(RefundOperation.company_id == company_id, RefundOperation.branch_id == branch_id)
        if order_id:
            query = query.where(RefundOperation.order_id == order_id)
        rows = await self.db.scalars(query.options(selectinload(RefundOperation.items), selectinload(RefundOperation.payment_legs)).order_by(RefundOperation.created_at.desc()).limit(100))
        return list(rows.all())

    async def tax_link(self, operation_id: uuid.UUID) -> RefundTaxLink | None:
        return await self.db.scalar(select(RefundTaxLink).where(RefundTaxLink.operation_id == operation_id))

    async def _call_provider(self, leg: RefundPaymentLeg, operation: RefundOperation, *, kind: str, inquiry: bool) -> None:
        if settings.refund_provider_mode != "sandbox":
            raise refund_error("provider_disabled", "Refund provider adapter is disabled")
        attempt_no = leg.attempt_count + 1
        result = SandboxRefundAdapter.result(operation.provider_scenario, attempt_no, inquiry=inquiry)
        request_id = f"refund-{leg.id}-{kind}-{attempt_no}"
        provider_ref = leg.provider_refund_ref or f"uat-rf-{leg.id}"
        self.db.add(ProviderRefundAttempt(
            payment_leg_id=leg.id, attempt_no=attempt_no, operation_kind=kind, request_id=request_id,
            request_snapshot={"amount": str(leg.amount), "currency": leg.currency, "original_ref": leg.provider_payment_ref},
            response_snapshot={"state": result, "provider_refund_ref": provider_ref, "simulated": True},
            result_state=result,
        ))
        leg.attempt_count = attempt_no
        leg.status = result
        leg.provider_refund_ref = provider_ref
        leg.last_error_code = "sandbox_declined" if result == "failed" else None
        leg.last_error_message = "Deterministic sandbox decline" if result == "failed" else None
        if result == "succeeded":
            leg.succeeded_at = datetime.now(timezone.utc)

    async def _derive_and_finalize(
        self,
        operation: RefundOperation,
        actor_id: uuid.UUID | None,
        *,
        audit_key: str,
        action_request_hash: str | None = None,
    ) -> None:
        legs = await self._load_legs(operation.id, lock=True)
        states = {leg.status for leg in legs}
        old = operation.status
        if states == {"succeeded"}:
            await self._finalize(operation, actor_id or operation.requester_id)
        elif "unknown" in states:
            operation.status = "needs_reconciliation" if "succeeded" in states else "unknown"
        elif "failed" in states:
            operation.status = "needs_reconciliation" if "succeeded" in states else "failed"
        elif "processing" in states or "requested" in states:
            operation.status = "processing"
        elif "cash_due" in states:
            operation.status = "cash_due"
        operation.row_version += 1
        self.db.add(RefundOperationAudit(
            operation_id=operation.id, company_id=operation.company_id, branch_id=operation.branch_id,
            actor_user_id=actor_id, action=audit_key.split(":", 1)[0], from_state=old,
            to_state=operation.status, idempotency_key=audit_key,
            evidence={
                "payment_states": sorted(states), "provider_scenario": operation.provider_scenario,
                "simulated": not self.retail_cash_pilot, "request_hash": action_request_hash,
                "retail_cash_pilot": self.retail_cash_pilot,
            },
        ))

    async def _finalize(self, operation: RefundOperation, actor_id: uuid.UUID) -> None:
        if operation.finalized_at is not None:
            return
        order = await self.db.scalar(select(SaleOrder).where(
            SaleOrder.id == operation.order_id, SaleOrder.company_id == operation.company_id,
            SaleOrder.branch_id == operation.branch_id,
        ).with_for_update())
        if order is None or order.status not in {"completed", "partially_refunded"}:
            raise refund_error("sale_not_refundable", "Sale changed before refund finalization")
        items = list((await self.db.scalars(select(RefundOperationItem).where(
            RefundOperationItem.operation_id == operation.id
        ).with_for_update())).all())
        sale_items = {item.id: item for item in (await self.db.scalars(select(SaleOrderItem).where(
            SaleOrderItem.order_id == order.id
        ).with_for_update())).all()}
        for item in items:
            sale_item = sale_items.get(item.sale_order_item_id)
            if sale_item is None or q4(Decimal(sale_item.refunded_qty or 0) + Decimal(item.quantity)) > q4(sale_item.qty):
                raise refund_error("over_refund", "Refund quantity is no longer available")
        if q2(Decimal(order.refund_amount or 0) + Decimal(operation.total_amount)) > q2(order.total_amount):
            raise refund_error("over_refund", "Refund amount is no longer available")

        for item in items:
            sale_item = sale_items[item.sale_order_item_id]
            sale_item.refunded_qty = q4(Decimal(sale_item.refunded_qty or 0) + Decimal(item.quantity))
            sale_item.refunded_amount = q2(Decimal(sale_item.refunded_amount or 0) + Decimal(item.total_amount))
            if item.stock_disposition == "sellable":
                balance = await self.stock_service._get_or_create_balance(
                    company_id=operation.company_id, branch_id=operation.branch_id, location_id=order.location_id,
                    product_id=item.product_id, variant_id=item.variant_id,
                )
                movement = await self.stock_service._record_movement(
                    balance=balance, movement_type="sale_return", qty_delta=Decimal(item.quantity), user_id=actor_id,
                    cost_per_unit=Decimal(balance.cost_per_unit or 0), reference_type="RefundOperation",
                    reference_id=str(operation.id), note=operation.reason_note or operation.reason_code,
                )
                item.stock_movement_id = movement.id

        order.refund_amount = q2(Decimal(order.refund_amount or 0) + Decimal(operation.total_amount))
        order.refunded_at = datetime.now(timezone.utc)
        order.status = "refunded" if q2(order.refund_amount) >= q2(order.total_amount) else "partially_refunded"
        order.row_version += 1
        shift = await self.db.scalar(select(CashierShift).where(CashierShift.id == operation.shift_id).with_for_update())
        if shift is None or shift.status != "open":
            raise refund_error("active_shift_required", "Refund shift is no longer open")
        shift.total_sales = q2(max(Decimal("0"), Decimal(shift.total_sales or 0) - Decimal(operation.total_amount)))
        shift.version = int(shift.version or 1) + 1

        for leg in await self._load_legs(operation.id, lock=True):
            existing = await self.db.scalar(select(Payment.id).where(
                Payment.refund_operation_id == operation.id, Payment.original_payment_id == leg.original_payment_id,
            ))
            if existing is None:
                self.db.add(Payment(
                    order_id=order.id, company_id=operation.company_id, payment_method=leg.payment_method,
                    amount=-q2(leg.amount), reference_no=leg.provider_refund_ref,
                    original_payment_id=leg.original_payment_id, currency=leg.currency,
                    provider_name=leg.provider_name, provider_payment_ref=leg.provider_refund_ref,
                    settlement_state="refunded", refund_operation_id=operation.id,
                    provider_refund_state="succeeded", note=operation.reason_note or operation.reason_code,
                ))

        operation.finalized_at = datetime.now(timezone.utc)
        operation.status = "succeeded"
        if self.retail_cash_pilot:
            link = await self.db.scalar(
                select(RefundTaxLink).where(RefundTaxLink.operation_id == operation.id)
            )
            if link is None:
                self.db.add(
                    RefundTaxLink(
                        operation_id=operation.id,
                        status="not_required",
                        idempotency_key=f"retail-non-fiscal:{operation.id}",
                    )
                )
            operation.status = "completed"
            operation.tax_completed_at = datetime.now(timezone.utc)
            return

        await self._reverse_earned_points(operation, order, actor_id, items)
        await self._create_credit_note(operation, order, actor_id, items)
        brand_context = await self._brand_context(order)
        await ensure_sale_state_changed_handoff(
            self.db, company_id=operation.company_id,
            brand_id=brand_context, branch_id=operation.branch_id, order_id=order.id,
            order_number=order.order_number, source_status=order.status,
            total_amount=Decimal(order.total_amount), refund_amount=Decimal(order.refund_amount or 0),
        )

    async def _create_credit_note(self, operation: RefundOperation, order: SaleOrder, actor_id: uuid.UUID, items: list[RefundOperationItem]) -> None:
        original = await self.db.scalar(select(TaxDocument).where(
            TaxDocument.company_id == operation.company_id,
            TaxDocument.reference_type == "SaleOrder", TaxDocument.reference_id == str(order.id),
            TaxDocument.status == "issued",
            TaxDocument.document_type.in_(("full_tax_invoice", "abbreviated_tax_invoice")),
        ).order_by(TaxDocument.issue_datetime.asc()))
        link = await self.db.scalar(select(RefundTaxLink).where(RefundTaxLink.operation_id == operation.id))
        if link is None:
            link = RefundTaxLink(operation_id=operation.id, original_document_id=original.id if original else None,
                                 status="pending" if original else "not_required", idempotency_key=f"credit-note:{operation.id}")
            self.db.add(link)
            await self.db.flush()
        if original is None:
            operation.status = "completed"
            operation.tax_completed_at = datetime.now(timezone.utc)
            return
        if not settings.refund_uat_non_fiscal_credit_note_enabled:
            link.status = "failed"
            link.last_error = "UAT non-fiscal Credit Note feature is disabled"
            operation.status = "tax_pending"
            return
        existing = await self.db.scalar(select(TaxDocument).where(TaxDocument.source_refund_operation_id == operation.id))
        if existing is not None:
            link.credit_note_id = existing.id
            link.status = "issued"
            operation.status = "completed"
            operation.tax_completed_at = datetime.now(timezone.utc)
            return
        number = await ETaxService(self.db)._generate_document_number(operation.company_id, "UATCN")
        document = TaxDocument(
            company_id=operation.company_id, branch_id=operation.branch_id, document_number=number,
            document_type="credit_note", status="issued", reference_type="RefundOperation", reference_id=str(operation.id),
            seller_tax_id=original.seller_tax_id, seller_name=original.seller_name,
            seller_branch_code=original.seller_branch_code, seller_address=original.seller_address,
            buyer_tax_id=original.buyer_tax_id, buyer_name=original.buyer_name,
            buyer_branch_code=original.buyer_branch_code, buyer_address=original.buyer_address,
            subtotal=q2(operation.subtotal_amount), discount_amount=q2(operation.discount_amount),
            vat_rate=q2(original.vat_rate), vat_amount=q2(operation.vat_amount), total_amount=q2(operation.total_amount),
            issue_date=date.today(), issue_datetime=datetime.now(timezone.utc), original_document_id=original.id,
            reason=operation.reason_note or operation.reason_code, source_refund_operation_id=operation.id,
            is_synthetic=True, watermark="UAT NON-FISCAL", submission_status="not_submitted", created_by=actor_id,
        )
        self.db.add(document)
        await self.db.flush()
        for index, item in enumerate(items, 1):
            self.db.add(TaxDocumentItem(
                document_id=document.id, line_number=index, description=item.product_name, unit_code=None,
                qty=-Decimal(item.quantity), unit_price=q4(Decimal(item.total_amount) / Decimal(item.quantity)),
                discount_amount=q4(item.discount_amount), vat_type=item.vat_type, vat_rate=item.vat_rate,
                vat_amount=-q4(item.vat_amount), line_total=-q4(item.total_amount),
            ))
        link.credit_note_id = document.id
        link.status = "issued"
        operation.status = "completed"
        operation.tax_completed_at = datetime.now(timezone.utc)

    async def _reverse_earned_points(
        self,
        operation: RefundOperation,
        order: SaleOrder,
        actor_id: uuid.UUID,
        operation_items: list[RefundOperationItem],
    ) -> None:
        original = await self.db.scalar(select(PointsTransaction).where(
            PointsTransaction.company_id == operation.company_id,
            PointsTransaction.transaction_type == "earn", PointsTransaction.reference_type == "SaleOrder",
            PointsTransaction.reference_id == str(order.id),
        ).options(selectinload(PointsTransaction.customer)))
        if original is None:
            return
        existing = await self.db.scalar(select(PointsTransaction.id).where(
            PointsTransaction.company_id == operation.company_id,
            PointsTransaction.transaction_type == "refund_earn", PointsTransaction.reference_type == "RefundOperation",
            PointsTransaction.reference_id == str(operation.id),
        ))
        if existing is not None:
            return
        ratio = min(Decimal("1"), Decimal(operation.total_amount) / max(Decimal(order.total_amount), Decimal("0.01")))
        points = int((Decimal(max(original.points, 0)) * ratio).quantize(Decimal("1"), rounding=ROUND_DOWN))
        customer: Customer = original.customer
        customer.points_balance = max(int(customer.points_balance or 0) - points, 0)
        customer.lifetime_spend = q2(max(Decimal("0"), Decimal(customer.lifetime_spend or 0) - Decimal(operation.total_amount)))
        tx = PointsTransaction(
            company_id=operation.company_id, customer_id=customer.id, transaction_type="refund_earn",
            points=-points, balance_after=customer.points_balance, reference_type="RefundOperation",
            reference_id=str(operation.id), spend_amount=-q2(operation.total_amount),
            note="WP46 idempotent refund loyalty reversal", created_by=actor_id,
        )
        self.db.add(tx)
        await self.db.flush()
        for item in operation_items:
            item.loyalty_reversal_id = tx.id

    async def _brand_context(self, order: SaleOrder) -> uuid.UUID | None:
        from app.models.restaurant import BrandBranch
        row = await self.db.scalar(select(BrandBranch.brand_id).where(
            BrandBranch.company_id == order.company_id, BrandBranch.branch_id == order.branch_id,
            BrandBranch.is_active.is_(True),
        ).order_by(BrandBranch.created_at.asc()))
        return row

    async def _locked_operation(self, operation_id: uuid.UUID, company_id: uuid.UUID, branch_id: uuid.UUID) -> RefundOperation:
        operation = await self.db.scalar(select(RefundOperation).where(
            RefundOperation.id == operation_id, RefundOperation.company_id == company_id,
            RefundOperation.branch_id == branch_id,
        ).with_for_update())
        if operation is None:
            raise refund_error("refund_not_found", "Refund operation not found", 404)
        return operation

    async def _locked_operation_by_id(self, operation_id: uuid.UUID) -> RefundOperation:
        operation = await self.db.scalar(select(RefundOperation).where(RefundOperation.id == operation_id).with_for_update())
        if operation is None:
            raise refund_error("refund_not_found", "Refund operation not found", 404)
        return operation

    async def _load_legs(self, operation_id: uuid.UUID, *, lock: bool = False) -> list[RefundPaymentLeg]:
        query = select(RefundPaymentLeg).where(RefundPaymentLeg.operation_id == operation_id).order_by(RefundPaymentLeg.created_at.asc())
        if lock:
            query = query.with_for_update()
        return list((await self.db.scalars(query)).all())

    async def _action_replayed(
        self,
        operation: RefundOperation,
        action: str,
        data: RefundOperationActionRequest,
    ) -> bool:
        audit = await self.db.scalar(select(RefundOperationAudit).where(
            RefundOperationAudit.operation_id == operation.id,
            RefundOperationAudit.idempotency_key == f"{action}:{data.idempotency_key}",
        ))
        if audit is None:
            return False
        request_hash = canonical_hash(data.model_dump(mode="json"))
        if audit.evidence.get("request_hash") != request_hash:
            raise refund_error("duplicate_request", "Idempotency key was used with another payload")
        return True

    @staticmethod
    def _require_version(operation: RefundOperation, expected: int) -> None:
        if operation.row_version != expected:
            raise refund_error("version_conflict", "Refund operation changed; refresh before continuing")


def serialize_quote(quote: RefundQuote) -> dict[str, Any]:
    return {
        "id": quote.id, "order_id": quote.order_id, "shift_id": quote.shift_id,
        "status": quote.status, "currency": quote.currency, "order_version": quote.order_version,
        "quote_hash": quote.quote_hash, "items": quote.items_snapshot,
        "payment_allocations": quote.payment_snapshot, "totals": quote.totals_snapshot,
        "policy": quote.policy_snapshot, "expires_at": quote.expires_at,
    }


async def serialize_operation(service: RefundService, operation: RefundOperation) -> dict[str, Any]:
    link = await service.tax_link(operation.id)
    return {
        "id": operation.id, "order_id": operation.order_id, "quote_id": operation.quote_id,
        "shift_id": operation.shift_id, "status": operation.status, "reason_code": operation.reason_code,
        "reason_note": operation.reason_note, "currency": operation.currency,
        "subtotal_amount": operation.subtotal_amount, "discount_amount": operation.discount_amount,
        "vat_amount": operation.vat_amount, "rounding_amount": operation.rounding_amount,
        "total_amount": operation.total_amount, "stock_disposition": operation.stock_disposition,
        "provider_scenario": operation.provider_scenario, "row_version": operation.row_version,
        "failure_code": operation.failure_code, "failure_message": operation.failure_message,
        "finalized_at": operation.finalized_at, "tax_completed_at": operation.tax_completed_at,
        "created_at": operation.created_at,
        "items": [{
            "id": item.id, "sale_order_item_id": item.sale_order_item_id, "product_name": item.product_name,
            "quantity": item.quantity, "total_amount": item.total_amount,
            "vat_amount": item.vat_amount, "stock_disposition": item.stock_disposition,
        } for item in operation.items],
        "payment_legs": [{
            "id": leg.id, "original_payment_id": leg.original_payment_id,
            "payment_method": leg.payment_method, "leg_type": leg.leg_type,
            "provider_name": leg.provider_name, "amount": leg.amount, "currency": leg.currency,
            "status": leg.status, "provider_refund_ref": leg.provider_refund_ref,
            "attempt_count": leg.attempt_count, "last_error_code": leg.last_error_code,
        } for leg in operation.payment_legs],
        "tax": None if link is None else {
            "status": link.status, "original_document_id": link.original_document_id,
            "credit_note_id": link.credit_note_id, "retry_count": link.retry_count,
            "last_error": link.last_error,
        },
    }
