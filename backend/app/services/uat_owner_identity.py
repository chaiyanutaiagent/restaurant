"""Revoke an explicitly linked UAT owner's Platform sessions on password reset.

No username-based linking and no Production identity linking are permitted.
"""
from __future__ import annotations

from datetime import datetime, timezone
import os
import uuid
from urllib.parse import urlsplit

from fastapi import HTTPException
from sqlalchemy import update

from app.config import settings
from app.models.platform import PlatformOperator, PlatformSession


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
