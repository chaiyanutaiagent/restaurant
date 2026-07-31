from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import uuid

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.services.business_context_service import resolve_user_branch_context
from app.utils.security import decode_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


@dataclass
class TokenData:
    user_id: uuid.UUID
    company_id: uuid.UUID
    branch_id: uuid.UUID | None
    permissions: list[str]
    brand_id: uuid.UUID | None = None
    business_type: str | None = None
    target_database: str | None = None


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> TokenData:
    payload = decode_token(token)
    if payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type",
        )
    user_id = uuid.UUID(payload["sub"])
    company_id = uuid.UUID(payload["company_id"])
    user = await db.scalar(
        select(User).where(
            User.id == user_id,
            User.company_id == company_id,
            User.deleted_at.is_(None),
            User.is_active.is_(True),
        )
    )
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User is inactive or no longer exists",
        )
    branch_id = uuid.UUID(payload["branch_id"]) if payload.get("branch_id") else None
    context = None
    if branch_id is not None:
        context = await resolve_user_branch_context(db, user, branch_id)
    return TokenData(
        user_id=user_id,
        company_id=company_id,
        branch_id=branch_id,
        permissions=payload.get("permissions", []),
        brand_id=context.brand_id if context else None,
        business_type=context.business_type if context else None,
        target_database=context.target_database if context else None,
    )


def require_permission(code: str) -> Callable:
    async def checker(current: TokenData = Depends(get_current_user)) -> TokenData:
        if "*" in current.permissions or code in current.permissions:
            return current
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Permission required: {code}",
        )

    return checker


def require_any_permission(*codes: str) -> Callable:
    async def checker(current: TokenData = Depends(get_current_user)) -> TokenData:
        if "*" in current.permissions or any(code in current.permissions for code in codes):
            return current
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Permission required: one of {', '.join(codes)}",
        )

    return checker


def require_business_type(expected: str) -> Callable:
    async def checker(current: TokenData = Depends(get_current_user)) -> TokenData:
        if current.business_type == expected:
            return current
        if current.business_type is None and (
            current.branch_id is None or "*" in current.permissions
        ):
            return current
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Business context required: {expected}",
        )

    return checker


async def get_current_user_db(
    current: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> User:
    user = await db.get(User, current.user_id)
    if user is None or user.deleted_at is not None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )
    return user
