"""Opt-in UAT setup smoke; Platform sessions and operational writes all roll back."""
import asyncio
import os
import uuid

import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import active_identity_session_factory, active_restaurant_service_session_factory, get_identity_db, get_restaurant_service_db
from app.main import app
from app.models.branch import Branch
from app.models.company import Company
from app.models.restaurant import Brand, DiningTable
from app.models.settings import BranchSettings
from app.models.user import User
from app.services.auth_service import AuthService
from app.utils.security import decode_token


async def main():
    assert settings.environment == "development" and "uat-" in settings.saas_public_base_url
    assert settings.identity_database == "platform_core" and settings.restaurant_service_database == "legacy"
    company_id = uuid.UUID(os.environ["UAT_BRANCH_SMOKE_COMPANY_ID"])
    branch_code = os.environ["UAT_BRANCH_SMOKE_BRANCH_CODE"]
    identity = active_identity_session_factory()
    operational = active_restaurant_service_session_factory()

    async def counts(factory):
        async with factory() as db:
            return [await db.scalar(select(func.count()).select_from(model).where(
                (model.id if model is Company else model.company_id) == company_id
            )) for model in (Company, Brand, Branch, BranchSettings, DiningTable)]

    baseline = await counts(operational)
    async with identity.kw["bind"].connect() as identity_conn, operational.kw["bind"].connect() as operational_conn:
        identity_tx, operational_tx = await identity_conn.begin(), await operational_conn.begin()
        async def identity_db():
            async with AsyncSession(bind=identity_conn, expire_on_commit=False, join_transaction_mode="create_savepoint") as db:
                yield db
        async def restaurant_db():
            async with AsyncSession(bind=operational_conn, expire_on_commit=False, join_transaction_mode="create_savepoint") as db:
                yield db
        app.dependency_overrides[get_identity_db] = identity_db
        app.dependency_overrides[get_restaurant_service_db] = restaurant_db
        try:
            async with AsyncSession(bind=identity_conn, expire_on_commit=False, join_transaction_mode="create_savepoint") as db:
                owner = await db.scalar(select(User).where(User.company_id == company_id, User.is_active, User.deleted_at.is_(None)).order_by(User.created_at))
                branch = await db.scalar(select(Branch).where(Branch.company_id == company_id, Branch.code == branch_code))
                assert owner and not owner.is_superuser and branch
                access, _ = await AuthService(db).create_session(owner, None, "127.0.0.1", "UAT rollback-only setup regression")
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://uat-app.foodchainservice.com", headers={"Authorization": "Bearer " + access}) as client:
                switched = await client.post("/api/v1/auth/switch-branch", json={"branch_id": str(branch.id)})
                assert switched.status_code == 200, switched.text[:300]
                token = switched.json()["data"]["access_token"]
                claims = decode_token(token)
                assert claims["branch_id"] == str(branch.id) and claims["business_type"] == "restaurant"
                client.headers["Authorization"] = "Bearer " + token
                client.headers["X-Branch-ID"] = str(branch.id)
                before = await client.get("/api/v1/restaurant/settings")
                assert before.status_code == 200, before.text[:300]
                payload = dict(has_tables=True, table_zones=[dict(zone_name="โซนหลัก", table_name_prefix="A", table_count=10, table_capacity=4)], table_qr_enabled=True, bill_at_table=True, queue_reset="daily", queue_prefix="T", pickup_display_enabled=True, kitchen_stations=["อาหาร", "เครื่องดื่มร้อน", "เครื่องดื่มเย็น"])
                for attempt in range(2):
                    response = await client.post("/api/v1/restaurant/setup", json=payload)
                    assert response.status_code == 201, response.text[:400]
                    data = response.json()["data"]
                    assert data["tables_ready"] == 10
                    assert data["settings"]["fb_setup_completed"] and data["settings"]["fb_queue_prefix"] == "T"
                    if attempt:
                        assert data["tables_created"] == []
                tables = await client.get("/api/v1/restaurant/tables", headers={"X-Branch-ID": str(uuid.uuid4()), "X-Company-ID": str(uuid.uuid4())})
                assert tables.status_code == 200, tables.text[:300]
                assert len(tables.json()["data"]) == 10
                print("Actual Owner switch-branch JWT context -> settings -> setup -> 10 tables PASS; retry creates no duplicates; spoofed headers cannot change JWT scope")
                assert identity_tx.is_active and operational_tx.is_active
        finally:
            app.dependency_overrides.clear()
            await operational_tx.rollback()
            await identity_tx.rollback()
    assert await counts(operational) == baseline
    print("Rollback confirmed: operational Company/Brand/Branch/Settings/Tables unchanged", baseline)


if __name__ == "__main__":
    asyncio.run(main())
