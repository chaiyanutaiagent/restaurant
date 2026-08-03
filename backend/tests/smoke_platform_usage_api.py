from __future__ import annotations

from datetime import datetime, timezone
import os
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.database import AsyncSessionLocal
from app.main import app
from app.models.audit import AuditLog
from app.models.branch import Branch
from app.models.company import Company
from app.models.device import DeviceRegistration
from app.models.platform import (
    PlatformOperator,
    PlatformTenantProfile,
    PlatformTenantUsageSnapshot,
)
from app.models.product import Product
from app.models.restaurant import Brand
from app.models.user import User
from app.utils.security import hash_password


DATABASE_PREFIX = "restaurant_saas_usage_"
PLATFORM_USERNAME = "saas.usage.owner"
PLATFORM_PASSWORD = "SaaS-Usage-Owner-Password!"
PRIVATE_MARKER = "private-tenant-marker@example.com"


def expect(response, expected: int, label: str):
    if response.status_code != expected:
        raise RuntimeError(
            f"{label}: expected HTTP {expected}, got {response.status_code}: {response.text}"
        )
    if expected >= 400:
        return response.json()
    return response.json()["data"]


async def prepare_usage_fixture() -> tuple[uuid.UUID, uuid.UUID]:
    configured_database = os.environ.get("SAAS_USAGE_DATABASE_NAME", "")
    if not configured_database.startswith(DATABASE_PREFIX):
        raise RuntimeError("SaaS usage smoke refuses to write a non-isolated database")
    async with AsyncSessionLocal() as db:
        actual_database = await db.scalar(func.current_database())
        if actual_database != configured_database:
            raise RuntimeError(
                f"SaaS usage database mismatch: {actual_database} != {configured_database}"
            )
        operator = PlatformOperator(
            username=PLATFORM_USERNAME,
            display_name="SaaS Usage Platform Owner",
            hashed_password=hash_password(PLATFORM_PASSWORD),
            is_active=True,
            is_superuser=True,
        )
        db.add(operator)
        await db.flush()
        company = Company(name="Private Usage Tenant", email=PRIVATE_MARKER, is_active=True)
        other_company = Company(name="Other Isolated Tenant", is_active=True)
        db.add_all([company, other_company])
        await db.flush()
        db.add(
            PlatformTenantProfile(
                company_id=company.id,
                plan_code="starter",
                feature_flags={"restaurant": True, "takeaway": False, "retail_pos": False},
                plan_limits={"brands": 0, "branches": 1, "users": 1, "devices": 1},
                created_by=operator.id,
            )
        )
        users = [
            User(
                company_id=company.id,
                username=f"usage-user-{index}",
                display_name=f"Private User {index}",
                email=f"private-user-{index}@example.com",
                hashed_password=hash_password(f"Usage-User-Password-{index}!"),
                is_active=True,
                is_superuser=False,
                last_login_at=datetime.now(timezone.utc),
            )
            for index in (1, 2)
        ]
        db.add_all(users)
        branch = Branch(
            company_id=company.id,
            code="USAGE-01",
            name="Private Usage Branch",
            is_active=True,
        )
        brand = Brand(
            company_id=company.id,
            slug="private-usage-brand",
            name="Private Usage Brand",
            business_type="restaurant",
            is_active=True,
        )
        db.add_all([branch, brand])
        await db.flush()
        db.add(
            DeviceRegistration(
                company_id=company.id,
                branch_id=branch.id,
                device_code="USAGE-COUNTER-01",
                name="Private Counter",
                device_type="counter",
                credential_version=1,
                created_by=users[0].id,
            )
        )
        db.add(
            Product(
                company_id=company.id,
                brand_id=brand.id,
                sku="PRIVATE-MENU-01",
                name="Private Menu Item",
                is_active=True,
                is_for_sale=True,
            )
        )
        await db.commit()
        return company.id, other_company.id


async def verify_snapshot_evidence(company_id: uuid.UUID, other_company_id: uuid.UUID) -> None:
    async with AsyncSessionLocal() as db:
        snapshots = list(
            await db.scalars(
                select(PlatformTenantUsageSnapshot)
                .where(
                    PlatformTenantUsageSnapshot.company_id.in_(
                        [company_id, other_company_id]
                    )
                )
                .order_by(PlatformTenantUsageSnapshot.company_id)
            )
        )
        audit_count = int(
            await db.scalar(
                select(func.count()).select_from(AuditLog).where(
                    AuditLog.action == "platform.usage.snapshot.capture"
                )
            )
            or 0
        )
        if len(snapshots) != 2 or audit_count != 2:
            raise RuntimeError("Daily usage snapshot idempotency/audit evidence is incomplete")
        by_company = {snapshot.company_id: snapshot for snapshot in snapshots}
        if set(by_company) != {company_id, other_company_id}:
            raise RuntimeError("Usage snapshots crossed the Company boundary")
        target = by_company[company_id]
        if target.usage.get("enabled_user_accounts") != 2:
            raise RuntimeError("Aggregate enabled-user usage was not captured")
        if PRIVATE_MARKER in str(target.usage) or PRIVATE_MARKER in str(target.limit_state):
            raise RuntimeError("Usage snapshot contains Tenant personal data")


def main() -> None:
    with TestClient(app) as client:
        company_id, other_company_id = client.portal.call(prepare_usage_fixture)
        session = expect(
            client.post(
                "/api/v1/platform/auth/login",
                json={"username": PLATFORM_USERNAME, "password": PLATFORM_PASSWORD},
            ),
            200,
            "Platform usage login",
        )
        headers = {"Authorization": f"Bearer {session['access_token']}"}
        usage_response = client.get(
            f"/api/v1/platform/companies/{company_id}/usage",
            headers=headers,
        )
        usage = expect(usage_response, 200, "Current Tenant aggregate usage")
        if PRIVATE_MARKER in usage_response.text:
            raise RuntimeError("Current usage API leaked Tenant contact data")
        if usage["usage"]["enabled_user_accounts"] != 2:
            raise RuntimeError("Current enabled-user usage is incorrect")
        if not usage["limit_state"]["brands"]["unlimited"]:
            raise RuntimeError("Zero plan limit was not treated as unlimited")
        if not usage["limit_state"]["users"]["exceeded"]:
            raise RuntimeError("User plan-limit breach was not detected")
        expected_attention = {"limit_exceeded:users", "onboarding_pending", "unpaired_devices"}
        if not expected_attention.issubset(set(usage["attention_codes"])):
            raise RuntimeError(f"Usage attention evidence is incomplete: {usage['attention_codes']}")

        first = expect(
            client.post("/api/v1/platform/usage/snapshots", headers=headers),
            200,
            "First daily usage snapshot",
        )
        second = expect(
            client.post("/api/v1/platform/usage/snapshots", headers=headers),
            200,
            "Idempotent daily usage snapshot",
        )
        if {item["id"] for item in first} != {item["id"] for item in second}:
            raise RuntimeError("Daily usage snapshot did not upsert idempotently")

        target_history = expect(
            client.get(
                f"/api/v1/platform/companies/{company_id}/usage/history",
                headers=headers,
            ),
            200,
            "Target Company usage history",
        )
        other_history = expect(
            client.get(
                f"/api/v1/platform/companies/{other_company_id}/usage/history",
                headers=headers,
            ),
            200,
            "Other Company usage history",
        )
        if len(target_history) != 1 or len(other_history) != 1:
            raise RuntimeError("Usage history was not isolated/idempotent per Company")
        if target_history[0]["company_id"] != str(company_id):
            raise RuntimeError("Target usage history crossed Company boundary")
        if other_history[0]["company_id"] != str(other_company_id):
            raise RuntimeError("Other usage history crossed Company boundary")
        client.portal.call(verify_snapshot_evidence, company_id, other_company_id)

    print("SaaS Platform usage API smoke passed")


if __name__ == "__main__":
    main()
