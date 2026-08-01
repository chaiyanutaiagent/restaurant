from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_identity_db
from app.dependencies import TokenData, get_current_user, get_current_user_db
from app.models.user import User
from app.schemas.auth import (
    BranchSwitchRequest,
    LoginRequest,
    LogoutRequest,
    MeResponse,
    RefreshRequest,
    TokenResponse,
)
from app.schemas.user import UserRead
from app.services.auth_service import AuthService
from app.utils.security import decode_token

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


def ok(data: Any) -> dict[str, Any]:
    return {
        "data": data,
        "meta": {
            "version": settings.app_version,
            "identity_database": settings.identity_database,
        },
        "error": None,
    }


def _token_response(access_token: str, refresh_token: str, user: User) -> TokenResponse:
    payload = decode_token(access_token)
    expires_in = int(
        datetime.fromtimestamp(payload["exp"], tz=timezone.utc).timestamp()
        - datetime.now(timezone.utc).timestamp()
    )
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=max(expires_in, 0),
        user=UserRead.model_validate(user),
    )


@router.post("/login")
async def login(
    payload: LoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_identity_db),
    x_company_id: str | None = Header(default=None, alias="X-Company-ID"),
) -> dict[str, Any]:
    company_id_raw = x_company_id or (str(payload.company_id) if payload.company_id else None)
    if company_id_raw is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Company ID is required",
        )
    company_id = uuid.UUID(company_id_raw)

    auth_service = AuthService(
        db,
        emit_reference_events=settings.identity_database == "platform_core",
    )
    user = await auth_service.authenticate_user(company_id, payload.username, payload.password)
    access_token, refresh_token = await auth_service.create_session(
        user=user,
        branch_id=payload.branch_id,
        station_key=payload.station_key,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    return ok(_token_response(access_token, refresh_token, user).model_dump())


@router.post("/refresh")
async def refresh(
    payload: RefreshRequest,
    request: Request,
    db: AsyncSession = Depends(get_identity_db),
) -> dict[str, Any]:
    auth_service = AuthService(db)
    access_token, refresh_token = await auth_service.refresh_session(
        payload.refresh_token,
        request.client.host if request.client else None,
    )
    access_payload = decode_token(access_token)
    user = await db.get(User, uuid.UUID(access_payload["sub"]))
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )
    return ok(_token_response(access_token, refresh_token, user).model_dump())


@router.post("/logout")
async def logout(
    payload: LogoutRequest,
    db: AsyncSession = Depends(get_identity_db),
) -> dict[str, Any]:
    auth_service = AuthService(db)
    await auth_service.logout(payload.refresh_token)
    return ok({"message": "Logged out"})


@router.get("/me")
async def me(
    current: TokenData = Depends(get_current_user),
    user: User = Depends(get_current_user_db),
) -> dict[str, Any]:
    data = MeResponse(
        user=UserRead.model_validate(user),
        company_id=current.company_id,
        branch_id=current.branch_id,
        brand_id=current.brand_id,
        business_type=current.business_type,
        target_database=current.target_database,
        station_key=current.station_key,
        assignment_ids=current.assignment_ids,
        scope_types=current.scope_types,
        permissions=current.permissions,
    )
    return ok(data.model_dump())


@router.post("/switch-branch")
async def switch_branch(
    payload: BranchSwitchRequest,
    db: AsyncSession = Depends(get_identity_db),
    user: User = Depends(get_current_user_db),
) -> dict[str, Any]:
    auth_service = AuthService(db)
    access_token, refresh_token = await auth_service.switch_branch(
        user,
        payload.branch_id,
        station_key=payload.station_key,
    )
    return ok(_token_response(access_token, refresh_token, user).model_dump())


@router.get("/permissions")
async def permissions(
    current: TokenData = Depends(get_current_user),
) -> dict[str, Any]:
    return ok({"permissions": current.permissions})
