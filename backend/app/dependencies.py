from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import uuid

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User, UserBranch
from app.utils.security import decode_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


@dataclass
class TokenData:
    user_id: uuid.UUID
    company_id: uuid.UUID
    branch_id: uuid.UUID | None
    permissions: list[str]
    brand_id: uuid.UUID | None = None


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
    brand_id: uuid.UUID | None = None
    if branch_id is not None and not user.is_superuser:
        assignment = await db.scalar(
            select(UserBranch).where(
                UserBranch.user_id == user.id,
                UserBranch.branch_id == branch_id,
                UserBranch.deleted_at.is_(None),
            )
        )
        if assignment is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Branch access is no longer active",
            )
        brand_id = assignment.brand_id
    return TokenData(
        user_id=user_id,
        company_id=company_id,
        branch_id=branch_id,
        permissions=payload.get("permissions", []),
        brand_id=brand_id,
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
