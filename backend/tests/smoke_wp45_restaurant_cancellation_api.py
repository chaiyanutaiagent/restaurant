from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import settings
from app.main import app
from app.models.etax import TaxDocument
from app.models.pos import Payment, SaleOrder
from app.models.product import Product, Unit
from app.models.restaurant import (
    DiningOrder,
    DiningOrderItem,
    DiningSession,
    KitchenCancellationEvent,
    KitchenTicket,
    Recipe,
    RecipeIngredient,
    RestaurantCancellation,
    RestaurantCancellationAudit,
    RestaurantCancellationWaste,
)
from app.models.stock import StockBalance, StockMovement
from tests.smoke_approval_api import (
    MANAGER_PIN,
    PASSWORD,
    expect,
    expect_detail_code,
    issue_approval,
    login,
    prepare,
)
from app.utils.create_superuser import DEFAULT_COMPANY_ID


async def prepare_wp45(context: dict[str, str]) -> dict[str, str]:
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    marker = uuid.uuid4().hex[:8]
    async with factory() as db:
        unit = Unit(
            company_id=DEFAULT_COMPANY_ID,
            code=f"G-{marker}",
            name="กรัม",
            decimal_places=2,
            is_active=True,
        )
        db.add(unit)
        await db.flush()
        ingredient = Product(
            company_id=DEFAULT_COMPANY_ID,
            brand_id=uuid.UUID(context["brand_id"]),
            unit_id=unit.id,
            sku=f"WP45-RAW-{marker}",
            name=f"วัตถุดิบ WP45 {marker}",
            product_type="raw_material",
            inventory_role="store_local",
            selling_price=Decimal("0"),
            cost_price=Decimal("2"),
            vat_type="excluded",
            vat_rate=Decimal("0"),
            is_active=True,
            is_for_sale=False,
            is_for_purchase=True,
        )
        menu = Product(
            company_id=ingredient.company_id,
            brand_id=uuid.UUID(context["brand_id"]),
            unit_id=unit.id,
            sku=f"WP45-MENU-{marker}",
            name=f"เมนู WP45 {marker}",
            product_type="menu_item",
            inventory_role="not_stocked",
            selling_price=Decimal("120"),
            cost_price=Decimal("20"),
            vat_type="included",
            vat_rate=Decimal("7"),
            is_active=True,
            is_for_sale=True,
            is_for_purchase=False,
        )
        missing_recipe_menu = Product(
            company_id=ingredient.company_id,
            brand_id=uuid.UUID(context["brand_id"]),
            unit_id=unit.id,
            sku=f"WP45-NO-RECIPE-{marker}",
            name=f"เมนูไม่มีสูตร WP45 {marker}",
            product_type="menu_item",
            inventory_role="not_stocked",
            selling_price=Decimal("80"),
            cost_price=Decimal("10"),
            vat_type="included",
            vat_rate=Decimal("7"),
            is_active=True,
            is_for_sale=True,
            is_for_purchase=False,
        )
        db.add_all([ingredient, menu, missing_recipe_menu])
        await db.flush()
        recipe = Recipe(
            company_id=ingredient.company_id,
            branch_id=uuid.UUID(context["branch_id"]),
            brand_id=uuid.UUID(context["brand_id"]),
            product_id=menu.id,
            recipe_type="menu_recipe",
            version_no=1,
            name=f"สูตร WP45 {marker}",
            yield_qty=Decimal("1"),
            yield_unit="จาน",
            loss_percent=Decimal("0"),
            is_active=True,
        )
        db.add(recipe)
        await db.flush()
        db.add(
            RecipeIngredient(
                recipe_id=recipe.id,
                ingredient_id=ingredient.id,
                quantity=Decimal("2"),
                unit=unit.code,
                sort_order=0,
            )
        )
        db.add(
            StockBalance(
                company_id=ingredient.company_id,
                branch_id=uuid.UUID(context["branch_id"]),
                location_id=uuid.UUID(context["location_id"]),
                product_id=ingredient.id,
                variant_id=None,
                qty_on_hand=Decimal("100"),
                qty_reserved=Decimal("0"),
                cost_per_unit=Decimal("2"),
            )
        )
        session = DiningSession(
            company_id=ingredient.company_id,
            branch_id=uuid.UUID(context["branch_id"]),
            opened_by=uuid.UUID(context["cashier_id"]),
            status="open",
            guest_count=2,
        )
        db.add(session)
        await db.flush()

        rows: dict[str, tuple[DiningOrder, DiningOrderItem, KitchenTicket]] = {}
        for label, state, product, qty in (
            ("pending", "pending", menu, 1),
            ("cooking", "cooking", menu, 1),
            ("done", "done", menu, 1),
            ("served", "served", menu, 1),
            ("race", "pending", menu, 1),
            ("shortage", "cooking", menu, 60),
            ("missing", "cooking", missing_recipe_menu, 1),
        ):
            order = DiningOrder(
                company_id=ingredient.company_id,
                branch_id=session.branch_id,
                session_id=session.id,
                order_number=f"WP45-{label.upper()}-{marker}",
                source="staff",
                status="pending",
                row_version=1,
            )
            db.add(order)
            await db.flush()
            item = DiningOrderItem(
                order_id=order.id,
                product_id=product.id,
                product_name=product.name,
                qty=qty,
                unit_price=Decimal(product.selling_price),
                original_price=Decimal(product.selling_price),
                vat_type="included",
                vat_rate=Decimal("7"),
                vat_amount=Decimal("7.8505"),
                line_total=Decimal(product.selling_price) * qty,
                price_source="product",
                price_version=f"wp45-{marker}",
                status=state,
                station="Hot Kitchen",
                row_version=1,
            )
            db.add(item)
            await db.flush()
            ticket = KitchenTicket(
                company_id=ingredient.company_id,
                branch_id=session.branch_id,
                session_id=session.id,
                order_item_id=item.id,
                product_name=product.name,
                qty=qty,
                station="Hot Kitchen",
                status=state,
                row_version=1,
            )
            db.add(ticket)
            rows[label] = (order, item, ticket)
        await db.commit()
        result = {
            **context,
            "ingredient_id": str(ingredient.id),
            "menu_id": str(menu.id),
            "missing_recipe_menu_id": str(missing_recipe_menu.id),
            "session_id": str(session.id),
        }
        for label, (order, item, ticket) in rows.items():
            result[f"{label}_order_id"] = str(order.id)
            result[f"{label}_item_id"] = str(item.id)
            result[f"{label}_ticket_id"] = str(ticket.id)
    await engine.dispose()
    return result


def cancel_payload(context: dict[str, str], label: str, key: str, *, reason: str = "wrong_item") -> dict:
    return {
        "target_type": "item",
        "target_id": context[f"{label}_item_id"],
        "expected_order_version": 1,
        "expected_item_version": 1,
        "reason_code": reason,
        "reason_note": f"WP45 {label} smoke",
        "idempotency_key": key,
    }


async def snapshot(context: dict[str, str]) -> dict[str, Decimal | int]:
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db:
        result = {
            "stock": Decimal(
                await db.scalar(
                    select(StockBalance.qty_on_hand).where(
                        StockBalance.product_id == uuid.UUID(context["ingredient_id"]),
                        StockBalance.location_id == uuid.UUID(context["location_id"]),
                    )
                )
                or 0
            ),
            "sales": int(await db.scalar(select(func.count(SaleOrder.id))) or 0),
            "payments": int(await db.scalar(select(func.count(Payment.id))) or 0),
            "tax_documents": int(await db.scalar(select(func.count(TaxDocument.id))) or 0),
        }
    await engine.dispose()
    return result


async def verify_persistence(context: dict[str, str], cooking_cancellation_id: str) -> None:
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db:
        cancellation_id = uuid.UUID(cooking_cancellation_id)
        cancellation = await db.get(RestaurantCancellation, cancellation_id)
        if cancellation is None or cancellation.waste_status != "posted" or cancellation.approver_id is None:
            raise RuntimeError("Approved cancellation receipt is incomplete")
        waste_count = int(
            await db.scalar(
                select(func.count(RestaurantCancellationWaste.id)).where(
                    RestaurantCancellationWaste.cancellation_id == cancellation_id
                )
            )
            or 0
        )
        movement_count = int(
            await db.scalar(
                select(func.count(StockMovement.id)).where(
                    StockMovement.reference_type == "restaurant_cancellation",
                    StockMovement.reference_id == cooking_cancellation_id,
                )
            )
            or 0
        )
        audit_count = int(
            await db.scalar(
                select(func.count(RestaurantCancellationAudit.id)).where(
                    RestaurantCancellationAudit.cancellation_id == cancellation_id,
                    RestaurantCancellationAudit.action == "cancel",
                )
            )
            or 0
        )
        event_count = int(
            await db.scalar(
                select(func.count(KitchenCancellationEvent.id)).where(
                    KitchenCancellationEvent.cancellation_id == cancellation_id
                )
            )
            or 0
        )
        if (waste_count, movement_count, audit_count, event_count) != (1, 1, 1, 1):
            raise RuntimeError(
                f"Cancellation retry duplicated side effects: {(waste_count, movement_count, audit_count, event_count)}"
            )
        event_brand = await db.scalar(
            select(KitchenCancellationEvent.brand_id).where(
                KitchenCancellationEvent.cancellation_id == cancellation_id
            )
        )
        if event_brand != uuid.UUID(context["brand_id"]):
            raise RuntimeError("KDS cancellation event lost its Brand scope")
        try:
            await db.execute(
                update(RestaurantCancellation)
                .where(RestaurantCancellation.id == cancellation_id)
                .values(reason_note="tampered")
            )
            await db.commit()
        except Exception:
            await db.rollback()
        else:
            raise RuntimeError("Append-only cancellation receipt accepted an UPDATE")
        for model, values in (
            (RestaurantCancellationWaste, {"unit": "tampered"}),
            (RestaurantCancellationAudit, {"action": "tampered"}),
        ):
            try:
                await db.execute(
                    update(model)
                    .where(model.cancellation_id == cancellation_id)
                    .values(**values)
                )
                await db.commit()
            except Exception:
                await db.rollback()
            else:
                raise RuntimeError(f"Append-only {model.__tablename__} accepted an UPDATE")
    await engine.dispose()


def run() -> None:
    context = asyncio.run(prepare())
    context = asyncio.run(prepare_wp45(context))
    with TestClient(app) as client:
        cashier_headers = login(client, context["cashier_username"])
        manager_headers = login(client, context["manager_username"])
        expect(
            client.put(
                "/api/v1/approvals/manager-pin",
                headers=manager_headers,
                json={"current_password": PASSWORD, "pin": MANAGER_PIN},
            ),
            200,
        )
        financial_before = asyncio.run(snapshot(context))

        pending_key = f"wp45-pending-{uuid.uuid4()}"
        pending_payload = cancel_payload(context, "pending", pending_key)
        pending_preview = expect(
            client.post("/api/v1/restaurant/cancellations/preview", headers=cashier_headers, json=pending_payload),
            200,
        )
        if pending_preview["approval_required"] or pending_preview["waste_disposition"] != "none":
            raise RuntimeError("Pending cancellation policy is incorrect")
        pending_cancel = expect(
            client.post("/api/v1/restaurant/cancellations", headers=cashier_headers, json=pending_payload),
            201,
        )
        pending_replay = expect(
            client.post("/api/v1/restaurant/cancellations", headers=cashier_headers, json=pending_payload),
            201,
        )
        if pending_replay["id"] != pending_cancel["id"]:
            raise RuntimeError("Pending cancellation idempotency created two receipts")
        if asyncio.run(snapshot(context)) != financial_before:
            raise RuntimeError("Pending cancellation created a Sale/Payment/Tax/Waste side effect")
        expect_detail_code(
            client.post(
                "/api/v1/restaurant/cancellations",
                headers=cashier_headers,
                json={**pending_payload, "reason_code": "duplicate_order"},
            ),
            409,
            "duplicate_request",
        )

        events = expect(
            client.get("/api/v1/restaurant/kitchen-cancellation-events", headers=manager_headers),
            200,
        )
        pending_event = next(row for row in events if row["cancellation_id"] == pending_cancel["id"])
        ack_key = f"wp45-ack-{uuid.uuid4()}"
        ack_payload = {"expected_version": pending_event["row_version"], "idempotency_key": ack_key}
        acknowledged = expect(
            client.post(
                f"/api/v1/restaurant/kitchen-cancellation-events/{pending_event['id']}/acknowledge",
                headers=manager_headers,
                json=ack_payload,
            ),
            200,
        )
        if acknowledged["status"] != "acknowledged":
            raise RuntimeError("KDS cancellation acknowledgment did not persist")
        ack_replay = expect(
            client.post(
                f"/api/v1/restaurant/kitchen-cancellation-events/{pending_event['id']}/acknowledge",
                headers=manager_headers,
                json=ack_payload,
            ),
            200,
        )
        if ack_replay["row_version"] != acknowledged["row_version"]:
            raise RuntimeError("KDS acknowledgment replay changed the version")

        cooking_key = f"wp45-cooking-{uuid.uuid4()}"
        cooking_payload = cancel_payload(context, "cooking", cooking_key, reason="kitchen_error")
        cooking_preview = expect(
            client.post("/api/v1/restaurant/cancellations/preview", headers=cashier_headers, json=cooking_payload),
            200,
        )
        if not cooking_preview["approval_required"] or cooking_preview["waste_disposition"] != "full":
            raise RuntimeError("Cooking cancellation did not require approval and full Waste")
        expect_detail_code(
            client.post("/api/v1/restaurant/cancellations", headers=cashier_headers, json=cooking_payload),
            403,
            "approval_required",
        )
        approval = expect(
            issue_approval(
                client,
                cashier_headers,
                context,
                action="fb.order.cancel_after_kitchen",
                request_payload=cooking_payload,
                reason="ครัวทำผิด",
            ),
            200,
        )
        cooking_cancel = expect(
            client.post(
                "/api/v1/restaurant/cancellations",
                headers=cashier_headers,
                json={**cooking_payload, "approval_token": approval["approval_token"]},
            ),
            201,
        )
        cooking_replay = expect(
            client.post(
                "/api/v1/restaurant/cancellations",
                headers=cashier_headers,
                json={**cooking_payload, "approval_token": approval["approval_token"]},
            ),
            201,
        )
        if cooking_replay["id"] != cooking_cancel["id"]:
            raise RuntimeError("Approved cancellation replay created a second receipt")
        after_cooking = asyncio.run(snapshot(context))
        if after_cooking["stock"] != financial_before["stock"] - Decimal("2"):
            raise RuntimeError(f"Cooking Waste stock mismatch: {financial_before} -> {after_cooking}")
        for key in ("sales", "payments", "tax_documents"):
            if after_cooking[key] != financial_before[key]:
                raise RuntimeError(f"Cancellation created forbidden {key} side effect")

        done_key = f"wp45-done-{uuid.uuid4()}"
        done_payload = cancel_payload(context, "done", done_key, reason="quality_failed")
        done_preview = expect(
            client.post("/api/v1/restaurant/cancellations/preview", headers=cashier_headers, json=done_payload),
            200,
        )
        if not done_preview["approval_required"] or done_preview["waste_disposition"] != "full":
            raise RuntimeError("Done cancellation did not require approval and full Waste")
        done_approval = expect(
            issue_approval(
                client,
                cashier_headers,
                context,
                action="fb.order.cancel_after_kitchen",
                request_payload=done_payload,
                reason="คุณภาพไม่ผ่าน",
            ),
            200,
        )
        done_cancel = expect(
            client.post(
                "/api/v1/restaurant/cancellations",
                headers=cashier_headers,
                json={**done_payload, "approval_token": done_approval["approval_token"]},
            ),
            201,
        )
        after_waste = asyncio.run(snapshot(context))
        if after_waste["stock"] != financial_before["stock"] - Decimal("4"):
            raise RuntimeError(f"Done Waste stock mismatch: {financial_before} -> {after_waste}")

        shortage_preview = expect(
            client.post(
                "/api/v1/restaurant/cancellations/preview",
                headers=cashier_headers,
                json=cancel_payload(context, "shortage", f"wp45-shortage-{uuid.uuid4()}"),
            ),
            200,
        )
        if shortage_preview["waste_ready"] or not shortage_preview["blockers"]:
            raise RuntimeError("Insufficient Waste stock did not fail closed")
        missing_preview = expect(
            client.post(
                "/api/v1/restaurant/cancellations/preview",
                headers=cashier_headers,
                json=cancel_payload(context, "missing", f"wp45-missing-{uuid.uuid4()}"),
            ),
            200,
        )
        if missing_preview["waste_ready"] or not missing_preview["blockers"]:
            raise RuntimeError("Missing recipe mapping did not fail closed")

        expect_detail_code(
            client.post(
                "/api/v1/restaurant/cancellations/preview",
                headers=cashier_headers,
                json=cancel_payload(context, "served", f"wp45-served-{uuid.uuid4()}"),
            ),
            409,
            "served_requires_comp_or_refund",
        )
        if client.post(
            f"/api/v1/restaurant/order-items/{context['served_item_id']}/cancel",
            headers=cashier_headers,
            json={"reason": "legacy"},
        ).status_code != 410:
            raise RuntimeError("Legacy unstructured cancellation endpoint is still active")

        race_payload_a = cancel_payload(context, "race", f"wp45-race-a-{uuid.uuid4()}")
        race_payload_b = cancel_payload(context, "race", f"wp45-race-b-{uuid.uuid4()}")

        def race_cancel(payload: dict):
            return client.post("/api/v1/restaurant/cancellations", headers=cashier_headers, json=payload)

        with ThreadPoolExecutor(max_workers=2) as executor:
            race_responses = list(executor.map(race_cancel, [race_payload_a, race_payload_b]))
        if sorted(response.status_code for response in race_responses) != [201, 409]:
            raise RuntimeError(f"Concurrent cancellation did not produce one winner: {[r.status_code for r in race_responses]}")

        reopen_key = f"wp45-reopen-{uuid.uuid4()}"
        reopen_payload = {
            "cancellation_id": pending_cancel["id"],
            "idempotency_key": reopen_key,
            "reason": "ลูกค้าขอเปิดรายการใหม่",
        }
        reopen_approval = expect(
            issue_approval(
                client,
                cashier_headers,
                context,
                action="fb.order.cancel.reopen",
                request_payload=reopen_payload,
                reason=reopen_payload["reason"],
            ),
            200,
        )
        reopened = expect(
            client.post(
                f"/api/v1/restaurant/cancellations/{pending_cancel['id']}/reopen",
                headers=cashier_headers,
                json={
                    "idempotency_key": reopen_key,
                    "reason": reopen_payload["reason"],
                    "approval_token": reopen_approval["approval_token"],
                },
            ),
            200,
        )
        reopened_replay = expect(
            client.post(
                f"/api/v1/restaurant/cancellations/{pending_cancel['id']}/reopen",
                headers=cashier_headers,
                json={
                    "idempotency_key": reopen_key,
                    "reason": reopen_payload["reason"],
                    "approval_token": reopen_approval["approval_token"],
                },
            ),
            200,
        )
        if reopened_replay["new_order_id"] != reopened["new_order_id"]:
            raise RuntimeError("Reopen replay created a second order")
        final_snapshot = asyncio.run(snapshot(context))
        if final_snapshot != after_waste:
            raise RuntimeError("Reopen changed Sale, Payment, Tax or Waste stock state")

        history = expect(
            client.get(
                f"/api/v1/restaurant/cancellations?session_id={context['session_id']}",
                headers=cashier_headers,
            ),
            200,
        )
        if {pending_cancel["id"], cooking_cancel["id"], done_cancel["id"]}.difference({row["id"] for row in history}):
            raise RuntimeError("Cancellation history is incomplete")

    asyncio.run(verify_persistence(context, cooking_cancel["id"]))
    asyncio.run(verify_persistence(context, done_cancel["id"]))
    print("WP45 restaurant cancellation API smoke passed")


if __name__ == "__main__":
    run()
