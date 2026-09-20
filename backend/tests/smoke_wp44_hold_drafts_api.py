from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import uuid

from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import settings
from app.main import app
from app.models.pos import Payment, PosHoldDraft, PosHoldDraftAudit, SaleOrder
from app.models.product import Product
from app.models.stock import StockBalance
from app.services.hold_draft_service import HoldDraftService
from tests.smoke_approval_api import expect, expect_detail_code, login, prepare
from app.utils.create_superuser import DEFAULT_COMPANY_ID


def hold_payload(context: dict[str, str], shift_id: str, key: str, label: str) -> dict:
    return {
        "shift_id": shift_id,
        "location_id": context["location_id"],
        "label": label,
        "source_type": "walk_in",
        "items": [
            {
                "product_id": context["product_id"],
                "qty": "1",
                "expected_unit_price": "0.01",
                "display_name": "client text is presentation only",
            }
        ],
        "order_discount": "0",
        "loyalty_discount_intent": "0",
        "currency": "THB",
        "cart_version": 1,
        "idempotency_key": key,
        "payment_method": "cash",
        "paid_amount": "9999",
        "payment_reference": "must-not-persist",
    }


async def database_snapshot(context: dict[str, str]) -> dict[str, Decimal | int]:
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db:
        result = {
            "orders": int(await db.scalar(select(func.count(SaleOrder.id))) or 0),
            "payments": int(await db.scalar(select(func.count(Payment.id))) or 0),
            "stock": Decimal(
                await db.scalar(
                    select(StockBalance.qty_on_hand).where(
                        StockBalance.product_id == uuid.UUID(context["product_id"]),
                        StockBalance.location_id == uuid.UUID(context["location_id"]),
                    )
                )
                or 0
            ),
        }
    await engine.dispose()
    return result


async def expire_draft(draft_id: str) -> None:
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db:
        await db.execute(
            update(PosHoldDraft)
            .where(PosHoldDraft.id == uuid.UUID(draft_id))
            .values(expires_at=datetime.now(timezone.utc) - timedelta(seconds=1))
        )
        await db.commit()
    await engine.dispose()


async def set_product_price(product_id: str, amount: str) -> None:
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db:
        await db.execute(
            update(Product)
            .where(Product.id == uuid.UUID(product_id))
            .values(selling_price=Decimal(amount), updated_at=func.now())
        )
        await db.commit()
    await engine.dispose()


async def verify_audit_and_isolation(
    context: dict[str, str], converted_id: str, cancelled_id: str
) -> None:
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db:
        converted = await db.get(PosHoldDraft, uuid.UUID(converted_id))
        cancelled = await db.get(PosHoldDraft, uuid.UUID(cancelled_id))
        if converted is None or converted.status != "converted" or converted.converted_order_id is None:
            raise RuntimeError("Resumed Hold Draft was not atomically converted with the Sale")
        if cancelled is None or cancelled.status != "cancelled" or not cancelled.cancel_reason:
            raise RuntimeError("Discarded Hold Draft is missing its reason")
        actions = list(
            (
                await db.scalars(
                    select(PosHoldDraftAudit.action)
                    .where(PosHoldDraftAudit.draft_id == uuid.UUID(converted_id))
                    .order_by(PosHoldDraftAudit.created_at.asc())
                )
            ).all()
        )
        if actions != ["create", "claim", "resume", "convert"]:
            raise RuntimeError(f"Unexpected Hold Draft audit lifecycle: {actions}")
        audit = await db.scalar(
            select(PosHoldDraftAudit).where(PosHoldDraftAudit.draft_id == uuid.UUID(converted_id))
        )
        assert audit is not None
        try:
            await db.execute(
                update(PosHoldDraftAudit)
                .where(PosHoldDraftAudit.id == audit.id)
                .values(reason="tampered")
            )
            await db.commit()
        except Exception:
            await db.rollback()
        else:
            raise RuntimeError("Append-only Hold Draft audit accepted an UPDATE")
        wrong_branch_count = await db.scalar(
            select(func.count(PosHoldDraft.id)).where(
                PosHoldDraft.id == uuid.UUID(converted_id),
                PosHoldDraft.branch_id != uuid.UUID(context["branch_id"]),
            )
        )
        if wrong_branch_count:
            raise RuntimeError("Hold Draft escaped its Branch scope")
        for wrong_brand, wrong_branch in (
            (uuid.uuid4(), uuid.UUID(context["branch_id"])),
            (uuid.UUID(context["brand_id"]), uuid.uuid4()),
        ):
            try:
                await HoldDraftService(db).get(
                    draft_id=uuid.UUID(converted_id),
                    company_id=DEFAULT_COMPANY_ID,
                    brand_id=wrong_brand,
                    branch_id=wrong_branch,
                )
            except HTTPException as exc:
                if exc.status_code != 404:
                    raise RuntimeError(f"Unexpected scope rejection status: {exc.status_code}") from exc
            else:
                raise RuntimeError("Hold Draft was readable outside its Brand/Branch scope")
    await engine.dispose()


def run() -> None:
    context = asyncio.run(prepare())
    with TestClient(app) as client:
        cashier_headers = login(client, context["cashier_username"])
        manager_headers = login(client, context["manager_username"])
        shift = expect(
            client.post(
                "/api/v1/pos/shifts/open",
                headers=cashier_headers,
                json={"location_id": context["location_id"], "opening_cash": "0"},
            ),
            201,
        )
        before = asyncio.run(database_snapshot(context))

        create_key = f"wp44-create-{uuid.uuid4()}"
        payload = hold_payload(context, shift["id"], create_key, "โต๊ะ A1")
        draft = expect(
            client.post("/api/v1/pos/drafts", headers=cashier_headers, json=payload),
            201,
        )
        replay = expect(
            client.post("/api/v1/pos/drafts", headers=cashier_headers, json=payload),
            201,
        )
        if replay["id"] != draft["id"]:
            raise RuntimeError("Create idempotency produced two Hold Drafts")
        expect_detail_code(
            client.post(
                "/api/v1/pos/drafts",
                headers=cashier_headers,
                json={**payload, "label": "different payload"},
            ),
            409,
            "duplicate_request",
        )
        if Decimal(draft["pricing_snapshot"]["total_amount"]) != Decimal("100"):
            raise RuntimeError("Client price changed the server-authoritative Hold total")
        serialized = str(draft["content"])
        if "paid_amount" in serialized or "payment_reference" in serialized:
            raise RuntimeError("Hold Draft persisted payment state")

        listed = expect(
            client.get("/api/v1/pos/drafts", headers=manager_headers),
            200,
        )
        if draft["id"] not in {row["id"] for row in listed}:
            raise RuntimeError("Hold Draft was not visible across staff devices in the Branch")
        expect_detail_code(
            client.get("/api/v1/pos/drafts?this_counter=true", headers=cashier_headers),
            409,
            "counter_device_required",
        )
        after_hold = asyncio.run(database_snapshot(context))
        if before != after_hold:
            raise RuntimeError(f"Hold Draft created a financial or stock side effect: {before} -> {after_hold}")
        expect_detail_code(
            client.post(
                f"/api/v1/pos/shifts/{shift['id']}/close",
                headers=cashier_headers,
                json={"closing_cash": "0"},
            ),
            409,
            "hold_drafts_pending",
        )

        race_source = expect(
            client.post(
                "/api/v1/pos/drafts",
                headers=cashier_headers,
                json=hold_payload(
                    context, shift["id"], f"wp44-race-create-{uuid.uuid4()}", "แข่งสอง Counter"
                ),
            ),
            201,
        )

        def race_claim(key: str):
            return client.post(
                f"/api/v1/pos/drafts/{race_source['id']}/claim",
                headers=cashier_headers,
                json={
                    "expected_version": race_source["version"],
                    "idempotency_key": key,
                    "shift_id": shift["id"],
                    "location_id": context["location_id"],
                },
            )

        with ThreadPoolExecutor(max_workers=2) as executor:
            race_responses = list(
                executor.map(
                    race_claim,
                    [f"wp44-race-a-{uuid.uuid4()}", f"wp44-race-b-{uuid.uuid4()}"],
                )
            )
        if sorted(response.status_code for response in race_responses) != [200, 409]:
            raise RuntimeError(
                f"Concurrent claim did not produce one winner: {[response.status_code for response in race_responses]}"
            )
        race_winner = next(response.json()["data"] for response in race_responses if response.status_code == 200)
        race_loser = next(response for response in race_responses if response.status_code == 409)
        expect_detail_code(race_loser, 409, "draft_conflict")
        released_race = expect(
            client.post(
                f"/api/v1/pos/drafts/{race_source['id']}/release",
                headers=cashier_headers,
                json={
                    "expected_version": race_winner["draft"]["version"],
                    "idempotency_key": f"wp44-race-release-{uuid.uuid4()}",
                    "claim_id": race_winner["draft"]["claim_id"],
                    "shift_id": shift["id"],
                    "reason": "จบการทดสอบ concurrency",
                },
            ),
            200,
        )
        expect(
            client.post(
                f"/api/v1/pos/drafts/{race_source['id']}/discard",
                headers=cashier_headers,
                json={
                    "expected_version": released_race["version"],
                    "idempotency_key": f"wp44-race-discard-{uuid.uuid4()}",
                    "reason": "จบการทดสอบ concurrency",
                },
            ),
            200,
        )

        claim_key = f"wp44-claim-{uuid.uuid4()}"
        claim_payload = {
            "expected_version": draft["version"],
            "idempotency_key": claim_key,
            "shift_id": shift["id"],
            "location_id": context["location_id"],
        }
        claim = expect(
            client.post(
                f"/api/v1/pos/drafts/{draft['id']}/claim",
                headers=cashier_headers,
                json=claim_payload,
            ),
            200,
        )
        claim_replay = expect(
            client.post(
                f"/api/v1/pos/drafts/{draft['id']}/claim",
                headers=cashier_headers,
                json=claim_payload,
            ),
            200,
        )
        if claim_replay["draft"]["claim_id"] != claim["draft"]["claim_id"]:
            raise RuntimeError("Claim idempotency did not replay the same claim")
        expect_detail_code(
            client.post(
                f"/api/v1/pos/drafts/{draft['id']}/claim",
                headers=cashier_headers,
                json={**claim_payload, "idempotency_key": f"wp44-race-{uuid.uuid4()}"},
            ),
            409,
            "draft_conflict",
        )
        resume_key = f"wp44-resume-{uuid.uuid4()}"
        resume_payload = {
            "expected_version": claim["draft"]["version"],
            "idempotency_key": resume_key,
            "shift_id": shift["id"],
            "location_id": context["location_id"],
            "claim_id": claim["draft"]["claim_id"],
            "accept_revalidation": False,
        }
        resumed = expect(
            client.post(
                f"/api/v1/pos/drafts/{draft['id']}/resume",
                headers=cashier_headers,
                json=resume_payload,
            ),
            200,
        )
        replayed_resume = expect(
            client.post(
                f"/api/v1/pos/drafts/{draft['id']}/resume",
                headers=cashier_headers,
                json=resume_payload,
            ),
            200,
        )
        if replayed_resume["id"] != resumed["id"]:
            raise RuntimeError("Resume idempotency did not replay the same draft")

        quote = expect(
            client.post(
                "/api/v1/pos/pricing/calculate",
                headers=cashier_headers,
                json={
                    "items": [{"product_id": context["product_id"], "qty": "1", "expected_unit_price": "100"}],
                    "discount_amount": "0",
                    "channel": "pos",
                    "currency": "THB",
                    "cart_version": 1,
                    "idempotency_key": f"wp44-price-{uuid.uuid4()}",
                },
            ),
            200,
        )
        sale = expect(
            client.post(
                "/api/v1/pos/sales",
                headers=cashier_headers,
                json={
                    "shift_id": shift["id"],
                    "location_id": context["location_id"],
                    "items": [{"product_id": context["product_id"], "qty": "1", "unit_price": "0.01", "original_price": "100", "discount_amount": "0", "discount_type": "amount", "vat_type": "excluded", "vat_rate": "99"}],
                    "discount_amount": "0",
                    "discount_type": "amount",
                    "payment_method": "cash",
                    "paid_amount": quote["total_amount"],
                    "client_order_id": f"wp44-sale-{uuid.uuid4()}",
                    "pricing_quote_id": quote["quote_id"],
                    "pricing_calculation_hash": quote["calculation_hash"],
                    "channel": "pos",
                    "currency": "THB",
                    "cart_version": 1,
                    "source_hold_draft_id": resumed["id"],
                    "source_hold_draft_version": resumed["version"],
                },
            ),
            201,
        )
        if Decimal(sale["total_amount"]) != Decimal("100"):
            raise RuntimeError("Converted sale did not use the server-authoritative total")

        cancel_payload = hold_payload(
            context, shift["id"], f"wp44-cancel-create-{uuid.uuid4()}", "ยกเลิกภายหลัง"
        )
        cancelled_source = expect(
            client.post("/api/v1/pos/drafts", headers=cashier_headers, json=cancel_payload),
            201,
        )
        cancelled = expect(
            client.post(
                f"/api/v1/pos/drafts/{cancelled_source['id']}/discard",
                headers=cashier_headers,
                json={
                    "expected_version": cancelled_source["version"],
                    "idempotency_key": f"wp44-discard-{uuid.uuid4()}",
                    "reason": "ลูกค้าเปลี่ยนใจ",
                },
            ),
            200,
        )

        expiry_source = expect(
            client.post(
                "/api/v1/pos/drafts",
                headers=cashier_headers,
                json=hold_payload(
                    context, shift["id"], f"wp44-expire-create-{uuid.uuid4()}", "หมดอายุ"
                ),
            ),
            201,
        )
        asyncio.run(expire_draft(expiry_source["id"]))
        expired = expect(
            client.get(f"/api/v1/pos/drafts/{expiry_source['id']}", headers=cashier_headers),
            200,
        )
        if expired["status"] != "expired":
            raise RuntimeError("Expired Hold Draft was not materialized by the Server")
        reopened = expect(
            client.post(
                f"/api/v1/pos/drafts/{expired['id']}/reopen",
                headers=cashier_headers,
                json={
                    "expected_version": expired["version"],
                    "idempotency_key": f"wp44-reopen-{uuid.uuid4()}",
                    "shift_id": shift["id"],
                    "location_id": context["location_id"],
                },
            ),
            201,
        )
        if reopened["parent_draft_id"] != expired["id"] or reopened["status"] != "active":
            raise RuntimeError("Expired Hold Draft recovery did not create a traceable revision")
        expect(
            client.post(
                f"/api/v1/pos/drafts/{reopened['id']}/discard",
                headers=cashier_headers,
                json={
                    "expected_version": reopened["version"],
                    "idempotency_key": f"wp44-reopen-discard-{uuid.uuid4()}",
                    "reason": "จบชุดทดสอบ",
                },
            ),
            200,
        )

        stale_source = expect(
            client.post(
                "/api/v1/pos/drafts",
                headers=cashier_headers,
                json=hold_payload(
                    context, shift["id"], f"wp44-stale-create-{uuid.uuid4()}", "ราคาเปลี่ยน"
                ),
            ),
            201,
        )
        asyncio.run(set_product_price(context["product_id"], "120"))
        stale_claim = expect(
            client.post(
                f"/api/v1/pos/drafts/{stale_source['id']}/claim",
                headers=cashier_headers,
                json={
                    "expected_version": stale_source["version"],
                    "idempotency_key": f"wp44-stale-claim-{uuid.uuid4()}",
                    "shift_id": shift["id"],
                    "location_id": context["location_id"],
                },
            ),
            200,
        )
        if not stale_claim["requires_review"] or not stale_claim["price_changes"]:
            raise RuntimeError("A changed Server price did not require explicit review")
        stale_resume_payload = {
            "expected_version": stale_claim["draft"]["version"],
            "idempotency_key": f"wp44-stale-resume-{uuid.uuid4()}",
            "shift_id": shift["id"],
            "location_id": context["location_id"],
            "claim_id": stale_claim["draft"]["claim_id"],
            "accept_revalidation": False,
        }
        expect_detail_code(
            client.post(
                f"/api/v1/pos/drafts/{stale_source['id']}/resume",
                headers=cashier_headers,
                json=stale_resume_payload,
            ),
            409,
            "draft_revalidation_required",
        )
        accepted = expect(
            client.post(
                f"/api/v1/pos/drafts/{stale_source['id']}/resume",
                headers=cashier_headers,
                json={
                    **stale_resume_payload,
                    "idempotency_key": f"wp44-stale-accept-{uuid.uuid4()}",
                    "accept_revalidation": True,
                },
            ),
            200,
        )
        if accepted["status"] != "resumed":
            raise RuntimeError("Reviewed price change could not be resumed")
        asyncio.run(set_product_price(context["product_id"], "100"))

        audit_rows = expect(
            client.get(f"/api/v1/pos/drafts/{draft['id']}/audit", headers=manager_headers),
            200,
        )
        if [row["action"] for row in audit_rows] != ["create", "claim", "resume", "convert"]:
            raise RuntimeError("Audit API did not return the expected lifecycle")

        handoff_source = expect(
            client.post(
                "/api/v1/pos/drafts",
                headers=cashier_headers,
                json=hold_payload(
                    context, shift["id"], f"wp44-handoff-create-{uuid.uuid4()}", "ส่งต่อผู้จัดการ"
                ),
            ),
            201,
        )
        handed_off = expect(
            client.patch(
                f"/api/v1/pos/drafts/{handoff_source['id']}",
                headers=manager_headers,
                json={
                    "expected_version": handoff_source["version"],
                    "idempotency_key": f"wp44-handoff-{uuid.uuid4()}",
                    "assignee_user_id": context["manager_id"],
                    "reason": "ส่งต่อก่อนปิดกะ",
                },
            ),
            200,
        )
        if handed_off["assignee_user_id"] != context["manager_id"]:
            raise RuntimeError("Hold Draft assignee was not updated within Branch scope")
        expect(
            client.post(
                f"/api/v1/pos/shifts/{shift['id']}/close",
                headers=cashier_headers,
                json={"closing_cash": "100"},
            ),
            200,
        )
        expect(
            client.post(
                f"/api/v1/pos/drafts/{handed_off['id']}/discard",
                headers=manager_headers,
                json={
                    "expected_version": handed_off["version"],
                    "idempotency_key": f"wp44-handoff-discard-{uuid.uuid4()}",
                    "reason": "จบชุดทดสอบส่งต่อ",
                },
            ),
            200,
        )

    asyncio.run(verify_audit_and_isolation(context, draft["id"], cancelled["id"]))
    print("WP44 Hold Draft API smoke passed")


if __name__ == "__main__":
    run()
