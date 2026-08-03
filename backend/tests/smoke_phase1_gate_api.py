from __future__ import annotations

from dataclasses import dataclass
import os
import secrets
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.config import settings
from app.database import AsyncSessionLocal
from app.main import app
from app.models.branch import Branch
from app.models.company import Company
from app.models.pos import SaleOrder
from app.models.product import Product
from app.models.restaurant import Brand, BrandBranch, DiningSession, DiningTable
from app.models.role import Role
from app.models.user import User, UserBranch
from app.utils.security import hash_password


GATE_DATABASE_PREFIX = "restaurant_p1_gate_"
GATE_PASSWORD = f"Aa1!{secrets.token_urlsafe(24)}"


@dataclass(frozen=True)
class GateContext:
    company_a_id: uuid.UUID
    brand_a_id: uuid.UUID
    branch_a_id: uuid.UUID
    user_a_name: str
    company_b_id: uuid.UUID
    branch_b_id: uuid.UUID
    table_b_id: uuid.UUID
    user_b_name: str
    company_b_restaurant_brand_slug: str


def expect_status(response, expected: int, label: str) -> dict:
    if response.status_code != expected:
        raise RuntimeError(
            f"{label}: expected HTTP {expected}, got {response.status_code}: {response.text}"
        )
    if expected >= 400:
        return response.json()
    return response.json()["data"]


async def seed_gate_context() -> GateContext:
    configured_database = os.environ.get("P1_GATE_DATABASE_NAME", "")
    if not configured_database.startswith(GATE_DATABASE_PREFIX):
        raise RuntimeError("Phase 1 gate refuses to write a non-gate database")

    async with AsyncSessionLocal() as db:
        actual_database = await db.scalar(func.current_database())
        if actual_database != configured_database:
            raise RuntimeError(
                f"Phase 1 gate database mismatch: {actual_database} != {configured_database}"
            )

        brand_a = await db.scalar(
            select(Brand).where(
                Brand.slug == "kruapa-pla-khuean",
                Brand.business_type == "restaurant",
                Brand.is_active.is_(True),
            )
        )
        if brand_a is None:
            raise RuntimeError("Canonical Restaurant Brand is missing")
        branch_a = await db.scalar(
            select(Branch)
            .join(BrandBranch, BrandBranch.branch_id == Branch.id)
            .where(
                Branch.company_id == brand_a.company_id,
                Branch.code == "BKK-01",
                Branch.deleted_at.is_(None),
                Branch.is_active.is_(True),
                BrandBranch.brand_id == brand_a.id,
                BrandBranch.is_active.is_(True),
            )
        )
        if branch_a is None:
            raise RuntimeError("Canonical BKK-01 Brand assignment is missing")

        retained_counts = {
            "products": await db.scalar(
                select(func.count()).select_from(Product).where(
                    Product.company_id == brand_a.company_id,
                    Product.deleted_at.is_(None),
                )
            ),
            "tables": await db.scalar(
                select(func.count()).select_from(DiningTable).where(
                    DiningTable.company_id == brand_a.company_id,
                    DiningTable.branch_id == branch_a.id,
                )
            ),
            "sessions": await db.scalar(
                select(func.count()).select_from(DiningSession).where(
                    DiningSession.company_id == brand_a.company_id,
                    DiningSession.branch_id == branch_a.id,
                )
            ),
            "sales": await db.scalar(
                select(func.count()).select_from(SaleOrder).where(
                    SaleOrder.company_id == brand_a.company_id,
                    SaleOrder.branch_id == branch_a.id,
                )
            ),
        }
        if any((count or 0) < 1 for count in retained_counts.values()):
            raise RuntimeError(f"BKK-01 retained-data gate failed: {retained_counts}")

        marker = uuid.uuid4().hex[:8]
        role_a = Role(
            company_id=brand_a.company_id,
            name=f"P1 Gate A {marker}",
            is_system=False,
        )
        user_a = User(
            company_id=brand_a.company_id,
            username=f"p1_gate_a_{marker}",
            hashed_password=hash_password(GATE_PASSWORD),
            display_name="P1 Gate Restaurant User",
            is_active=True,
            is_superuser=True,
        )
        db.add_all([role_a, user_a])
        await db.flush()
        db.add(
            UserBranch(
                user_id=user_a.id,
                branch_id=branch_a.id,
                brand_id=brand_a.id,
                business_type="restaurant",
                target_database="restaurant",
                role_id=role_a.id,
                is_default=True,
            )
        )

        company_b = Company(name=f"P1 Gate Tenant B {marker}", is_active=True)
        db.add(company_b)
        await db.flush()
        branch_b = Branch(
            company_id=company_b.id,
            code=f"GATE-{marker}"[:20],
            name="P1 Gate Retail Branch",
            is_active=True,
        )
        role_b = Role(
            company_id=company_b.id,
            name=f"P1 Gate B {marker}",
            is_system=False,
        )
        db.add_all([branch_b, role_b])
        await db.flush()
        brand_b_retail = Brand(
            company_id=company_b.id,
            central_branch_id=branch_b.id,
            slug=f"p1-gate-retail-{marker}",
            name="P1 Gate Retail Brand",
            business_type="retail_pos",
            is_active=True,
        )
        brand_b_restaurant = Brand(
            company_id=company_b.id,
            slug=f"p1-gate-restaurant-{marker}",
            name="P1 Gate Foreign Restaurant Brand",
            business_type="restaurant",
            is_active=True,
        )
        db.add_all([brand_b_retail, brand_b_restaurant])
        await db.flush()
        db.add(
            BrandBranch(
                company_id=company_b.id,
                brand_id=brand_b_retail.id,
                branch_id=branch_b.id,
                is_active=True,
            )
        )
        user_b = User(
            company_id=company_b.id,
            username=f"p1_gate_b_{marker}",
            hashed_password=hash_password(GATE_PASSWORD),
            display_name="P1 Gate Retail User",
            is_active=True,
            is_superuser=True,
        )
        table_b = DiningTable(
            company_id=company_b.id,
            branch_id=branch_b.id,
            name="P1-GATE-FOREIGN-TABLE",
            capacity=2,
            is_active=True,
        )
        db.add_all([user_b, table_b])
        await db.flush()
        db.add(
            UserBranch(
                user_id=user_b.id,
                branch_id=branch_b.id,
                brand_id=brand_b_retail.id,
                business_type="retail_pos",
                target_database="retail_pos",
                role_id=role_b.id,
                is_default=True,
            )
        )
        await db.commit()

        print(
            "retained_data="
            f"products:{retained_counts['products']},"
            f"tables:{retained_counts['tables']},"
            f"sessions:{retained_counts['sessions']},"
            f"sales:{retained_counts['sales']}"
        )
        return GateContext(
            company_a_id=brand_a.company_id,
            brand_a_id=brand_a.id,
            branch_a_id=branch_a.id,
            user_a_name=user_a.username,
            company_b_id=company_b.id,
            branch_b_id=branch_b.id,
            table_b_id=table_b.id,
            user_b_name=user_b.username,
            company_b_restaurant_brand_slug=brand_b_restaurant.slug,
        )


def login(client: TestClient, company_id: uuid.UUID, branch_id: uuid.UUID, username: str) -> dict:
    return expect_status(
        client.post(
            "/api/v1/auth/login",
            json={
                "company_id": str(company_id),
                "branch_id": str(branch_id),
                "username": username,
                "password": GATE_PASSWORD,
            },
        ),
        200,
        f"login {username}",
    )


def run() -> None:
    if settings.identity_database != "legacy" or settings.restaurant_service_database != "legacy":
        raise RuntimeError("Phase 1 gate must exercise rollback-safe legacy defaults")

    with TestClient(app) as client:
        health = client.get("/health/ready")
        if health.status_code != 200:
            raise RuntimeError(f"readiness failed: {health.text}")
        health_payload = health.json()
        if set(health_payload) != {"status", "version"}:
            raise RuntimeError(f"public readiness leaked internal runtime detail: {health_payload}")

        if client.portal is None:
            raise RuntimeError("TestClient portal is unavailable")
        # Seed through TestClient's portal so seed queries and API requests share
        # one event loop and one asyncpg pool safely.
        context = client.portal.call(seed_gate_context)

        token_a = login(
            client,
            context.company_a_id,
            context.branch_a_id,
            context.user_a_name,
        )["access_token"]
        headers_a = {"Authorization": f"Bearer {token_a}"}
        me_a = expect_status(client.get("/api/v1/auth/me", headers=headers_a), 200, "tenant A me")
        if (
            me_a["company_id"] != str(context.company_a_id)
            or me_a["brand_id"] != str(context.brand_a_id)
            or me_a["branch_id"] != str(context.branch_a_id)
            or me_a["business_type"] != "restaurant"
            or me_a["target_database"] != "restaurant"
        ):
            raise RuntimeError(f"Tenant A canonical context mismatch: {me_a}")

        expect_status(
            client.get(f"/api/v1/system/branches/{context.branch_a_id}", headers=headers_a),
            200,
            "tenant A own branch",
        )
        expect_status(
            client.get(
                f"/api/v1/system/branches/{context.branch_a_id}/settings",
                headers=headers_a,
            ),
            200,
            "tenant A own settings",
        )
        expect_status(
            client.get("/api/v1/restaurant/tables", headers=headers_a),
            200,
            "tenant A legacy Restaurant tables",
        )
        brands_a = expect_status(
            client.get("/api/v1/restaurant/brands", headers=headers_a),
            200,
            "tenant A legacy Brand list",
        )
        brand_slugs_a = {row["slug"] for row in brands_a}
        if "kruapa-pla-khuean" not in brand_slugs_a:
            raise RuntimeError("Tenant A lost the canonical Restaurant Brand")
        if context.company_b_restaurant_brand_slug in brand_slugs_a:
            raise RuntimeError("Tenant A Brand list leaked Tenant B")

        expect_status(
            client.get(f"/api/v1/system/branches/{context.branch_b_id}", headers=headers_a),
            404,
            "tenant A cannot read tenant B branch",
        )
        expect_status(
            client.get(
                f"/api/v1/system/branches/{context.branch_b_id}/settings",
                headers=headers_a,
            ),
            404,
            "tenant A cannot read tenant B settings",
        )
        expect_status(
            client.get(f"/api/v1/restaurant/tables/{context.table_b_id}", headers=headers_a),
            404,
            "tenant A cannot read tenant B table",
        )
        expect_status(
            client.post(
                "/api/v1/auth/switch-branch",
                headers=headers_a,
                json={"branch_id": str(context.branch_b_id)},
            ),
            403,
            "tenant A cannot switch to tenant B branch",
        )
        expect_status(
            client.post(
                "/api/v1/auth/login",
                json={
                    "company_id": str(context.company_a_id),
                    "branch_id": str(context.branch_a_id),
                    "username": context.user_b_name,
                    "password": GATE_PASSWORD,
                },
            ),
            401,
            "tenant B identity cannot authenticate under tenant A",
        )

        token_b = login(
            client,
            context.company_b_id,
            context.branch_b_id,
            context.user_b_name,
        )["access_token"]
        headers_b = {"Authorization": f"Bearer {token_b}"}
        me_b = expect_status(client.get("/api/v1/auth/me", headers=headers_b), 200, "tenant B me")
        if me_b["business_type"] != "retail_pos" or me_b["target_database"] != "retail_pos":
            raise RuntimeError(f"Tenant B canonical context mismatch: {me_b}")
        expect_status(
            client.get(f"/api/v1/system/branches/{context.branch_b_id}", headers=headers_b),
            200,
            "tenant B own branch",
        )
        expect_status(
            client.get(f"/api/v1/system/branches/{context.branch_a_id}", headers=headers_b),
            404,
            "tenant B cannot read tenant A branch",
        )
        expect_status(
            client.get("/api/v1/restaurant/settings", headers=headers_b),
            403,
            "Retail context cannot open Restaurant settings",
        )
        expect_status(
            client.get("/api/v1/restaurant/brands", headers=headers_b),
            403,
            "Retail context cannot open Restaurant Brand API",
        )

    print("phase1_tenant_isolation=ok")
    print("phase1_branch_assignment=ok")
    print("phase1_business_type_guard=ok")
    print("phase1_legacy_routes=ok")


if __name__ == "__main__":
    run()
