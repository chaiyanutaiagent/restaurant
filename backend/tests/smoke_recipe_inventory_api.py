from __future__ import annotations

import asyncio
from decimal import Decimal
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import settings
from app.database import AsyncSessionLocal, engine
from app.main import app
from app.models.audit import AuditLog
from app.models.branch import Branch
from app.models.product import Product
from app.models.restaurant import Brand, BrandBranch, BranchReplenishmentPolicy
from app.models.role import Permission, Role
from app.models.stock import StockBalance, StockLocation, StockMovement
from app.models.user import User, UserBranch
from app.utils.create_superuser import DEFAULT_COMPANY_ID, ensure_default_company_seed_in_session
from app.utils.seed_test_beverage import seed_test_beverage
from app.utils.seed_permissions import seed_default_permissions
from app.utils.security import hash_password


PASSWORD = "RecipeSmoke123!"


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
            or brand is None
            or other_brand is None
            or brand.central_location_id is None
        ):
            raise RuntimeError("Default brands and RAW location were not seeded")

        ready_location = StockLocation(
            company_id=DEFAULT_COMPANY_ID,
            branch_id=branch.id,
            code=f"R-RDY-{marker}",
            name="Recipe Smoke Ready",
            is_active=True,
        )
        store_location = StockLocation(
            company_id=DEFAULT_COMPANY_ID,
            branch_id=branch.id,
            code=f"R-STR-{marker}",
            name="Recipe Smoke Store",
            is_active=True,
        )
        db.add_all([ready_location, store_location])
        await db.flush()
        brand.central_ready_location_id = ready_location.id
        brand_branch = await db.scalar(
            select(BrandBranch).where(
                BrandBranch.brand_id == brand.id,
                BrandBranch.branch_id == branch.id,
            )
        )
        if brand_branch is None:
            raise RuntimeError("Restaurant branch mapping was not seeded")
        brand_branch.store_location_id = store_location.id
        store_location_ids = list(
            (
                await db.scalars(
                    select(BrandBranch.store_location_id).where(
                        BrandBranch.brand_id == brand.id,
                        BrandBranch.is_active.is_(True),
                        BrandBranch.store_location_id.is_not(None),
                    )
                )
            ).all()
        )
        store_location_ids = list(dict.fromkeys(store_location_ids))

        def product(suffix: str, name: str, product_type: str = "raw_material") -> Product:
            return Product(
                company_id=DEFAULT_COMPANY_ID,
                brand_id=brand.id,
                sku=f"RECIPE-{suffix}-{marker}",
                name=name,
                product_type=product_type,
                inventory_role=None,
                cost_price=Decimal("1"),
                selling_price=Decimal("0"),
                is_active=True,
                is_for_sale=product_type == "menu_item",
                is_for_purchase=product_type == "raw_material",
            )

        raw_input = product("RAW-1", "Recipe Raw One")
        second_raw_input = product("RAW-2", "Recipe Raw Two")
        production_output = product("READY-OUT", "Recipe Ready Output")
        menu_input = product("MENU-IN", "Recipe Menu Input")
        menu_output = product("MENU-OUT", "Recipe Menu Output", "menu_item")
        other_brand_output = Product(
            company_id=DEFAULT_COMPANY_ID,
            brand_id=other_brand.id,
            sku=f"RECIPE-OTHER-{marker}",
            name="Other Brand Output",
            product_type="menu_item",
            cost_price=Decimal("0"),
            selling_price=Decimal("0"),
            is_active=True,
            is_for_sale=True,
            is_for_purchase=False,
        )
        db.add_all(
            [
                raw_input,
                second_raw_input,
                production_output,
                menu_input,
                menu_output,
                other_brand_output,
            ]
        )
        await db.flush()

        permission_codes = [
            "fb.menu.view",
            "fb.recipe.manage",
            "brand.central.raw_stock.view",
            "brand.central.ready_stock.view",
        ]
        permissions = list(
            (
                await db.scalars(
                    select(Permission).where(Permission.code.in_(permission_codes))
                )
            ).all()
        )
        if len(permissions) != len(permission_codes):
            raise RuntimeError("Recipe smoke permissions were not seeded")
        role = Role(
            company_id=DEFAULT_COMPANY_ID,
            name=f"recipe_smoke_{marker}",
            is_branch_assignable=True,
        )
        role.permissions = permissions
        db.add(role)
        await db.flush()

        username = f"recipe-smoke-{marker}"
        user = User(
            company_id=DEFAULT_COMPANY_ID,
            username=username,
            hashed_password=hash_password(PASSWORD),
            is_active=True,
        )
        db.add(user)
        await db.flush()
        db.add(
            UserBranch(
                user_id=user.id,
                branch_id=branch.id,
                role_id=role.id,
                brand_id=brand.id,
                is_default=True,
            )
        )
        await db.commit()

        result = {
            "username": username,
            "brand_id": str(brand.id),
            "raw_location_id": str(brand.central_location_id),
            "ready_location_id": str(ready_location.id),
            "store_location_id": str(store_location.id),
            "store_location_ids": ",".join(str(item) for item in store_location_ids),
            "raw_input_id": str(raw_input.id),
            "second_raw_input_id": str(second_raw_input.id),
            "production_output_id": str(production_output.id),
            "menu_input_id": str(menu_input.id),
            "menu_output_id": str(menu_output.id),
            "other_brand_output_id": str(other_brand_output.id),
            "marker": marker,
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


async def verify_database(context: dict[str, str], store_local_product_id: str) -> None:
    expected_roles = {
        uuid.UUID(context["raw_input_id"]): "central_raw",
        uuid.UUID(context["second_raw_input_id"]): "central_raw",
        uuid.UUID(context["production_output_id"]): "central_ready",
        uuid.UUID(context["menu_input_id"]): "central_ready",
        uuid.UUID(store_local_product_id): "store_local",
    }
    verify_engine = create_async_engine(settings.database_url, poolclass=NullPool)
    verify_session = async_sessionmaker(verify_engine, expire_on_commit=False)
    async with verify_session() as db:
        products = list(
            (
                await db.scalars(
                    select(Product).where(Product.id.in_(expected_roles))
                )
            ).all()
        )
        actual_roles = {product.id: product.inventory_role for product in products}
        if actual_roles != expected_roles:
            raise RuntimeError(f"Unexpected inventory roles: {actual_roles}")

        balances = list(
            (
                await db.scalars(
                    select(StockBalance).where(
                        StockBalance.product_id.in_(expected_roles),
                        StockBalance.variant_id.is_(None),
                    )
                )
            ).all()
        )
        expected_locations = {
            uuid.UUID(context["raw_input_id"]): uuid.UUID(context["raw_location_id"]),
            uuid.UUID(context["second_raw_input_id"]): uuid.UUID(context["raw_location_id"]),
            uuid.UUID(context["production_output_id"]): uuid.UUID(context["ready_location_id"]),
            uuid.UUID(context["menu_input_id"]): uuid.UUID(context["ready_location_id"]),
        }
        actual_locations: dict[uuid.UUID, set[uuid.UUID]] = {}
        for balance in balances:
            actual_locations.setdefault(balance.product_id, set()).add(balance.location_id)
        for product_id, location_id in expected_locations.items():
            if actual_locations.get(product_id) != {location_id}:
                raise RuntimeError(f"Unexpected provisioned locations: {actual_locations}")
        expected_store_locations = {
            uuid.UUID(item)
            for item in context["store_location_ids"].split(",")
            if item
        }
        if actual_locations.get(uuid.UUID(store_local_product_id)) != expected_store_locations:
            raise RuntimeError(f"Unexpected STORE-STOCK locations: {actual_locations}")
        if any(balance.qty_on_hand != 0 or balance.qty_reserved != 0 for balance in balances):
            raise RuntimeError("Recipe provisioning changed stock quantity")

        movement_count = await db.scalar(
            select(func.count(StockMovement.id)).where(
                StockMovement.product_id.in_(expected_roles)
            )
        )
        if movement_count != 0:
            raise RuntimeError("Recipe provisioning created stock movements")
        audit_count = await db.scalar(
            select(func.count(AuditLog.id)).where(
                AuditLog.action == "recipe.inventory_provisioned",
                AuditLog.new_value["brand_id"].as_string() == context["brand_id"],
            )
        )
        if not audit_count or audit_count < 3:
            raise RuntimeError("Recipe inventory provisioning audit is missing")
        policy_count = await db.scalar(
            select(func.count(BranchReplenishmentPolicy.id)).where(
                BranchReplenishmentPolicy.brand_id == uuid.UUID(context["brand_id"]),
                BranchReplenishmentPolicy.product_id == uuid.UUID(context["menu_input_id"]),
            )
        )
        if not policy_count:
            raise RuntimeError("Menu recipe did not provision a default replenishment policy")
    await verify_engine.dispose()


def run() -> None:
    if not settings.default_admin_password:
        raise RuntimeError("DEFAULT_ADMIN_PASSWORD is required for recipe inventory smoke")
    context = asyncio.run(prepare())
    store_local_product_id = ""

    with TestClient(app) as client:
        headers = login(client, context["username"])

        production_recipe = expect(
            client.post(
                "/api/v1/restaurant/central/test-beverage/recipes",
                headers=headers,
                json={
                    "product_id": context["production_output_id"],
                    "recipe_type": "production_recipe",
                    "name": "Recipe Smoke Production",
                    "yield_qty": 1,
                    "yield_unit": "batch",
                    "ingredients": [
                        {
                            "ingredient_id": context["raw_input_id"],
                            "quantity": 1,
                            "unit": "kg",
                        }
                    ],
                },
            ),
            201,
        )
        updates = production_recipe["inventory_updates"]
        if len(updates) != 2 or not all(item["balance_created"] for item in updates):
            raise RuntimeError(f"Production recipe did not provision RAW/READY: {updates}")

        unchanged = expect(
            client.patch(
                f"/api/v1/restaurant/central/test-beverage/recipes/{production_recipe['id']}",
                headers=headers,
                json={
                    "ingredients": [
                        {
                            "ingredient_id": context["raw_input_id"],
                            "quantity": 2,
                            "unit": "kg",
                        }
                    ]
                },
            ),
            200,
        )
        if unchanged["inventory_updates"]:
            raise RuntimeError("Idempotent recipe update created duplicate inventory rows")

        with_new_input = expect(
            client.patch(
                f"/api/v1/restaurant/central/test-beverage/recipes/{production_recipe['id']}",
                headers=headers,
                json={
                    "ingredients": [
                        {
                            "ingredient_id": context["raw_input_id"],
                            "quantity": 2,
                            "unit": "kg",
                        },
                        {
                            "ingredient_id": context["second_raw_input_id"],
                            "quantity": 1,
                            "unit": "kg",
                        },
                    ]
                },
            ),
            200,
        )
        if len(with_new_input["inventory_updates"]) != 1:
            raise RuntimeError("New production ingredient was not added to RAW stock")

        menu_recipe = expect(
            client.post(
                "/api/v1/restaurant/central/test-beverage/recipes",
                headers=headers,
                json={
                    "product_id": context["menu_output_id"],
                    "recipe_type": "menu_recipe",
                    "name": "Recipe Smoke Menu",
                    "yield_qty": 1,
                    "yield_unit": "portion",
                    "ingredients": [
                        {
                            "ingredient_id": context["menu_input_id"],
                            "quantity": 1,
                            "unit": "portion",
                        }
                    ],
                },
            ),
            201,
        )
        menu_updates = menu_recipe["inventory_updates"]
        if len(menu_updates) != 1 or menu_updates[0]["inventory_role"] != "central_ready":
            raise RuntimeError(f"Menu ingredient was not added to READY: {menu_updates}")

        store_local = expect(
            client.post(
                "/api/v1/restaurant/central/test-beverage/raw-materials",
                headers=headers,
                json={
                    "sku": f"RECIPE-STORE-LOCAL-{context['marker']}",
                    "name": "Recipe Store Local",
                    "unit": "piece",
                    "inventory_role": "store_local",
                },
            ),
            201,
        )
        store_local_product_id = store_local["id"]
        store_update = expect(
            client.patch(
                f"/api/v1/restaurant/central/test-beverage/recipes/{menu_recipe['id']}",
                headers=headers,
                json={
                    "ingredients": [
                        {
                            "ingredient_id": context["menu_input_id"],
                            "quantity": 1,
                            "unit": "portion",
                        },
                        {
                            "ingredient_id": store_local_product_id,
                            "quantity": 1,
                            "unit": "piece",
                        },
                    ]
                },
            ),
            200,
        )
        expected_store_count = len(
            [item for item in context["store_location_ids"].split(",") if item]
        )
        if len(store_update["inventory_updates"]) != expected_store_count:
            raise RuntimeError(
                f"STORE-STOCK ingredient was not provisioned for every branch: "
                f"{store_update['inventory_updates']}"
            )

        expect(
            client.post(
                "/api/v1/restaurant/central/test-food/recipes",
                headers=headers,
                json={
                    "product_id": context["other_brand_output_id"],
                    "recipe_type": "menu_recipe",
                    "name": "Cross Brand Must Fail",
                    "ingredients": [],
                },
            ),
            404,
        )

    asyncio.run(verify_database(context, store_local_product_id))
    print(
        "recipe_inventory_api_smoke=ok "
        f"raw={context['raw_location_id']} "
        f"ready={context['ready_location_id']} "
        f"store={context['store_location_id']}"
    )


if __name__ == "__main__":
    run()
