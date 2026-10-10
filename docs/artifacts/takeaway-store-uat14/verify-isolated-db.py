"""Candidate integration check. ONLY an isolated loopback PostgreSQL clone is allowed."""
import asyncio
import json
import uuid
from copy import copy
from sqlalchemy import select, text, func
from app.database import TakeawaySessionLocal
from app.dependencies import TokenData
from app.models.takeaway import TakeawayOrder, TakeawayReceipt, TakeawayOperationalOutbox
from app.schemas.takeaway import TakeawayReceiptPrintCreate
from app.services.takeaway_service import TakeawayService

ORDER = uuid.UUID("b27b4470-7506-4c2e-b901-ac79b1911aaf")

async def main():
    async with TakeawaySessionLocal() as db:
        assert (await db.execute(text("SELECT current_database(), host(inet_server_addr())"))).one() == ("takeaway_ops_db", "127.0.0.1")
        order = await db.get(TakeawayOrder, ORDER)
        current = TokenData(user_id=uuid.uuid4(), company_id=order.company_id, brand_id=order.brand_id,
            branch_id=order.branch_id, business_type="takeaway", target_database="takeaway", permissions=["takeaway.sale.create"])
        receipt = await db.scalar(select(TakeawayReceipt).where(TakeawayReceipt.order_id == ORDER))
        before = receipt.print_count
        financial = {k: v for k, v in receipt.payload.items() if k not in ("print_copies", "preparation_items", "note")}
        status = (order.status, order.fulfillment_status)
    batch = uuid.uuid4()
    async def record(copy):
        async with TakeawaySessionLocal() as db:
            return (await TakeawayService(db, current).mark_receipt_printed(ORDER,
                TakeawayReceiptPrintCreate(copy_type=copy, batch_id=batch, idempotency_key="isolated-fixture")))[1]
    # Actual PostgreSQL locks, separate connections, concurrent duplicate confirmations.
    results = await asyncio.gather(*(record(copy) for copy in ("customer", "customer", "preparation", "preparation")))
    assert sorted(results) == [False, False, True, True]
    async with TakeawaySessionLocal() as db:
        service = TakeawayService(db, current)
        receipt = await service.get_receipt(ORDER)
        assert receipt.print_count == before + 2
        assert {k: v for k, v in receipt.payload.items() if k not in ("print_copies", "preparation_items", "note")} == financial
        assert "preparation_items" in receipt.payload
        count = await db.scalar(select(func.count()).select_from(TakeawayOperationalOutbox).where(
            TakeawayOperationalOutbox.idempotency_key.like(f"receipt-print:{ORDER}:batch:{batch}:%")))
        assert count == 2
        assert not db.is_modified(receipt)
        order = await db.get(TakeawayOrder, ORDER)
        assert (order.status, order.fulfillment_status) == status
        assert any(r.order_id == ORDER for r in await service.list_receipts())
        # No foreign-company history; scope is part of the SQL read boundary.
        foreign = copy(current)
        foreign.company_id = uuid.uuid4()
        assert await TakeawayService(db, foreign).list_receipts() == []
    print(json.dumps({"isolated_database": True, "migration": "p6takeaway0010", "concurrent_duplicate_results": results,
        "new_copy_audits": count, "financial_snapshot_unchanged": True, "order_fulfillment_unchanged": True,
        "read_projection_clean": True, "foreign_company_history_empty": True}))

asyncio.run(main())
