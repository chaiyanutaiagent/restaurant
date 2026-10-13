"""UAT-only guards shared by legacy entry points; never enable Production flags."""
from urllib.parse import urlparse
from fastapi import HTTPException
from sqlalchemy import select
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
        governed = await db.scalar(select(RecipeReview.id).where(RecipeReview.company_id == company_id,
            RecipeReview.system == system, RecipeReview.status == "published",
            RecipeReview.proposal["recipe_type"].astext == "production",
            RecipeReview.proposal["output_id"].astext.in_([str(i) for i in output_ids])))
        if governed:
            raise HTTPException(409, "สินค้านี้ใช้สูตรอนุมัติและคลังวัตถุดิบกลาง ให้ผลิตผ่านทะเบียนสูตรเพื่อไม่ตัดสต๊อกซ้ำ")
