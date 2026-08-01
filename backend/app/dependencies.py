from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import uuid

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_identity_db, get_restaurant_service_db
from app.models.device import DeviceRegistration
from app.models.settings import BranchSettings
from app.models.user import User
from app.services.business_context_service import (
    load_branch_business_context,
    resolve_user_branch_context,
)
from app.services.staff_scope_policy import normalized_station_key
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
    station_key: str | None = None
    assignment_ids: list[uuid.UUID] = field(default_factory=list)
    scope_types: list[str] = field(default_factory=list)


@dataclass
class DeviceTokenData:
    device_id: uuid.UUID
    company_id: uuid.UUID
    brand_id: uuid.UUID
    branch_id: uuid.UUID
    device_code: str
    name: str
    device_type: str
    station_key: str | None
    business_type: str
    target_database: str
    credential_version: int
    paired_at: datetime
    last_seen_at: datetime


def _device_unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Device credential is invalid or revoked",
    )


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_identity_db),
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
        context = await resolve_user_branch_context(
            db,
            user,
            branch_id,
            station_key=payload.get("station_key"),
        )
    return TokenData(
        user_id=user_id,
        company_id=company_id,
        branch_id=branch_id,
        permissions=payload.get("permissions", []),
        brand_id=context.brand_id if context else None,
        business_type=context.business_type if context else None,
        target_database=context.target_database if context else None,
        station_key=payload.get("station_key"),
        assignment_ids=[uuid.UUID(value) for value in payload.get("assignment_ids", [])],
        scope_types=list(payload.get("scope_types", [])),
    )


async def resolve_device_token(
    token: str,
    db: AsyncSession,
    restaurant_db: AsyncSession,
) -> DeviceTokenData:
    payload = decode_token(token)
    if payload.get("type") != "device_access":
        raise _device_unauthorized()
    try:
        device_id = uuid.UUID(payload["sub"])
        company_id = uuid.UUID(payload["company_id"])
        branch_id = uuid.UUID(payload["branch_id"])
        brand_id = uuid.UUID(payload["brand_id"])
        credential_version = int(payload["credential_version"])
    except (KeyError, TypeError, ValueError) as exc:
        raise _device_unauthorized() from exc

    device = await db.scalar(
        select(DeviceRegistration).where(
            DeviceRegistration.id == device_id,
            DeviceRegistration.company_id == company_id,
            DeviceRegistration.branch_id == branch_id,
        )
    )
    if (
        device is None
        or device.revoked_at is not None
        or device.paired_at is None
        or device.credential_version != credential_version
        or device.device_type != payload.get("device_type")
        or device.station_key != payload.get("station_key")
    ):
        raise _device_unauthorized()

    try:
        context = await load_branch_business_context(db, company_id, branch_id)
    except HTTPException as exc:
        raise _device_unauthorized() from exc
    if (
        context is None
        or context.brand_id != brand_id
        or context.business_type != "restaurant"
        or context.target_database != "restaurant"
        or payload.get("business_type") != "restaurant"
        or payload.get("target_database") != "restaurant"
    ):
        raise _device_unauthorized()

    if device.device_type == "kitchen":
        settings_row = await restaurant_db.scalar(
            select(BranchSettings).where(
                BranchSettings.company_id == company_id,
                BranchSettings.branch_id == branch_id,
            )
        )
        configured_stations = settings_row.fb_kitchen_stations if settings_row else []
        if not any(
            normalized_station_key(value) == normalized_station_key(device.station_key)
            for value in configured_stations or []
        ):
            raise _device_unauthorized()

    now = datetime.now(timezone.utc)
    last_seen_at = device.last_seen_at
    if last_seen_at is None or last_seen_at <= now - timedelta(
        seconds=settings.device_last_seen_write_interval_seconds
    ):
        device.last_seen_at = now
        last_seen_at = now
        await db.commit()
    return DeviceTokenData(
        device_id=device.id,
        company_id=device.company_id,
        brand_id=context.brand_id,
        branch_id=device.branch_id,
        device_code=device.device_code,
        name=device.name,
        device_type=device.device_type,
        station_key=device.station_key,
        business_type=context.business_type,
        target_database=context.target_database,
        credential_version=device.credential_version,
        paired_at=device.paired_at,
        last_seen_at=last_seen_at,
    )


async def get_current_device(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_identity_db),
    restaurant_db: AsyncSession = Depends(get_restaurant_service_db),
) -> DeviceTokenData:
    return await resolve_device_token(token, db, restaurant_db)


async def get_optional_counter_device(
    device_authorization: str | None = Header(default=None, alias="X-Device-Authorization"),
    db: AsyncSession = Depends(get_identity_db),
    restaurant_db: AsyncSession = Depends(get_restaurant_service_db),
) -> DeviceTokenData | None:
    if device_authorization is None:
        return None
    scheme, separator, token = device_authorization.partition(" ")
    if separator != " " or scheme.lower() != "bearer" or not token.strip():
        raise _device_unauthorized()
    current = await resolve_device_token(token.strip(), db, restaurant_db)
    if current.device_type != "counter" or current.station_key is not None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Counter device required for this workspace",
        )
    return current


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


def require_device_type(*device_types: str) -> Callable:
    async def checker(current: DeviceTokenData = Depends(get_current_device)) -> DeviceTokenData:
        if current.device_type in device_types:
            return current
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Device type required: one of {', '.join(device_types)}",
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
    db: AsyncSession = Depends(get_identity_db),
) -> User:
    user = await db.get(User, current.user_id)
    if user is None or user.deleted_at is not None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )
    return user
