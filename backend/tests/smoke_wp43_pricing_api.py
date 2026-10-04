from __future__ import annotations

import asyncio
from decimal import Decimal
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import settings
from app.main import app
from app.models.pos import Payment, SaleOrder
from app.models.pricing import PriceOverrideAudit
from app.models.product import Product
from app.models.stock import StockBalance
from tests.smoke_approval_api import (
    MANAGER_PIN,
    PASSWORD,
    expect,
    expect_detail_code,
    issue_approval,
    login,
    prepare,
)


def pricing_payload(context: dict[str, str], key: str, *, expected: str = "100", override: str | None = None, cart_version: int = 1) -> dict:
    line: dict = {
        "product_id": context["product_id"],
        "qty": 1,
        "discount_amount": 0,
        "discount_type": "amount",
        "expected_unit_price": expected,
    }
    if override is not None:
        line["price_override"] = {
            "requested_unit_price": override,
            "reason_code": "price_match",
            "reason": "WP43 isolated price match",
        }
    return {
        "items": [line],
        "discount_amount": 0,
        "discount_type": "amount",
        "channel": "pos",
        "currency": "THB",
        "idempotency_key": key,
        "cart_version": cart_version,
    }


def sale_payload(context: dict[str, str], shift_id: str, quote: dict, client_order_id: str, *, expected: str = "100", override: str | None = None, cart_version: int = 1) -> dict:
    line: dict = {
        "product_id": context["product_id"],
        "qty": 1,
        "unit_price": "0.01",
        "original_price": expected,
        "discount_amount": 0,
        "discount_type": "amount",
        "vat_type": "excluded",
        "vat_rate": 99,
    }
    if override is not None:
        line["price_override"] = {
            "requested_unit_price": override,
            "reason_code": "price_match",
            "reason": "WP43 isolated price match",
        }
    total = Decimal(str(quote["total_amount"]))
    return {
        "shift_id": shift_id,
        "location_id": context["location_id"],
        "items": [line],
        "discount_amount": 0,
        "discount_type": "amount",
        "payment_method": "cash",
        "paid_amount": str(total),
        "client_order_id": client_order_id,
        "channel": "pos",
        "currency": "THB",
        "cart_version": cart_version,
        "pricing_quote_id": quote["quote_id"],
        "pricing_calculation_hash": quote["calculation_hash"],
    }


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


async def verify(context: dict[str, str], sale_keys: tuple[str, str]) -> None:
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db:
        orders = list(
            (
                await db.scalars(
                    select(SaleOrder).where(SaleOrder.client_order_id.in_(sale_keys))
                )
            ).all()
        )
        if len(orders) != 2:
            raise RuntimeError(f"Expected two replay-safe WP43 sales, got {len(orders)}")
        order_ids = [order.id for order in orders]
        payment_count = await db.scalar(
            select(func.count(Payment.id)).where(Payment.order_id.in_(order_ids))
        )
        if payment_count != 2:
            raise RuntimeError(f"Expected two payments without replay duplicates, got {payment_count}")
        balance = await db.scalar(
            select(StockBalance).where(
                StockBalance.product_id == uuid.UUID(context["product_id"]),
                StockBalance.location_id == uuid.UUID(context["location_id"]),
            )
        )
        if balance is None or Decimal(balance.qty_on_hand) != Decimal("98"):
            raise RuntimeError(f"Expected stock 98 after two sales, got {balance.qty_on_hand if balance else None}")
        override_audits = list(
            (
                await db.scalars(
                    select(PriceOverrideAudit).where(PriceOverrideAudit.order_id.in_(order_ids))
                )
            ).all()
        )
        if len(override_audits) != 1:
            raise RuntimeError(f"Expected one immutable override audit, got {len(override_audits)}")
        audit = override_audits[0]
        if audit.reason_code != "price_match" or audit.requester_id == audit.approver_id:
            raise RuntimeError("Override audit is missing reason code or separation of duties")
        try:
            await db.execute(
                text("UPDATE price_override_audits SET reason = 'tampered' WHERE id = :id"),
                {"id": audit.id},
            )
            await db.commit()
        except Exception:
            await db.rollback()
        else:
            raise RuntimeError("Append-only override audit accepted an UPDATE")
    await engine.dispose()


def run() -> None:
    context = asyncio.run(prepare())
    with TestClient(app) as client:
        manager_headers = login(client, context["manager_username"])
        cashier_headers = login(client, context["cashier_username"])
        expect(
            client.put(
                "/api/v1/approvals/manager-pin",
                headers=manager_headers,
                json={"current_password": PASSWORD, "pin": MANAGER_PIN},
            ),
            200,
        )
        shift = expect(
            client.post(
                "/api/v1/pos/shifts/open",
                headers=cashier_headers,
                json={"location_id": context["location_id"], "opening_cash": 0},
            ),
            201,
        )
        expect_detail_code(
            client.post(
                "/api/v1/restaurant/wap/orders",
                headers=cashier_headers,
                json={
                    "items": [
                        {
                            "product_id": context["product_id"],
                            "qty": 1,
                            "expected_unit_price": "100",
                        }
                    ],
                    "payment_method": "cash",
                    "paid_amount": "100",
                    "payments": [{"payment_method": "cash", "amount": "100"}],
                    "shift_id": shift["id"],
                    "location_id": context["location_id"],
                    "client_order_id": f"wp43-offline-{uuid.uuid4()}",
                    "is_offline": True,
                },
            ),
            409,
            "stale_price",
        )

        tamper_quote = expect(
            client.post(
                "/api/v1/pos/pricing/calculate",
                headers=cashier_headers,
                json=pricing_payload(context, f"wp43-price-{uuid.uuid4()}", expected="0.01"),
            ),
            200,
        )
        if Decimal(str(tamper_quote["total_amount"])) != Decimal("100") or not tamper_quote["has_price_discrepancy"]:
            raise RuntimeError("Client price/VAT tampering changed the server-authoritative total")
        tamper_key = f"wp43-sale-{uuid.uuid4()}"
        tamper_sale_payload = sale_payload(
            context,
            shift["id"],
            tamper_quote,
            tamper_key,
            expected="0.01",
        )
        tamper_sale = expect(
            client.post("/api/v1/pos/sales", headers=cashier_headers, json=tamper_sale_payload),
            201,
        )
        if Decimal(str(tamper_sale["total_amount"])) != Decimal("100"):
            raise RuntimeError("Tampered checkout did not settle at the server total")
        expect(
            client.post("/api/v1/pos/sales", headers=cashier_headers, json=tamper_sale_payload),
            200,
        )
        expect_detail_code(
            client.post(
                "/api/v1/pos/sales",
                headers=cashier_headers,
                json={**tamper_sale_payload, "note": "changed replay"},
            ),
            409,
            "duplicate_request",
        )

        override_quote = expect(
            client.post(
                "/api/v1/pos/pricing/calculate",
                headers=cashier_headers,
                json=pricing_payload(context, f"wp43-override-price-{uuid.uuid4()}", override="80"),
            ),
            200,
        )
        if not override_quote["requires_price_override_approval"]:
            raise RuntimeError("Override threshold did not require manager approval")
        override_key = f"wp43-override-sale-{uuid.uuid4()}"
        override_sale_payload = sale_payload(
            context,
            shift["id"],
            override_quote,
            override_key,
            override="80",
        )
        expect_detail_code(
            client.post("/api/v1/pos/sales", headers=cashier_headers, json=override_sale_payload),
            403,
            "approval_required",
        )
        approval = expect(
            issue_approval(
                client,
                cashier_headers,
                context,
                action="pos.price.override",
                request_payload=override_sale_payload,
                reason="Approve WP43 price match",
            ),
            200,
        )
        approved_sale = expect(
            client.post(
                "/api/v1/pos/sales",
                headers=cashier_headers,
                json={**override_sale_payload, "price_override_approval_token": approval["approval_token"]},
            ),
            201,
        )
        if Decimal(str(approved_sale["total_amount"])) != Decimal("80"):
            raise RuntimeError("Approved override did not use the server-approved price")

        manager_quote = expect(
            client.post(
                "/api/v1/pos/pricing/calculate",
                headers=manager_headers,
                json=pricing_payload(context, f"wp43-manager-price-{uuid.uuid4()}"),
            ),
            200,
        )
        expect_detail_code(
            client.post(
                "/api/v1/pos/sales",
                headers=cashier_headers,
                json=sale_payload(context, shift["id"], manager_quote, f"wp43-user-mismatch-{uuid.uuid4()}"),
            ),
            409,
            "context_mismatch",
        )

        stale_quote = expect(
            client.post(
                "/api/v1/pos/pricing/calculate",
                headers=cashier_headers,
                json=pricing_payload(context, f"wp43-stale-price-{uuid.uuid4()}"),
            ),
            200,
        )
        asyncio.run(set_product_price(context["product_id"], "120"))
        expect_detail_code(
            client.post(
                "/api/v1/pos/sales",
                headers=cashier_headers,
                json=sale_payload(context, shift["id"], stale_quote, f"wp43-stale-sale-{uuid.uuid4()}"),
            ),
            409,
            "stale_price",
        )

        version_quote = expect(
            client.post(
                "/api/v1/pos/pricing/calculate",
                headers=cashier_headers,
                json=pricing_payload(context, f"wp43-version-price-{uuid.uuid4()}", expected="120"),
            ),
            200,
        )
        expect_detail_code(
            client.post(
                "/api/v1/pos/sales",
                headers=cashier_headers,
                json=sale_payload(
                    context,
                    shift["id"],
                    version_quote,
                    f"wp43-version-sale-{uuid.uuid4()}",
                    expected="120",
                    cart_version=2,
                ),
            ),
            409,
            "version_conflict",
        )

    asyncio.run(verify(context, (tamper_key, override_key)))
    print(
        "wp43_pricing_api_smoke=ok authority=true tamper=true vat=true override=true "
        "approval=true separation_of_duties=true idempotency=true replay=true "
        "context_mismatch=true stale=true offline_fail_closed=true version_conflict=true "
        "audit_immutable=true reconciliation=true"
    )


if __name__ == "__main__":
    run()
