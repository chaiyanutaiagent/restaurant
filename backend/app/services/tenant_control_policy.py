from __future__ import annotations

import uuid

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.branch import Branch
from app.models.device import DeviceRegistration
from app.models.platform import PlatformTenantProfile
from app.models.restaurant import Brand
from app.models.user import User


class TenantControlPolicy:
    """Enforce manual Platform controls only for Companies with a profile."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def require_feature(self, company_id: uuid.UUID, feature_key: str) -> None:
        profile = await self._profile(company_id)
        if profile is None:
            return
        canonical_key = {
            "restaurant": "restaurant_pos",
            "takeaway": "takeaway_pos",
        }.get(feature_key, feature_key)
        enabled = profile.feature_flags.get(
            canonical_key,
            profile.feature_flags.get(feature_key),
        )
        if enabled is False:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Feature is disabled for this Company: {feature_key}",
            )

    async def require_capacity(self, company_id: uuid.UUID, resource_key: str) -> None:
        profile = await self._profile(company_id)
        if profile is None or resource_key not in profile.plan_limits:
            return
        limit = int(profile.plan_limits[resource_key])
        if limit == 0:
            return
        current = await self._count(company_id, resource_key)
        if current >= limit:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Plan limit reached for {resource_key}: {current}/{limit}",
            )

    async def _profile(self, company_id: uuid.UUID) -> PlatformTenantProfile | None:
        return await self.db.scalar(
            select(PlatformTenantProfile).where(PlatformTenantProfile.company_id == company_id)
        )

    async def _count(self, company_id: uuid.UUID, resource_key: str) -> int:
        if resource_key == "brands":
            statement = select(func.count()).select_from(Brand).where(
                Brand.company_id == company_id,
                Brand.is_active.is_(True),
            )
        elif resource_key == "branches":
            statement = select(func.count()).select_from(Branch).where(
                Branch.company_id == company_id,
                Branch.deleted_at.is_(None),
                Branch.is_active.is_(True),
            )
        elif resource_key == "users":
            statement = select(func.count()).select_from(User).where(
                User.company_id == company_id,
                User.deleted_at.is_(None),
                User.is_active.is_(True),
            )
        elif resource_key == "devices":
            statement = select(func.count()).select_from(DeviceRegistration).where(
                DeviceRegistration.company_id == company_id,
                DeviceRegistration.revoked_at.is_(None),
            )
        else:
            raise ValueError(f"Unsupported plan resource: {resource_key}")
        return int(await self.db.scalar(statement) or 0)
