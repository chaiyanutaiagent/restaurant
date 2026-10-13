"""UAT-only guards shared by legacy entry points; never enable Production flags."""
from urllib.parse import urlparse
from fastapi import HTTPException
from sqlalchemy import select
from uuid import uuid5, NAMESPACE_URL
from app.config import settings
from app.database import AsyncSessionLocal
from app.models.recipe_review import RecipeReview


def enabled():
    host = urlparse(settings.saas_public_base_url).hostname or ""
    return settings.environment != "production" and host.startswith("uat-")


def direct_write():
    if enabled():
        raise HTTPException(409, "แก้สูตรผ่านทะเบียนสูตรและอนุมัติครัวกลาง /company/recipe-reviews")


async def legacy_production(company_id, system, output_ids):
    if not enabled() or not output_ids:
        return
    async with AsyncSessionLocal() as db:
        candidates = (await db.scalars(select(RecipeReview).where(RecipeReview.company_id == company_id,
            RecipeReview.system == system, RecipeReview.status.in_(["approved_hold", "published"]),
            RecipeReview.proposal["recipe_type"].astext == "production",
            RecipeReview.proposal["output_id"].astext.in_([str(i) for i in output_ids])))).all()
        for row in candidates:
            governed = row.status == "published"
            if not governed:
                # A source commit can have succeeded before the central status
                # update failed. Close legacy stock routes during that gap too.
                from app.services.recipe_review_service import source_factory
                from app.models.restaurant import Recipe
                from app.models.takeaway import TakeawayRecipe
                model = Recipe if system == "restaurant" else TakeawayRecipe
                async with source_factory(system)() as source:
                    governed = await source.scalar(select(model.id).where(model.company_id == company_id,
                        model.id == uuid5(NAMESPACE_URL, f"approved-recipe:{row.id}"))) is not None
            if governed:
                raise HTTPException(409, "สินค้านี้ใช้สูตรอนุมัติและคลังวัตถุดิบกลาง ให้ผลิตผ่านทะเบียนสูตรเพื่อไม่ตัดสต๊อกซ้ำ")
