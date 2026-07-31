from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.dependencies import TokenData
from app.business_context import RESTAURANT
from app.models.restaurant import Brand, BrandBranch
from app.models.role import Role
from app.models.user import UserBranch
from app.services.brand_navigation import build_brand_navigation


class BrandNavigationService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_for_user(self, current: TokenData) -> list[dict[str, Any]]:
        brands = (
            await self.db.scalars(
                select(Brand)
                .options(
                    selectinload(Brand.branches).selectinload(BrandBranch.branch)
                )
                .where(
                    Brand.company_id == current.company_id,
                    Brand.business_type == RESTAURANT,
                    Brand.is_active.is_(True),
                )
                .order_by(Brand.name)
            )
        ).all()
        assignments = (
            await self.db.scalars(
                select(UserBranch)
                .options(
                    selectinload(UserBranch.branch),
                    selectinload(UserBranch.role).selectinload(Role.permissions),
                )
                .where(
                    UserBranch.user_id == current.user_id,
                    UserBranch.deleted_at.is_(None),
                )
            )
        ).all()
        return build_brand_navigation(brands, assignments, current)
