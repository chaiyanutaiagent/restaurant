"""Explicit UAT-only link: one credential owner, two separately scoped profiles.

Never link accounts by username. Production retains fully separate identities.
"""
from __future__ import annotations

from datetime import datetime, timezone
import os
import uuid
from urllib.parse import urlsplit

from fastapi import HTTPException
from sqlalchemy import update

from app.config import settings
from app.models.auth import RefreshToken
from app.models.company import Company
from app.models.platform import PlatformOperator, PlatformSession, SaasAccountCredential
from app.models.user import User


def owner_link() -> tuple[uuid.UUID, uuid.UUID] | None:
    user_id = os.environ.get("UAT_OWNER_TENANT_USER_ID")
    operator_id = os.environ.get("UAT_OWNER_PLATFORM_OPERATOR_ID")
    if not user_id and not operator_id:
        return None
    if (not user_id or not operator_id or settings.environment != "development"
            or settings.identity_database != "platform_core"
            or not (urlsplit(settings.saas_public_base_url).hostname or "").startswith("uat-")):
        raise HTTPException(503, "UAT owner identity configuration is invalid")
    try:
        return uuid.UUID(user_id), uuid.UUID(operator_id)
    except ValueError as exc:
        raise HTTPException(503, "UAT owner identity configuration is invalid") from exc


async def linked_owner_user(db, operator):
    link = owner_link()
    if link is None or operator.id != link[1]:
        return None
    user = await db.get(User, link[0])
    company = await db.get(Company, user.company_id) if user else None
    if (not operator.is_active or not user or not user.is_active
            or user.deleted_at is not None or not user.is_superuser
            or not company or not company.is_active):
        raise HTTPException(401, "Owner identity is inactive")
    return user


async def platform_password_hash(db, operator):
    user = await linked_owner_user(db, operator)
    return user.hashed_password if user is not None else operator.hashed_password


async def revoke_linked_platform_sessions(db, user, *, now=None):
    link = owner_link()
    if link is None or user.id != link[0]:
        return
    operator = await db.get(PlatformOperator, link[1])
    if operator is None:
        raise HTTPException(503, "Owner access profile is missing")
    operator.credential_version += 1
    operator.password_changed_at = now or datetime.now(timezone.utc)
    await db.execute(update(PlatformSession).where(
        PlatformSession.operator_id == operator.id,
        PlatformSession.revoked_at.is_(None),
    ).values(revoked_at=operator.password_changed_at, revocation_reason="owner-password-changed"))


async def change_linked_owner_password(db, operator, password_hash, now):
    user = await linked_owner_user(db, operator)
    if user is None:
        return False
    user.hashed_password = password_hash
    user.password_changed_at = now
    user.credential_version += 1
    await db.execute(update(RefreshToken).where(
        RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None),
    ).values(revoked_at=now))
    await db.execute(update(SaasAccountCredential).where(
        SaasAccountCredential.owner_user_id == user.id,
        SaasAccountCredential.used_at.is_(None),
    ).values(used_at=now))
    return True
