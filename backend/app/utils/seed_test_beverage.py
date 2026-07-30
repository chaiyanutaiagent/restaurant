from __future__ import annotations

import asyncio
from decimal import Decimal
import uuid

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.models.branch import Branch
from app.models.company import Company
from app.models.product import Category, Product, Unit
from app.models.restaurant import Brand, BrandBranch, Recipe, RecipeIngredient
from app.utils.seed_catalog import seed_default_stock_location


TEST_BEVERAGE_CATEGORY = {"code": "TEST-BEVERAGE-MAIN", "name": "Test Beverage", "sort_order": 10}
TEST_BEVERAGE_SUPPLY_CATEGORY = {"code": "TEST-BEVERAGE-SUPPLY", "name": "Test Beverage Supplies", "sort_order": 11}

TEST_BEVERAGE_PRODUCTS: list[dict[str, object]] = [
    {"sku": "TB-DRINK-A", "name": "Test Drink A", "price": Decimal("65"), "description": "Test beverage menu item A"},
    {"sku": "TB-DRINK-B", "name": "Test Drink B", "price": Decimal("55"), "description": "Test beverage menu item B"},
    {"sku": "TB-DRINK-C", "name": "Test Drink C", "price": Decimal("85"), "description": "Test beverage menu item C"},
]

TEST_BEVERAGE_SUPPLY_PRODUCTS: list[dict[str, object]] = [
    {"sku": "TB-RAW-A", "name": "Test Raw Material A", "unit": "G", "cost": Decimal("0.80"), "type": "raw_material"},
    {"sku": "TB-RAW-B", "name": "Test Raw Material B", "unit": "G", "cost": Decimal("0.55"), "type": "raw_material"},
    {"sku": "TB-WATER", "name": "Test Water", "unit": "L", "cost": Decimal("1.00"), "type": "raw_material"},
    {"sku": "TB-SYRUP", "name": "Test Syrup", "unit": "ML", "cost": Decimal("0.08"), "type": "raw_material"},
    {"sku": "TB-POWDER", "name": "Test Powder", "unit": "G", "cost": Decimal("1.20"), "type": "raw_material"},
    {"sku": "TB-BASE", "name": "Test Beverage Base", "unit": "L", "cost": Decimal("0"), "type": "raw_material"},
    {"sku": "TB-CUP", "name": "Test Cup", "unit": "PCS", "cost": Decimal("2.20"), "type": "raw_material"},
    {"sku": "TB-LID", "name": "Test Lid", "unit": "PCS", "cost": Decimal("0.80"), "type": "raw_material"},
]

TEST_BEVERAGE_RECIPES: list[dict[str, object]] = [
    {
        "product_sku": "TB-BASE",
        "name": "Test Production Recipe",
        "recipe_type": "production_recipe",
        "yield_qty": Decimal("5"),
        "yield_unit": "L",
        "loss_percent": Decimal("3"),
        "ingredients": [
            ("TB-RAW-A", Decimal("180"), "g"),
            ("TB-RAW-B", Decimal("60"), "g"),
            ("TB-WATER", Decimal("5.5"), "L"),
        ],
    },
    {
        "product_sku": "TB-DRINK-A",
        "name": "Test Menu Recipe A",
        "recipe_type": "menu_recipe",
        "yield_qty": Decimal("1"),
        "yield_unit": "แก้ว",
        "loss_percent": Decimal("0"),
        "ingredients": [
            ("TB-BASE", Decimal("250"), "ml"),
            ("TB-SYRUP", Decimal("20"), "ml"),
            ("TB-CUP", Decimal("1"), "ชิ้น"),
            ("TB-LID", Decimal("1"), "ชิ้น"),
        ],
    },
    {
        "product_sku": "TB-DRINK-B",
        "name": "Test Menu Recipe B",
        "recipe_type": "menu_recipe",
        "yield_qty": Decimal("1"),
        "yield_unit": "แก้ว",
        "loss_percent": Decimal("0"),
        "ingredients": [
            ("TB-BASE", Decimal("220"), "ml"),
            ("TB-SYRUP", Decimal("15"), "ml"),
            ("TB-CUP", Decimal("1"), "ชิ้น"),
            ("TB-LID", Decimal("1"), "ชิ้น"),
        ],
    },
    {
        "product_sku": "TB-DRINK-C",
        "name": "Test Menu Recipe C",
        "recipe_type": "menu_recipe",
        "yield_qty": Decimal("1"),
        "yield_unit": "แก้ว",
        "loss_percent": Decimal("0"),
        "ingredients": [
            ("TB-BASE", Decimal("250"), "ml"),
            ("TB-POWDER", Decimal("25"), "g"),
            ("TB-CUP", Decimal("1"), "ชิ้น"),
            ("TB-LID", Decimal("1"), "ชิ้น"),
        ],
    },
]


async def _resolve_company(db: AsyncSession, company_id: str | None) -> Company:
    if company_id:
        company = await db.get(Company, uuid.UUID(company_id))
    else:
        company = await db.scalar(select(Company).where(Company.is_active.is_(True)).order_by(Company.created_at).limit(1))
    if not company:
        raise RuntimeError("No active company found")
    return company


async def _ensure_unit(db: AsyncSession, company_id: uuid.UUID, code: str, name: str, decimals: int) -> Unit:
    unit = await db.scalar(
        select(Unit).where(Unit.company_id == company_id, Unit.code == code, Unit.deleted_at.is_(None)).limit(1)
    )
    if unit:
        unit.name = name
        unit.decimal_places = decimals
        unit.is_active = True
        return unit
    unit = Unit(company_id=company_id, code=code, name=name, name_en=code, decimal_places=decimals, is_active=True)
    db.add(unit)
    await db.flush()
    return unit


async def _ensure_category(db: AsyncSession, company_id: uuid.UUID, data: dict[str, object]) -> Category:
    category = await db.scalar(
        select(Category).where(Category.company_id == company_id, Category.code == data["code"], Category.deleted_at.is_(None))
    )
    if category:
        category.name = str(data["name"])
        category.sort_order = int(data["sort_order"])
        category.is_active = True
        return category
    category = Category(company_id=company_id, is_active=True, **data)
    db.add(category)
    await db.flush()
    return category


async def seed_test_beverage(db: AsyncSession, company_id: str | None = None) -> int:
    company = await _resolve_company(db, company_id)
    branches = list((await db.scalars(
        select(Branch).where(Branch.company_id == company.id, Branch.deleted_at.is_(None), Branch.is_active.is_(True)).order_by(Branch.sort_order, Branch.created_at)
    )).all())
    central_branch = branches[0] if branches else None
    central_location = await seed_default_stock_location(db, company.id, central_branch.id) if central_branch else None

    brand = await db.scalar(select(Brand).where(Brand.company_id == company.id, Brand.slug == "test-beverage").limit(1))
    if brand:
        brand.name = "Test Beverage"
        brand.central_branch_id = brand.central_branch_id or (central_branch.id if central_branch else None)
        brand.central_location_id = brand.central_location_id or (central_location.id if central_location else None)
        brand.storefront_mode = "drink_shop"
        brand.theme_config = {"accent": "green", "queue_prefix": "H", "order_mode": "beverage"}
        brand.is_active = True
    else:
        brand = Brand(
            company_id=company.id,
            central_branch_id=central_branch.id if central_branch else None,
            central_location_id=central_location.id if central_location else None,
            slug="test-beverage",
            name="Test Beverage",
            storefront_mode="drink_shop",
            theme_config={"accent": "green", "queue_prefix": "H", "order_mode": "beverage"},
            is_active=True,
        )
        db.add(brand)
        await db.flush()

    comparison_brand = await db.scalar(
        select(Brand).where(
            Brand.company_id == company.id,
            Brand.slug == "test-food",
        ).limit(1)
    )
    if comparison_brand:
        comparison_brand.name = "Test Food"
        comparison_brand.central_branch_id = comparison_brand.central_branch_id or (
            central_branch.id if central_branch else None
        )
        comparison_brand.central_location_id = comparison_brand.central_location_id or (
            central_location.id if central_location else None
        )
        comparison_brand.is_active = True
    else:
        comparison_brand = Brand(
            company_id=company.id,
            central_branch_id=central_branch.id if central_branch else None,
            central_location_id=central_location.id if central_location else None,
            slug="test-food",
            name="Test Food",
            storefront_mode="restaurant",
            theme_config={"accent": "orange", "queue_prefix": "F", "order_mode": "food"},
            is_active=True,
        )
        db.add(comparison_brand)
        await db.flush()

    for branch in branches:
        store_location = await seed_default_stock_location(db, company.id, branch.id)
        brand_branch = await db.scalar(
            select(BrandBranch).where(BrandBranch.brand_id == brand.id, BrandBranch.branch_id == branch.id).limit(1)
        )
        if brand_branch:
            brand_branch.store_location_id = brand_branch.store_location_id or store_location.id
            brand_branch.is_active = True
        else:
            db.add(BrandBranch(
                company_id=company.id,
                brand_id=brand.id,
                branch_id=branch.id,
                store_location_id=store_location.id,
                branch_type="company_owned",
                is_active=True,
            ))
        comparison_branch = await db.scalar(
            select(BrandBranch).where(
                BrandBranch.brand_id == comparison_brand.id,
                BrandBranch.branch_id == branch.id,
            ).limit(1)
        )
        if comparison_branch:
            comparison_branch.store_location_id = comparison_branch.store_location_id or store_location.id
            comparison_branch.is_active = True
        else:
            db.add(BrandBranch(
                company_id=company.id,
                brand_id=comparison_brand.id,
                branch_id=branch.id,
                store_location_id=store_location.id,
                branch_type="company_owned",
                is_active=True,
            ))

    units = {
        "PCS": await _ensure_unit(db, company.id, "PCS", "ชิ้น", 0),
        "G": await _ensure_unit(db, company.id, "G", "กรัม", 0),
        "L": await _ensure_unit(db, company.id, "L", "ลิตร", 2),
        "ML": await _ensure_unit(db, company.id, "ML", "มิลลิลิตร", 0),
    }
    category = await _ensure_category(db, company.id, TEST_BEVERAGE_CATEGORY)
    supply_category = await _ensure_category(db, company.id, TEST_BEVERAGE_SUPPLY_CATEGORY)

    menu_values = [
        {
            "company_id": company.id,
            "sku": item["sku"],
            "name": item["name"],
            "description": item["description"],
            "category_id": category.id,
            "brand_id": brand.id,
            "unit_id": units["PCS"].id,
            "product_type": "menu_item",
            "cost_price": Decimal("0"),
            "selling_price": item["price"],
            "vat_type": "included",
            "vat_rate": Decimal("7.00"),
            "is_active": True,
            "is_for_sale": True,
            "is_for_purchase": False,
        }
        for item in TEST_BEVERAGE_PRODUCTS
    ]
    statement = insert(Product).values(menu_values)
    statement = statement.on_conflict_do_update(
        index_elements=["company_id", "sku"],
        set_={
            "name": statement.excluded.name,
            "description": statement.excluded.description,
            "category_id": statement.excluded.category_id,
            "brand_id": statement.excluded.brand_id,
            "unit_id": statement.excluded.unit_id,
            "product_type": "menu_item",
            "selling_price": statement.excluded.selling_price,
            "vat_type": "included",
            "vat_rate": Decimal("7.00"),
            "is_active": True,
            "is_for_sale": True,
            "is_for_purchase": False,
        },
    )
    await db.execute(statement)

    supply_values = [
        {
            "company_id": company.id,
            "sku": item["sku"],
            "name": item["name"],
            "description": None,
            "category_id": supply_category.id,
            "brand_id": brand.id,
            "unit_id": units[str(item["unit"])].id,
            "product_type": item["type"],
            "cost_price": item["cost"],
            "selling_price": Decimal("0"),
            "vat_type": "included",
            "vat_rate": Decimal("7.00"),
            "is_active": True,
            "is_for_sale": False,
            "is_for_purchase": True,
        }
        for item in TEST_BEVERAGE_SUPPLY_PRODUCTS
    ]
    supply_statement = insert(Product).values(supply_values)
    supply_statement = supply_statement.on_conflict_do_update(
        index_elements=["company_id", "sku"],
        set_={
            "name": supply_statement.excluded.name,
            "category_id": supply_statement.excluded.category_id,
            "brand_id": supply_statement.excluded.brand_id,
            "unit_id": supply_statement.excluded.unit_id,
            "product_type": supply_statement.excluded.product_type,
            "cost_price": supply_statement.excluded.cost_price,
            "is_active": True,
            "is_for_sale": False,
            "is_for_purchase": True,
        },
    )
    await db.execute(supply_statement)
    await db.flush()

    products = (await db.scalars(select(Product).where(Product.company_id == company.id, Product.sku.like("TB-%")))).all()
    product_by_sku = {product.sku: product for product in products}

    for recipe_data in TEST_BEVERAGE_RECIPES:
        product = product_by_sku.get(str(recipe_data["product_sku"]))
        if not product:
            continue
        recipe = await db.scalar(
            select(Recipe).where(
                Recipe.company_id == company.id,
                Recipe.product_id == product.id,
                Recipe.branch_id.is_(None),
                Recipe.brand_id == brand.id,
            )
        )
        if recipe:
            recipe.name = str(recipe_data["name"])
            recipe.recipe_type = str(recipe_data["recipe_type"])
            recipe.yield_qty = recipe_data["yield_qty"]
            recipe.yield_unit = str(recipe_data["yield_unit"])
            recipe.loss_percent = recipe_data["loss_percent"]
            recipe.is_active = True
            old_items = (await db.scalars(select(RecipeIngredient).where(RecipeIngredient.recipe_id == recipe.id))).all()
            for old_item in old_items:
                await db.delete(old_item)
            await db.flush()
        else:
            recipe = Recipe(
                company_id=company.id,
                branch_id=None,
                brand_id=brand.id,
                product_id=product.id,
                recipe_type=str(recipe_data["recipe_type"]),
                name=str(recipe_data["name"]),
                yield_qty=recipe_data["yield_qty"],
                yield_unit=str(recipe_data["yield_unit"]),
                loss_percent=recipe_data["loss_percent"],
                notes="สูตรตั้งต้นจากระบบ สามารถแก้ไขได้",
                is_active=True,
            )
            db.add(recipe)
            await db.flush()

        for index, (ingredient_sku, quantity, unit_name) in enumerate(recipe_data["ingredients"]):
            ingredient = product_by_sku.get(ingredient_sku)
            if not ingredient:
                continue
            db.add(RecipeIngredient(
                recipe_id=recipe.id,
                ingredient_id=ingredient.id,
                quantity=quantity,
                unit=unit_name,
                sort_order=index,
            ))

    await db.commit()
    return len(menu_values) + len(supply_values)


async def main() -> None:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--company-id", default=None)
    args = parser.parse_args()

    async with AsyncSessionLocal() as db:
        count = await seed_test_beverage(db, args.company_id)
        print(f"Seeded {count} test beverage items")


if __name__ == "__main__":
    asyncio.run(main())
