"""Governance matrix on disposable restored PostgreSQL. Never run against UAT."""
import asyncio
from uuid import uuid4
from dataclasses import replace
from unittest.mock import patch
from datetime import date
from fastapi import HTTPException
from sqlalchemy import select, text, func
from app.config import settings
from app.database import AsyncSessionLocal, engine
from app.dependencies import TokenData
from app.models.restaurant import Brand, BrandBranch, Recipe
from app.models.branch import Branch
from app.models.product import Product, Unit
from app.models.takeaway import TakeawayCatalogItem, TakeawayRecipe, TakeawayRecipeIngredient
from app.models.recipe_review import RecipeReview
from app.schemas.recipe_review import ReviewCreate, ReviewAction
from app.services import recipe_review_service as service

assert settings.database_url=="postgresql+asyncpg://unused:unused@127.0.0.1/unused"

async def main():
    # Legacy backup intentionally excludes the independent Takeaway database.
    # Build only its three source tables inside the isolated test clone.
    async with engine.begin() as connection:
        assert await connection.scalar(text("select current_database()"))=="unused"
        for model in (TakeawayCatalogItem,TakeawayRecipe,TakeawayRecipeIngredient):
            await connection.run_sync(lambda sync,table=model.__table__: table.create(sync,checkfirst=True))
    async with AsyncSessionLocal() as db:
        assert await db.scalar(text("select current_database()"))=="unused"
        c,u=(await db.execute(text("SELECT c.id,u.id FROM companies c JOIN users u ON u.company_id=c.id LIMIT 1"))).one()
        unit=Unit(company_id=c,code="RV"+uuid4().hex[:8],name="kg")
        # Unit code needs a known conversion; reuse the company's active KG if present.
        unit=await db.scalar(select(Unit).where(Unit.company_id==c,func.lower(Unit.code)=="kg")) or Unit(company_id=c,code="kg",name="kg")
        db.add(unit); await db.flush()
        actors=[]
        for system in ("restaurant","takeaway"):
            brand=Brand(company_id=c,slug="review-"+uuid4().hex[:8],name="Isolated Review",business_type=system)
            branch=Branch(company_id=c,code="R"+uuid4().hex[:8],name="Isolated Review")
            db.add_all([brand,branch]); await db.flush()
            db.add(BrandBranch(company_id=c,brand_id=brand.id,branch_id=branch.id))
            items=[]
            for name in ("Output","Material"):
                if system=="restaurant":
                    item=Product(company_id=c,brand_id=brand.id,sku="RV-"+uuid4().hex[:12],name=name,unit_id=unit.id,cost_price=100,selling_price=150,product_type="raw_material",is_active=True)
                else:
                    item=TakeawayCatalogItem(company_id=c,brand_id=brand.id,sku="RV-"+uuid4().hex[:12],name=name,unit="kg",price=150,is_active=True)
                db.add(item); items.append(item)
            await db.flush()
            actor=TokenData(user_id=u,company_id=c,brand_id=brand.id,branch_id=branch.id,permissions=[service.PERMISSIONS[system]])
            actors.append((actor,items))
        await db.commit()
        before={m.__tablename__:await db.scalar(select(func.count()).select_from(m)) for m in (Recipe,TakeawayRecipe,Product,TakeawayCatalogItem)}
    approver=replace(actors[0][0],user_id=uuid4(),permissions=["company.kitchen.manage"],scope_types=["company"],brand_id=None,branch_id=None)
    with patch.object(service,"active_identity_session_factory",return_value=AsyncSessionLocal),patch.object(service,"source_factory",return_value=AsyncSessionLocal):
        for actor,items in actors:
            system="restaurant" if actor.permissions[0]=="fb.recipe.manage" else "takeaway"
            p=ReviewCreate(system=system,brand_id=actor.brand_id,branch_id=actor.branch_id,request_key=uuid4(),proposal=dict(
                output_id=items[0].id,name="Review test",recipe_type="production",yield_qty=1,yield_unit="kg",effective_from=date.today(),reason="Need review",
                ingredients=[dict(requested_name="New material",quantity="150",unit="g")]))
            async with AsyncSessionLocal() as db: created=await service.create(db,actor,p)
            async with AsyncSessionLocal() as db: assert (await service.create(db,actor,p))["id"]==created["id"]
            async def action(who,revision,verb,**extra):
                async with AsyncSessionLocal() as db:
                    return await service.act(db,who,created["id"],ReviewAction(revision=revision,action=verb,reason="Test decision",**extra))
            submitted=await action(actor,1,"submit")
            assert submitted["status"]=="submitted"
            for who in (replace(actor,permissions=["*"],scope_types=["company"]),actor):
                try: await action(who,2,"approve")
                except HTTPException as e: assert e.status_code==403
                else: raise AssertionError("self approval")
            try: await action(approver,2,"approve")
            except HTTPException as e: assert e.status_code==409
            else: raise AssertionError("unresolved material")
            resolved=await action(approver,2,"resolve",line_index=0,item_id=items[1].id)
            assert resolved["revision"]==3
            try: await action(approver,2,"approve")
            except HTTPException as e: assert e.status_code==409
            else: raise AssertionError("stale revision")
            approved=await action(approver,3,"approve")
            assert approved["status"]=="approved_hold" and len(approved["history"])==4
            try: await action(actor,4,"submit")
            except HTTPException as e: assert e.status_code==409
            else: raise AssertionError("approved immutable")
            try:
                async with AsyncSessionLocal() as db: await service.act(db,replace(actor,branch_id=uuid4()),created["id"],ReviewAction(revision=4,action="submit",reason="wrong scope"))
            except HTTPException as e: assert e.status_code==404
            else: raise AssertionError("scope leak")
        async with AsyncSessionLocal() as db:
            after={m.__tablename__:await db.scalar(select(func.count()).select_from(m)) for m in (Recipe,TakeawayRecipe,Product,TakeawayCatalogItem)}
            assert before==after,(before,after)
    print("PASS Restaurant/Takeaway isolated workflow, maker-checker, unresolved ingredients, scoped visibility, revision conflicts, idempotent create and no source writes")

asyncio.run(main())
