from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from decimal import Decimal
import secrets
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import func, select, text, update

from app.config import settings
from app.database import (
    AsyncSessionLocal,
    PlatformSessionLocal,
    RetailSessionLocal,
    engine,
    platform_engine,
    restaurant_engine,
    retail_engine,
    takeaway_engine,
)
from app.main import app
from app.models.audit import AuditLog
from app.models.auth import RefreshToken
from app.models.pos import CashierShift, Payment, PosCashMovement, PosHoldDraft, PosHoldDraftAudit
from app.models.product import Product, Unit
from app.models.refund import RefundOperationAudit, RefundTaxLink
from app.models.restaurant import Brand, BrandBranch
from app.models.settings import BranchSettings
from app.models.staff_assignment import StaffRoleAssignment
from app.models.stock import StockBalance, StockLocation, StockMovement
from app.models.user import User, UserBranch
from app.services.retail_reference_projector import project_retail_reference_snapshot
from app.utils.create_superuser import DEFAULT_COMPANY_ID
from tests.smoke_approval_api import expect, expect_detail_code, issue_approval, prepare
from tests.smoke_wp43_pricing_api import pricing_payload, sale_payload


def _guard_uat() -> None:
    if (
        settings.environment != "development"
        or not settings.saas_public_base_url.startswith("https://uat-")
        or settings.identity_database != "platform_core"
        or settings.retail_service_database != "retail"
        or settings.uat_auth_bypass_enabled
    ):
        raise RuntimeError("WP57 smoke is restricted to isolated authenticated Retail UAT")


def _clone(model, row):
    return model(**{column.name: getattr(row, column.name) for column in model.__table__.columns})


def _detach_engines() -> None:
    for database_engine in {
        id(value): value
        for value in (engine, platform_engine, restaurant_engine, retail_engine, takeaway_engine)
        if value is not None
    }.values():
        database_engine.sync_engine.dispose(close=False)


async def _prepare_retail_fixture(context: dict[str, str]) -> None:
    brand_id = uuid.UUID(context["brand_id"])
    branch_id = uuid.UUID(context["branch_id"])
    user_ids = (uuid.UUID(context["cashier_id"]), uuid.UUID(context["manager_id"]))

    async with PlatformSessionLocal() as db:
        brand = await db.get(Brand, brand_id)
        link = await db.scalar(select(BrandBranch).where(BrandBranch.brand_id == brand_id))
        branches = list((await db.scalars(select(UserBranch).where(UserBranch.user_id.in_(user_ids)))).all())
        if brand is None or link is None or len(branches) != 2:
            raise RuntimeError("WP57 Platform fixture is incomplete")
        brand.business_type = "retail_pos"
        link.store_location_id = None
        for row in branches:
            row.business_type = "retail_pos"
            row.target_database = "retail_pos"
        await db.commit()

    await project_retail_reference_snapshot(
        company_id=DEFAULT_COMPANY_ID,
        brand_ids=(brand_id,),
    )

    async with AsyncSessionLocal() as source:
        location = await source.get(StockLocation, uuid.UUID(context["location_id"]))
        product = await source.get(Product, uuid.UUID(context["product_id"]))
        unit = await source.get(Unit, product.unit_id) if product is not None else None
        balance = await source.scalar(
            select(StockBalance).where(
                StockBalance.product_id == uuid.UUID(context["product_id"]),
                StockBalance.location_id == uuid.UUID(context["location_id"]),
            )
        )
        branch_settings = await source.scalar(
            select(BranchSettings).where(
                BranchSettings.company_id == DEFAULT_COMPANY_ID,
                BranchSettings.branch_id == branch_id,
            )
        )
        if any(row is None for row in (location, product, unit, balance, branch_settings)):
            raise RuntimeError("WP57 source fixture is incomplete")
        clones = (
            _clone(Unit, unit),
            _clone(StockLocation, location),
            _clone(Product, product),
            _clone(StockBalance, balance),
            _clone(BranchSettings, branch_settings),
        )

    if RetailSessionLocal is None:
        raise RuntimeError("Retail UAT database is not configured")
    async with RetailSessionLocal() as retail:
        retail.add_all(clones)
        await retail.commit()

    async with PlatformSessionLocal() as db:
        link = await db.scalar(select(BrandBranch).where(BrandBranch.brand_id == brand_id))
        assert link is not None
        link.store_location_id = uuid.UUID(context["location_id"])
        await db.commit()
    await project_retail_reference_snapshot(
        company_id=DEFAULT_COMPANY_ID,
        brand_ids=(brand_id,),
    )


async def _disable_personas(context: dict[str, str]) -> None:
    user_ids = (uuid.UUID(context["cashier_id"]), uuid.UUID(context["manager_id"]))
    async with PlatformSessionLocal() as db:
        users = list((await db.scalars(select(User).where(User.id.in_(user_ids)))).all())
        for user in users:
            user.is_active = False
        await db.execute(
            update(RefreshToken)
            .where(RefreshToken.user_id.in_(user_ids), RefreshToken.revoked_at.is_(None))
            .values(revoked_at=func.now())
        )
        assignments = list(
            (
                await db.scalars(
                    select(StaffRoleAssignment).where(
                        StaffRoleAssignment.user_id.in_(user_ids),
                        StaffRoleAssignment.revoked_at.is_(None),
                    )
                )
            ).all()
        )
        for assignment in assignments:
            assignment.revoked_at = datetime.now(timezone.utc)
            assignment.revocation_reason = "WP57 targeted UAT complete"
        db.add(
            AuditLog(
                company_id=DEFAULT_COMPANY_ID,
                user_id=user_ids[1],
                action="uat.wp57.personas.disable",
                resource="User",
                resource_id=str(DEFAULT_COMPANY_ID),
                new_value={"count": len(users), "sessions_revoked": True},
            )
        )
        await db.commit()

    # The shared approval fixture creates its initial personas in the legacy
    # source before projecting them into Platform/Retail. Keep those source
    # identities fail-closed as well so a UAT smoke can never leave a usable
    # credential in any configured identity copy.
    async with AsyncSessionLocal() as legacy:
        await legacy.execute(
            update(User)
            .where(User.id.in_(user_ids))
            .values(is_active=False)
        )
        await legacy.commit()
    await project_retail_reference_snapshot(
        company_id=DEFAULT_COMPANY_ID,
        brand_ids=(uuid.UUID(context["brand_id"]),),
    )


def _login(client: TestClient, context: dict[str, str], username: str, password: str) -> dict[str, str]:
    data = expect(
        client.post(
            "/api/v1/auth/login",
            json={
                "company_id": str(DEFAULT_COMPANY_ID),
                "branch_id": context["branch_id"],
                "username": username,
                "password": password,
            },
        ),
        200,
    )
    return {"Authorization": f"Bearer {data['access_token']}"}


async def _verify(
    context: dict[str, str],
    *,
    draft_id: str,
    operation_id: str,
    movement_id: str,
    shift_id: str,
) -> None:
    assert RetailSessionLocal is not None
    async with RetailSessionLocal() as db:
        draft = await db.get(PosHoldDraft, uuid.UUID(draft_id))
        shift = await db.get(CashierShift, uuid.UUID(shift_id))
        movement = await db.get(PosCashMovement, uuid.UUID(movement_id))
        link = await db.scalar(select(RefundTaxLink).where(RefundTaxLink.operation_id == uuid.UUID(operation_id)))
        negative = list(
            (
                await db.scalars(
                    select(Payment).where(
                        Payment.refund_operation_id == uuid.UUID(operation_id),
                        Payment.amount < 0,
                    )
                )
            ).all()
        )
        balance = await db.scalar(
            select(StockBalance).where(
                StockBalance.product_id == uuid.UUID(context["product_id"]),
                StockBalance.location_id == uuid.UUID(context["location_id"]),
            )
        )
        stock_returns = int(
            await db.scalar(
                select(func.count(StockMovement.id)).where(
                    StockMovement.reference_type == "RefundOperation",
                    StockMovement.reference_id == operation_id,
                )
            )
            or 0
        )
        audit = await db.scalar(
            select(AuditLog).where(
                AuditLog.action == "pos.shift.cash_movement",
                AuditLog.resource_id == movement_id,
            )
        )
        if draft is None or draft.status != "converted":
            raise RuntimeError("Retail Hold did not finish converted")
        if shift is None or shift.status != "closed":
            raise RuntimeError("Retail shift did not close")
        if movement is None or movement.journal_entry_id is not None:
            raise RuntimeError("Retail cash movement crossed into the shared journal")
        if audit is None or audit.new_value.get("journal_state") != "not_applicable":
            raise RuntimeError("Retail cash movement audit is missing no-journal evidence")
        if link is None or link.status != "not_required" or link.credit_note_id is not None:
            raise RuntimeError("Retail Cash Pilot created or requested a tax document")
        if len(negative) != 1 or negative[0].original_payment_id is None:
            raise RuntimeError("Retail Return does not have exactly one linked negative Payment")
        if balance is None or Decimal(balance.qty_on_hand) != Decimal("100") or stock_returns != 1:
            raise RuntimeError("Retail sellable Return did not restore stock exactly once")

        hold_audit = await db.scalar(select(PosHoldDraftAudit).where(PosHoldDraftAudit.draft_id == draft.id))
        refund_audit = await db.scalar(
            select(RefundOperationAudit).where(RefundOperationAudit.operation_id == uuid.UUID(operation_id))
        )
        for table_name, row_id in (
            ("pos_hold_draft_audits", hold_audit.id if hold_audit else None),
            ("refund_operation_audits", refund_audit.id if refund_audit else None),
        ):
            if row_id is None:
                raise RuntimeError(f"{table_name} evidence is missing")
            try:
                await db.execute(text(f"UPDATE {table_name} SET id = id WHERE id = :id"), {"id": row_id})
                await db.commit()
            except Exception:
                await db.rollback()
            else:
                raise RuntimeError(f"{table_name} accepted an UPDATE")


def run() -> None:
    _guard_uat()
    password = secrets.token_urlsafe(30)
    manager_pin = f"{secrets.randbelow(1_000_000):06d}"
    context: dict[str, str] | None = None
    try:
        context = asyncio.run(prepare(password=password))
        _detach_engines()
        asyncio.run(_prepare_retail_fixture(context))
        _detach_engines()
        with TestClient(app) as client:
            cashier = _login(client, context, context["cashier_username"], password)
            manager = _login(client, context, context["manager_username"], password)
            expect(
                client.put(
                    "/api/v1/approvals/manager-pin",
                    headers=manager,
                    json={"current_password": password, "pin": manager_pin},
                ),
                200,
            )
            shift_payload = {
                "location_id": context["location_id"],
                "opening_cash": "0",
                "idempotency_key": f"wp57-open-{uuid.uuid4()}",
            }
            shift = expect(client.post("/api/v1/pos/shifts/open", headers=cashier, json=shift_payload), 201)
            if expect(client.post("/api/v1/pos/shifts/open", headers=cashier, json=shift_payload), 201)["id"] != shift["id"]:
                raise RuntimeError("Retail shift-open replay created a duplicate")

            hold_payload = {
                "shift_id": shift["id"],
                "location_id": context["location_id"],
                "label": "WP57 Retail Hold",
                "source_type": "walk_in",
                "items": [{"product_id": context["product_id"], "qty": "1", "expected_unit_price": "0.01"}],
                "order_discount": "0",
                "loyalty_discount_intent": "0",
                "currency": "THB",
                "cart_version": 1,
                "idempotency_key": f"wp57-hold-{uuid.uuid4()}",
            }
            draft = expect(client.post("/api/v1/pos/drafts", headers=cashier, json=hold_payload), 201)
            replay = expect(client.post("/api/v1/pos/drafts", headers=cashier, json=hold_payload), 201)
            if replay["id"] != draft["id"] or Decimal(draft["pricing_snapshot"]["total_amount"]) != Decimal("100"):
                raise RuntimeError("Retail Hold replay or Server price authority failed")
            listed = expect(client.get("/api/v1/pos/drafts", headers=manager), 200)
            if draft["id"] not in {row["id"] for row in listed}:
                raise RuntimeError("Retail Hold was not visible to another staff context")
            claim_payload = {
                "expected_version": draft["version"],
                "shift_id": shift["id"],
                "location_id": context["location_id"],
                "idempotency_key": f"wp57-claim-{uuid.uuid4()}",
            }
            claim = expect(client.post(f"/api/v1/pos/drafts/{draft['id']}/claim", headers=cashier, json=claim_payload), 200)
            expect_detail_code(
                client.patch(
                    f"/api/v1/pos/drafts/{draft['id']}",
                    headers=cashier,
                    json={"expected_version": draft["version"], "label": "stale", "idempotency_key": f"wp57-stale-{uuid.uuid4()}"},
                ),
                409,
                "draft_conflict",
            )
            resume = expect(
                client.post(
                    f"/api/v1/pos/drafts/{draft['id']}/resume",
                    headers=cashier,
                    json={
                        "expected_version": claim["draft"]["version"],
                        "claim_id": claim["draft"]["claim_id"],
                        "shift_id": shift["id"],
                        "location_id": context["location_id"],
                        "accept_revalidation": True,
                        "idempotency_key": f"wp57-resume-{uuid.uuid4()}",
                    },
                ),
                200,
            )

            quote = expect(
                client.post(
                    "/api/v1/pos/pricing/calculate",
                    headers=cashier,
                    json=pricing_payload(context, f"wp57-price-{uuid.uuid4()}"),
                ),
                200,
            )
            sale_request = sale_payload(context, shift["id"], quote, f"wp57-sale-{uuid.uuid4()}")
            sale_request.update({"source_hold_draft_id": draft["id"], "source_hold_draft_version": resume["version"]})
            expect_detail_code(
                client.post(
                    "/api/v1/pos/sales",
                    headers=cashier,
                    json={**sale_request, "is_offline": True},
                ),
                409,
                "retail_offline_not_authorized",
            )
            sale = expect(client.post("/api/v1/pos/sales", headers=cashier, json=sale_request), 201)

            void_request = {"order_id": sale["id"], "void_reason": "WP57 settled cash must use Return"}
            void_approval = expect(
                issue_approval(
                    client,
                    cashier,
                    context,
                    action="pos.sale.void",
                    request_payload=void_request,
                    reason="Verify settled-payment Void guard",
                    pin=manager_pin,
                ),
                200,
            )
            expect_detail_code(
                client.post(
                    f"/api/v1/pos/sales/{sale['id']}/void",
                    headers=cashier,
                    json={"void_reason": void_request["void_reason"], "approval_token": void_approval["approval_token"]},
                ),
                409,
                "settled_payment_requires_refund",
            )

            refund_request = {
                "order_id": sale["id"],
                "shift_id": shift["id"],
                "items": [{"order_item_id": sale["items"][0]["id"], "qty": "1"}],
                "reason_code": "customer_request",
                "reason_note": "WP57 Retail Cash Return",
                "stock_disposition": "sellable",
                "currency": "THB",
                "idempotency_key": f"wp57-return-quote-{uuid.uuid4()}",
            }
            refund_quote = expect(client.post("/api/v1/pos/refunds/quotes", headers=cashier, json=refund_request), 201)
            execute_request = {
                "quote_id": refund_quote["id"],
                "quote_hash": refund_quote["quote_hash"],
                "order_id": sale["id"],
                "expected_order_version": refund_quote["order_version"],
                "total_amount": refund_quote["totals"]["total_amount"],
                "reason_code": "customer_request",
                "reason_note": "WP57 Retail Cash Return",
                "stock_disposition": "sellable",
                "provider_scenario": "succeeded",
                "idempotency_key": f"wp57-return-execute-{uuid.uuid4()}",
            }
            expect_detail_code(client.post("/api/v1/pos/refunds", headers=cashier, json=execute_request), 403, "approval_required")
            approval = expect(
                issue_approval(
                    client,
                    cashier,
                    context,
                    action="pos.refund.create",
                    request_payload=execute_request,
                    reason="Approve WP57 cash Return",
                    pin=manager_pin,
                ),
                200,
            )
            operation = expect(
                client.post("/api/v1/pos/refunds", headers=cashier, json={**execute_request, "approval_token": approval["approval_token"]}),
                201,
            )
            if operation["status"] != "cash_due" or operation["payment_legs"][0]["leg_type"] != "cash":
                raise RuntimeError("Retail Return escaped the cash-only state machine")
            if expect(client.post("/api/v1/pos/refunds", headers=cashier, json={**execute_request, "approval_token": approval["approval_token"]}), 201)["id"] != operation["id"]:
                raise RuntimeError("Retail Return execute replay created a duplicate")
            blocked = client.post(f"/api/v1/pos/shifts/{shift['id']}/close", headers=cashier, json={"closing_cash": "0"})
            expect_detail_code(blocked, 409, "shift_close_blocked")
            completed = expect(
                client.post(
                    f"/api/v1/pos/refunds/{operation['id']}/cash-confirm",
                    headers=manager,
                    json={"expected_version": operation["row_version"], "idempotency_key": f"wp57-cash-{uuid.uuid4()}"},
                ),
                200,
            )
            if completed["status"] != "completed" or completed["tax"]["status"] != "not_required":
                raise RuntimeError("Retail Return did not complete with non-fiscal tax state")

            action_payload = {"expected_version": completed["row_version"], "idempotency_key": f"wp57-disabled-{uuid.uuid4()}"}
            for path, headers in (
                (f"/api/v1/pos/refunds/{operation['id']}/inquire", cashier),
                (f"/api/v1/pos/refunds/{operation['id']}/retry", manager),
                (f"/api/v1/pos/refunds/{operation['id']}/tax-retry", manager),
            ):
                expect_detail_code(client.post(path, headers=headers, json=action_payload), 409, "retail_return_capability_not_available")

            summary = expect(client.get(f"/api/v1/pos/shifts/{shift['id']}/summary", headers=cashier), 200)
            movement_request = {
                "movement_type": "cash_in",
                "amount": "1000",
                "reason_code": "change_fund",
                "reason": "WP57 approval and no-journal verification",
                "expected_shift_version": summary["version"],
                "idempotency_key": f"wp57-movement-{uuid.uuid4()}",
            }
            expect_detail_code(
                client.post(f"/api/v1/pos/shifts/{shift['id']}/cash-movements", headers=cashier, json=movement_request),
                403,
                "approval_required",
            )
            movement_approval = expect(
                issue_approval(
                    client,
                    cashier,
                    context,
                    action="pos.cash_movement.approve",
                    request_payload={"shift_id": shift["id"], **movement_request},
                    reason="Approve WP57 Retail cash movement",
                    pin=manager_pin,
                ),
                200,
            )
            movement = expect(
                client.post(
                    f"/api/v1/pos/shifts/{shift['id']}/cash-movements",
                    headers=cashier,
                    json={**movement_request, "approval_token": movement_approval["approval_token"]},
                ),
                201,
            )
            if expect(client.post(f"/api/v1/pos/shifts/{shift['id']}/cash-movements", headers=cashier, json=movement_request), 201)["id"] != movement["id"]:
                raise RuntimeError("Retail cash movement replay created a duplicate")
            summary = expect(client.get(f"/api/v1/pos/shifts/{shift['id']}/summary", headers=cashier), 200)
            closed = expect(
                client.post(
                    f"/api/v1/pos/shifts/{shift['id']}/close",
                    headers=cashier,
                    json={
                        "closing_cash": summary["expected_cash"],
                        "expected_version": summary["version"],
                        "idempotency_key": f"wp57-close-{uuid.uuid4()}",
                    },
                ),
                200,
            )
            if closed["status"] != "closed":
                raise RuntimeError("Retail shift did not close")
            expect_detail_code(
                client.post(
                    f"/api/v1/pos/shifts/{shift['id']}/handover",
                    headers=cashier,
                    json={"closing_cash": summary["expected_cash"]},
                ),
                409,
                "counter_device_required",
            )

        _detach_engines()
        asyncio.run(
            _verify(
                context,
                draft_id=draft["id"],
                operation_id=completed["id"],
                movement_id=movement["id"],
                shift_id=shift["id"],
            )
        )
        print("WP57 Retail Hold/Return/Shift authenticated UAT smoke: PASS")
    finally:
        if context is not None:
            _detach_engines()
            asyncio.run(_disable_personas(context))


if __name__ == "__main__":
    run()
