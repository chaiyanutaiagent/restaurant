from __future__ import annotations

import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.company import Company
from app.utils.business_slug import normalize_business_slug, suggest_business_slug


async def allocate_business_slug(
    db: AsyncSession,
    *,
    requested_slug: str | None,
    business_name: str,
    company_id: uuid.UUID,
) -> str:
    candidate = (
        normalize_business_slug(requested_slug)
        if requested_slug
        else suggest_business_slug(business_name, fallback_suffix=company_id.hex[:12])
    )
    existing = await db.scalar(select(Company.id).where(Company.business_slug == candidate))
    if existing is None:
        return candidate
    if requested_slug:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Business URL is already in use",
        )
    for attempt in range(1, 101):
        suffix = company_id.hex[:8] if attempt == 1 else f"{company_id.hex[:8]}-{attempt}"
        prefix = candidate[: 62 - len(suffix)].rstrip("-")
        generated = normalize_business_slug(f"{prefix}-{suffix}")
        existing = await db.scalar(select(Company.id).where(Company.business_slug == generated))
        if existing is None:
            return generated
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="Could not allocate a unique business URL",
    )


async def resolve_active_business(db: AsyncSession, business_slug: str) -> Company:
    try:
        normalized = normalize_business_slug(business_slug)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Business not found") from exc
    company = await db.scalar(
        select(Company).where(
            Company.business_slug == normalized,
            Company.is_active.is_(True),
        )
    )
    if company is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Business not found")
    return company
