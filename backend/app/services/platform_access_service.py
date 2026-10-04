from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime, timezone
import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.platform import PlatformOperator, PlatformOperatorRoleAssignment


PLATFORM_ROLE_LABELS: dict[str, str] = {
    "platform_owner": "Platform Owner",
    "operations": "Operations",
    "support": "Support",
    "billing": "Billing",
    "security": "Security",
    "auditor": "Auditor",
}

PLATFORM_ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    "platform_owner": frozenset({"*"}),
    "operations": frozenset(
        {
            "platform.company.view",
            "platform.module.view",
            "platform.operations.view",
            "platform.operations.manage",
            "platform.release.propose",
            "platform.audit.view",
        }
    ),
    "support": frozenset(
        {
            "platform.company.view",
            "platform.module.view",
            "platform.support.view",
            "platform.support.respond",
            "platform.support.request_access",
            "platform.privacy.view",
        }
    ),
    "billing": frozenset(
        {
            "platform.company.view",
            "platform.module.view",
            "platform.billing.view",
            "platform.billing.manage",
            "platform.audit.view",
        }
    ),
    "security": frozenset(
        {
            "platform.security.view",
            "platform.security.manage",
            "platform.security.session.revoke",
            "platform.team.view",
            "platform.team.manage",
            "platform.audit.view",
            "platform.audit.export",
        }
    ),
    "auditor": frozenset(
        {
            "platform.company.view",
            "platform.module.view",
            "platform.billing.view",
            "platform.operations.view",
            "platform.support.view",
            "platform.privacy.view",
            "platform.security.view",
            "platform.team.view",
            "platform.audit.view",
            "platform.audit.export",
        }
    ),
}


def platform_environment() -> str:
    return "production" if settings.environment == "production" else "uat"


def permissions_for_roles(role_codes: Iterable[str]) -> frozenset[str]:
    permissions: set[str] = set()
    for role_code in role_codes:
        permissions.update(PLATFORM_ROLE_PERMISSIONS.get(role_code, ()))
    return frozenset(permissions)


def has_permission(permissions: Iterable[str], permission: str) -> bool:
    values = set(permissions)
    return "*" in values or permission in values


async def effective_platform_access(
    db: AsyncSession,
    operator: PlatformOperator,
    *,
    environment: str | None = None,
) -> tuple[list[str], list[str]]:
    target_environment = environment or platform_environment()
    if operator.is_superuser:
        return ["platform_owner"], ["*"]
    role_codes = list(
        (
            await db.scalars(
                select(PlatformOperatorRoleAssignment.role_code)
                .where(
                    PlatformOperatorRoleAssignment.operator_id == operator.id,
                    PlatformOperatorRoleAssignment.environment == target_environment,
                    PlatformOperatorRoleAssignment.revoked_at.is_(None),
                )
                .order_by(PlatformOperatorRoleAssignment.role_code)
            )
        ).all()
    )
    # Existing installations bootstrap their first owner with is_superuser. It
    # remains an explicit owner grant until the account is migrated in Team.
    permissions = sorted(permissions_for_roles(role_codes))
    return role_codes, permissions


def require_platform_permission(current, permission: str) -> None:
    if not current.is_superuser and not has_permission(current.permissions, permission):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "platform_permission_denied",
                "message": "You do not have permission to perform this Platform action",
                "required_permission": permission,
                "environment": current.environment,
            },
        )


async def active_owner_count(
    db: AsyncSession,
    *,
    environment: str,
    excluding_operator_id: uuid.UUID | None = None,
) -> int:
    operators = (
        await db.scalars(
            select(PlatformOperator).where(PlatformOperator.is_active.is_(True))
        )
    ).all()
    count = 0
    now = datetime.now(timezone.utc)
    for operator in operators:
        if excluding_operator_id is not None and operator.id == excluding_operator_id:
            continue
        role_codes, _ = await effective_platform_access(
            db, operator, environment=environment
        )
        if "platform_owner" in role_codes:
            count += 1
        # Keep the loop deterministic if a test supplies a stale in-memory row.
        _ = now
    return count
