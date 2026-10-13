"""Disposable PostgreSQL only; central and Takeaway are physically separate DBs."""
import asyncio
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4, UUID
from unittest.mock import patch
from sqlalchemy import select, text, func
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from fastapi import HTTPException
from app.config import settings
from app.database import AsyncSessionLocal, Base
from app.dependencies import TokenData
from app.models.branch import Branch
from app.models.restaurant import Brand, BrandBranch, Recipe
from app.models.product import Product, Unit
from app.models.stock import StockLocation, StockMovement
from app.models.shared_kitchen import CompanyKitchen, CompanyIngredient, CompanyIngredientLot, CompanyKitchenMovement
from app.models.recipe_review import RecipeReview, RecipeProductionRun
from app.models.takeaway import TakeawayCatalogItem, TakeawayRecipe, TakeawayStockLocation, TakeawayStockMovement
from app.schemas.recipe_review import ReviewCreate, ReviewAction, RecipeProductionCreate
from app.services import recipe_review_service as review, recipe_production_service as production
from app.services import recipe_publication_service as publication

assert settings.database_url == "postgresql+asyncpg://unused:unused@127.0.0.1/unused"
takeaway_engine = create_async_engine("postgresql+asyncpg://unused:unused@127.0.0.1/takeaway_unused")
TakeawayDB = async_sessionmaker(takeaway_engine, expire_on_commit=False)


async def expect(code, fn):
    try: await fn()
    except HTTPException as e: assert e.status_code == code, (e.status_code, e.detail)
    else: raise AssertionError(f"Expected HTTP {code}")


async def main():
    async with takeaway_engine.begin() as connection:
        assert await connection.scalar(text("select current_database()")) == "takeaway_unused"
        tables = [t for t in Base.metadata.sorted_tables if t.name.startswith("takeaway_")]
        await connection.run_sync(lambda conn: Base.metadata.create_all(conn, tables=tables))
    async with AsyncSessionLocal() as db:
        assert await db.scalar(text("select current_database()")) == "unused"
        c, u = (await db.execute(text("SELECT c.id,u.id FROM companies c JOIN users u ON u.company_id=c.id LIMIT 1"))).first()
        unit = await db.scalar(select(Unit).where(Unit.company_id == c, func.lower(Unit.code) == "kg"))
        if not unit:
            unit = Unit(company_id=c, code="kg", name="kg"); db.add(unit); await db.flush()
        branch = Branch(company_id=c, code="R"+uuid4().hex[:8], name="Recipe isolated")
        db.add(branch); await db.flush()
        raw = StockLocation(company_id=c, branch_id=branch.id, code="R"+uuid4().hex[:8], name="Shared raw")
        ready = StockLocation(company_id=c, branch_id=branch.id, code="O"+uuid4().hex[:8], name="Restaurant ready")
        db.add_all([raw, ready]); await db.flush()
        kitchen = await db.scalar(select(CompanyKitchen).where(CompanyKitchen.company_id == c))
        if not kitchen:
            kitchen = CompanyKitchen(company_id=c, branch_id=branch.id, raw_location_id=raw.id, name="Shared test", created_by=u)
            db.add(kitchen); await db.flush()
        kitchen.is_active = True
        actors = []
        for system in ("restaurant", "takeaway"):
            if system == "takeaway":
                branch = Branch(company_id=c, code="T"+uuid4().hex[:8], name="Takeaway isolated")
                db.add(branch); await db.flush()
            brand = Brand(company_id=c, slug="op-"+uuid4().hex[:8], name="Recipe test", business_type=system,
                central_branch_id=branch.id, central_ready_location_id=ready.id if system == "restaurant" else None)
            db.add(brand); await db.flush()
            db.add(BrandBranch(company_id=c, brand_id=brand.id, branch_id=branch.id))
            if system == "restaurant":
                output = Product(company_id=c, brand_id=brand.id, sku="OUT-"+uuid4().hex[:10], name="Output",
                    unit_id=unit.id, product_type="raw_material", inventory_role="central_ready", cost_price=0, selling_price=100)
                db.add(output); await db.flush(); location_id = ready.id
            else:
                async with TakeawayDB() as source:
                    output = TakeawayCatalogItem(company_id=c, brand_id=brand.id, sku="OUT-"+uuid4().hex[:10], name="Output", unit="kg", price=100)
                    location = TakeawayStockLocation(company_id=c, branch_id=branch.id, code="ready", name="Takeaway ready", location_type="central_ready")
                    source.add_all([output, location]); await source.commit(); location_id = location.id
            maker = TokenData(user_id=uuid4(), company_id=c, brand_id=brand.id, branch_id=branch.id, permissions=[review.PERMISSIONS[system]])
            actors.append((system, maker, output.id, location_id))
        await db.commit()
        kitchen_id = kitchen.id
    manager = TokenData(user_id=u, company_id=c, branch_id=None, permissions=["company.kitchen.manage"], scope_types=["company"])
    factory = lambda system: AsyncSessionLocal if system == "restaurant" else TakeawayDB
    with patch.object(review, "source_factory", side_effect=factory), patch.object(review, "active_identity_session_factory", return_value=AsyncSessionLocal), patch.object(production, "active_identity_session_factory", return_value=AsyncSessionLocal), patch.object(settings, "company_kitchen_writes_enabled", True):
        shared_id = None
        for system, maker, output, location_id in actors:
            p = ReviewCreate(system=system, brand_id=maker.brand_id, branch_id=maker.branch_id, request_key=uuid4(), proposal=dict(
                output_id=output, name="Approved recipe", recipe_type="production", yield_qty="1", yield_unit="kg", loss_percent="0",
                effective_from=publication.today(), reason="Test operations", ingredients=[dict(requested_name="Shared material "+str(c), quantity="500", unit="g")]))
            async with AsyncSessionLocal() as db: row = await review.create(db, maker, p)
            async def action(actor, revision, verb, **extra):
                async with AsyncSessionLocal() as db:
                    return await review.act(db, actor, row["id"], ReviewAction(revision=revision, action=verb, reason="Reviewed test", **extra))
            row = await action(maker, 1, "submit")
            await expect(403, lambda: action(replace(maker, permissions=["*"], scope_types=["company"]), 2, "approve"))
            await expect(409, lambda: action(manager, 2, "approve"))
            row = await action(manager, 2, "material", line_index=0, canonical_id=shared_id)
            shared_id = UUID(row["proposal"]["ingredients"][0]["canonical_id"])
            assert row["revision"] == 3
            async with AsyncSessionLocal() as db:
                assert not await db.scalar(select(CompanyIngredientLot.id).where(CompanyIngredientLot.ingredient_id == shared_id)) if system == "restaurant" else True
            row = await action(manager, 3, "approve")
            # Simulate lost central commit AFTER successful source commit.
            async with AsyncSessionLocal() as db:
                from unittest.mock import AsyncMock
                with patch.object(db, "commit", new=AsyncMock(side_effect=RuntimeError("lost central commit"))):
                    try: await review.act(db, manager, row["id"], ReviewAction(revision=4, action="publish", reason="Publish test"))
                    except RuntimeError: pass
                    else: raise AssertionError("failure injection")
            row = await action(manager, 4, "publish")
            assert row["status"] == "published"
            async with factory(system)() as source:
                cls = Recipe if system == "restaurant" else TakeawayRecipe
                assert await source.scalar(select(func.count()).select_from(cls).where(cls.brand_id == maker.brand_id)) == 1
            await expect(409, lambda: action(maker, 5, "save", proposal=p.proposal))
            async with AsyncSessionLocal() as db:
                db.add(CompanyIngredientLot(company_id=c, kitchen_id=kitchen_id, ingredient_id=shared_id,
                    lot_code=system, qty_on_hand=10, unit_cost=Decimal("0.165")))
                # Expired stock must never be consumed.
                db.add(CompanyIngredientLot(company_id=c, kitchen_id=kitchen_id, ingredient_id=shared_id,
                    lot_code=system+"-expired", qty_on_hand=999, unit_cost=1, expires_on=publication.today()-timedelta(days=1)))
                await db.commit()
            payload = RecipeProductionCreate(review_id=row["id"], request_key=uuid4(), quantity="0.01", output_location_id=location_id, reason="Physical simulation only")
            from unittest.mock import AsyncMock
            async with AsyncSessionLocal() as db:
                with patch.object(production, "deliver", new=AsyncMock(side_effect=RuntimeError("source unavailable"))):
                    try: await production.produce(db, manager, payload)
                    except RuntimeError: pass
                    else: raise AssertionError("failure injection")
            async with AsyncSessionLocal() as db:
                run = await db.scalar(select(RecipeProductionRun).where(RecipeProductionRun.request_key == payload.request_key))
                assert run.status == "output_pending"
                before = await db.scalar(select(func.sum(CompanyKitchenMovement.qty)).where(CompanyKitchenMovement.reference_id == str(run.id)))
                assert before == Decimal("-5.0000"), before
            async with AsyncSessionLocal() as db: done = await production.produce(db, manager, payload)
            assert done["status"] == "completed"
            async with AsyncSessionLocal() as db: assert (await production.produce(db, manager, payload))["id"] == done["id"]
            async with AsyncSessionLocal() as db:
                assert await db.scalar(select(func.sum(CompanyKitchenMovement.qty)).where(CompanyKitchenMovement.reference_id == str(run.id))) == before
            async with factory(system)() as source:
                if system == "restaurant":
                    count = await source.scalar(select(func.count()).select_from(StockMovement).where(StockMovement.reference_id == str(run.id)))
                else:
                    count = await source.scalar(select(func.count()).select_from(TakeawayStockMovement).where(TakeawayStockMovement.idempotency_key == f"recipe-output:{run.id}"))
                assert count == 1
            async with AsyncSessionLocal() as db:
                changed = payload.model_copy(update={"quantity": Decimal("2")})
                await expect(409, lambda: production.produce(db, manager, changed))
            async with AsyncSessionLocal() as db:
                assert (await publication.register_legacy(db, manager, system, maker.brand_id))["registered"] == 1
                assert (await publication.register_legacy(db, manager, system, maker.brand_id))["registered"] == 0
        print("PASS split-DB Restaurant + Takeaway: maker/checker, canonical no opening stock, shared ingredient, immutable publication retry, FIFO/expiry, raw-once/output-once recovery, replay conflict, legacy registration")
        # Native Takeaway assembly: consume store lots and refund the exact
        # historical movement even after the recipe is disabled/replaced.
        from app.models.takeaway import TakeawayOrder, TakeawayOrderItem, TakeawayStockBalance
        from app.services.takeaway_service import TakeawayService
        from app.services import recipe_takeaway_sale
        ingredient_id = UUID(row["proposal"]["ingredients"][0]["item_id"])
        sale = p.model_copy(update={"request_key": uuid4(), "proposal": p.proposal.model_copy(update={
            "recipe_type": "sale", "ingredients": [p.proposal.ingredients[0].model_copy(update={"item_id": ingredient_id})]})})
        async with AsyncSessionLocal() as db: row = await review.create(db, maker, sale)
        row = await action(maker, 1, "submit")
        row = await action(manager, 2, "approve")
        row = await action(manager, 3, "publish")
        async with TakeawayDB() as source:
            location = TakeawayStockLocation(company_id=c, branch_id=maker.branch_id, code="store", name="Store", location_type="store")
            source.add(location); await source.flush()
            balance = TakeawayStockBalance(company_id=c, location_id=location.id, item_id=ingredient_id, lot_code="store-lot",
                on_hand_qty=10, reserved_qty=0, average_cost=Decimal("0.165"))
            order = TakeawayOrder(company_id=c, brand_id=maker.brand_id, branch_id=maker.branch_id,
                shift_id=uuid4(), order_number="RECIPE-TEST", business_date=publication.today(), status="paid", idempotency_key=str(uuid4()))
            source.add_all([balance, order]); await source.flush()
            item = TakeawayOrderItem(order_id=order.id, catalog_item_id=output, sku="OUT", name="Menu", quantity=Decimal("0.002"), unit_price=100, line_total=1)
            source.add(item); await source.flush()
            with patch.object(recipe_takeaway_sale, "enabled", return_value=True):
                assert await recipe_takeaway_sale.consume(TakeawayService(source, manager), order, item, location.id)
            await source.commit()
            assert balance.on_hand_qty == Decimal("9.0000")
            assert order.source_metadata["recipe_snapshots"][0]["recipe_id"] == row["publication"]["source_id"]
            source_recipe = await source.get(TakeawayRecipe, UUID(row["publication"]["source_id"]))
            source_recipe.is_active = False
            await source.commit()
            await TakeawayService(source, manager).refund_order(order.id, str(uuid4()), "Test historical return")
            await source.refresh(balance)
            assert balance.on_hand_qty == Decimal("10.0000")
        print("PASS approved Takeaway sale consumes only store lots; refund restores exact movements after recipe changes")
        from app.services.shared_kitchen_service import SharedKitchenService
        with patch("app.services.recipe_governance_guard.enabled", return_value=True):
            async with AsyncSessionLocal() as db:
                report = await SharedKitchenService(db).report(c, publication.today(), publication.today())
                for _, actor, _, _ in actors:
                    summary = next(r for r in report["production_by_brand"] if r["brand_id"] == actor.brand_id)
                    assert summary["completed_count"] == 1
                    assert summary["input_cost"] == Decimal("0.8250")
        print("PASS shared-kitchen report includes both Restaurant and Takeaway costs by brand")
    await takeaway_engine.dispose()

asyncio.run(main())
