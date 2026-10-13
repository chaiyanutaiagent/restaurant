import asyncio, json
from uuid import UUID
from sqlalchemy import select, text, func
from app.database import AsyncSessionLocal, active_identity_session_factory
from app.dependencies import TokenData
from app.models.restaurant import Brand
from app.models.user import User
from app.models.recipe_review import RecipeReview, RecipeProductionRun
from app.services.recipe_review_service import sources, catalog
from app.services.recipe_publication_service import register_legacy
from app.services.recipe_governance_guard import direct_write
from app.main import app
from fastapi import HTTPException

async def main():
    assert "/api/v1/company/recipe-reviews/production" in app.openapi()["paths"]
    company = UUID("1b8a1818-44d6-4d5f-9d22-e5e17b23c081")
    async with AsyncSessionLocal() as db:
        assert await db.scalar(text("SELECT version_num FROM alembic_version")) == "recipeops0034"
        assert await db.scalar(select(func.count()).select_from(RecipeProductionRun)) == 0
        assert await db.scalar(select(func.count()).select_from(RecipeReview).where(RecipeReview.status == "published")) == 0
    async with active_identity_session_factory()() as identity:
        brands = (await identity.scalars(select(Brand).where(Brand.company_id == company, Brand.is_active.is_(True), Brand.business_type.in_(["restaurant", "takeaway"])))).all()
        user = await identity.scalar(select(User).where(User.company_id == company, User.is_active.is_(True), User.is_superuser.is_(True)).order_by(User.username).limit(1))
        assert user is not None
        actor = TokenData(user_id=user.id, company_id=company, branch_id=None, permissions=["*"], scope_types=["company"])
    result = []
    for brand in brands:
        rows = await sources(actor, brand.business_type, brand.id)
        items = await catalog(actor, brand.business_type, brand.id)
        async with AsyncSessionLocal() as db:
            registered = await register_legacy(db, actor, brand.business_type, brand.id)
        after = await sources(actor, brand.business_type, brand.id)
        assert rows == after, "Registration must not change source recipes"
        result.append({"brand": brand.name, "system": brand.business_type, "recipes": len(rows), "catalog": len(items), "registration": registered,
            "pork_recipes": [{"name": r["name"], "version": r["version_no"], "yield_qty": r["yield_qty"], "yield_unit": r["yield_unit"], "active": r["is_active"]} for r in rows if "หมู" in r["name"] or "No-Brine" in r["name"]]})
    try: direct_write()
    except HTTPException as e: assert e.status_code == 409
    else: raise AssertionError("Legacy write guard inactive")
    print(json.dumps({"schema": "recipeops0034", "brands": result, "published": 0, "production_runs": 0, "source_recipes_unchanged": True}, ensure_ascii=False))

asyncio.run(main())
