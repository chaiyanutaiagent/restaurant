"""Explicit UAT-only API fixture; all identity/legacy writes are rolled back.

The password verifier is replaced ONLY inside this isolated ASGI test process.
No real password is needed, changed, or printed; live authentication is untouched.
All branch resolution, projection, session issuance and permission checks are real.
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
import os
import uuid
from unittest.mock import AsyncMock, patch

from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import active_identity_session_factory, AsyncSessionLocal, get_identity_db
from app.main import app
from app.models.auth import RefreshToken
from app.models.branch import Branch
from app.models.restaurant import Brand, BrandBranch
from app.models.user import User
from app.services.mobile_store_policy import STORE_PERMISSIONS, uat_superadmin_store_access
from app.services.platform_reference_projection import ensure_legacy_operational_user_reference
from app.utils.security import decode_token


async def main() -> None:
    if os.environ.get("UAT_STORE_LOGIN_ROLLBACK_SMOKE") != "1":
        raise RuntimeError("Explicit rollback smoke gate required")
    identity_engine = active_identity_session_factory().kw["bind"]
    legacy_engine = AsyncSessionLocal.kw["bind"]
    async with identity_engine.connect() as identity_connection, legacy_engine.connect() as legacy_connection:
        identity_transaction = await identity_connection.begin()
        legacy_transaction = await legacy_connection.begin()
        session_id = None
        try:
            identity_target = (await identity_connection.execute(text("SELECT current_database(), host(inet_server_addr())"))).one()
            legacy_target = (await legacy_connection.execute(text("SELECT current_database(), host(inet_server_addr())"))).one()
            if identity_target != ("restaurant_platform_core_db", "172.18.0.4") or legacy_target != ("restaurant_uat_db", "172.18.0.4"):
                raise RuntimeError("Refusing databases outside the verified UAT instance")
            async with (
                AsyncSession(bind=identity_connection, expire_on_commit=False, join_transaction_mode="create_savepoint") as identity,
                AsyncSession(bind=legacy_connection, expire_on_commit=False, join_transaction_mode="create_savepoint") as legacy,
            ):
                user = (await identity.scalars(select(User).where(
                    User.company_id == settings.uat_superadmin_company_id,
                    User.username == settings.uat_superadmin_username,
                    User.is_active.is_(True), User.deleted_at.is_(None),
                ))).one()
                assert uat_superadmin_store_access(user), "UAT gate must already be enabled"
                branch, brand = (await identity.execute(select(Branch, Brand).join(
                    BrandBranch, BrandBranch.branch_id == Branch.id,
                ).join(Brand, Brand.id == BrandBranch.brand_id).where(
                    Branch.company_id == user.company_id, Brand.company_id == user.company_id,
                    BrandBranch.company_id == user.company_id,
                    Branch.code == "BKK-01", Branch.is_active.is_(True), Branch.deleted_at.is_(None),
                    Brand.business_type == "takeaway", Brand.is_active.is_(True), BrandBranch.is_active.is_(True),
                ))).one()
                company_id, user_id, branch_id, brand_id = user.company_id, user.id, branch.id, brand.id
                prior_password_change = user.password_changed_at

                async def identity_override():
                    yield identity

                @asynccontextmanager
                async def legacy_factory():
                    yield legacy

                async def project(actor):
                    return await ensure_legacy_operational_user_reference(actor, legacy_session_factory=legacy_factory)

                fixture_password = uuid.uuid4().hex
                device_id = str(uuid.uuid4())
                body = dict(business_code="sketch-biz", username="superadmin", password=fixture_password,
                            station_key="counter-1", device_id=device_id)
                previous_overrides = app.dependency_overrides.copy()
                app.dependency_overrides[get_identity_db] = identity_override
                try:
                    with (
                        patch("app.services.auth_service.verify_password", side_effect=lambda candidate, _: candidate == fixture_password),
                        patch("app.services.auth_service.ensure_legacy_operational_user_reference", side_effect=project),
                        patch("app.routers.mobile_store_auth.require_public_rate_limit", new_callable=AsyncMock),
                    ):
                        async with AsyncClient(transport=ASGITransport(app=app), base_url="https://uat-pos.foodchainservice.com") as client:
                            branches = await client.post("/api/v1/mobile-store/branches", json=body)
                            assert branches.status_code == 200, f"Branches HTTP {branches.status_code}"
                            assert str(branch_id) in {row["id"] for row in branches.json()["data"]}
                            response = await client.post("/api/v1/mobile-store/login", json={**body, "branch_id": str(branch_id)})
                            assert response.status_code == 200, f"Login HTTP {response.status_code}"
                            tokens = response.json()["data"]
                            claims = decode_token(tokens["access_token"])
                            refresh = decode_token(tokens["refresh_token"])
                            expected = dict(client_surface="takeaway_store", business_type="takeaway", target_database="takeaway",
                                            company_id=str(company_id), branch_id=str(branch_id), brand_id=str(brand_id),
                                            station_key="counter-1", store_device_id=device_id)
                            assert all(claims.get(key) == value for key, value in expected.items())
                            assert set(claims["permissions"]) == STORE_PERMISSIONS and "*" not in claims["permissions"]
                            assert claims["scope_types"] == ["branch"]
                            assert refresh["client_surface"] == "takeaway_store" and refresh["store_device_id"] == device_id
                            session_id = uuid.UUID(claims["sid"])
                            assert await identity.scalar(select(RefreshToken.id).where(RefreshToken.id == session_id))
                            headers = {"Authorization": "Bearer " + tokens["access_token"], "X-Company-ID": str(company_id),
                                       "X-Branch-ID": str(branch_id), "X-Store-Device-ID": device_id}
                            me = await client.get("/api/v1/auth/me", headers=headers)
                            assert me.status_code == 200, f"Auth/me HTTP {me.status_code}"
                            denied_routes = [("GET", "/api/v1/restaurant/recipes"), ("GET", "/api/v1/takeaway/central/orders"),
                                             ("POST", "/api/v1/takeaway/production/batches"), ("POST", "/api/v1/auth/switch-branch")]
                            for method, path in denied_routes:
                                denied = await client.request(method, path, headers=headers, json={"branch_id": str(branch_id)})
                                assert denied.status_code == 403, f"Forbidden route {path}: HTTP {denied.status_code}"
                            wrong_device = await client.get("/api/v1/auth/me", headers={**headers, "X-Store-Device-ID": str(uuid.uuid4())})
                            assert wrong_device.status_code == 403
                            mirrored_id = await legacy.scalar(select(User.id).where(User.id == user_id, User.company_id == company_id))
                            assert mirrored_id == user_id
                            assert user.password_changed_at == prior_password_change
                            print("PASS: branches/login/auth-me 200; Store claims scoped to company/brand/BKK-01/station/device; no wildcard")
                            print("PASS: four forbidden routes and a different device return 403; password unchanged")
                finally:
                    app.dependency_overrides.clear()
                    app.dependency_overrides.update(previous_overrides)
        finally:
            await legacy_transaction.rollback()
            await identity_transaction.rollback()
        if session_id is not None:
            assert not await identity_connection.scalar(select(RefreshToken.id).where(RefreshToken.id == session_id))
        print("PASS: identity, operational projection, audit and test session rolled back; no live session retained")


if __name__ == "__main__":
    asyncio.run(main())
