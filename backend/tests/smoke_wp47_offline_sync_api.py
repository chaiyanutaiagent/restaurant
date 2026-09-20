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
from app.models.integration import OperationalOutboxEvent
from app.models.offline_sync import OfflinePosOperation, OfflinePosOperationEvent
from app.models.pos import Payment, SaleOrder
from app.models.product import Product
from app.models.restaurant import Brand, BrandBranch, DiningSession, Recipe, RecipeIngredient
from app.models.stock import StockBalance, StockMovement
from app.schemas.restaurant import WapOfflinePaidOrderRequest
from app.services.offline_sync_service import offline_request_hash


ORDER_COUNT = 100
REPLAY_COUNT = 10
BATCH_SIZE = 50
BASE_URL = os.environ.get("WP47_UAT_INTERNAL_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
BRAND_SLUG = os.environ.get("WP47_UAT_BRAND_SLUG", "p5-uat-restaurant")
PRODUCT_SKU = os.environ.get("WP47_UAT_PRODUCT_SKU", "FNB-DEMO-004")
BRANCH_ID = os.environ.get("WP47_UAT_BRANCH_ID")
USERNAME = os.environ.get("WP47_UAT_USERNAME", "admin")
PASSWORD = os.environ.get("WP47_UAT_PASSWORD") or settings.default_admin_password


def request_json(
    method: str,
    path: str,
    *,
    token: str | None = None,
    device_token: str | None = None,
    body: object | None = None,
    expected: int = 200,
    timeout: float = 120,
) -> object:
    payload = None if body is None else json.dumps(body).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if device_token:
        headers["X-Device-Authorization"] = f"Bearer {device_token}"
    request = urllib.request.Request(f"{BASE_URL}{path}", data=payload, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status_code = response.status
            response_body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        status_code = exc.code
        response_body = exc.read().decode("utf-8")
    if status_code != expected:
        raise RuntimeError(f"{method} {path}: expected {expected}, got {status_code}: {response_body}")
    decoded = json.loads(response_body) if response_body else None
    return decoded.get("data", decoded) if isinstance(decoded, dict) else decoded


async def prepare() -> dict[str, str]:
    if not settings.pos_offline_mode_enabled:
        raise RuntimeError("WP47 smoke requires the UAT-only Offline feature flag")
    if settings.environment != "development" or not settings.saas_public_base_url.startswith("https://uat-"):
        raise RuntimeError("WP47 smoke refuses a non-UAT environment")
    async with AsyncSessionLocal() as db:
        brand = await db.scalar(select(Brand).where(Brand.slug == BRAND_SLUG, Brand.is_active.is_(True)))
        if brand is None:
            raise RuntimeError(f"UAT brand not found: {BRAND_SLUG}")
        membership_query = select(BrandBranch).where(
            BrandBranch.company_id == brand.company_id,
            BrandBranch.brand_id == brand.id,
            BrandBranch.is_active.is_(True),
            BrandBranch.store_location_id.is_not(None),
        )
        if BRANCH_ID:
            membership_query = membership_query.where(BrandBranch.branch_id == uuid.UUID(BRANCH_ID))
        membership = await db.scalar(membership_query.order_by(BrandBranch.created_at))
        product = await db.scalar(select(Product).where(
            Product.company_id == brand.company_id,
            Product.brand_id == brand.id,
            Product.sku == PRODUCT_SKU,
            Product.product_type == "menu_item",
            Product.is_active.is_(True),
            Product.is_for_sale.is_(True),
        ))
        if membership is None or membership.store_location_id is None or product is None:
            raise RuntimeError("UAT Brand/Branch/product/store location is incomplete")
        recipe = await db.scalar(select(Recipe).where(
            Recipe.company_id == brand.company_id,
            Recipe.brand_id == brand.id,
            Recipe.product_id == product.id,
            Recipe.recipe_type == "menu_recipe",
            Recipe.is_active.is_(True),
        ))
        if recipe is not None:
            ingredient_ids = list((await db.scalars(select(RecipeIngredient.ingredient_id).where(
                RecipeIngredient.recipe_id == recipe.id,
            ))).all())
            balances = list((await db.scalars(select(StockBalance).where(
                StockBalance.company_id == brand.company_id,
                StockBalance.branch_id == membership.branch_id,
                StockBalance.location_id == membership.store_location_id,
                StockBalance.product_id.in_(ingredient_ids),
            ))).all()) if ingredient_ids else []
            for balance in balances:
                balance.qty_on_hand = max(Decimal(balance.qty_on_hand), Decimal("1000000"))
            await db.commit()
        return {
            "company_id": str(brand.company_id),
            "brand_id": str(brand.id),
            "branch_id": str(membership.branch_id),
            "product_id": str(product.id),
            "unit_price": str(Decimal(product.selling_price)),
        }


def signed_order(
    *,
    index: int,
    prefix: str,
    context: dict[str, str],
    menu: dict,
    device_id: str,
    device_code: str,
    payment_method: str = "cash",
    company_id: str | None = None,
) -> dict:
    client_id = f"{prefix}{index:03d}"
    amount = Decimal(context["unit_price"])
    raw = {
        "client_order_id": client_id,
        "client_operation_id": client_id,
        "idempotency_key": f"offline-sale:{device_id}:{client_id}",
        "schema_version": "offline-pos-v1",
        "request_hash": "0" * 64,
        "company_id": company_id or context["company_id"],
        "brand_id": context["brand_id"],
        "branch_id": context["branch_id"],
        "station_key": device_code,
        "shift_id": menu["shift_id"],
        "location_id": menu["location_id"],
        "operation_type": "cash_sale",
        "sequence_no": index + 1,
        "price_snapshot_version": menu["offline_snapshot_version"],
        "currency": "THB",
        "local_created_at": datetime.now(timezone.utc).isoformat(),
        "offline_policy_version": menu["offline_policy_version"],
        "offline_authorization": menu["offline_authorization"],
        "items": [{
            "product_id": context["product_id"],
            "qty": 1,
            "special_request": None,
            "expected_unit_price": str(amount),
            "expected_price_version": None,
        }],
        "payment_method": payment_method,
        "paid_amount": str(amount),
        "payments": [{"payment_method": payment_method, "amount": str(amount), "reference_no": None}],
        "is_offline": True,
    }
    parsed = WapOfflinePaidOrderRequest.model_validate(raw)
    parsed = parsed.model_copy(update={"request_hash": offline_request_hash(parsed)})
    return json.loads(parsed.model_dump_json())


async def verify(prefix: str, canonical_ids: set[uuid.UUID], expected_total: Decimal) -> dict[str, int | str]:
    async with AsyncSessionLocal() as db:
        sales = list((await db.scalars(select(SaleOrder).where(SaleOrder.client_order_id.like(f"{prefix}%")))).all())
        sale_ids = {row.id for row in sales}
        reconciled = int(await db.scalar(select(func.count(OfflinePosOperation.id)).where(
            OfflinePosOperation.client_operation_id.like(f"{prefix}%"),
            OfflinePosOperation.status == "reconciled",
        )) or 0)
        event_count = int(await db.scalar(select(func.count(OfflinePosOperationEvent.id)).join(
            OfflinePosOperation,
            OfflinePosOperation.id == OfflinePosOperationEvent.operation_id,
        ).where(OfflinePosOperation.client_operation_id.like(f"{prefix}%"))) or 0)
        payments = int(await db.scalar(select(func.count(Payment.id)).where(Payment.order_id.in_(sale_ids))) or 0)
        sessions = int(await db.scalar(select(func.count(DiningSession.id)).where(DiningSession.sale_order_id.in_(sale_ids))) or 0)
        journals = int(await db.scalar(select(func.count(JournalEntry.id)).where(
            JournalEntry.reference_type == "SaleOrder",
            JournalEntry.reference_id.in_([str(value) for value in sale_ids]),
            JournalEntry.entry_type == "sale",
        )) or 0)
        outbox_events = int(await db.scalar(select(func.count(OperationalOutboxEvent.id)).where(
            OperationalOutboxEvent.aggregate_id.in_(sale_ids),
        )) or 0)
        stock_movements = int(await db.scalar(select(func.count(StockMovement.id)).where(
            StockMovement.reference_type == "pos_sale_recipe",
            StockMovement.reference_id.in_([str(value) for value in sale_ids]),
        )) or 0)
        total = sum((Decimal(row.total_amount) for row in sales), Decimal("0"))
        if sale_ids != canonical_ids or len(sales) != ORDER_COUNT or reconciled != ORDER_COUNT:
            raise RuntimeError(f"Exactly-once mismatch: sales={len(sales)} reconciled={reconciled}")
        if payments != ORDER_COUNT or sessions != ORDER_COUNT or journals != ORDER_COUNT or outbox_events != ORDER_COUNT:
            raise RuntimeError(
                f"Parity mismatch: payments={payments} sessions={sessions} journals={journals} events={outbox_events}"
            )
        if total != expected_total:
            raise RuntimeError(f"Total mismatch: {total} != {expected_total}")
        return {
            "sales": len(sales), "payments": payments, "sessions": sessions,
            "journals": journals, "outbox_events": outbox_events,
            "stock_movements": stock_movements, "offline_events": event_count,
            "total": str(total),
        }


async def run_async() -> None:
    if not PASSWORD:
        raise RuntimeError("WP47_UAT_PASSWORD or DEFAULT_ADMIN_PASSWORD is required")
    context = await prepare()
    login = request_json("POST", "/api/v1/auth/login", body={
        "company_id": context["company_id"], "branch_id": context["branch_id"],
        "username": USERNAME, "password": PASSWORD,
    })
    if not isinstance(login, dict):
        raise RuntimeError("Login response is invalid")
    token = str(login["access_token"])
    provisioning = request_json("POST", "/api/v1/system/devices", token=token, body={
        "name": f"WP47 Smoke {uuid.uuid4().hex[:6]}", "device_type": "counter",
        "branch_id": context["branch_id"], "station_key": None, "reason": "WP47 UAT automated smoke",
    }, expected=201)
    paired = request_json("POST", "/api/v1/device-auth/pair", body={
        "company_id": context["company_id"],
        "device_code": provisioning["device"]["device_code"],
        "pairing_pin": provisioning["pairing_pin"],
    })
    device_id = str(provisioning["device"]["id"])
    device_code = str(provisioning["device"]["device_code"])
    device_token = str(paired["access_token"])
    menu = request_json(
        "GET", f"/api/v1/restaurant/store/{BRAND_SLUG}/menu", token=token, device_token=device_token,
    )
    if not isinstance(menu, dict) or not menu.get("offline_mode_enabled") or not menu.get("offline_authorization"):
        raise RuntimeError("UAT offline menu lease was not issued to the paired Counter")

    network_transitions = 0
    for index in range(20):
        if index % 2:
            request_json("GET", "/health")
        else:
            try:
                urllib.request.urlopen("http://127.0.0.1:1/health", timeout=0.1)
            except (urllib.error.URLError, TimeoutError, OSError):
                pass
        network_transitions += 1

    marker = uuid.uuid4().hex[:10]
    prefix = f"wp47-{marker}-"
    orders = [signed_order(index=index, prefix=prefix, context=context, menu=menu, device_id=device_id, device_code=device_code) for index in range(ORDER_COUNT)]
    canonical_ids: set[uuid.UUID] = set()
    started = time.monotonic()
    for offset in range(0, ORDER_COUNT, BATCH_SIZE):
        response = request_json(
            "POST", f"/api/v1/restaurant/store/{BRAND_SLUG}/orders/sync",
            token=token, device_token=device_token, body={"orders": orders[offset:offset + BATCH_SIZE]}, timeout=180,
        )
        for row in response["results"]:
            if row["status"] != "synced" or row.get("sync_state") != "reconciled" or not row.get("order"):
                raise RuntimeError(f"Offline row did not reconcile: {row}")
            canonical_ids.add(uuid.UUID(row["order"]["sale_order_id"]))
    initial_seconds = time.monotonic() - started

    replay = request_json(
        "POST", f"/api/v1/restaurant/store/{BRAND_SLUG}/orders/sync",
        token=token, device_token=device_token, body={"orders": orders[:REPLAY_COUNT]}, timeout=180,
    )
    replay_ids = {uuid.UUID(row["order"]["sale_order_id"]) for row in replay["results"]}
    if len(replay_ids) != REPLAY_COUNT or not replay_ids.issubset(canonical_ids):
        raise RuntimeError("Lost-ack replay returned a non-canonical SaleOrder")

    tampered = signed_order(
        index=ORDER_COUNT + 1,
        prefix=f"{prefix}tamper-",
        context=context,
        menu=menu,
        device_id=device_id,
        device_code=device_code,
    )
    tampered["paid_amount"] = str(Decimal(context["unit_price"]) + Decimal("1"))
    tampered_result = request_json(
        "POST", f"/api/v1/restaurant/store/{BRAND_SLUG}/orders/sync",
        token=token, device_token=device_token, body={"orders": [tampered]},
    )["results"][0]
    if tampered_result["status"] != "quarantined":
        raise RuntimeError(f"Payload mismatch was not quarantined: {tampered_result}")

    promptpay = signed_order(index=ORDER_COUNT + 2, prefix=f"{prefix}deny-", context=context, menu=menu, device_id=device_id, device_code=device_code, payment_method="promptpay")
    promptpay_result = request_json(
        "POST", f"/api/v1/restaurant/store/{BRAND_SLUG}/orders/sync",
        token=token, device_token=device_token, body={"orders": [promptpay]},
    )["results"][0]
    if promptpay_result.get("error_code") != "payment_not_allowed_offline":
        raise RuntimeError(f"Offline PromptPay was not rejected: {promptpay_result}")

    cross_tenant = signed_order(
        index=ORDER_COUNT + 3,
        prefix=f"{prefix}tenant-",
        context=context,
        menu=menu,
        device_id=device_id,
        device_code=device_code,
        company_id=str(uuid.uuid4()),
    )
    cross_tenant_result = request_json(
        "POST", f"/api/v1/restaurant/store/{BRAND_SLUG}/orders/sync",
        token=token, device_token=device_token, body={"orders": [cross_tenant]},
    )["results"][0]
    if cross_tenant_result.get("error_code") != "tenant_scope_mismatch":
        raise RuntimeError(f"Cross-tenant payload was not quarantined: {cross_tenant_result}")

    evidence = await verify(prefix, canonical_ids, Decimal(context["unit_price"]) * ORDER_COUNT)
    inquiry = request_json("GET", f"/api/v1/restaurant/offline-sync/{orders[0]['client_operation_id']}", token=token)
    if inquiry.get("status") != "reconciled":
        raise RuntimeError(f"Inquiry did not return reconciled: {inquiry}")

    resolved = request_json(
        "POST",
        f"/api/v1/restaurant/offline-sync/{tampered['client_operation_id']}/resolve",
        token=token,
        body={"reason": "WP47 intentional hash-mismatch evidence captured"},
    )
    if resolved.get("status") != "rejected":
        raise RuntimeError(f"Quarantined smoke operation was not resolved: {resolved}")

    request_json("POST", f"/api/v1/system/devices/{device_id}/revoke", token=token, body={"reason": "WP47 smoke completed"})
    request_json(
        "POST", f"/api/v1/restaurant/store/{BRAND_SLUG}/orders/sync",
        token=token, device_token=device_token, body={"orders": [orders[0]]}, expected=401,
    )
    print(json.dumps({
        "status": "pass", "orders": ORDER_COUNT, "lost_ack_replays": REPLAY_COUNT,
        "network_transitions": network_transitions, "device_revocation": "pass",
        "offline_promptpay": "rejected", "payload_mismatch": "quarantined",
        "cross_tenant": "quarantined",
        "initial_seconds": round(initial_seconds, 3), "evidence": evidence,
    }, sort_keys=True))


if __name__ == "__main__":
    asyncio.run(run_async())
