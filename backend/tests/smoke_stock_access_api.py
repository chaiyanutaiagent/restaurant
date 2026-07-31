from __future__ import annotations

import asyncio
from decimal import Decimal
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.config import settings
from app.database import AsyncSessionLocal, engine
from app.main import app
from app.models.branch import Branch
from app.models.product import Product
from app.models.restaurant import Brand, BrandBranch
from app.models.role import Permission, Role
from app.models.stock import StockBalance, StockLocation
from app.models.user import User, UserBranch
from app.utils.create_superuser import DEFAULT_COMPANY_ID, ensure_default_company_seed_in_session
from app.utils.seed_test_beverage import seed_test_beverage
from app.utils.seed_permissions import seed_default_permissions
from app.utils.security import hash_password


PASSWORD = "SmokePass123!"


def expect(response, expected: int):
    if response.status_code != expected:
        raise RuntimeError(
            f"Expected HTTP {expected}, got {response.status_code}: {response.text}"
        )
    payload = response.json()
    return payload.get("data")


async def prepare() -> dict[str, str]:
    marker = uuid.uuid4().hex[:8]
    async with AsyncSessionLocal() as db:
        await seed_default_permissions(db)
        await ensure_default_company_seed_in_session(db)
        await seed_test_beverage(db, str(DEFAULT_COMPANY_ID))

        branch = await db.scalar(
            select(Branch).where(
                Branch.company_id == DEFAULT_COMPANY_ID,
                Branch.code == "BKK-01",
            )
        )
        other_branch = await db.scalar(
            select(Branch).where(
                Branch.company_id == DEFAULT_COMPANY_ID,
                Branch.code == "BKK-02",
            )
        )
        brand = await db.scalar(
            select(Brand).where(
                Brand.company_id == DEFAULT_COMPANY_ID,
                Brand.slug == "test-beverage",
            )
        )
        other_brand = await db.scalar(
            select(Brand).where(
                Brand.company_id == DEFAULT_COMPANY_ID,
                Brand.slug == "test-food",
            )
        )
        if (
            branch is None
            or other_branch is None
            or brand is None
            or other_brand is None
            or brand.central_location_id is None
        ):
            raise RuntimeError("Default Restaurant stock configuration was not seeded")

        ready_location = StockLocation(
            company_id=DEFAULT_COMPANY_ID,
            branch_id=branch.id,
            code=f"READY-{marker}",
            name="Smoke Central Ready",
            is_active=True,
        )
        store_location = StockLocation(
            company_id=DEFAULT_COMPANY_ID,
            branch_id=branch.id,
            code=f"STORE-{marker}",
            name="Smoke Store",
            is_active=True,
        )
        other_raw_location = StockLocation(
            company_id=DEFAULT_COMPANY_ID,
            branch_id=branch.id,
            code=f"OTHER-RAW-{marker}",
            name="Smoke Other Brand Raw",
            is_active=True,
        )
        other_ready_location = StockLocation(
            company_id=DEFAULT_COMPANY_ID,
            branch_id=branch.id,
            code=f"OTHER-READY-{marker}",
            name="Smoke Other Brand Ready",
            is_active=True,
        )
        other_store_location = StockLocation(
            company_id=DEFAULT_COMPANY_ID,
            branch_id=branch.id,
            code=f"OTHER-STORE-{marker}",
            name="Smoke Other Brand Store",
            is_active=True,
        )
        db.add_all(
            [
                ready_location,
                store_location,
                other_raw_location,
                other_ready_location,
                other_store_location,
            ]
        )
        await db.flush()

        brand.central_ready_location_id = ready_location.id
        brand_branch = await db.scalar(
            select(BrandBranch).where(
                BrandBranch.brand_id == brand.id,
                BrandBranch.branch_id == branch.id,
            )
        )
        if brand_branch is None:
            raise RuntimeError("Default Restaurant branch mapping was not seeded")
        brand_branch.store_location_id = store_location.id
        other_brand.central_branch_id = branch.id
        other_brand.central_location_id = other_raw_location.id
        other_brand.central_ready_location_id = other_ready_location.id
        other_brand_branch = await db.scalar(
            select(BrandBranch).where(
                BrandBranch.brand_id == other_brand.id,
                BrandBranch.branch_id == branch.id,
            )
        )
        if other_brand_branch is None:
            raise RuntimeError("Default other-brand branch mapping was not seeded")
        other_brand_branch.store_location_id = other_store_location.id

        product = await db.scalar(
            select(Product).where(
                Product.company_id == DEFAULT_COMPANY_ID,
                Product.sku == "TB-RAW-A",
            )
        )
        if product is None:
            raise RuntimeError("Default Restaurant product was not seeded")
        product.inventory_role = "central_raw"

        for location_id, qty in (
            (brand.central_location_id, Decimal("30")),
            (ready_location.id, Decimal("20")),
            (store_location.id, Decimal("5")),
        ):
            db.add(
                StockBalance(
                    company_id=DEFAULT_COMPANY_ID,
                    branch_id=branch.id,
                    location_id=location_id,
                    product_id=product.id,
                    variant_id=None,
                    qty_on_hand=qty,
                    qty_reserved=Decimal("0"),
                    cost_per_unit=Decimal("1"),
                )
            )

        permissions = {
            permission.code: permission
            for permission in (
                await db.scalars(
                    select(Permission).where(
                        Permission.code.in_(
                            [
                                "brand.store.stock.view",
                                "brand.central.raw_stock.view",
                                "brand.central.ready_stock.view",
                                "fb.kitchen.manage",
                            ]
                        )
                    )
                )
            ).all()
        }
        store_role = Role(
            company_id=DEFAULT_COMPANY_ID,
            name=f"smoke_store_{marker}",
            is_branch_assignable=True,
        )
        central_role = Role(
            company_id=DEFAULT_COMPANY_ID,
            name=f"smoke_central_{marker}",
            is_branch_assignable=True,
        )
        store_role.permissions = [
            permissions["brand.store.stock.view"],
        ]
        central_role.permissions = [
            permissions["brand.central.raw_stock.view"],
            permissions["brand.central.ready_stock.view"],
            permissions["fb.kitchen.manage"],
        ]
        db.add_all([store_role, central_role])
        await db.flush()

        store_username = f"smoke-store-{marker}"
        central_username = f"smoke-central-{marker}"
        store_user = User(
            company_id=DEFAULT_COMPANY_ID,
            username=store_username,
            hashed_password=hash_password(PASSWORD),
            is_active=True,
        )
        central_user = User(
            company_id=DEFAULT_COMPANY_ID,
            username=central_username,
            hashed_password=hash_password(PASSWORD),
            is_active=True,
        )
        db.add_all([store_user, central_user])
        await db.flush()
        db.add_all(
            [
                UserBranch(
                    user_id=store_user.id,
                    branch_id=branch.id,
                    role_id=store_role.id,
                    brand_id=brand.id,
                    business_type="restaurant",
                    target_database="restaurant",
                    is_default=True,
                ),
                UserBranch(
                    user_id=central_user.id,
                    branch_id=branch.id,
                    role_id=central_role.id,
                    brand_id=brand.id,
                    business_type="restaurant",
                    target_database="restaurant",
                    is_default=True,
                ),
            ]
        )
        await db.commit()

        result = {
            "store_username": store_username,
            "central_username": central_username,
            "store_location_id": str(store_location.id),
            "raw_location_id": str(brand.central_location_id),
            "ready_location_id": str(ready_location.id),
            "other_branch_id": str(other_branch.id),
            "central_branch_id": str(branch.id),
            "product_id": str(product.id),
        }
    await engine.dispose()
    return result


def login(client: TestClient, username: str) -> dict[str, str]:
    data = expect(
        client.post(
            "/api/v1/auth/login",
            json={
                "company_id": str(DEFAULT_COMPANY_ID),
                "username": username,
                "password": PASSWORD,
            },
        ),
        200,
    )
    return {"Authorization": f"Bearer {data['access_token']}"}


def run() -> None:
    if not settings.default_admin_password:
        raise RuntimeError("DEFAULT_ADMIN_PASSWORD is required for stock access smoke")
    context = asyncio.run(prepare())
    with TestClient(app) as client:
        store_headers = login(client, context["store_username"])
        central_headers = login(client, context["central_username"])

        store_locations = expect(
            client.get("/api/v1/stock/locations", headers=store_headers),
            200,
        )
        store_location_ids = {row["id"] for row in store_locations}
        if store_location_ids != {context["store_location_id"]}:
            raise RuntimeError(f"Store location scope leaked central stock: {store_locations}")

        expect(
            client.get(
                "/api/v1/stock/balances",
                headers=store_headers,
                params={"location_id": context["raw_location_id"]},
            ),
            404,
        )
        expect(
            client.get(
                "/api/v1/stock/balances",
                headers=store_headers,
                params={"location_id": context["ready_location_id"]},
            ),
            404,
        )
        expect(
            client.get(
                "/api/v1/stock/locations",
                headers=store_headers,
                params={"branch_id": context["other_branch_id"]},
            ),
            404,
        )

        store_product = expect(
            client.get(
                f"/api/v1/stock/products/{context['product_id']}",
                headers=store_headers,
            ),
            200,
        )
        if {row["location_id"] for row in store_product} != {context["store_location_id"]}:
            raise RuntimeError(f"Store product endpoint leaked central balances: {store_product}")

        raw_balances = expect(
            client.get(
                "/api/v1/stock/balances",
                headers=central_headers,
                params={"location_id": context["raw_location_id"]},
            ),
            200,
        )
        ready_balances = expect(
            client.get(
                "/api/v1/stock/balances",
                headers=central_headers,
                params={"location_id": context["ready_location_id"]},
            ),
            200,
        )
        if not raw_balances or not ready_balances:
            raise RuntimeError("Central stock user could not read RAW and READY balances")

        saved_config = expect(
            client.patch(
                "/api/v1/restaurant/central/test-beverage/transfer-config",
                headers=central_headers,
                json={
                    "central_branch_id": context["central_branch_id"],
                    "central_location_id": context["raw_location_id"],
                    "central_ready_location_id": context["ready_location_id"],
                },
            ),
            200,
        )
        if saved_config["central_ready_location_id"] != context["ready_location_id"]:
            raise RuntimeError(f"READY location was not persisted: {saved_config}")
        expect(
            client.patch(
                "/api/v1/restaurant/central/test-beverage/transfer-config",
                headers=central_headers,
                json={
                    "central_ready_location_id": context["raw_location_id"],
                },
            ),
            400,
        )
        expect(
            client.patch(
                "/api/v1/restaurant/central/test-food/transfer-config",
                headers=central_headers,
                json={},
            ),
            404,
        )

        print(
            "stock_access_api_smoke=ok "
            f"store={context['store_location_id']} "
            f"raw={context['raw_location_id']} "
            f"ready={context['ready_location_id']}"
        )


if __name__ == "__main__":
    run()
