from __future__ import annotations

from datetime import datetime, timedelta, timezone
import uuid

from fastapi import HTTPException, status
from jose import JWTError, jwt
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
) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": subject,
        "company_id": company_id,
        "branch_id": branch_id,
        "station_key": station_key,
        "type": "refresh",
        "jti": str(uuid.uuid4()),
        "exp": now + timedelta(days=settings.refresh_token_expire_days),
        "iat": now,
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        ) from exc
