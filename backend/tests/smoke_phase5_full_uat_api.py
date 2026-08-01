from __future__ import annotations

import asyncio
from datetime import datetime
from decimal import Decimal
import json
import os
import urllib.error
import urllib.request
import uuid
from zoneinfo import ZoneInfo

from sqlalchemy import func, select

from app.config import settings
from app.database import AsyncSessionLocal
from app.models.accounting import JournalEntry, JournalLine
from app.models.branch import Branch
from app.models.company import Company
from app.models.integration import OperationalOutboxEvent
from app.models.pos import Payment, SaleOrder
from app.models.product import Product
from app.models.restaurant import (
    Brand,
    BrandBranch,
    DiningSession,
    KitchenTicket,
    Recipe,
)
from app.models.stock import StockBalance, StockLocation, StockMovement
from app.utils.create_superuser import DEFAULT_COMPANY_ID
from app.utils.seed_fnb_demo import DEMO_RAW_MATERIALS, seed_fnb_demo_menu


PROJECT_PREFIX = "restaurant-p5-uat"
BRAND_SLUG = "p5-uat-restaurant"
BASE_URL = os.environ.get("P5_UAT_INTERNAL_BASE_URL", "http://127.0.0.1:8000").rstrip("/")


def expect_http(
    method: str,
    path: str,
    *,
    expected: int = 200,
    token: str | None = None,
    body: object | None = None,
) -> object:
    payload = None if body is None else json.dumps(body).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(
        f"{BASE_URL}{path}",
        data=payload,
        headers=headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            status_code = response.status
            response_body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        status_code = exc.code
        response_body = exc.read().decode("utf-8")
    if status_code != expected:
        raise RuntimeError(
            f"{method} {path}: expected HTTP {expected}, got {status_code}: {response_body}"
        )
    if not response_body:
        return None
    decoded = json.loads(response_body)
    return decoded.get("data", decoded)


async def prepare() -> dict[str, str]:
    compose_project = os.environ.get("P5_UAT_PROJECT_NAME", "")
    if not compose_project.startswith(PROJECT_PREFIX):
        raise RuntimeError("Phase 5 UAT smoke refuses to write outside an isolated UAT Compose project")
    if not settings.default_admin_password:
        raise RuntimeError("P5 UAT admin password is missing")

    async with AsyncSessionLocal() as db:
        actual_database = str(await db.scalar(func.current_database()) or "")
        if actual_database != settings.postgres_db:
            raise RuntimeError(
                f"Phase 5 UAT database mismatch: {actual_database} != {settings.postgres_db}"
            )
        company = await db.get(Company, DEFAULT_COMPANY_ID)
        branch = await db.scalar(
            select(Branch)
            .where(
                Branch.company_id == DEFAULT_COMPANY_ID,
                Branch.is_active.is_(True),
                Branch.deleted_at.is_(None),
            )
            .order_by(Branch.sort_order, Branch.created_at)
            .limit(1)
        )
        if company is None or branch is None:
            raise RuntimeError("Fresh UAT bootstrap Company/Branch is missing")

        store_location = await db.scalar(
            select(StockLocation)
            .where(
                StockLocation.company_id == company.id,
                StockLocation.branch_id == branch.id,
                StockLocation.is_active.is_(True),
                StockLocation.deleted_at.is_(None),
            )
            .order_by(StockLocation.created_at)
            .limit(1)
        )
        if store_location is None:
            raise RuntimeError("Fresh UAT bootstrap Stock Location is missing")

        async def ensure_location(code: str, name: str) -> StockLocation:
            row = await db.scalar(
                select(StockLocation).where(
                    StockLocation.company_id == company.id,
                    StockLocation.branch_id == branch.id,
                    StockLocation.code == code,
                    StockLocation.deleted_at.is_(None),
                )
            )
            if row is None:
                row = StockLocation(
                    company_id=company.id,
                    branch_id=branch.id,
                    code=code,
                    name=name,
                    is_active=True,
                )
                db.add(row)
                await db.flush()
            return row

        central_raw = await ensure_location("UAT-C-RAW", "UAT Central Raw")
        central_ready = await ensure_location("UAT-C-READY", "UAT Central Ready")
        brand = await db.scalar(
            select(Brand).where(
                Brand.company_id == company.id,
                Brand.slug == BRAND_SLUG,
            )
        )
        if brand is None:
            brand = Brand(
                company_id=company.id,
                central_branch_id=branch.id,
                central_location_id=central_raw.id,
                central_ready_location_id=central_ready.id,
                slug=BRAND_SLUG,
                name="Phase 5 UAT Restaurant",
                business_type="restaurant",
                is_active=True,
            )
            db.add(brand)
            await db.flush()
        else:
            brand.central_branch_id = branch.id
            brand.central_location_id = central_raw.id
            brand.central_ready_location_id = central_ready.id
            brand.business_type = "restaurant"
            brand.is_active = True

        membership = await db.scalar(
            select(BrandBranch).where(
                BrandBranch.company_id == company.id,
                BrandBranch.brand_id == brand.id,
                BrandBranch.branch_id == branch.id,
            )
        )
        if membership is None:
            membership = BrandBranch(
                company_id=company.id,
                brand_id=brand.id,
                branch_id=branch.id,
                store_location_id=store_location.id,
                is_active=True,
            )
            db.add(membership)
        else:
            membership.store_location_id = store_location.id
            membership.is_active = True
        await db.commit()

        await seed_fnb_demo_menu(db, str(company.id), str(branch.id))
        demo_products = list(
            (
                await db.scalars(
                    select(Product).where(
                        Product.company_id == company.id,
                        Product.sku.like("FNB-%"),
                        Product.deleted_at.is_(None),
                    )
                )
            ).all()
        )
        raw_costs = {str(item["sku"]): Decimal(str(item["cost"])) for item in DEMO_RAW_MATERIALS}
        for product in demo_products:
            product.brand_id = brand.id
            if product.sku in raw_costs:
                product.inventory_role = "store_local"
        recipes = list(
            (
                await db.scalars(
                    select(Recipe).where(
                        Recipe.company_id == company.id,
                        Recipe.branch_id == branch.id,
                    )
                )
            ).all()
        )
        for recipe in recipes:
            recipe.brand_id = brand.id
            recipe.is_active = True

        for product in demo_products:
            if product.sku not in raw_costs:
                continue
            balance = await db.scalar(
                select(StockBalance).where(
                    StockBalance.company_id == company.id,
                    StockBalance.branch_id == branch.id,
                    StockBalance.location_id == store_location.id,
                    StockBalance.product_id == product.id,
                    StockBalance.variant_id.is_(None),
                )
            )
            if balance is None:
                balance = StockBalance(
                    company_id=company.id,
                    branch_id=branch.id,
                    location_id=store_location.id,
                    product_id=product.id,
                    variant_id=None,
                    qty_on_hand=Decimal("10000"),
                    qty_reserved=Decimal("0"),
                    cost_per_unit=raw_costs[product.sku],
                )
                db.add(balance)
            else:
                balance.qty_on_hand = Decimal("10000")
                balance.qty_reserved = Decimal("0")
                balance.cost_per_unit = raw_costs[product.sku]
        await db.commit()

        uat_product = await db.scalar(
            select(Product).where(
                Product.company_id == company.id,
                Product.sku == "FNB-DEMO-004",
                Product.brand_id == brand.id,
                Product.is_active.is_(True),
            )
        )
        browser_product = await db.scalar(
            select(Product).where(
                Product.company_id == company.id,
                Product.sku == "FNB-DEMO-007",
                Product.brand_id == brand.id,
                Product.is_active.is_(True),
            )
        )
        if uat_product is None or browser_product is None:
            raise RuntimeError("UAT menu products are missing")
        return {
            "company_id": str(company.id),
            "branch_id": str(branch.id),
            "brand_id": str(brand.id),
            "brand_slug": brand.slug,
            "store_location_id": str(store_location.id),
            "product_id": str(uat_product.id),
            "browser_product_id": str(browser_product.id),
        }


async def verify_handoffs(context: dict[str, str], sale_order_id: str, total: Decimal) -> dict[str, object]:
    order_uuid = uuid.UUID(sale_order_id)
    async with AsyncSessionLocal() as db:
        order = await db.get(SaleOrder, order_uuid)
        session = await db.scalar(
            select(DiningSession).where(DiningSession.sale_order_id == order_uuid)
        )
        payment_count = int(
            await db.scalar(select(func.count(Payment.id)).where(Payment.order_id == order_uuid)) or 0
        )
        movements = list(
            (
                await db.scalars(
                    select(StockMovement).where(
                        StockMovement.company_id == uuid.UUID(context["company_id"]),
                        StockMovement.location_id == uuid.UUID(context["store_location_id"]),
                        StockMovement.reference_type == "pos_sale_recipe",
                        StockMovement.reference_id == sale_order_id,
                    )
                )
            ).all()
        )
        events = list(
            (
                await db.scalars(
                    select(OperationalOutboxEvent).where(
                        OperationalOutboxEvent.aggregate_id == order_uuid
                    )
                )
            ).all()
        )
        journals = list(
            (
                await db.scalars(
                    select(JournalEntry).where(
                        JournalEntry.company_id == uuid.UUID(context["company_id"]),
                        JournalEntry.entry_type == "sale",
                        JournalEntry.reference_type == "SaleOrder",
                        JournalEntry.reference_id == sale_order_id,
                    )
                )
            ).all()
        )
        if order is None or session is None:
            raise RuntimeError("Checkout did not persist its SaleOrder/DiningSession handoff")
        if order.status != "completed" or Decimal(order.total_amount) != total:
            raise RuntimeError(f"SaleOrder mismatch: {order.status}/{order.total_amount}")
        if session.status != "closed" or session.sale_order_id != order.id:
            raise RuntimeError("Dining session did not close against the SaleOrder")
        if payment_count != 1 or len(events) != 1 or len(journals) != 1:
            raise RuntimeError(
                "Exactly-once payment/outbox/accounting failed: "
                f"{payment_count}/{len(events)}/{len(journals)}"
            )
        if order.recipe_stock_status != "posted" or len(movements) != 3:
            raise RuntimeError(
                f"Recipe stock posting failed: status={order.recipe_stock_status} movements={len(movements)}"
            )
        if any(Decimal(row.qty) >= 0 or Decimal(row.qty_after) >= Decimal(row.qty_before) for row in movements):
            raise RuntimeError("Recipe stock movement direction is invalid")
        event = events[0]
        if event.event_type != "restaurant.sale.completed.v1" or str(event.brand_id) != context["brand_id"]:
            raise RuntimeError("Restaurant sale outbox contract is invalid")
        journal = journals[0]
        debit, credit = (
            await db.execute(
                select(
                    func.coalesce(func.sum(JournalLine.debit_amount), 0),
                    func.coalesce(func.sum(JournalLine.credit_amount), 0),
                ).where(JournalLine.entry_id == journal.id)
            )
        ).one()
        if Decimal(debit).quantize(Decimal("0.01")) != Decimal(credit).quantize(Decimal("0.01")):
            raise RuntimeError(f"Journal is not balanced: debit={debit} credit={credit}")
        return {
            "payment_count": payment_count,
            "recipe_stock_movement_count": len(movements),
            "outbox_event_count": len(events),
            "journal_entry_count": len(journals),
            "journal_debit": str(Decimal(debit).quantize(Decimal("0.01"))),
            "journal_credit": str(Decimal(credit).quantize(Decimal("0.01"))),
        }


async def run() -> None:
    expect_http("GET", "/health")
    context = await prepare()
    login = expect_http(
        "POST",
        "/api/v1/auth/login",
        body={
            "company_id": context["company_id"],
            "branch_id": context["branch_id"],
            "username": "admin",
            "password": settings.default_admin_password,
        },
    )
    if not isinstance(login, dict) or not login.get("access_token"):
        raise RuntimeError("UAT staff login did not return an access token")
    token = str(login["access_token"])
    expect_http(
        "POST",
        "/api/v1/restaurant/setup",
        expected=201,
        token=token,
        body={
            "has_tables": True,
            "table_zones": [
                {
                    "zone_name": "Phase 5 UAT",
                    "table_count": 2,
                    "table_name_prefix": "UAT",
                    "table_capacity": 4,
                }
            ],
            "table_qr_enabled": True,
            "bill_at_table": True,
            "queue_reset": "daily",
            "queue_prefix": "U",
            "pickup_display_enabled": True,
            "kitchen_stations": ["ครัวหลัก", "เครื่องดื่ม"],
        },
    )

    marker = datetime.now(ZoneInfo("Asia/Bangkok")).strftime("%H%M%S")
    table = expect_http(
        "POST",
        "/api/v1/restaurant/tables",
        expected=201,
        token=token,
        body={"name": f"UAT-FULL-{marker}", "zone": "Phase 5 UAT", "capacity": 4, "table_type": "dine_in"},
    )
    session = expect_http(
        "POST",
        "/api/v1/restaurant/sessions",
        expected=201,
        token=token,
        body={"table_id": table["id"], "guest_count": 2, "customer_name": "Phase 5 UAT"},
    )
    session_id = str(session["id"])
    qr_token = str(session["qr_token"])
    menu = expect_http("GET", f"/api/public/menu/{qr_token}")
    if not isinstance(menu, dict) or menu.get("source_type") != "dine_in" or len(menu.get("products", [])) < 12:
        raise RuntimeError("Public QR menu is incomplete")

    order = expect_http(
        "POST",
        f"/api/public/menu/{qr_token}/orders",
        expected=201,
        body={
            "items": [
                {
                    "product_id": context["product_id"],
                    "qty": 1,
                    "special_request": "UAT ไม่เผ็ด",
                }
            ],
            "note": "Phase 5 QR-to-ERP UAT",
        },
    )
    if not isinstance(order, dict) or str(order.get("session_id")) != session_id:
        raise RuntimeError("Public QR order was not attached to its DiningSession")
    public_status = expect_http("GET", f"/api/public/menu/{qr_token}/status?session_id={session_id}")
    order_item_id = str(public_status["items"][0]["id"])
    if public_status["items"][0]["status"] != "pending":
        raise RuntimeError("New QR order did not enter the pending kitchen state")

    kitchen = expect_http("GET", "/api/v1/restaurant/kitchen", token=token)
    ticket = next((row for row in kitchen if str(row["session_id"]) == session_id), None)
    if ticket is None:
        raise RuntimeError("Kitchen API did not expose the QR order ticket")
    ticket_id = str(ticket["id"])
    expect_http(
        "PATCH",
        f"/api/v1/restaurant/kitchen/{ticket_id}",
        token=token,
        body={"status": "cooking"},
    )
    expect_http(
        "PATCH",
        f"/api/v1/restaurant/kitchen/{ticket_id}",
        token=token,
        body={"status": "done"},
    )
    expect_http(
        "PATCH",
        f"/api/v1/restaurant/order-items/{order_item_id}/status",
        token=token,
        body={"status": "served"},
    )
    bill = expect_http(
        "POST",
        f"/api/public/menu/{qr_token}/bill?session_id={session_id}",
        body={},
    )
    if bill["status"] != "bill_requested":
        raise RuntimeError("Public bill request did not reach bill_requested")

    detail = expect_http("GET", f"/api/v1/restaurant/sessions/{session_id}/detail", token=token)
    total = sum(
        (
            Decimal(str(item["unit_price"])) * Decimal(str(item["qty"]))
            for row in detail["orders"]
            for item in row["items"]
            if item["status"] != "cancelled"
        ),
        Decimal("0"),
    ).quantize(Decimal("0.01"))
    checkout = expect_http(
        "POST",
        f"/api/v1/restaurant/sessions/{session_id}/checkout",
        token=token,
        body={
            "payment_method": "cash",
            "paid_amount": str(total),
            "payments": [{"payment_method": "cash", "amount": str(total)}],
            "note": "Phase 5 full UAT checkout",
        },
    )
    sale_order_id = str(checkout["sale_order_id"])
    if checkout["source_type"] != "dine_in" or Decimal(str(checkout["total_amount"])) != total:
        raise RuntimeError("Restaurant checkout response is inconsistent")
    expect_http(
        "POST",
        f"/api/v1/restaurant/sessions/{session_id}/checkout",
        expected=400,
        token=token,
        body={"payment_method": "cash", "paid_amount": str(total)},
    )
    handoffs = await verify_handoffs(context, sale_order_id, total)

    today = datetime.now(ZoneInfo("Asia/Bangkok")).date().isoformat()
    report = expect_http(
        "GET",
        f"/api/v1/restaurant/central/{context['brand_slug']}/reports/operations?date_from={today}&date_to={today}",
        token=token,
    )
    if report["reconciliation"]["sales"]["is_reconciled"] is not True:
        raise RuntimeError(f"ERP sales reconciliation failed: {report['reconciliation']['sales']}")
    if report["reconciliation"]["payments"]["is_reconciled"] is not True:
        raise RuntimeError(f"ERP payment reconciliation failed: {report['reconciliation']['payments']}")
    if Decimal(str(report["dashboard_totals"]["sales_amount"])) < total:
        raise RuntimeError("ERP report sales total does not include the QR checkout")
    if Decimal(str(report["dashboard_totals"]["estimated_recipe_cogs"])) <= 0:
        raise RuntimeError("ERP report recipe COGS was not calculated")
    if not any(row["product_id"] == context["product_id"] for row in report["recipe_costs"]):
        raise RuntimeError("ERP report did not include the sold menu recipe")

    browser_table = expect_http(
        "POST",
        "/api/v1/restaurant/tables",
        expected=201,
        token=token,
        body={"name": f"UAT-BROWSER-{marker}", "zone": "Phase 5 UAT", "capacity": 2, "table_type": "dine_in"},
    )
    browser_session = expect_http(
        "POST",
        "/api/v1/restaurant/sessions",
        expected=201,
        token=token,
        body={"table_id": browser_table["id"], "guest_count": 1, "customer_name": "Browser UAT"},
    )
    browser_qr_token = str(browser_session["qr_token"])
    expect_http(
        "POST",
        f"/api/public/menu/{browser_qr_token}/orders",
        expected=201,
        body={
            "items": [
                {
                    "product_id": context["browser_product_id"],
                    "qty": 1,
                    "special_request": "Browser UAT หวานน้อย",
                }
            ],
            "note": "Prepared for visual UAT",
        },
    )

    public_context = {
        "scope": "P5-UAT-SECURITY-03",
        "company_id": context["company_id"],
        "branch_id": context["branch_id"],
        "brand_slug": context["brand_slug"],
        "completed_session_id": session_id,
        "sale_order_id": sale_order_id,
        "checkout_total": str(total),
        "browser_table_name": f"UAT-BROWSER-{marker}",
        "browser_session_id": str(browser_session["id"]),
        "browser_qr_token": browser_qr_token,
        "browser_paths": {
            "login": "/login",
            "public_menu": f"/menu/{browser_qr_token}",
            "tables": "/restaurant/tables",
            "kitchen": "/restaurant/kitchen",
            "report": f"/central/{context['brand_slug']}/reports",
        },
        "handoffs": handoffs,
        "report": {
            "sales_amount": report["dashboard_totals"]["sales_amount"],
            "payment_amount": report["dashboard_totals"]["payment_amount"],
            "estimated_recipe_cogs": report["dashboard_totals"]["estimated_recipe_cogs"],
            "sales_reconciled": report["reconciliation"]["sales"]["is_reconciled"],
            "payments_reconciled": report["reconciliation"]["payments"]["is_reconciled"],
        },
    }
    print("BROWSER_CONTEXT=" + json.dumps(public_context, ensure_ascii=False, sort_keys=True))
    print(
        "PASS: Phase 5 full UAT API QR->kitchen->payment->stock/accounting->ERP report "
        f"session={session_id} sale={sale_order_id} total={total}"
    )


if __name__ == "__main__":
    asyncio.run(run())
