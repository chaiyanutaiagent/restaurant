"""Explicit UAT-only rollback smoke. Never commits a fixture or business transaction."""
import asyncio
from decimal import Decimal
import uuid
from fastapi import HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import engine
from app.models.product import Product
from app.models.stock import StockBalance
from app.models.shared_kitchen import CompanyKitchen, CompanyIngredientAlias
from app.services.recipe_material_service import RecipeMaterialQuickCreate, create_recipe_material, material_identity
from app.services.recipe_service import RecipeService
from app.schemas.restaurant import RecipeCreate, RecipeIngredientCreate
from tests.smoke_shared_kitchen import seed_fixture


async def main():
    async with engine.connect() as connection:
        transaction = await connection.begin()
        name = await connection.scalar(select(func.current_database()))
        if name != "restaurant_uat_db":
            raise RuntimeError("Refusing non-UAT database")
        # Service commits release SAVEPOINTs only; the outer transaction always rolls back.
        async with AsyncSession(bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint") as db:
            try:
                fixture = await seed_fixture(db)
                company, actor, brand = fixture['company'].id, fixture['actor'].id, fixture['brand_a']
                db.add(CompanyKitchen(company_id=company, branch_id=fixture['central'].id,
                    raw_location_id=fixture['shared_raw'].id, name="Rollback kitchen", created_by=actor, is_active=True))
                await db.commit()
                payload = RecipeMaterialQuickCreate(name="กะทิใหม่", unit="kg", cost_price=80,
                    inventory_role="central_raw", idempotency_key=uuid.uuid4(), use_company_kitchen=True)
                first = await create_recipe_material(db, company, actor, payload, brand)
                replay = await create_recipe_material(db, company, actor, payload, brand)
                assert first['id'] == replay['id']
                assert first['inventory_setup'] == {'zero_balances_created': 1, 'mapping_created': True, 'stock_deferred': False}
                balances = list((await db.scalars(select(StockBalance).where(StockBalance.product_id == first['id']))).all())
                assert len(balances) == 1 and balances[0].qty_on_hand == 0
                aliases = list((await db.scalars(select(CompanyIngredientAlias).where(CompanyIngredientAlias.source_product_id == first['id']))).all())
                assert len(aliases) == 1 and aliases[0].conversion_factor == 1 and aliases[0].brand_id == brand.id
                for duplicate in [payload.model_copy(update={'idempotency_key': uuid.uuid4()}), payload.model_copy(update={'cost_price': Decimal('1')})]:
                    try:
                        await create_recipe_material(db, company, actor, duplicate, brand)
                    except HTTPException as error:
                        assert error.status_code == 409
                    else:
                        raise AssertionError('duplicate/conflicting replay accepted')
                assert not await db.scalar(select(Product).where(Product.company_id == fixture['foreign'].id, Product.id == first['id']))
                # Use a new output product; never replace the fixture's existing recipe.
                output = Product(company_id=company, brand_id=brand.id, name="ผลผลิตทดสอบ", sku=f"OUT-{uuid.uuid4().hex}",
                    unit_id=fixture['output_a'].unit_id, product_type="manufactured", inventory_role="central_ready", is_active=True)
                db.add(output); await db.flush()
                recipe, _ = await RecipeService(db).create_recipe(company, RecipeCreate(product_id=output.id,
                    brand_id=brand.id, recipe_type="production_recipe", name="สูตรทดสอบ rollback", yield_qty=2, yield_unit="ea",
                    ingredients=[RecipeIngredientCreate(ingredient_id=first['id'], quantity=500, unit="g")]), actor)
                enriched = await RecipeService(db)._enrich_recipe(recipe, company)
                assert enriched.total_cost == Decimal('40') and enriched.cost_per_yield == Decimal('20')
                print('PASS: atomic quick-create, zero stock, canonical mapping, replay, duplicate, tenant isolation, recipe and unit costing')
            finally:
                await db.close()
                await transaction.rollback()
        async with AsyncSession(bind=connection) as verify:
            assert not await verify.scalar(select(Product.id).where(Product.id == material_identity(company, brand.id, payload.idempotency_key)))
        print('PASS: fixture rolled back; no live records retained')


if __name__ == '__main__':
    asyncio.run(main())
