"""Opt-in UAT integration regression; all company changes and test sessions roll back."""
import asyncio
import os
import uuid
import httpx
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.config import settings
from app.database import active_identity_session_factory, get_identity_db
from app.main import app
from app.models.company import Company
from app.models.branch import Branch
from app.models.restaurant import Brand
from app.models.user import User
from app.services.auth_service import AuthService


async def main():
    assert settings.environment == "development" and settings.identity_database == "platform_core"
    assert "uat-" in settings.saas_public_base_url
    company_id = uuid.UUID(os.environ["UAT_BRANCH_SMOKE_COMPANY_ID"])
    factory = active_identity_session_factory()
    async def counts(db):
        return [await db.scalar(select(func.count()).select_from(model).where(model.company_id == company_id)) for model in (Brand, Branch)]
    async with factory() as check:
        company = await check.get(Company, company_id)
        assert company and company.business_slug == os.environ["UAT_BRANCH_SMOKE_BUSINESS_SLUG"]
        baseline = await counts(check)
    suffix = uuid.uuid4().hex[:10]
    async with factory.kw["bind"].connect() as connection:
        outer = await connection.begin()
        async def isolated_db():
            async with AsyncSession(bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint") as session:
                yield session
        app.dependency_overrides[get_identity_db] = isolated_db
        try:
            async with AsyncSession(bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint") as db:
                owner = await db.scalar(select(User).where(User.company_id == company_id, User.is_active.is_(True), User.deleted_at.is_(None)).order_by(User.created_at))
                assert owner and not owner.is_superuser
                access, _ = await AuthService(db).create_session(owner, None, "127.0.0.1", "UAT rollback-only branch regression")
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://uat-app.foodchainservice.com", headers={"Authorization": "Bearer " + access}, timeout=30) as client:
                old = await client.post("/api/v1/system/branches", json={"code": "TEST2-BKK-01", "name": "สาขาทดสอบกรุงเทพ"})
                assert old.status_code == 409, f"Legacy path {old.status_code}"
                assert old.json()["detail"]["code"] == "BRANCH_WORKSPACE_REQUIRED"
                print("Old branch form: explanatory 409, no legacy write")
                payload = dict(idempotency_key="branch-smoke-"+suffix, module_key="restaurant_pos", brand_slug="qa-"+suffix, brand_name="QA rollback brand", branch_code="QA-"+suffix.upper(), branch_name="QA rollback branch", branch_type="company_owned", storefront_mode="food_stall")
                forged = await client.post("/api/v1/membership/workspaces", json={**payload, "company_id": str(uuid.uuid4())})
                assert forged.status_code == 422
                created = await client.post("/api/v1/membership/workspaces", json=payload)
                assert created.status_code in (200, 201), f"Workspace status {created.status_code}: {created.text[:400]}"
                workspace = created.json()["data"]["workspace"]
                assert created.json()["data"]["created"]
                listing = await client.get("/api/v1/system/branches")
                assert listing.status_code == 200, listing.text[:300]
                assert listing.json()["meta"]["branch_creation_mode"] == "workspace"
                assert any(row["id"] == workspace["branch_id"] and row["company_id"] == str(company_id) for row in listing.json()["data"])
                print("Existing new Company + actual Owner permissions: Brand/Branch/Workspace create and canonical listing PASS")
                spoof = await client.get("/api/v1/system/branches", headers={"X-Company-ID": str(uuid.uuid4())})
                assert spoof.status_code in (200, 403)
                if spoof.status_code == 200:
                    assert all(row["company_id"] == str(company_id) for row in spoof.json()["data"])
                conflict_slug = "qa-conflict-"+suffix
                conflict = await client.post("/api/v1/membership/workspaces", json={**payload, "idempotency_key":"conflict-"+suffix, "brand_slug":conflict_slug})
                assert conflict.status_code == 409, conflict.text[:300]
                async with AsyncSession(bind=connection, join_transaction_mode="create_savepoint") as verify:
                    assert await verify.scalar(select(Brand.id).where(Brand.company_id == company_id, Brand.slug == conflict_slug)) is None
                print("Conflict after partial flush: rollback removed intermediate Brand; tenant spoofing denied/ignored safely")
                assert outer.is_active
        finally:
            app.dependency_overrides.clear()
            await outer.rollback()
    async with factory() as verify:
        assert await counts(verify) == baseline
    print("Outer rollback confirmed: Company Brand/Branch counts unchanged", baseline)


if __name__ == "__main__":
    asyncio.run(main())
