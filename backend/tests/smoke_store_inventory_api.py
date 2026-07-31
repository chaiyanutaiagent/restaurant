from __future__ import annotations

import asyncio
from decimal import Decimal
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import settings
from app.database import AsyncSessionLocal, engine
from app.main import app
from app.models.branch import Branch
from app.models.pos import SaleOrder
from app.models.product import Product, Unit
from app.models.restaurant import Brand, BrandBranch, Recipe, RecipeIngredient
from app.models.role import Permission, Role
from app.models.stock import StockBalance, StockLocation, StockMovement
from app.models.user import User, UserBranch
from app.utils.create_superuser import DEFAULT_COMPANY_ID, ensure_default_company_seed_in_session
from app.utils.security import hash_password
from app.utils.seed_permissions import seed_default_permissions


PASSWORD = "StoreInventorySmoke123!"


def expect(response, expected: int):
    if response.status_code != expected:
        raise RuntimeError(f"Expected HTTP {expected}, got {response.status_code}: {response.text}")
    return response.json().get("data")


async def prepare() -> dict[str, str]:
    marker = uuid.uuid4().hex[:8]
    async with AsyncSessionLocal() as db:
        await seed_default_permissions(db)
        await ensure_default_company_seed_in_session(db)
        branch = Branch(
            company_id=DEFAULT_COMPANY_ID,
            code=f"SI-{marker}",
            name=f"Store Inventory Smoke {marker}",
            is_active=True,
        )
        db.add(branch)
        await db.flush()
        location = StockLocation(
            company_id=DEFAULT_COMPANY_ID,
            branch_id=branch.id,
            code=f"STORE-{marker}",
            name=f"STORE-STOCK {marker}",
            is_active=True,
        )
        db.add(location)
        await db.flush()
        brand = Brand(
            company_id=DEFAULT_COMPANY_ID,
            slug=f"stock-smoke-{marker}",
            name=f"Stock Smoke {marker}",
            is_active=True,
        )
        db.add(brand)
        await db.flush()
        db.add(
            BrandBranch(
                company_id=DEFAULT_COMPANY_ID,
                brand_id=brand.id,
                branch_id=branch.id,
                store_location_id=location.id,
                is_active=True,
            )
        )
        unit = await db.scalar(
            select(Unit).where(Unit.company_id == DEFAULT_COMPANY_ID, Unit.code == "g")
        )
        if unit is None:
            unit = Unit(
                company_id=DEFAULT_COMPANY_ID,
                code="g",
                name="กรัม",
                decimal_places=4,
                is_active=True,
            )
            db.add(unit)
            await db.flush()
        menu = Product(
            company_id=DEFAULT_COMPANY_ID,
            brand_id=brand.id,
            unit_id=unit.id,
            sku=f"SI-MENU-{marker}",
            name=f"Menu {marker}",
            product_type="menu_item",
            selling_price=Decimal("100"),
            cost_price=Decimal("0"),
            vat_type="none",
            vat_rate=Decimal("0"),
            is_active=True,
            is_for_sale=True,
            is_for_purchase=False,
        )
        ingredient = Product(
            company_id=DEFAULT_COMPANY_ID,
            brand_id=brand.id,
            unit_id=unit.id,
            sku=f"SI-ING-{marker}",
            name=f"Ingredient {marker}",
            product_type="raw_material",
            inventory_role="central_ready",
            selling_price=Decimal("0"),
            cost_price=Decimal("10"),
            is_active=True,
            is_for_sale=False,
            is_for_purchase=False,
        )
        db.add_all([menu, ingredient])
        await db.flush()
        recipe = Recipe(
            company_id=DEFAULT_COMPANY_ID,
            brand_id=brand.id,
            branch_id=None,
            product_id=menu.id,
            recipe_type="menu_recipe",
            name=f"Recipe {marker}",
            yield_qty=Decimal("1"),
            yield_unit="จาน",
            loss_percent=Decimal("0"),
            is_active=True,
        )
        db.add(recipe)
        await db.flush()
        db.add(
            RecipeIngredient(
                recipe_id=recipe.id,
                ingredient_id=ingredient.id,
                quantity=Decimal("2"),
                unit="g",
            )
        )
        db.add(
            StockBalance(
                company_id=DEFAULT_COMPANY_ID,
                branch_id=branch.id,
                location_id=location.id,
                product_id=ingredient.id,
                variant_id=None,
                qty_on_hand=Decimal("3"),
                qty_reserved=Decimal("0"),
                cost_per_unit=Decimal("10"),
            )
        )
        permissions = list(
            (
                await db.scalars(
                    select(Permission).where(
                        Permission.code.in_(
                            [
                                "brand.store.order.create",
                                "brand.store.stock.view",
                                "brand.store.stock.adjust",
                                "fb.order.create",
                                "fb.kitchen.manage",
                                "pos.sale.void",
                            ]
                        )
                    )
                )
            ).all()
        )
        role = Role(
            company_id=DEFAULT_COMPANY_ID,
            name=f"store_inventory_smoke_{marker}",
            is_branch_assignable=True,
        )
        role.permissions = permissions
        db.add(role)
        await db.flush()
        username = f"store-inventory-smoke-{marker}"
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
                brand_id=brand.id,
                business_type="restaurant",
                target_database="restaurant",
                role_id=role.id,
                is_default=True,
            )
        )
        await db.commit()
        result = {
            "username": username,
            "brand_slug": brand.slug,
            "branch_id": str(branch.id),
            "location_id": str(location.id),
            "menu_id": str(menu.id),
            "ingredient_id": str(ingredient.id),
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


async def verify_sale(context: dict[str, str], sale_order_id: str) -> None:
    verify_engine = create_async_engine(settings.database_url, poolclass=NullPool)
    factory = async_sessionmaker(verify_engine, expire_on_commit=False)
    async with factory() as db:
        balance = await db.scalar(
            select(StockBalance).where(
                StockBalance.location_id == uuid.UUID(context["location_id"]),
                StockBalance.product_id == uuid.UUID(context["ingredient_id"]),
            )
        )
        order = await db.get(SaleOrder, uuid.UUID(sale_order_id))
        movements = list(
            (
                await db.scalars(
                    select(StockMovement).where(
                        StockMovement.reference_type == "pos_sale_recipe",
                        StockMovement.reference_id == sale_order_id,
                    )
                )
            ).all()
        )
        if balance is None or balance.qty_on_hand != Decimal("-1"):
            raise RuntimeError("Paid store order did not consume the recipe into negative STORE-STOCK")
        if order is None or order.recipe_stock_status != "posted_with_warning" or len(movements) != 1:
            raise RuntimeError("Recipe stock posting status/idempotency marker was not persisted")
    await verify_engine.dispose()


async def verify_final(context: dict[str, str]) -> None:
    verify_engine = create_async_engine(settings.database_url, poolclass=NullPool)
    factory = async_sessionmaker(verify_engine, expire_on_commit=False)
    async with factory() as db:
        balance = await db.scalar(
            select(StockBalance).where(
                StockBalance.location_id == uuid.UUID(context["location_id"]),
                StockBalance.product_id == uuid.UUID(context["ingredient_id"]),
            )
        )
        movement_types = list(
            (
                await db.scalars(
                    select(StockMovement.movement_type).where(
                        StockMovement.location_id == uuid.UUID(context["location_id"]),
                        StockMovement.product_id == uuid.UUID(context["ingredient_id"]),
                    )
                )
            ).all()
        )
        if balance is None or balance.qty_on_hand != Decimal("2"):
            raise RuntimeError("Store adjustment and waste did not result in the expected balance")
        if "adjust" not in movement_types or "waste" not in movement_types:
            raise RuntimeError("Store adjustment reasons did not create distinct movement types")
    await verify_engine.dispose()


def run() -> None:
    context = asyncio.run(prepare())
    with TestClient(app) as client:
        headers = login(client, context["username"])
        order = expect(
            client.post(
                f"/api/v1/restaurant/store/{context['brand_slug']}/orders",
                headers=headers,
                json={
                    "items": [{"product_id": context["menu_id"], "qty": 2}],
                    "payment_method": "cash",
                    "paid_amount": 200,
                    "payments": [{"payment_method": "cash", "amount": 200}],
                },
            ),
            201,
        )
        if order["recipe_stock_status"] != "posted_with_warning" or not order["recipe_stock_warnings"]:
            raise RuntimeError("Negative recipe posting warning was not returned to POS")
        asyncio.run(verify_sale(context, order["sale_order_id"]))

        void_order = expect(
            client.post(
                f"/api/v1/restaurant/store/{context['brand_slug']}/orders",
                headers=headers,
                json={
                    "items": [{"product_id": context["menu_id"], "qty": 2}],
                    "payment_method": "cash",
                    "paid_amount": 200,
                    "payments": [{"payment_method": "cash", "amount": 200}],
                },
            ),
            201,
        )
        voided = expect(
            client.post(
                f"/api/v1/pos/sales/{void_order['sale_order_id']}/void",
                headers=headers,
                json={"void_reason": "store recipe reversal smoke"},
            ),
            200,
        )
        if voided["status"] != "voided" or not voided["recipe_stock_reversed_at"]:
            raise RuntimeError("Voided store sale did not reverse its recipe stock")

        daily = expect(
            client.get(
                f"/api/v1/restaurant/store/{context['brand_slug']}/stock/daily",
                headers=headers,
            ),
            200,
        )
        line = next(item for item in daily["items"] if item["product_id"] == context["ingredient_id"])
        if (
            daily["negative_count"] != 1
            or Decimal(str(line["used_sales_qty"])) != Decimal("8.0")
            or Decimal(str(line["sale_return_qty"])) != Decimal("4.0")
        ):
            raise RuntimeError("Daily store summary did not classify recipe usage/negative stock")

        expect(
            client.post(
                f"/api/v1/restaurant/store/{context['brand_slug']}/stock/adjustments",
                headers=headers,
                json={
                    "product_id": context["ingredient_id"],
                    "qty": 5,
                    "kind": "adjustment",
                    "reason": "count_higher",
                    "note": "smoke count correction",
                },
            ),
            201,
        )
        expect(
            client.post(
                f"/api/v1/restaurant/store/{context['brand_slug']}/stock/adjustments",
                headers=headers,
                json={
                    "product_id": context["ingredient_id"],
                    "qty": 1,
                    "kind": "waste",
                    "reason": "prep_waste",
                    "note": "smoke waste",
                },
            ),
            201,
        )
        count_session = expect(
            client.post(
                "/api/v1/stock-count/sessions",
                headers=headers,
                json={
                    "branch_id": context["branch_id"],
                    "location_id": context["location_id"],
                    "product_ids": [context["ingredient_id"]],
                    "note": "store smoke count",
                },
            ),
            201,
        )
        count_session = expect(
            client.post(
                f"/api/v1/stock-count/sessions/{count_session['id']}/start",
                headers=headers,
            ),
            200,
        )
        if len(count_session["items"]) != 1:
            raise RuntimeError("Store daily count did not include its requested balance")
        expect(
            client.post(
                f"/api/v1/stock-count/sessions/{count_session['id']}/items/batch",
                headers=headers,
                json={
                    "items": [
                        {
                            "item_id": count_session["items"][0]["id"],
                            "actual_qty": 2,
                        }
                    ]
                },
            ),
            200,
        )
        completed_count = expect(
            client.post(
                f"/api/v1/stock-count/sessions/{count_session['id']}/complete",
                headers=headers,
                json={"apply_adjustments": True, "note": "store smoke close"},
            ),
            200,
        )
        if completed_count["items_short"] != 1:
            raise RuntimeError("Store daily count did not persist its variance")
        asyncio.run(verify_final(context))

        suggestion = expect(
            client.get(
                f"/api/v1/restaurant/store/{context['brand_slug']}/replenishment-suggestion",
                headers=headers,
            ),
            200,
        )
        suggestion_item = next(
            item for item in suggestion["items"] if item["product_id"] == context["ingredient_id"]
        )
        if (
            Decimal(str(suggestion_item["forecast_qty"])) != Decimal("4.0")
            or Decimal(str(suggestion_item["store_on_hand_qty"])) != Decimal("2.0")
            or Decimal(str(suggestion_item["safety_stock_qty"])) != Decimal("0.4")
            or Decimal(str(suggestion_item["suggested_qty"])) != Decimal("3.0")
        ):
            raise RuntimeError("Tomorrow replenishment suggestion formula is incorrect")

        policy = expect(
            client.put(
                f"/api/v1/restaurant/central/{context['brand_slug']}/branches/{context['branch_id']}/replenishment-policies/{context['ingredient_id']}",
                headers=headers,
                json={
                    "is_enabled": True,
                    "safety_stock_percent": 20,
                    "safety_stock_qty": 0,
                    "pack_size": 2,
                    "lead_time_days": 1,
                    "forecast_method": "auto",
                    "minimum_order_qty": 0,
                },
            ),
            200,
        )
        if policy["safety_stock_percent"] != 20 or policy["pack_size"] != 2:
            raise RuntimeError("Central replenishment policy was not persisted")
        configured_suggestion = expect(
            client.get(
                f"/api/v1/restaurant/store/{context['brand_slug']}/replenishment-suggestion",
                headers=headers,
            ),
            200,
        )
        suggestion_item = next(
            item for item in configured_suggestion["items"] if item["product_id"] == context["ingredient_id"]
        )
        if Decimal(str(suggestion_item["suggested_qty"])) != Decimal("4.0"):
            raise RuntimeError("Configured safety stock and pack size were not applied")

        expect(
            client.post(
                f"/api/v1/restaurant/store/{context['brand_slug']}/shift-close",
                headers=headers,
            ),
            200,
        )
        central_order = expect(
            client.post(
                f"/api/v1/restaurant/store/{context['brand_slug']}/daily-central-order",
                headers=headers,
                json={
                    "items": [
                        {
                            "product_id": context["ingredient_id"],
                            "sku": suggestion_item["sku"],
                            "product_name": suggestion_item["product_name"],
                            "unit": suggestion_item["unit"],
                            "system_qty": 999,
                            "requested_qty": 5,
                            "source": "tampered_client_value",
                        }
                    ]
                },
            ),
            201,
        )
        if (
            Decimal(str(central_order["items"][0]["system_qty"])) != Decimal("4.0")
            or Decimal(str(central_order["items"][0]["requested_qty"])) != Decimal("5.0")
            or central_order["items"][0]["source"] != "replenishment_latest_day"
        ):
            raise RuntimeError("Central order did not preserve server suggestion vs requested quantity")
    print("Store inventory API smoke passed")


if __name__ == "__main__":
    run()
