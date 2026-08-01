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
from app.models.role import Role
from app.models.staff_assignment import StaffRoleAssignment
from app.models.user import User, UserBranch
from app.services.staff_scope_policy import assignment_applies_to_context


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
    station_key: str | None = None,
) -> CanonicalBusinessContext | None:
    context = await load_branch_business_context(
        db,
        user.company_id,
        branch_id,
        required=require_business_context,
    )
    if user.is_superuser:
        return context

    legacy_row = (
        await db.execute(
            select(UserBranch, Role.allowed_scope_types)
            .join(Role, Role.id == UserBranch.role_id)
            .where(
                UserBranch.user_id == user.id,
                UserBranch.branch_id == branch_id,
                UserBranch.deleted_at.is_(None),
                Role.deleted_at.is_(None),
            )
        )
    ).one_or_none()
    legacy_assignment = (
        legacy_row[0]
        if legacy_row is not None and "branch" in legacy_row[1]
        else None
    )
    scoped_assignment_rows = (
        await db.execute(
            select(StaffRoleAssignment, Role.allowed_scope_types)
            .join(Role, Role.id == StaffRoleAssignment.role_id)
            .where(
                StaffRoleAssignment.company_id == user.company_id,
                StaffRoleAssignment.user_id == user.id,
                StaffRoleAssignment.revoked_at.is_(None),
                Role.deleted_at.is_(None),
            )
        )
    ).all()
    has_scoped_access = context is not None and any(
        assignment.scope_type in role_scope_types
        and assignment_applies_to_context(assignment, context, station_key)
        for assignment, role_scope_types in scoped_assignment_rows
    )
    if legacy_assignment is None and not has_scoped_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Branch access is no longer active",
        )
    if legacy_assignment is not None and context is not None and not assignment_matches_context(
        assignment_brand_id=legacy_assignment.brand_id,
        assignment_business_type=legacy_assignment.business_type,
        assignment_target_database=legacy_assignment.target_database,
        context=context,
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Branch assignment business context is no longer valid",
        )
    return context
