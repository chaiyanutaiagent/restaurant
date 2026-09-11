from __future__ import annotations

import asyncio
from datetime import date, datetime, timezone
from decimal import Decimal
import hashlib
import json
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import takeaway_engine
from app.dependencies import TokenData
from app.models.takeaway import (
    TakeawayKitchenTicket,
    TakeawayOperationalOutbox,
    TakeawayProductionLine,
    TakeawayReferenceProjection,
    TakeawayStockBalance,
)
from app.schemas.takeaway import (
    TakeawayCatalogItemCreate,
    TakeawayCategoryCreate,
    TakeawayCentralOrderCreate,
    TakeawayCentralOrderLineCreate,
    TakeawayCreditEntryCreate,
    TakeawayCreditLimitUpdate,
    TakeawayPaymentCreate,
    TakeawayProductionBatchCreate,
    TakeawayProductionComplete,
    TakeawayProductionCompleteLine,
    TakeawayProductionLineCreate,
    TakeawaySaleCreate,
    TakeawaySaleLine,
    TakeawayShiftClose,
    TakeawayShiftOpen,
    TakeawayStockMovementCreate,
    TakeawayTransferCreate,
    TakeawayTransferLineCreate,
    TakeawayTransferStatusUpdate,
)
from app.services.takeaway_service import TakeawayService


def projection(
    *,
    aggregate_type: str,
    aggregate_id: uuid.UUID,
    company_id: uuid.UUID,
    payload: dict[str, object],
) -> TakeawayReferenceProjection:
    canonical = json.dumps(payload, default=str, sort_keys=True)
    return TakeawayReferenceProjection(
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        company_id=company_id,
        source_updated_at=datetime(2026, 9, 11, tzinfo=timezone.utc),
        payload=payload,
        source_digest=hashlib.sha256(canonical.encode()).hexdigest(),
    )


async def run() -> None:
    if takeaway_engine is None:
        raise RuntimeError("TAKEAWAY_DATABASE_URL is required")
    company_id = uuid.uuid4()
    brand_a = uuid.uuid4()
    brand_b = uuid.uuid4()
    branch_id = uuid.uuid4()
    brand_branch_id = uuid.uuid4()
    user_id = uuid.uuid4()
    central_location = uuid.uuid4()
    raw_item = uuid.uuid4()
    output_a = uuid.uuid4()
    output_b = uuid.uuid4()
    business_date = date(2026, 9, 11)

    async with takeaway_engine.connect() as connection:
        outer = await connection.begin()
        db = AsyncSession(bind=connection, expire_on_commit=False)
        try:
            db.add_all(
                [
                    projection(
                        aggregate_type="company",
                        aggregate_id=company_id,
                        company_id=company_id,
                        payload={"id": str(company_id), "name": "Takeaway Smoke", "is_active": True},
                    ),
                    projection(
                        aggregate_type="brand",
                        aggregate_id=brand_a,
                        company_id=company_id,
                        payload={
                            "id": str(brand_a),
                            "company_id": str(company_id),
                            "name": "Brand A",
                            "business_type": "takeaway",
                            "is_active": True,
                        },
                    ),
                    projection(
                        aggregate_type="brand",
                        aggregate_id=brand_b,
                        company_id=company_id,
                        payload={
                            "id": str(brand_b),
                            "company_id": str(company_id),
                            "name": "Brand B",
                            "business_type": "takeaway",
                            "is_active": True,
                        },
                    ),
                    projection(
                        aggregate_type="branch",
                        aggregate_id=branch_id,
                        company_id=company_id,
                        payload={"id": str(branch_id), "company_id": str(company_id), "is_active": True},
                    ),
                    projection(
                        aggregate_type="brand_branch",
                        aggregate_id=brand_branch_id,
                        company_id=company_id,
                        payload={
                            "id": str(brand_branch_id),
                            "company_id": str(company_id),
                            "brand_id": str(brand_a),
                            "branch_id": str(branch_id),
                            "is_active": True,
                        },
                    ),
                ]
            )
            await db.flush()
            current_a = TokenData(
                user_id=user_id,
                company_id=company_id,
                branch_id=branch_id,
                brand_id=brand_a,
                business_type="takeaway",
                target_database="takeaway",
                permissions=["*"],
                scope_types=["company"],
            )
            service_a = TakeawayService(db, current_a)
            category = await service_a.create_category(
                TakeawayCategoryCreate(brand_id=brand_a, code="food", name="อาหาร")
            )
            item = await service_a.create_catalog_item(
                TakeawayCatalogItemCreate(
                    brand_id=brand_a,
                    category_id=category.id,
                    sku="SMOKE-FOOD-1",
                    name="หมูย่างทดสอบ",
                    price=Decimal("100"),
                    tax_rate=Decimal("7"),
                    kitchen_station="grill",
                    track_stock=True,
                )
            )
            await service_a.create_stock_movement(
                TakeawayStockMovementCreate(
                    location_id=branch_id,
                    item_id=item.id,
                    quantity_delta=Decimal("10"),
                    unit_cost=Decimal("40"),
                    movement_type="receive",
                    brand_id=brand_a,
                    branch_id=branch_id,
                    idempotency_key=f"smoke-receive-{uuid.uuid4()}",
                )
            )
            shift = await service_a.open_shift(
                TakeawayShiftOpen(business_date=business_date, opening_cash=Decimal("500"))
            )
            sale_payload = TakeawaySaleCreate(
                brand_id=brand_a,
                branch_id=branch_id,
                shift_id=shift.id,
                idempotency_key=f"smoke-sale-{uuid.uuid4()}",
                items=[TakeawaySaleLine(catalog_item_id=item.id, quantity=Decimal("2"))],
                payment=TakeawayPaymentCreate(
                    method="cash",
                    amount=Decimal("214"),
                    idempotency_key=f"smoke-payment-{uuid.uuid4()}",
                ),
            )
            order, pickup_token, replayed = await service_a.create_sale(sale_payload)
            replay_order, replay_token, was_replayed = await service_a.create_sale(sale_payload)
            assert not replayed and pickup_token and was_replayed and replay_token is None
            assert replay_order.id == order.id
            tickets = list(
                await db.scalars(
                    select(TakeawayKitchenTicket).where(TakeawayKitchenTicket.order_id == order.id)
                )
            )
            for ticket in tickets:
                await service_a.update_kitchen_ticket(ticket.id, "preparing")
                await service_a.update_kitchen_ticket(ticket.id, "ready")
            await service_a.mark_picked_up(order.id)

            round_row = await service_a.create_central_round(brand_a, business_date, 1)
            central = await service_a.create_central_order(
                TakeawayCentralOrderCreate(
                    brand_id=brand_a,
                    branch_id=branch_id,
                    round_id=round_row.id,
                    order_type="unlisted",
                    items=[
                        TakeawayCentralOrderLineCreate(
                            item_name="สินค้าไม่อยู่ในแคตตาล็อก",
                            quantity=Decimal("3"),
                            unit="ถุง",
                            source_kind="unlisted",
                        )
                    ],
                )
            )
            for state in ("approved", "in_production", "packed", "shipped", "received"):
                central = await service_a.update_central_order_status(central.id, state)
            assert central.status == "received"

            await service_a.create_stock_movement(
                TakeawayStockMovementCreate(
                    location_id=central_location,
                    item_id=raw_item,
                    quantity_delta=Decimal("10"),
                    unit_cost=Decimal("50"),
                    movement_type="receive",
                    idempotency_key=f"smoke-raw-{uuid.uuid4()}",
                )
            )
            batch_a = await service_a.create_production_batch(
                TakeawayProductionBatchCreate(
                    brand_id=brand_a,
                    location_id=central_location,
                    lines=[
                        TakeawayProductionLineCreate(item_id=raw_item, line_type="input", planned_qty=Decimal("2"), unit="kg"),
                        TakeawayProductionLineCreate(item_id=output_a, line_type="output", planned_qty=Decimal("2"), unit="kg"),
                    ],
                )
            )
            lines_a = list(
                await db.scalars(
                    select(TakeawayProductionLine).where(
                        TakeawayProductionLine.batch_id == batch_a.id
                    )
                )
            )
            await service_a.complete_production_batch(
                batch_a.id,
                TakeawayProductionComplete(
                    idempotency_key=f"smoke-batch-a-{uuid.uuid4()}",
                    lines=[TakeawayProductionCompleteLine(line_id=line.id, actual_qty=line.planned_qty) for line in lines_a],
                ),
            )

            current_b = TokenData(
                user_id=user_id,
                company_id=company_id,
                branch_id=None,
                brand_id=brand_b,
                business_type="takeaway",
                target_database="takeaway",
                permissions=["*"],
                scope_types=["brand"],
            )
            service_b = TakeawayService(db, current_b)
            batch_b = await service_b.create_production_batch(
                TakeawayProductionBatchCreate(
                    brand_id=brand_b,
                    location_id=central_location,
                    lines=[
                        TakeawayProductionLineCreate(item_id=raw_item, line_type="input", planned_qty=Decimal("3"), unit="kg"),
                        TakeawayProductionLineCreate(item_id=output_b, line_type="output", planned_qty=Decimal("3"), unit="kg"),
                    ],
                )
            )
            lines_b = list(await db.scalars(select(TakeawayProductionLine).where(TakeawayProductionLine.batch_id == batch_b.id)))
            await service_b.complete_production_batch(
                batch_b.id,
                TakeawayProductionComplete(
                    idempotency_key=f"smoke-batch-b-{uuid.uuid4()}",
                    lines=[TakeawayProductionCompleteLine(line_id=line.id, actual_qty=line.planned_qty) for line in lines_b],
                ),
            )
            shared_raw = await db.scalar(
                select(TakeawayStockBalance).where(
                    TakeawayStockBalance.company_id == company_id,
                    TakeawayStockBalance.location_id == central_location,
                    TakeawayStockBalance.item_id == raw_item,
                )
            )
            assert shared_raw is not None and shared_raw.on_hand_qty == Decimal("5.0000")

            transfer = await service_a.create_transfer(
                TakeawayTransferCreate(
                    brand_id=brand_a,
                    from_location_id=central_location,
                    to_location_id=branch_id,
                    items=[TakeawayTransferLineCreate(item_id=output_a, requested_qty=Decimal("1"), unit="kg")],
                )
            )
            await service_a.update_transfer(
                transfer.id,
                TakeawayTransferStatusUpdate(status="shipped", idempotency_key=f"smoke-ship-{uuid.uuid4()}"),
            )
            transfer = await service_a.update_transfer(
                transfer.id,
                TakeawayTransferStatusUpdate(status="received", idempotency_key=f"smoke-receive-{uuid.uuid4()}"),
            )
            assert transfer.status == "received"

            account = await service_a.set_credit_limit(
                TakeawayCreditLimitUpdate(brand_id=brand_a, branch_id=branch_id, credit_limit=Decimal("1000"))
            )
            account = await service_a.create_credit_entry(
                account.id,
                TakeawayCreditEntryCreate(
                    entry_type="charge",
                    amount=Decimal("300"),
                    reference_type="smoke",
                    reference_id=uuid.uuid4(),
                    idempotency_key=f"smoke-credit-{uuid.uuid4()}",
                ),
            )
            assert account.balance == Decimal("300.00")
            summary = await service_a.sales_summary(date_from=business_date, date_to=business_date)
            assert summary["order_count"] == 1 and summary["gross_sales"] == "214.00"
            shift = await service_a.close_shift(
                shift.id,
                TakeawayShiftClose(counted_cash=Decimal("714")),
            )
            assert shift.expected_cash == Decimal("714.00")
            outbox_count = int(
                await db.scalar(
                    select(func.count()).select_from(TakeawayOperationalOutbox).where(
                        TakeawayOperationalOutbox.company_id == company_id
                    )
                )
                or 0
            )
            assert outbox_count >= 10
            print(
                json.dumps(
                    {
                        "status": "ok",
                        "paid_first_order": order.order_number,
                        "idempotent_replay": was_replayed,
                        "shared_raw_balance_after_two_brands": str(shared_raw.on_hand_qty),
                        "central_order_status": central.status,
                        "transfer_status": transfer.status,
                        "credit_balance": str(account.balance),
                        "outbox_events": outbox_count,
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                )
            )
        finally:
            await db.close()
            await outer.rollback()


if __name__ == "__main__":
    asyncio.run(run())
