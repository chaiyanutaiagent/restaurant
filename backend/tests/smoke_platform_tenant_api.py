from __future__ import annotations

from datetime import datetime, timezone
import os
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.database import AsyncSessionLocal
from app.main import app
from app.models.audit import AuditLog
from app.models.auth import RefreshToken
from app.models.branch import Branch
from app.models.company import Company
from app.models.device import DeviceRegistration
from app.models.platform import PlatformOperator, PlatformTenantProfile
from app.models.restaurant import Brand, BrandBranch
from app.utils.security import create_device_access_token, hash_password


DATABASE_PREFIX = "restaurant_p5_tenant_"
PLATFORM_USERNAME = "phase5.owner"
PLATFORM_PASSWORD = "Phase5PlatformOwner!"
TENANT_PASSWORD = "Phase5TenantOwner!"


def expect(response, expected: int, label: str):
    if response.status_code != expected:
        raise RuntimeError(
            f"{label}: expected HTTP {expected}, got {response.status_code}: {response.text}"
        )
    if expected >= 400:
        return response.json()
    return response.json()["data"]


async def prepare_operator() -> None:
    configured_database = os.environ.get("P5_TENANT_DATABASE_NAME", "")
    if not configured_database.startswith(DATABASE_PREFIX):
        raise RuntimeError("Phase 5 tenant smoke refuses to write a non-isolated database")
    async with AsyncSessionLocal() as db:
        actual_database = await db.scalar(func.current_database())
        if actual_database != configured_database:
            raise RuntimeError(
                f"Phase 5 tenant database mismatch: {actual_database} != {configured_database}"
            )
        db.add(
            PlatformOperator(
                username=PLATFORM_USERNAME,
                display_name="Phase 5 Platform Owner",
                hashed_password=hash_password(PLATFORM_PASSWORD),
                is_active=True,
                is_superuser=True,
            )
        )
        await db.commit()


async def seed_device(company_id: uuid.UUID, owner_id: uuid.UUID) -> tuple[str, uuid.UUID]:
    async with AsyncSessionLocal() as db:
        company = await db.get(Company, company_id)
        if company is None:
            raise RuntimeError("Created Company is missing")
        marker = uuid.uuid4().hex[:8]
        branch = Branch(
            company_id=company.id,
            code=f"P5-{marker}"[:20],
            name="Phase 5 Branch",
            is_active=True,
        )
        db.add(branch)
        await db.flush()
        brand = Brand(
            company_id=company.id,
            slug=f"phase5-{marker}",
            name="Phase 5 Restaurant",
            business_type="restaurant",
            is_active=True,
        )
        db.add(brand)
        await db.flush()
        db.add(
            BrandBranch(
                company_id=company.id,
                brand_id=brand.id,
                branch_id=branch.id,
                is_active=True,
            )
        )
        now = datetime.now(timezone.utc)
        device = DeviceRegistration(
            company_id=company.id,
            branch_id=branch.id,
            device_code=f"C-{uuid.uuid4().hex[:10].upper()}",
            name="Phase 5 Counter",
            device_type="counter",
            credential_version=1,
            paired_at=now,
            last_seen_at=now,
            created_by=owner_id,
        )
        db.add(device)
        await db.commit()
        token = create_device_access_token(
            device_id=device.id,
            company_id=company.id,
            brand_id=brand.id,
            branch_id=branch.id,
            device_type="counter",
            station_key=None,
            credential_version=device.credential_version,
            company_credential_version=company.credential_version,
        )
        return token, device.id


async def verify_evidence(company_id: uuid.UUID, device_id: uuid.UUID) -> None:
    async with AsyncSessionLocal() as db:
        company = await db.get(Company, company_id)
        profile = await db.scalar(
            select(PlatformTenantProfile).where(PlatformTenantProfile.company_id == company_id)
        )
        device = await db.get(DeviceRegistration, device_id)
        active_refresh_count = int(
            await db.scalar(
                select(func.count()).select_from(RefreshToken).where(
                    RefreshToken.company_id == company_id,
                    RefreshToken.revoked_at.is_(None),
                )
            )
            or 0
        )
        actions = set(
            await db.scalars(
                select(AuditLog.action).where(
                    AuditLog.company_id == company_id,
                    AuditLog.action.like("platform.%"),
                )
            )
        )
        if (
            company is None
            or not company.is_active
            or company.credential_version != 2
            or profile is None
            or profile.plan_code != "uat"
            or profile.feature_flags.get("restaurant") is not False
            or device is None
            or device.paired_at is not None
            or device.credential_version != 2
            or active_refresh_count != 1
        ):
            raise RuntimeError("Phase 5 lifecycle evidence is incomplete")
        required_actions = {
            "platform.company.create",
            "platform.company.export",
            "platform.company.controls.update",
            "platform.company.suspend",
            "platform.company.reactivate",
        }
        if not required_actions.issubset(actions):
            raise RuntimeError(f"Platform audit evidence is incomplete: {actions}")


def main() -> None:
    with TestClient(app) as client:
        client.portal.call(prepare_operator)
        platform_session = expect(
            client.post(
                "/api/v1/platform/auth/login",
                json={"username": PLATFORM_USERNAME, "password": PLATFORM_PASSWORD},
            ),
            200,
            "Platform login",
        )
        platform_headers = {"Authorization": f"Bearer {platform_session['access_token']}"}
        created = expect(
            client.post(
                "/api/v1/platform/companies",
                headers=platform_headers,
                json={
                    "name": "Phase 5 Tenant",
                    "tax_id": "0999999999999",
                    "plan_code": "starter",
                    "feature_flags": {"restaurant": True, "retail_pos": False, "takeaway": False},
                    "plan_limits": {"brands": 1, "branches": 1, "users": 2, "devices": 1},
                    "owner": {
                        "username": "tenant.owner",
                        "password": TENANT_PASSWORD,
                        "display_name": "Tenant Owner",
                    },
                    "reason": "Phase 5 isolated tenant gate",
                },
            ),
            201,
            "Create Company",
        )
        company_id = uuid.UUID(created["id"])
        if created["onboarding"]["completed_steps"] != 2:
            raise RuntimeError(f"Unexpected initial onboarding: {created['onboarding']}")

        tenant_session = expect(
            client.post(
                "/api/v1/auth/login",
                headers={"X-Company-ID": str(company_id)},
                json={"username": "tenant.owner", "password": TENANT_PASSWORD},
            ),
            200,
            "Tenant Owner login",
        )
        tenant_headers = {"Authorization": f"Bearer {tenant_session['access_token']}"}
        expect(client.get("/api/v1/auth/me", headers=tenant_headers), 200, "Tenant access")
        owner_id = uuid.UUID(tenant_session["user"]["id"])
        exported = expect(
            client.post(
                f"/api/v1/platform/companies/{company_id}/export",
                headers=platform_headers,
                json={"reason": "Phase 5 tenant portability evidence"},
            ),
            200,
            "Export Company",
        )
        identity_tables = exported["boundaries"]["identity"]["tables"]
        user_rows = identity_tables["users"]["rows"]
        if (
            exported["format"] != "restaurant-tenant-export"
            or len(exported["content_sha256"]) != 64
            or not user_rows
            or user_rows[0]["hashed_password"] != "[REDACTED]"
            or exported["redaction"]["redacted_cells"] < 1
        ):
            raise RuntimeError("Tenant export security evidence is incomplete")
        device_token, device_id = client.portal.call(seed_device, company_id, owner_id)
        device_headers = {"Authorization": f"Bearer {device_token}"}
        expect(client.get("/api/v1/device-auth/me", headers=device_headers), 200, "Device access")

        updated = expect(
            client.put(
                f"/api/v1/platform/companies/{company_id}/controls",
                headers=platform_headers,
                json={
                    "plan_code": "uat",
                    "feature_flags": {"restaurant": False, "retail_pos": False, "takeaway": False},
                    "plan_limits": {"brands": 1, "branches": 1, "users": 2, "devices": 1},
                    "reason": "Verify manual Platform controls",
                },
            ),
            200,
            "Update controls",
        )
        if updated["onboarding"]["completed_steps"] != 5:
            raise RuntimeError(f"Unexpected seeded onboarding: {updated['onboarding']}")
        expect(
            client.get("/api/v1/restaurant/brands", headers=tenant_headers),
            403,
            "Disabled Restaurant feature",
        )

        expect(
            client.post(
                f"/api/v1/platform/companies/{company_id}/suspend",
                headers=platform_headers,
                json={"reason": "Phase 5 suspension security test"},
            ),
            200,
            "Suspend Company",
        )
        expect(client.get("/api/v1/auth/me", headers=tenant_headers), 401, "Suspended user")
        expect(client.get("/api/v1/device-auth/me", headers=device_headers), 401, "Suspended device")

        expect(
            client.post(
                f"/api/v1/platform/companies/{company_id}/reactivate",
                headers=platform_headers,
                json={"reason": "Phase 5 controlled reactivation"},
            ),
            200,
            "Reactivate Company",
        )
        expect(client.get("/api/v1/auth/me", headers=tenant_headers), 401, "Old user generation")
        expect(client.get("/api/v1/device-auth/me", headers=device_headers), 401, "Old device generation")
        expect(
            client.post(
                "/api/v1/auth/login",
                headers={"X-Company-ID": str(company_id)},
                json={"username": "tenant.owner", "password": TENANT_PASSWORD},
            ),
            200,
            "Fresh Tenant Owner login",
        )
        expect(client.get("/api/v1/platform/audit", headers=platform_headers), 200, "Platform audit")
        client.portal.call(verify_evidence, company_id, device_id)
    print("Phase 5 Platform tenant lifecycle smoke passed")


if __name__ == "__main__":
    main()
