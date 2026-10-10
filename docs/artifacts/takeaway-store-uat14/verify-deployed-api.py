"""Real authenticated read smoke + ASGI print API fixture inside outer rollback.

No auth dependency overrides, no real queue writes, no real payment or stock operation.
The only dependency override confines operational DB commits to savepoints on a rollback connection.
"""
import asyncio, json, uuid
from datetime import datetime, timedelta, timezone
import httpx
from sqlalchemy import select, text, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import active_identity_session_factory, TakeawaySessionLocal, takeaway_engine
from app.models.user import User
from app.models.takeaway import TakeawayOrder, TakeawayOrderItem, TakeawayReceipt, TakeawayOperationalOutbox
from app.services.auth_service import AuthService
from app.routers.auth import _token_response
from app.dependencies import get_takeaway_operational_db
from app.main import app

COMPANY = uuid.UUID("1b8a1818-44d6-4d5f-9d22-e5e17b23c081")
BRANCH = uuid.UUID("1f397253-0479-4970-8288-f72d6cde6d7e")
ORDER = uuid.UUID("b27b4470-7506-4c2e-b901-ac79b1911aaf")
BASE = "https://uat-takeaway.foodchainservice.com"

def values(row):
    return {column.name: getattr(row, column.name) for column in row.__table__.columns}

async def main():
    async with TakeawaySessionLocal() as db:
        assert (await db.execute(text("SELECT current_database(), host(inet_server_addr())"))).one() == ("takeaway_ops_db", "172.18.0.4")
        assert await db.scalar(text("SELECT version_num FROM alembic_version")) == "p6takeaway0010"
        original_queue = await db.get(TakeawayOrder, ORDER)
        expected_queue_state = (original_queue.status, original_queue.fulfillment_status)
    async with active_identity_session_factory()() as db:
        assert (await db.execute(text("SELECT current_database(), host(inet_server_addr())"))).one() == ("restaurant_platform_core_db", "172.18.0.4")
        user = (await db.scalars(select(User).where(User.username == "test.chambo.store-cashier", User.company_id == COMPANY, User.is_active.is_(True)))).one()
        device = str(uuid.uuid4())
        issued = await AuthService(db).create_session(user=user, branch_id=BRANCH, station_key="counter-1",
            ip_address="127.0.0.1", user_agent="UAT14 deployment read smoke + rollback fixture; no password change",
            qa_deadline=datetime.now(timezone.utc) + timedelta(minutes=15), client_surface="takeaway_store", store_device_id=device)
        tokens = (await _token_response(*issued, user, db)).model_dump(mode="json")
    report = {"authentication": "Temporary 15-minute scoped cashier session; real token checks; no password login test", "public_gets": {}, "original_queue_state": expected_queue_state}
    try:
        headers = {"Authorization": f"Bearer {tokens['access_token']}", "X-Company-ID": str(COMPANY),
            "X-Branch-ID": str(BRANCH), "X-Store-Device-ID": device, "Origin": "https://localhost"}
        async with httpx.AsyncClient(base_url=BASE, headers=headers, timeout=20) as client:
            paths = ["/takeaway/status", "/takeaway/receipts?limit=10", f"/takeaway/orders/{ORDER}/receipt", "/takeaway/orders?active_only=true"]
            for path in paths:
                response = await client.get("/api/v1" + path)
                assert response.status_code == 200, (path, response.status_code)
                report["public_gets"][path] = response.status_code
                data = response.json()["data"]
                if path == "/takeaway/status":
                    assert data["company_id"] == str(COMPANY) and data["branch_id"] == str(BRANCH)
                    assert data["counter_two_step"] is True
                if "/orders?" in path:
                    queue = next((row for row in data if row["id"] == str(ORDER)), None)
                    if expected_queue_state[0] == "paid" and expected_queue_state[1] in ("queued", "preparing", "ready"):
                        assert queue and (queue["status"], queue["fulfillment_status"]) == expected_queue_state
                    else:
                        assert queue is None  # Already handed-off real orders must stay out of active queue.
                if path.endswith("/receipt"): assert "preparation_items" in data["payload"]
            denied = await client.get("/api/v1/takeaway/receipts", headers={"X-Company-ID": str(uuid.uuid4())})
            assert denied.status_code in (403, 404)
            report["wrong_company_denied"] = denied.status_code
        fixture_id = uuid.uuid4(); batch = uuid.uuid4()
        async with takeaway_engine.connect() as connection:
            transaction = await connection.begin()
            try:
                async with AsyncSession(bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False) as db:
                    original = await db.get(TakeawayOrder, ORDER)
                    original_receipt = await db.scalar(select(TakeawayReceipt).where(TakeawayReceipt.order_id == ORDER))
                    clone = values(original)
                    clone.update(id=fixture_id, order_number=f"UAT14-{fixture_id.hex}", idempotency_key=f"uat14-fixture:{fixture_id}", queue_number=None)
                    db.add(TakeawayOrder(**clone))
                    clone = values(original_receipt)
                    clone.update(id=uuid.uuid4(), order_id=fixture_id, receipt_number=f"UAT14-{fixture_id.hex}", print_count=0, last_printed_at=None, last_printed_copy=None,
                        payload={k: v for k, v in original_receipt.payload.items() if k not in ("print_copies", "preparation_items")})
                    db.add(TakeawayReceipt(**clone))
                    await db.commit()  # Releases SAVEPOINT only; outer transaction remains uncommitted.
                async def isolated_db():
                    async with AsyncSession(bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False) as db:
                        yield db
                app.dependency_overrides[get_takeaway_operational_db] = isolated_db
                results = []
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE, headers=headers, timeout=20) as client:
                    for copy in ("customer", "preparation"):
                        body = {"copy_type": copy, "batch_id": str(batch), "idempotency_key": "uat14-rollback-fixture"}
                        for expected_replay in (False, True):
                            response = await client.post(f"/api/v1/takeaway/orders/{fixture_id}/receipt/prints", json=body)
                            assert response.status_code == 200, response.status_code
                            assert response.json()["meta"]["idempotent_replay"] is expected_replay
                            results.append({"copy": copy, "replay": expected_replay})
                async with AsyncSession(bind=connection, join_transaction_mode="create_savepoint") as db:
                    receipt = await db.scalar(select(TakeawayReceipt).where(TakeawayReceipt.order_id == fixture_id))
                    assert receipt.print_count == 2
                    assert set(receipt.payload["print_copies"]) == {"customer", "preparation"}
                    count = await db.scalar(select(func.count()).select_from(TakeawayOperationalOutbox).where(TakeawayOperationalOutbox.idempotency_key.like(f"receipt-print:{fixture_id}:%")))
                    assert count == 2
                report["rollback_fixture_api_results"] = results
            finally:
                app.dependency_overrides.pop(get_takeaway_operational_db, None)
                await transaction.rollback()
        async with TakeawaySessionLocal() as db:
            real_order = await db.get(TakeawayOrder, ORDER)
            assert (real_order.status, real_order.fulfillment_status) == expected_queue_state
            assert await db.get(TakeawayOrder, fixture_id) is None
            assert await db.scalar(select(func.count()).select_from(TakeawayReceipt).where(TakeawayReceipt.order_id == fixture_id)) == 0
            assert await db.scalar(select(func.count()).select_from(TakeawayOperationalOutbox).where(TakeawayOperationalOutbox.idempotency_key.like(f"receipt-print:{fixture_id}:%"))) == 0
        report["fixture_order_receipt_audits_remaining"] = 0
    finally:
        async with active_identity_session_factory()() as db:
            await AuthService(db).logout(tokens["refresh_token"])
        report["temporary_session_revoked"] = True
    print(json.dumps(report, ensure_ascii=False))

asyncio.run(main())
