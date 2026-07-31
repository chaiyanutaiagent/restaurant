from __future__ import annotations

import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.business_context import (
    CanonicalBusinessContext,
    assignment_matches_context,
    target_database_for,
)
from app.models.branch import Branch
from app.models.restaurant import Brand, BrandBranch
from app.models.user import User, UserBranch


async def load_branch_business_context(
    db: AsyncSession,
    company_id: uuid.UUID,
    branch_id: uuid.UUID,
    *,
    required: bool = True,
) -> CanonicalBusinessContext | None:
    branch_exists = await db.scalar(
        select(Branch.id).where(
            Branch.id == branch_id,
            Branch.company_id == company_id,
            Branch.deleted_at.is_(None),
            Branch.is_active.is_(True),
        )
    )
    if branch_exists is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Branch not found")

    row = (
        await db.execute(
            select(Brand.id, Brand.business_type)
            .join(BrandBranch, BrandBranch.brand_id == Brand.id)
            .where(
                Brand.company_id == company_id,
                Brand.is_active.is_(True),
                BrandBranch.company_id == company_id,
                BrandBranch.branch_id == branch_id,
                BrandBranch.is_active.is_(True),
            )
            .limit(1)
        )
    ).one_or_none()
    if row is None:
        if required:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Branch has no active Brand business context",
            )
        return None

    brand_id, business_type = row
    try:
        target_database = target_database_for(business_type)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Brand has an unsupported business type",
        ) from exc
    return CanonicalBusinessContext(
        company_id=company_id,
        brand_id=brand_id,
        branch_id=branch_id,
        business_type=business_type,
        target_database=target_database,
    )


async def resolve_user_branch_context(
    db: AsyncSession,
    user: User,
    branch_id: uuid.UUID,
    *,
    require_business_context: bool = False,
) -> CanonicalBusinessContext | None:
    context = await load_branch_business_context(
        db,
        user.company_id,
        branch_id,
        required=require_business_context,
    )
    if user.is_superuser:
        return context

    assignment = await db.scalar(
        select(UserBranch).where(
            UserBranch.user_id == user.id,
            UserBranch.branch_id == branch_id,
            UserBranch.deleted_at.is_(None),
        )
    )
    if assignment is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Branch access is no longer active",
        )
    if context is not None and not assignment_matches_context(
        assignment_brand_id=assignment.brand_id,
        assignment_business_type=assignment.business_type,
        assignment_target_database=assignment.target_database,
        context=context,
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Branch assignment business context is no longer valid",
        )
    return context
