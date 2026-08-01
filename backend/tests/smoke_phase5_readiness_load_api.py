from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from decimal import Decimal
import json
import os
import time
import urllib.error
import urllib.request
import uuid

from sqlalchemy import func, select

from app.config import settings
from app.database import AsyncSessionLocal
from app.models.accounting import JournalEntry
from app.models.company import Company
from app.models.integration import OperationalOutboxEvent
from app.models.pos import Payment, SaleOrder
from app.models.product import Product
from app.models.restaurant import Brand, BrandBranch, DiningSession, Recipe, RecipeIngredient
from app.models.stock import StockBalance, StockMovement
from app.utils.create_superuser import DEFAULT_COMPANY_ID


PROJECT_PREFIX = "restaurant-p5-uat"
BRAND_SLUG = "p5-uat-restaurant"
ORDER_COUNT = 100
BATCH_SIZE = 50
BASE_URL = os.environ.get("P5_UAT_INTERNAL_BASE_URL", "http://127.0.0.1:8000").rstrip("/")


def request_json(
    method: str,
    path: str,
    *,
    token: str | None = None,
    body: object | None = None,
    expected: int = 200,
    timeout: float = 120,
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
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status_code = response.status
            response_body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        status_code = exc.code
        response_body = exc.read().decode("utf-8")
    if status_code != expected:
        raise RuntimeError(
            f"{method} {path}: expected HTTP {expected}, got {status_code}: {response_body}"
        )
    decoded = json.loads(response_body) if response_body else None
    return decoded.get("data", decoded) if isinstance(decoded, dict) else decoded


async def prepare() -> dict[str, str]:
    compose_project = os.environ.get("P5_UAT_PROJECT_NAME", "")
    if not compose_project.startswith(PROJECT_PREFIX):
        raise RuntimeError("Phase 5 readiness load smoke refuses a non-UAT Compose project")

    async with AsyncSessionLocal() as db:
        actual_database = str(await db.scalar(func.current_database()) or "")
        if actual_database != settings.postgres_db:
            raise RuntimeError(
                f"Phase 5 readiness database mismatch: {actual_database} != {settings.postgres_db}"
            )
        company = await db.get(Company, DEFAULT_COMPANY_ID)
        brand = await db.scalar(
            select(Brand).where(
                Brand.company_id == DEFAULT_COMPANY_ID,
                Brand.slug == BRAND_SLUG,
                Brand.business_type == "restaurant",
                Brand.is_active.is_(True),
            )
        )
        if company is None or brand is None:
            raise RuntimeError("Phase 5 UAT Company/Restaurant Brand is missing")
        membership = await db.scalar(
            select(BrandBranch).where(
                BrandBranch.company_id == company.id,
                BrandBranch.brand_id == brand.id,
                BrandBranch.is_active.is_(True),
                BrandBranch.store_location_id.is_not(None),
            )
        )
        product = await db.scalar(
            select(Product).where(
                Product.company_id == company.id,
                Product.brand_id == brand.id,
                Product.sku == "FNB-DEMO-004",
                Product.product_type == "menu_item",
                Product.is_active.is_(True),
                Product.is_for_sale.is_(True),
            )
        )
        if membership is None or membership.store_location_id is None or product is None:
            raise RuntimeError("Phase 5 UAT store membership/menu product is incomplete")

        recipe = await db.scalar(
            select(Recipe).where(
                Recipe.company_id == company.id,
                Recipe.brand_id == brand.id,
                Recipe.product_id == product.id,
                Recipe.recipe_type == "menu_recipe",
                Recipe.is_active.is_(True),
            )
        )
        if recipe is None:
            raise RuntimeError("Phase 5 UAT load product recipe is missing")
        ingredient_ids = list(
            (
                await db.scalars(
                    select(RecipeIngredient.ingredient_id).where(
                        RecipeIngredient.recipe_id == recipe.id
                    )
                )
            ).all()
        )
        balances = list(
            (
                await db.scalars(
                    select(StockBalance).where(
                        StockBalance.company_id == company.id,
                        StockBalance.branch_id == membership.branch_id,
                        StockBalance.location_id == membership.store_location_id,
                        StockBalance.product_id.in_(ingredient_ids),
                    )
                )
            ).all()
        )
        if len(balances) != len(set(ingredient_ids)):
            raise RuntimeError("Phase 5 UAT recipe stock balances are incomplete")
        for balance in balances:
            balance.qty_on_hand = Decimal("1000000")
        await db.commit()
        return {
            "company_id": str(company.id),
            "branch_id": str(membership.branch_id),
            "brand_id": str(brand.id),
            "location_id": str(membership.store_location_id),
            "product_id": str(product.id),
            "unit_price": str(Decimal(product.selling_price)),
        }


async def verify(prefix: str, expected_sale_ids: set[uuid.UUID], unit_price: Decimal) -> dict[str, object]:
    async with AsyncSessionLocal() as db:
        sales = list(
            (
                await db.scalars(
                    select(SaleOrder).where(SaleOrder.client_order_id.like(f"{prefix}%"))
                )
            ).all()
        )
        sale_ids = {sale.id for sale in sales}
        if sale_ids != expected_sale_ids or len(sales) != ORDER_COUNT:
            raise RuntimeError(
                f"Offline replay changed canonical sales: sales={len(sales)} ids={len(sale_ids)}"
            )
        payment_count = int(
            await db.scalar(
                select(func.count(Payment.id)).where(Payment.order_id.in_(sale_ids))
            )
            or 0
        )
        session_count = int(
            await db.scalar(
                select(func.count(DiningSession.id)).where(DiningSession.sale_order_id.in_(sale_ids))
            )
            or 0
        )
        outbox_count = int(
            await db.scalar(
                select(func.count(OperationalOutboxEvent.id)).where(
                    OperationalOutboxEvent.aggregate_id.in_(sale_ids)
                )
            )
            or 0
        )
        journal_count = int(
            await db.scalar(
                select(func.count(JournalEntry.id)).where(
                    JournalEntry.reference_type == "SaleOrder",
                    JournalEntry.reference_id.in_([str(sale_id) for sale_id in sale_ids]),
                    JournalEntry.entry_type == "sale",
                )
            )
            or 0
        )
        movement_count = int(
            await db.scalar(
                select(func.count(StockMovement.id)).where(
                    StockMovement.reference_type == "pos_sale_recipe",
                    StockMovement.reference_id.in_([str(sale_id) for sale_id in sale_ids]),
                )
            )
            or 0
        )
        total = sum((Decimal(sale.total_amount) for sale in sales), Decimal("0"))
        expected_total = unit_price * ORDER_COUNT
        if (
            payment_count != ORDER_COUNT
            or session_count != ORDER_COUNT
            or outbox_count != ORDER_COUNT
            or journal_count != ORDER_COUNT
            or movement_count < ORDER_COUNT
            or total != expected_total
        ):
            raise RuntimeError(
                "Phase 5 load reconciliation failed: "
                f"payments={payment_count} sessions={session_count} outbox={outbox_count} "
                f"journals={journal_count} movements={movement_count} total={total}/{expected_total}"
            )
        return {
            "sales": len(sales),
            "payments": payment_count,
            "sessions": session_count,
            "outbox_events": outbox_count,
            "journals": journal_count,
            "recipe_movements": movement_count,
            "total": str(total.quantize(Decimal("0.01"))),
        }


async def run_async() -> None:
    context = await prepare()
    login = request_json(
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
        raise RuntimeError("Phase 5 readiness admin login did not return a token")
    token = str(login["access_token"])
    menu = request_json("GET", f"/api/v1/restaurant/store/{BRAND_SLUG}/menu", token=token)
    if not isinstance(menu, dict):
        raise RuntimeError("Phase 5 readiness store menu is invalid")
    product = next(
        (item for item in menu.get("products", []) if item.get("id") == context["product_id"]),
        None,
    )
    if product is None:
        raise RuntimeError("Phase 5 readiness load product is absent from the store menu")

    disconnected = False
    try:
        urllib.request.urlopen("http://127.0.0.1:1/health", timeout=0.25)
    except (urllib.error.URLError, TimeoutError, OSError):
        disconnected = True
    if not disconnected:
        raise RuntimeError("Reconnect precondition did not observe an unavailable endpoint")
    request_json("GET", "/health/ready", timeout=10)

    marker = uuid.uuid4().hex[:10]
    prefix = f"p5-ready-{marker}-"
    unit_price = Decimal(str(product["selling_price"]))
    now = datetime.now(timezone.utc).isoformat()
    orders = [
        {
            "client_order_id": f"{prefix}{index:03d}",
            "items": [{"product_id": context["product_id"], "qty": 1}],
            "payment_method": "cash",
            "paid_amount": str(unit_price),
            "payments": [{"payment_method": "cash", "amount": str(unit_price)}],
            "shift_id": menu["shift_id"],
            "location_id": menu["location_id"],
            "local_created_at": now,
            "offline_policy_version": menu["offline_policy_version"],
            "offline_authorization": menu["offline_authorization"],
            "is_offline": True,
        }
        for index in range(ORDER_COUNT)
    ]

    canonical_ids: set[uuid.UUID] = set()
    start = time.monotonic()
    for offset in range(0, ORDER_COUNT, BATCH_SIZE):
        response = request_json(
            "POST",
            f"/api/v1/restaurant/store/{BRAND_SLUG}/orders/sync",
            token=token,
            body={"orders": orders[offset : offset + BATCH_SIZE]},
            timeout=180,
        )
        if not isinstance(response, dict) or len(response.get("results", [])) != BATCH_SIZE:
            raise RuntimeError("Offline load batch response is incomplete")
        for item in response["results"]:
            if item["status"] != "synced" or not item.get("order"):
                raise RuntimeError(f"Offline load row did not sync: {item}")
            canonical_ids.add(uuid.UUID(item["order"]["sale_order_id"]))
    first_duration = time.monotonic() - start
    if len(canonical_ids) != ORDER_COUNT:
        raise RuntimeError(f"Offline load created {len(canonical_ids)} canonical sales")

    replay_ids: set[uuid.UUID] = set()
    replay_start = time.monotonic()
    for offset in range(0, ORDER_COUNT, BATCH_SIZE):
        response = request_json(
            "POST",
            f"/api/v1/restaurant/store/{BRAND_SLUG}/orders/sync",
            token=token,
            body={"orders": orders[offset : offset + BATCH_SIZE]},
            timeout=180,
        )
        if not isinstance(response, dict):
            raise RuntimeError("Offline replay response is invalid")
        replay_ids.update(
            uuid.UUID(item["order"]["sale_order_id"])
            for item in response.get("results", [])
            if item.get("status") == "synced" and item.get("order")
        )
    replay_duration = time.monotonic() - replay_start
    if replay_ids != canonical_ids:
        raise RuntimeError("Lost-acknowledgement replay did not return the canonical sale IDs")

    evidence = await verify(prefix, canonical_ids, unit_price)
    print(
        "PASS: Phase 5 readiness load/reconnect/idempotency "
        f"orders={ORDER_COUNT} batch_size={BATCH_SIZE} first_seconds={first_duration:.3f} "
        f"replay_seconds={replay_duration:.3f} reconnect_probe=passed "
        f"evidence={json.dumps(evidence, sort_keys=True)}"
    )


if __name__ == "__main__":
    asyncio.run(run_async())
