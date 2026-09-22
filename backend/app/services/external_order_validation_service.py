from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product import Product
from app.schemas.api_integration import PublicOrderCreate


MONEY = Decimal("0.01")
ALLOWED_PAYMENT_STATES = {"paid", "pending", "unpaid", "cod"}


async def validate_external_order(
    db: AsyncSession,
    company_id,
    payload: PublicOrderCreate,
) -> tuple[list[dict[str, Any]], Decimal | None, list[str]]:
    """Return server-priced items, authoritative total, and review reasons.

    Client prices and totals are evidence only. Missing/invalid mappings are
    quarantined as needs_review and cannot be fulfilled.
    """
    reasons: list[str] = []
    skus = list(dict.fromkeys(item.sku.strip() for item in payload.items if item.sku.strip()))
    products = list(
        (
            await db.scalars(
                select(Product).where(
                    Product.company_id == company_id,
                    Product.sku.in_(skus),
                    Product.deleted_at.is_(None),
                    Product.is_active.is_(True),
                    Product.is_for_sale.is_(True),
                )
            )
        ).all()
    )
    product_by_sku = {row.sku: row for row in products}
    normalized: list[dict[str, Any]] = []
    server_total = Decimal("0")

    if not payload.items:
        reasons.append("items_required")
    for index, item in enumerate(payload.items):
        sku = item.sku.strip()
        product = product_by_sku.get(sku)
        if product is None:
            reasons.append(f"sku_not_found:{sku or index}")
            continue
        try:
            qty = Decimal(str(item.qty))
        except (InvalidOperation, ValueError):
            reasons.append(f"invalid_qty:{sku}")
            continue
        if qty <= 0:
            reasons.append(f"invalid_qty:{sku}")
            continue
        server_price = Decimal(str(product.selling_price)).quantize(MONEY, rounding=ROUND_HALF_UP)
        client_price = Decimal(str(item.unit_price)).quantize(MONEY, rounding=ROUND_HALF_UP)
        if client_price != server_price:
            reasons.append(f"price_mismatch:{sku}")
        line_total = (qty * server_price).quantize(MONEY, rounding=ROUND_HALF_UP)
        server_total += line_total
        normalized.append(
            {
                "sku": sku,
                "product_id": str(product.id),
                "qty": str(qty),
                "client_unit_price": str(client_price),
                "server_unit_price": str(server_price),
                "line_total": str(line_total),
            }
        )

    if len(normalized) != len(payload.items):
        server_total_value: Decimal | None = None
    else:
        server_total_value = server_total.quantize(MONEY, rounding=ROUND_HALF_UP)
        client_total = Decimal(str(payload.total_amount)).quantize(MONEY, rounding=ROUND_HALF_UP)
        if client_total != server_total_value:
            reasons.append("total_mismatch")

    payment_state = (payload.payment_status or "pending").strip().lower()
    if payment_state not in ALLOWED_PAYMENT_STATES:
        reasons.append("unsupported_payment_status")
    return normalized, server_total_value, list(dict.fromkeys(reasons))
