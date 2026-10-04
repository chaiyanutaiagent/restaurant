from __future__ import annotations

from decimal import Decimal
import uuid

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.integration import OperationalOutboxEvent


SALE_COMPLETED_EVENT = "restaurant.sale.completed.v1"
SALE_STATE_CHANGED_EVENT = "pos.sale.state.changed.v1"


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


def sale_state_changed_idempotency_key(
    order_id: uuid.UUID,
    source_status: str,
    refund_amount: Decimal,
) -> str:
    normalized_refund = Decimal(refund_amount).quantize(Decimal("0.01"))
    return f"{SALE_STATE_CHANGED_EVENT}:{order_id}:{source_status}:{normalized_refund}"


def sale_state_changed_payload(
    *,
    order_id: uuid.UUID,
    order_number: str,
    source_status: str,
    total_amount: Decimal,
    refund_amount: Decimal,
) -> dict[str, object]:
    total = Decimal(total_amount).quantize(Decimal("0.01"))
    refunded = Decimal(refund_amount).quantize(Decimal("0.01"))
    return {
        "schema": "pos.sale.state.changed",
        "version": 1,
        "sale_order_id": str(order_id),
        "order_number": order_number,
        "source_status": source_status,
        "total_amount": str(total),
        "refund_amount": str(refunded),
        "net_amount": str(max(Decimal("0.00"), total - refunded)),
        "currency": "THB",
    }


async def ensure_sale_state_changed_handoff(
    db: AsyncSession,
    *,
    company_id: uuid.UUID,
    brand_id: uuid.UUID | None,
    branch_id: uuid.UUID,
    order_id: uuid.UUID,
    order_number: str,
    source_status: str,
    total_amount: Decimal,
    refund_amount: Decimal,
) -> OperationalOutboxEvent:
    idempotency_key = sale_state_changed_idempotency_key(
        order_id,
        source_status,
        refund_amount,
    )
    event_id = (
        await db.execute(
            insert(OperationalOutboxEvent)
            .values(
                id=uuid.uuid4(),
                company_id=company_id,
                brand_id=brand_id,
                branch_id=branch_id,
                event_type=SALE_STATE_CHANGED_EVENT,
                contract_version=1,
                aggregate_type="SaleOrder",
                aggregate_id=order_id,
                idempotency_key=idempotency_key,
                payload=sale_state_changed_payload(
                    order_id=order_id,
                    order_number=order_number,
                    source_status=source_status,
                    total_amount=total_amount,
                    refund_amount=refund_amount,
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
            raise RuntimeError("Sale state handoff conflict did not return the existing event")
        return existing
    event = await db.get(OperationalOutboxEvent, event_id)
    if event is None:
        raise RuntimeError("Sale state handoff event was not created")
    return event
