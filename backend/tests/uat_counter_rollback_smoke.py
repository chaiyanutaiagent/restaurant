"""Explicit opt-in UAT13 real-DB smoke. All business writes are rolled back."""
import asyncio
import json
import os
import uuid
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException
from sqlalchemy import func, select, text
from app.database import TakeawaySessionLocal, active_identity_session_factory
from app.dependencies import TokenData
from app.models.takeaway import TakeawayOrder, TakeawayOperationalOutbox
from app.services.takeaway_service import TakeawayService

SOURCE = uuid.UUID("b27b4470-7506-4c2e-b901-ac79b1911aaf")
COMPANY = uuid.UUID("1b8a1818-44d6-4d5f-9d22-e5e17b23c081")
BRAND = uuid.UUID("d6391cbe-ee53-4873-b95b-219c9bc23e7c")
BRANCH = uuid.UUID("1f397253-0479-4970-8288-f72d6cde6d7e")


async def main():
    assert os.environ.get("UAT13_ROLLBACK_SMOKE") == "1", "Explicit opt-in required"
    report = {"all_fixture_writes_rolled_back": True, "cases": []}
    async with TakeawaySessionLocal() as db, active_identity_session_factory()() as platform:
        assert (await db.execute(text("SELECT current_database(), host(inet_server_addr())"))).one() == ("takeaway_ops_db", "172.18.0.4")
        assert (await platform.execute(text("SELECT current_database(), host(inet_server_addr())"))).one() == ("restaurant_platform_core_db", "172.18.0.4")
        snapshot_sql = text("SELECT to_jsonb(o) FROM takeaway_orders o WHERE id=:id")
        original = await db.scalar(snapshot_sql, {"id": SOURCE})
        assert original and original["company_id"] == str(COMPANY)
        assert original["branch_id"] == str(BRANCH)
        report["queue4_before"] = {k: original[k] for k in ("id", "order_number", "status", "fulfillment_status")}
        await db.rollback()
        current = TokenData(user_id=uuid.uuid4(), company_id=COMPANY, brand_id=BRAND,
            branch_id=BRANCH, business_type="takeaway", target_database="takeaway",
            permissions=["takeaway.sale.create", "takeaway.sale.view"])
        for state in ("queued", "preparing", "ready"):
            fixture_id = uuid.uuid4()
            fixture = {**original, "id": str(fixture_id), "order_number": f"UAT13-{fixture_id.hex}",
                "idempotency_key": f"uat13-{fixture_id}", "offline_device_id": None,
                "offline_sequence": None, "queue_number": 999004, "fulfillment_status": state,
                "picked_up_at": None, "source_metadata": {}}
            try:
                await db.execute(text("INSERT INTO takeaway_orders SELECT * FROM jsonb_populate_record(NULL::takeaway_orders, CAST(:row AS jsonb))"), {"row": json.dumps(fixture)})
                service = TakeawayService(db, current)
                with patch.object(db, "commit", AsyncMock(side_effect=db.flush)):
                    if state == "queued":
                        try:
                            await service.counter_order_action(fixture_id, "handoff", platform)
                        except HTTPException as error:
                            assert error.status_code == 409
                        else:
                            raise AssertionError("queued handoff must be denied")
                        await service.counter_order_action(fixture_id, "accept", platform)
                        await service.counter_order_action(fixture_id, "accept", platform)
                    active = await service.list_orders(active_only=True, limit=500)
                    assert fixture_id in {o.id for o in active}
                    result = await service.counter_order_action(fixture_id, "handoff", platform)
                    history = list(result.source_metadata["fulfillment_history"])
                    await service.counter_order_action(fixture_id, "handoff", platform)
                    await service.counter_order_action(fixture_id, "accept", platform)
                    assert result.fulfillment_status == "picked_up" and result.picked_up_at
                    assert history == result.source_metadata["fulfillment_history"]
                    expected = ["picked_up"] if state == "ready" else ["ready", "picked_up"]
                    assert [h["status"] for h in history] == expected
                    count = await db.scalar(select(func.count()).select_from(TakeawayOperationalOutbox).where(TakeawayOperationalOutbox.aggregate_id == fixture_id))
                    assert count == len(expected)
                    assert fixture_id not in {o.id for o in await service.list_orders(active_only=True, limit=500)}
                    assert await db.get(TakeawayOrder, fixture_id) is not None
                    report["cases"].append({"initial_state": state, "final_state": "picked_up", "audit_statuses": expected,
                        "outbox_count": count, "duplicates_no_op": True, "active_removed_history_retained": True})
            finally:
                await db.rollback()
            assert await db.scalar(select(TakeawayOrder.id).where(TakeawayOrder.id == fixture_id)) is None
            await db.rollback()
        after = await db.scalar(snapshot_sql, {"id": SOURCE})
        assert after == original, "Actual queue4 changed during smoke"
        report["queue4_unchanged"] = True
        await db.rollback()
        await platform.rollback()
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
