from __future__ import annotations

from decimal import Decimal
import uuid

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.integration import OperationalOutboxEvent


SALE_COMPLETED_EVENT = "restaurant.sale.completed.v1"


def sale_completed_idempotency_key(order_id: uuid.UUID) -> str:
    return f"{SALE_COMPLETED_EVENT}:{order_id}"


def sale_completed_payload(
    *,
    order_id: uuid.UUID,
    order_number: str,
    total_amount: Decimal,
    item_count: int,
    payment_methods: list[str],
) -> dict[str, object]:
    return {
        "schema": "restaurant.sale.completed",
        "version": 1,
        "sale_order_id": str(order_id),
        "order_number": order_number,
        "total_amount": str(Decimal(total_amount).quantize(Decimal("0.01"))),
        "currency": "THB",
        "item_count": item_count,
        "payment_methods": sorted(set(payment_methods)),
        "stock_reference": {"type": "SaleOrder", "id": str(order_id)},
    }


async def ensure_sale_completed_handoff(
    db: AsyncSession,
    *,
    company_id: uuid.UUID,
    brand_id: uuid.UUID | None,
    branch_id: uuid.UUID,
    order_id: uuid.UUID,
    order_number: str,
    total_amount: Decimal,
    item_count: int,
    payment_methods: list[str],
) -> OperationalOutboxEvent:
    idempotency_key = sale_completed_idempotency_key(order_id)
    event_id = (
        await db.execute(
            insert(OperationalOutboxEvent)
            .values(
                id=uuid.uuid4(),
                company_id=company_id,
                brand_id=brand_id,
                branch_id=branch_id,
                event_type=SALE_COMPLETED_EVENT,
                contract_version=1,
                aggregate_type="SaleOrder",
                aggregate_id=order_id,
                idempotency_key=idempotency_key,
                payload=sale_completed_payload(
                    order_id=order_id,
                    order_number=order_number,
                    total_amount=total_amount,
                    item_count=item_count,
                    payment_methods=payment_methods,
                ),
            )
            .on_conflict_do_nothing(index_elements=[OperationalOutboxEvent.idempotency_key])
            .returning(OperationalOutboxEvent.id)
        )
    ).scalar_one_or_none()
    if event_id is None:
        existing = await db.scalar(
            select(OperationalOutboxEvent).where(
                OperationalOutboxEvent.idempotency_key == idempotency_key
            )
        )
        if existing is None:
            raise RuntimeError("Sale handoff conflict did not return the existing event")
        return existing
    event = await db.get(OperationalOutboxEvent, event_id)
    if event is None:
        raise RuntimeError("Sale handoff event was not created")
    return event
