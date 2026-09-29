"""Business-code onboarding. Credentials never yield a company-wide mobile token."""
from __future__ import annotations

import uuid
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_identity_db
from app.models.branch import Branch
from app.routers.auth import _token_response, ok
from app.services.auth_service import AuthService
from app.services.business_directory_service import resolve_active_business
from app.services.mobile_store_policy import (
    MOBILE_STORE_SURFACE,
    store_permissions,
    uat_superadmin_store_access,
)
from app.utils.public_rate_limit import require_public_rate_limit

router = APIRouter(prefix="/api/v1/mobile-store", tags=["mobile-store"])


class StoreCredentials(BaseModel):
    business_code: str = Field(min_length=3, max_length=63)
    username: str = Field(min_length=1, max_length=150)
    password: str = Field(min_length=1, max_length=256)
    station_key: str = Field(min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")
    device_id: uuid.UUID


class StoreLogin(StoreCredentials):
    branch_id: uuid.UUID


@router.get("/businesses/{business_code}")
async def business(business_code: str, request: Request, db: AsyncSession = Depends(get_identity_db)):
    await require_public_rate_limit(request, "store-business", limit=30)
    company = await resolve_active_business(db, business_code)
    return ok({"business_code": company.business_slug, "name": company.name})


async def authenticate(payload: StoreCredentials, request: Request, db: AsyncSession):
    await require_public_rate_limit(request, "store-login", subject=payload.business_code, limit=10)
    company = await resolve_active_business(db, payload.business_code)
    service = AuthService(db)
    user = await service.authenticate_user(company.id, payload.username.strip().lower(), payload.password)
    if user.is_superuser and not uat_superadmin_store_access(user):
        raise HTTPException(403, "Platform administrators cannot sign in to Takeaway Store")
    return company, user, service


@router.post("/branches")
async def branches(payload: StoreCredentials, request: Request, db: AsyncSession = Depends(get_identity_db)):
    company, user, service = await authenticate(payload, request, db)
    candidates = (await db.scalars(select(Branch).where(
        Branch.company_id == company.id, Branch.is_active.is_(True), Branch.deleted_at.is_(None),
    ).order_by(Branch.code))).all()
    allowed = []
    for branch in candidates:
        try:
            permissions, _, context, _, _, _ = await service.get_user_permissions(user, branch.id, payload.station_key)
            store_permissions(user=user, context=context, permissions=permissions, device_id=str(payload.device_id))
        except HTTPException as exc:
            if exc.status_code in {400, 403, 404}:
                continue
            raise
        allowed.append({"id": str(branch.id), "code": branch.code, "name": branch.name})
    if not allowed:
        raise HTTPException(403, "No Takeaway Store branch is assigned to this employee")
    return ok(allowed)


@router.post("/login")
async def login(payload: StoreLogin, request: Request, db: AsyncSession = Depends(get_identity_db)):
    company, user, service = await authenticate(payload, request, db)
    tokens = await service.create_session(
        user=user, branch_id=payload.branch_id, station_key=payload.station_key,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        client_surface=MOBILE_STORE_SURFACE, store_device_id=str(payload.device_id),
    )
    return ok((await _token_response(*tokens, user, db)).model_dump())
