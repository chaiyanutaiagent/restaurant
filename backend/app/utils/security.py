from __future__ import annotations

from datetime import datetime, timedelta, timezone
import uuid

from fastapi import HTTPException, status
import jwt
from jwt import PyJWTError
from passlib.context import CryptContext

from app.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain: str) -> str:
    return pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_access_token(
    subject: str,
    company_id: str,
    branch_id: str | None,
    permissions: list[str],
    expires_delta: timedelta | None = None,
    *,
    brand_id: str | None = None,
    business_type: str | None = None,
    target_database: str | None = None,
    station_key: str | None = None,
    assignment_ids: list[str] | None = None,
    scope_types: list[str] | None = None,
    company_credential_version: int = 1,
) -> str:
    now = datetime.now(timezone.utc)
    expire = now + (
        expires_delta or timedelta(minutes=settings.access_token_expire_minutes)
    )
    payload = {
        "sub": subject,
        "company_id": company_id,
        "branch_id": branch_id,
        "brand_id": brand_id,
        "business_type": business_type,
        "target_database": target_database,
        "station_key": station_key,
        "assignment_ids": assignment_ids or [],
        "scope_types": scope_types or [],
        "permissions": permissions,
        "company_credential_version": company_credential_version,
        "type": "access",
        "exp": expire,
        "iat": now,
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def create_refresh_token(
    subject: str,
    company_id: str,
    *,
    branch_id: str | None = None,
    station_key: str | None = None,
    company_credential_version: int = 1,
) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": subject,
        "company_id": company_id,
        "branch_id": branch_id,
        "station_key": station_key,
        "company_credential_version": company_credential_version,
        "type": "refresh",
        "jti": str(uuid.uuid4()),
        "exp": now + timedelta(days=settings.refresh_token_expire_days),
        "iat": now,
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def create_approval_token(
    *,
    grant_id: uuid.UUID,
    company_id: uuid.UUID,
    branch_id: uuid.UUID,
    requester_id: uuid.UUID,
    approver_id: uuid.UUID,
    action: str,
    reason: str,
    request_hash: str,
    expires_delta: timedelta | None = None,
) -> str:
    now = datetime.now(timezone.utc)
    expire = now + (
        expires_delta or timedelta(seconds=settings.approval_token_expire_seconds)
    )
    payload = {
        "sub": str(requester_id),
        "jti": str(grant_id),
        "company_id": str(company_id),
        "branch_id": str(branch_id),
        "requester_id": str(requester_id),
        "approver_id": str(approver_id),
        "action": action,
        "reason": reason,
        "request_hash": request_hash,
        "type": "approval",
        "exp": expire,
        "iat": now,
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def create_device_access_token(
    *,
    device_id: uuid.UUID,
    company_id: uuid.UUID,
    brand_id: uuid.UUID,
    branch_id: uuid.UUID,
    device_type: str,
    station_key: str | None,
    credential_version: int,
    company_credential_version: int = 1,
    expires_delta: timedelta | None = None,
) -> str:
    now = datetime.now(timezone.utc)
    expire = now + (
        expires_delta or timedelta(days=settings.device_access_token_expire_days)
    )
    payload = {
        "sub": str(device_id),
        "company_id": str(company_id),
        "brand_id": str(brand_id),
        "branch_id": str(branch_id),
        "business_type": "restaurant",
        "target_database": "restaurant",
        "device_type": device_type,
        "station_key": station_key,
        "credential_version": credential_version,
        "company_credential_version": company_credential_version,
        "type": "device_access",
        "jti": str(uuid.uuid4()),
        "exp": expire,
        "iat": now,
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def create_platform_access_token(
    *,
    operator_id: uuid.UUID,
    session_id: uuid.UUID,
    credential_version: int,
    is_superuser: bool,
    expires_delta: timedelta | None = None,
) -> str:
    now = datetime.now(timezone.utc)
    expire = now + (
        expires_delta or timedelta(minutes=settings.access_token_expire_minutes)
    )
    payload = {
        "sub": str(operator_id),
        "sid": str(session_id),
        "credential_version": credential_version,
        "is_superuser": is_superuser,
        "type": "platform_access",
        "jti": str(uuid.uuid4()),
        "exp": expire,
        "iat": now,
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def create_offline_sale_authorization(
    *,
    user_id: uuid.UUID,
    company_id: uuid.UUID,
    branch_id: uuid.UUID,
    shift_id: uuid.UUID | None,
    location_id: uuid.UUID | None,
    brand_id: uuid.UUID | None,
    device_id: uuid.UUID | None,
    device_credential_version: int | None,
    expires_delta: timedelta | None = None,
) -> str:
    now = datetime.now(timezone.utc)
    expire = now + (
        expires_delta
        or timedelta(hours=settings.offline_sale_authorization_expire_hours)
    )
    payload = {
        "sub": str(user_id),
        "company_id": str(company_id),
        "branch_id": str(branch_id),
        "shift_id": str(shift_id) if shift_id else None,
        "location_id": str(location_id) if location_id else None,
        "brand_id": str(brand_id) if brand_id else None,
        "device_id": str(device_id) if device_id else None,
        "device_credential_version": device_credential_version,
        "policy_version": 1,
        "type": "offline_sale_authorization",
        "exp": expire,
        "iat": now,
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def decode_offline_sale_authorization(token: str) -> dict:
    try:
        return jwt.decode(
            token,
            settings.secret_key,
            algorithms=[settings.algorithm],
            options={"verify_exp": False},
        )
    except PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid offline sale authorization",
        ) from exc


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
    except PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        ) from exc
