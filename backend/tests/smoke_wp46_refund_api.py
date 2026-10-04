from __future__ import annotations

import asyncio
from datetime import date
from decimal import Decimal
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import selectinload
from sqlalchemy.pool import NullPool

from app.config import settings
from app.main import app
from app.models.pos import Payment, SaleOrder
from app.models.etax import TaxDocument, TaxDocumentItem
from app.models.refund import ProviderRefundEvent, RefundOperation, RefundOperationAudit, RefundPaymentLeg, RefundTaxLink
from app.models.stock import StockBalance, StockMovement
from app.services.refund_service import provider_webhook_signature
from tests.smoke_approval_api import MANAGER_PIN, PASSWORD, expect, expect_detail_code, issue_approval, login, prepare
from tests.smoke_wp44_hold_drafts_api import expect_shift_blocker
from tests.smoke_wp43_pricing_api import pricing_payload, sale_payload


async def make_provider_payment(order_id: str) -> None:
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db:
        await db.execute(
            update(Payment)
            .where(Payment.order_id == uuid.UUID(order_id), Payment.amount > 0)
            .values(
                payment_method="promptpay",
                provider_name="sandbox_promptpay",
                provider_payment_ref=f"uat-pay-{order_id}",
                settlement_state="captured",
            )
        )
        await db.commit()
    await engine.dispose()


async def add_original_tax_document(order_id: str, user_id: str) -> str:
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db:
        order = await db.scalar(select(SaleOrder).where(SaleOrder.id == uuid.UUID(order_id)).options(selectinload(SaleOrder.items)))
        if order is None:
            raise RuntimeError("Tax smoke sale not found")
        document = TaxDocument(
            company_id=order.company_id, branch_id=order.branch_id,
            document_number=f"UAT-TINV-{uuid.uuid4().hex[:12]}", document_type="full_tax_invoice", status="issued",
            reference_type="SaleOrder", reference_id=str(order.id), seller_tax_id="0100000000000",
            seller_name="Foodchainservice UAT", seller_branch_code="00000", seller_address="UAT only",
            buyer_tax_id="0100000000001", buyer_name="Synthetic Buyer",
            subtotal=Decimal(order.total_amount) - Decimal(order.vat_amount), discount_amount=order.discount_amount,
            vat_rate=order.vat_rate, vat_amount=order.vat_amount, total_amount=order.total_amount,
            issue_date=date.today(), created_by=uuid.UUID(user_id),
        )
        db.add(document)
        await db.flush()
        for index, item in enumerate(order.items, 1):
            db.add(TaxDocumentItem(
                document_id=document.id, line_number=index, description=item.product_name,
                unit_code=item.unit_code, qty=item.qty, unit_price=item.unit_price,
                discount_amount=item.discount_amount, vat_type=item.vat_type, vat_rate=item.vat_rate,
                vat_amount=item.vat_amount, line_total=item.subtotal,
            ))
        await db.commit()
        result = str(document.id)
    await engine.dispose()
    return result


async def verify(context: dict[str, str], order_ids: list[str], operation_ids: list[str], initial_stock: Decimal) -> None:
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db:
        operation_uuids = [uuid.UUID(value) for value in operation_ids]
        orders = list((await db.scalars(select(SaleOrder).where(SaleOrder.id.in_([uuid.UUID(value) for value in order_ids])))).all())
        if len(orders) != len(order_ids) or any(order.status != "refunded" for order in orders):
            raise RuntimeError("Expected all WP46 smoke sales to finish refunded")
        negative_count = await db.scalar(select(func.count(Payment.id)).where(Payment.refund_operation_id.in_(operation_uuids), Payment.amount < 0))
        if negative_count != len(operation_ids):
            raise RuntimeError(f"Expected one negative ledger payment per operation, got {negative_count}")
        stock_returns = await db.scalar(select(func.count(StockMovement.id)).where(
            StockMovement.reference_type == "RefundOperation",
            StockMovement.reference_id.in_(operation_ids),
        ))
        if stock_returns:
            raise RuntimeError("stock_disposition=none unexpectedly returned stock")
        tax_links = list((await db.scalars(select(RefundTaxLink).where(RefundTaxLink.operation_id.in_(operation_uuids)))).all())
        if len(tax_links) != len(operation_ids):
            raise RuntimeError("Every completed refund must have one tax reconciliation link")
        statuses = sorted(row.status for row in tax_links)
        if statuses != ["issued", "not_required", "not_required", "not_required"]:
            raise RuntimeError(f"Unexpected tax reconciliation statuses: {statuses}")
        issued_link = next(row for row in tax_links if row.status == "issued")
        credit_note = await db.get(TaxDocument, issued_link.credit_note_id)
        if credit_note is None or not credit_note.is_synthetic or credit_note.watermark != "UAT NON-FISCAL" or credit_note.submission_status != "not_submitted":
            raise RuntimeError("UAT Credit Note is missing non-fiscal safeguards")
        events = list((await db.scalars(select(ProviderRefundEvent).where(
            ProviderRefundEvent.payment_leg_id.in_(
                select(RefundPaymentLeg.id).where(RefundPaymentLeg.operation_id.in_(operation_uuids))
            )
        ))).all())
        if len(events) != 2 or sum(1 for row in events if row.applied) != 1 or not any(row.ignored_reason == "out_of_order" for row in events):
            raise RuntimeError("Provider webhook duplicate/out-of-order evidence is incomplete")
        audits = list((await db.scalars(select(RefundOperationAudit).where(RefundOperationAudit.operation_id.in_(operation_uuids)))).all())
        if not audits:
            raise RuntimeError("Refund operation audit is missing")
        try:
            await db.execute(text("UPDATE refund_operation_audits SET action = 'tampered' WHERE id = :id"), {"id": audits[0].id})
            await db.commit()
        except Exception:
            await db.rollback()
        else:
            raise RuntimeError("Append-only refund audit accepted an UPDATE")
        try:
            await db.execute(
                text("UPDATE tax_documents SET watermark = 'tampered' WHERE id = :id"),
                {"id": credit_note.id},
            )
            await db.commit()
        except Exception:
            await db.rollback()
        else:
            raise RuntimeError("Synthetic refund Credit Note accepted an UPDATE")
        balance = await db.scalar(select(StockBalance).where(
            StockBalance.product_id == uuid.UUID(context["product_id"]),
            StockBalance.location_id == uuid.UUID(context["location_id"]),
        ))
        if balance is not None and Decimal(balance.qty_on_hand) >= initial_stock:
            raise RuntimeError("Sale stock issue was unexpectedly reversed for disposition none")
    await engine.dispose()


def run() -> None:
    context = asyncio.run(prepare())
    with TestClient(app) as client:
        cashier = login(client, context["cashier_username"])
        manager = login(client, context["manager_username"])
        expect(client.put("/api/v1/approvals/manager-pin", headers=manager, json={"current_password": PASSWORD, "pin": MANAGER_PIN}), 200)
        shift = expect(client.post("/api/v1/pos/shifts/open", headers=cashier, json={"location_id": context["location_id"], "opening_cash": 500}), 201)

        quote_price = expect(client.post("/api/v1/pos/pricing/calculate", headers=cashier, json=pricing_payload(context, f"wp46-price-{uuid.uuid4()}")), 200)
        sale = expect(client.post("/api/v1/pos/sales", headers=cashier, json=sale_payload(context, shift["id"], quote_price, f"wp46-sale-{uuid.uuid4()}")), 201)
        quote_request = {
            "order_id": sale["id"], "shift_id": shift["id"],
            "items": [{"order_item_id": sale["items"][0]["id"], "qty": "1"}],
            "reason_code": "customer_request", "reason_note": "WP46 cash refund",
            "stock_disposition": "none", "currency": "THB", "idempotency_key": f"wp46-quote-{uuid.uuid4()}",
        }
        refund_quote = expect(client.post("/api/v1/pos/refunds/quotes", headers=cashier, json=quote_request), 201)
        if Decimal(refund_quote["totals"]["total_amount"]) != Decimal(sale["total_amount"]):
            raise RuntimeError("Server refund quote does not match the original sale snapshot")
        execute_payload = {
            "quote_id": refund_quote["id"], "quote_hash": refund_quote["quote_hash"], "order_id": sale["id"],
            "expected_order_version": refund_quote["order_version"], "total_amount": refund_quote["totals"]["total_amount"],
            "reason_code": "customer_request", "reason_note": "WP46 cash refund", "stock_disposition": "none",
            "provider_scenario": "succeeded", "idempotency_key": f"wp46-execute-{uuid.uuid4()}",
        }
        expect_detail_code(client.post("/api/v1/pos/refunds", headers=cashier, json=execute_payload), 403, "approval_required")
        approval = expect(issue_approval(client, cashier, context, action="pos.refund.create", request_payload=execute_payload, reason="Approve WP46 cash refund"), 200)
        cash_operation = expect(client.post("/api/v1/pos/refunds", headers=cashier, json={**execute_payload, "approval_token": approval["approval_token"]}), 201)
        if cash_operation["status"] != "cash_due":
            raise RuntimeError(f"Expected cash_due, got {cash_operation['status']}")
        replay = expect(client.post("/api/v1/pos/refunds", headers=cashier, json={**execute_payload, "approval_token": approval["approval_token"]}), 201)
        if replay["id"] != cash_operation["id"]:
            raise RuntimeError("Refund execute replay created another operation")
        expect_shift_blocker(
            client.post(
                f"/api/v1/pos/shifts/{shift['id']}/close",
                headers=cashier,
                json={"closing_cash": 500},
            ),
            "refunds_pending",
        )
        cash_action = {"expected_version": cash_operation["row_version"], "idempotency_key": f"wp46-cash-{uuid.uuid4()}"}
        cash_done = expect(client.post(f"/api/v1/pos/refunds/{cash_operation['id']}/cash-confirm", headers=manager, json=cash_action), 200)
        if cash_done["status"] != "completed":
            raise RuntimeError(f"Cash refund did not complete: {cash_done['status']}")
        cash_replay = expect(client.post(f"/api/v1/pos/refunds/{cash_operation['id']}/cash-confirm", headers=manager, json=cash_action), 200)
        if cash_replay["id"] != cash_done["id"]:
            raise RuntimeError("Cash confirmation replay changed the operation")

        concurrent_price_payload = pricing_payload(context, f"wp46-concurrent-price-{uuid.uuid4()}")
        concurrent_price_payload["items"][0]["qty"] = 2
        concurrent_price = expect(client.post("/api/v1/pos/pricing/calculate", headers=cashier, json=concurrent_price_payload), 200)
        concurrent_sale_payload = sale_payload(context, shift["id"], concurrent_price, f"wp46-concurrent-sale-{uuid.uuid4()}")
        concurrent_sale_payload["items"][0]["qty"] = 2
        concurrent_sale = expect(client.post("/api/v1/pos/sales", headers=cashier, json=concurrent_sale_payload), 201)
        concurrent_base = {
            "order_id": concurrent_sale["id"], "shift_id": shift["id"],
            "reason_code": "customer_request", "reason_note": "WP46 concurrent reservation",
            "stock_disposition": "none", "currency": "THB",
        }
        first_pending_quote = expect(client.post("/api/v1/pos/refunds/quotes", headers=cashier, json={
            **concurrent_base,
            "items": [{"order_item_id": concurrent_sale["items"][0]["id"], "qty": "1"}],
            "idempotency_key": f"wp46-concurrent-quote-a-{uuid.uuid4()}",
        }), 201)
        stale_full_quote = expect(client.post("/api/v1/pos/refunds/quotes", headers=cashier, json={
            **concurrent_base,
            "items": [{"order_item_id": concurrent_sale["items"][0]["id"], "qty": "2"}],
            "idempotency_key": f"wp46-concurrent-quote-b-{uuid.uuid4()}",
        }), 201)
        first_pending_execute = {
            "quote_id": first_pending_quote["id"], "quote_hash": first_pending_quote["quote_hash"],
            "order_id": concurrent_sale["id"], "expected_order_version": first_pending_quote["order_version"],
            "total_amount": first_pending_quote["totals"]["total_amount"],
            "reason_code": "customer_request", "reason_note": "WP46 concurrent reservation",
            "stock_disposition": "none", "provider_scenario": "succeeded",
            "idempotency_key": f"wp46-concurrent-execute-a-{uuid.uuid4()}",
        }
        first_pending_approval = expect(issue_approval(
            client, cashier, context, action="pos.refund.create",
            request_payload=first_pending_execute, reason="Reserve the first partial refund",
        ), 200)
        first_pending_operation = expect(client.post("/api/v1/pos/refunds", headers=cashier, json={
            **first_pending_execute, "approval_token": first_pending_approval["approval_token"],
        }), 201)
        stale_full_execute = {
            **first_pending_execute,
            "quote_id": stale_full_quote["id"], "quote_hash": stale_full_quote["quote_hash"],
            "expected_order_version": stale_full_quote["order_version"],
            "total_amount": stale_full_quote["totals"]["total_amount"],
            "idempotency_key": f"wp46-concurrent-execute-b-{uuid.uuid4()}",
        }
        stale_full_approval = expect(issue_approval(
            client, cashier, context, action="pos.refund.create",
            request_payload=stale_full_execute, reason="Verify concurrent over-refund guard",
        ), 200)
        expect_detail_code(client.post("/api/v1/pos/refunds", headers=cashier, json={
            **stale_full_execute, "approval_token": stale_full_approval["approval_token"],
        }), 409, "version_conflict")
        expect(client.post(f"/api/v1/pos/refunds/{first_pending_operation['id']}/cash-confirm", headers=manager, json={
            "expected_version": first_pending_operation["row_version"],
            "idempotency_key": f"wp46-concurrent-cash-{uuid.uuid4()}",
        }), 200)

        provider_price = expect(client.post("/api/v1/pos/pricing/calculate", headers=cashier, json=pricing_payload(context, f"wp46-provider-price-{uuid.uuid4()}")), 200)
        provider_sale = expect(client.post("/api/v1/pos/sales", headers=cashier, json=sale_payload(context, shift["id"], provider_price, f"wp46-provider-sale-{uuid.uuid4()}")), 201)
        asyncio.run(make_provider_payment(provider_sale["id"]))
        provider_quote_request = {
            "order_id": provider_sale["id"], "shift_id": shift["id"],
            "items": [{"order_item_id": provider_sale["items"][0]["id"], "qty": "1"}],
            "reason_code": "payment_error", "reason_note": "WP46 provider unknown",
            "stock_disposition": "none", "currency": "THB", "idempotency_key": f"wp46-provider-quote-{uuid.uuid4()}",
        }
        provider_quote = expect(client.post("/api/v1/pos/refunds/quotes", headers=cashier, json=provider_quote_request), 201)
        provider_execute = {
            "quote_id": provider_quote["id"], "quote_hash": provider_quote["quote_hash"], "order_id": provider_sale["id"],
            "expected_order_version": provider_quote["order_version"], "total_amount": provider_quote["totals"]["total_amount"],
            "reason_code": "payment_error", "reason_note": "WP46 provider unknown", "stock_disposition": "none",
            "provider_scenario": "unknown_then_succeeded", "idempotency_key": f"wp46-provider-execute-{uuid.uuid4()}",
        }
        provider_approval = expect(issue_approval(client, cashier, context, action="pos.refund.create", request_payload=provider_execute, reason="Approve provider inquiry flow"), 200)
        provider_operation = expect(client.post("/api/v1/pos/refunds", headers=cashier, json={**provider_execute, "approval_token": provider_approval["approval_token"]}), 201)
        if provider_operation["status"] != "unknown":
            raise RuntimeError(f"Expected unknown provider result, got {provider_operation['status']}")
        before_inquiry = expect(client.get(f"/api/v1/pos/sales/{provider_sale['id']}", headers=cashier), 200)
        if before_inquiry["status"] != "completed" or any(Number < 0 for Number in [float(row["amount"]) for row in before_inquiry["payments"]]):
            raise RuntimeError("Unknown provider refund created a financial success side effect")
        inquiry_payload = {"expected_version": provider_operation["row_version"], "idempotency_key": f"wp46-inquiry-{uuid.uuid4()}"}
        provider_done = expect(client.post(f"/api/v1/pos/refunds/{provider_operation['id']}/inquire", headers=cashier, json=inquiry_payload), 200)
        if provider_done["status"] != "completed":
            raise RuntimeError(f"Provider inquiry did not reconcile: {provider_done['status']}")
        inquiry_replay = expect(client.post(f"/api/v1/pos/refunds/{provider_operation['id']}/inquire", headers=cashier, json=inquiry_payload), 200)
        if inquiry_replay["id"] != provider_done["id"]:
            raise RuntimeError("Inquiry replay created another result")

        tax_price = expect(client.post("/api/v1/pos/pricing/calculate", headers=cashier, json=pricing_payload(context, f"wp46-tax-price-{uuid.uuid4()}")), 200)
        tax_sale = expect(client.post("/api/v1/pos/sales", headers=cashier, json=sale_payload(context, shift["id"], tax_price, f"wp46-tax-sale-{uuid.uuid4()}")), 201)
        original_tax_id = asyncio.run(add_original_tax_document(tax_sale["id"], context["cashier_id"]))
        tax_quote_request = {
            "order_id": tax_sale["id"], "shift_id": shift["id"],
            "items": [{"order_item_id": tax_sale["items"][0]["id"], "qty": "1"}],
            "reason_code": "quality_issue", "reason_note": "WP46 synthetic Credit Note",
            "stock_disposition": "none", "currency": "THB", "idempotency_key": f"wp46-tax-quote-{uuid.uuid4()}",
        }
        tax_quote = expect(client.post("/api/v1/pos/refunds/quotes", headers=cashier, json=tax_quote_request), 201)
        tax_execute = {
            "quote_id": tax_quote["id"], "quote_hash": tax_quote["quote_hash"], "order_id": tax_sale["id"],
            "expected_order_version": tax_quote["order_version"], "total_amount": tax_quote["totals"]["total_amount"],
            "reason_code": "quality_issue", "reason_note": "WP46 synthetic Credit Note", "stock_disposition": "none",
            "provider_scenario": "succeeded", "idempotency_key": f"wp46-tax-execute-{uuid.uuid4()}",
        }
        tax_approval = expect(issue_approval(client, cashier, context, action="pos.refund.create", request_payload=tax_execute, reason="Approve UAT Credit Note flow"), 200)
        tax_operation = expect(client.post("/api/v1/pos/refunds", headers=cashier, json={**tax_execute, "approval_token": tax_approval["approval_token"]}), 201)
        tax_cash = {"expected_version": tax_operation["row_version"], "idempotency_key": f"wp46-tax-cash-{uuid.uuid4()}"}
        tax_done = expect(client.post(f"/api/v1/pos/refunds/{tax_operation['id']}/cash-confirm", headers=manager, json=tax_cash), 200)
        if tax_done["status"] != "completed" or tax_done["tax"]["status"] != "issued" or tax_done["tax"]["original_document_id"] != original_tax_id:
            raise RuntimeError(f"Synthetic UAT Credit Note did not reconcile: {tax_done}")

        webhook_price = expect(client.post("/api/v1/pos/pricing/calculate", headers=cashier, json=pricing_payload(context, f"wp46-webhook-price-{uuid.uuid4()}")), 200)
        webhook_sale = expect(client.post("/api/v1/pos/sales", headers=cashier, json=sale_payload(context, shift["id"], webhook_price, f"wp46-webhook-sale-{uuid.uuid4()}")), 201)
        asyncio.run(make_provider_payment(webhook_sale["id"]))
        webhook_quote = expect(client.post("/api/v1/pos/refunds/quotes", headers=cashier, json={
            "order_id": webhook_sale["id"], "shift_id": shift["id"],
            "items": [{"order_item_id": webhook_sale["items"][0]["id"], "qty": "1"}],
            "reason_code": "payment_error", "reason_note": "WP46 webhook ordering",
            "stock_disposition": "none", "currency": "THB", "idempotency_key": f"wp46-webhook-quote-{uuid.uuid4()}",
        }), 201)
        webhook_execute = {
            "quote_id": webhook_quote["id"], "quote_hash": webhook_quote["quote_hash"], "order_id": webhook_sale["id"],
            "expected_order_version": webhook_quote["order_version"], "total_amount": webhook_quote["totals"]["total_amount"],
            "reason_code": "payment_error", "reason_note": "WP46 webhook ordering", "stock_disposition": "none",
            "provider_scenario": "unknown_persistent", "idempotency_key": f"wp46-webhook-execute-{uuid.uuid4()}",
        }
        webhook_approval = expect(issue_approval(client, cashier, context, action="pos.refund.create", request_payload=webhook_execute, reason="Approve webhook ordering flow"), 200)
        webhook_operation = expect(client.post("/api/v1/pos/refunds", headers=cashier, json={**webhook_execute, "approval_token": webhook_approval["approval_token"]}), 201)
        leg_id = webhook_operation["payment_legs"][0]["id"]
        event_payload = {
            "provider_event_id": f"wp46-event-{uuid.uuid4()}", "payment_leg_id": leg_id,
            "sequence": 2, "state": "succeeded", "provider_refund_ref": f"uat-refund-{uuid.uuid4()}", "error_code": None,
        }
        sandbox_secret = settings.refund_sandbox_webhook_secret
        if not sandbox_secret:
            raise RuntimeError("WP46 smoke requires REFUND_SANDBOX_WEBHOOK_SECRET")
        signature = provider_webhook_signature(event_payload, sandbox_secret)
        webhook_done = expect(client.post("/api/v1/pos/refunds/provider/sandbox/webhook", json=event_payload, headers={"X-Refund-Signature": signature}), 200)
        if webhook_done["status"] != "completed":
            raise RuntimeError("Signed provider webhook did not finalize the refund")
        duplicate_webhook = expect(client.post("/api/v1/pos/refunds/provider/sandbox/webhook", json=event_payload, headers={"X-Refund-Signature": signature}), 200)
        if duplicate_webhook["id"] != webhook_done["id"]:
            raise RuntimeError("Duplicate provider webhook changed the operation")
        stale_event = {**event_payload, "provider_event_id": f"wp46-event-{uuid.uuid4()}", "sequence": 1, "state": "failed"}
        stale_signature = provider_webhook_signature(stale_event, sandbox_secret)
        stale_result = expect(client.post("/api/v1/pos/refunds/provider/sandbox/webhook", json=stale_event, headers={"X-Refund-Signature": stale_signature}), 200)
        if stale_result["status"] != "completed":
            raise RuntimeError("Out-of-order webhook regressed a completed refund")

        reconciliation = expect(client.get(f"/api/v1/pos/refunds/reconciliation?shift_id={shift['id']}", headers=cashier), 200)
        if reconciliation["pending_or_unknown"] != 0 or Decimal(reconciliation["cash_refund_succeeded"]) <= 0 or Decimal(reconciliation["provider_refund_succeeded"]) <= 0:
            raise RuntimeError(f"Refund reconciliation did not separate cash/provider correctly: {reconciliation}")

    asyncio.run(verify(
        context,
        [sale["id"], provider_sale["id"], tax_sale["id"], webhook_sale["id"]],
        [cash_done["id"], provider_done["id"], tax_done["id"], webhook_done["id"]],
        Decimal("100"),
    ))
    print("WP46 provider refund/tax smoke passed")


if __name__ == "__main__":
    run()
