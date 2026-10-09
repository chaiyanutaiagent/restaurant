from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime, timezone
import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.platform import PlatformCustomRole, PlatformOperator, PlatformOperatorRoleAssignment


PLATFORM_ROLE_LABELS: dict[str, str] = {
    "platform_owner": "Platform Owner",
    "operations": "Operations",
    "support": "Support",
    "billing": "Billing",
    "security": "Security",
    "auditor": "Auditor",
}

PLATFORM_ROLE_DESCRIPTIONS: dict[str, str] = {
    "platform_owner": "Full Platform control. Keep at least one active owner.",
    "operations": "Company visibility, runtime operations, releases, and audit visibility.",
    "support": "Customer support with tenant-approved access requests.",
    "billing": "Subscription, invoice, and billing administration.",
    "security": "Platform identities, sessions, security, and audit administration.",
    "auditor": "Read-only oversight across Platform operations.",
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

PLATFORM_PERMISSION_CATALOG: tuple[dict[str, str], ...] = (
    {"code": "platform.company.view", "label": "ดูบริษัทลูกค้า", "group": "companies", "group_label": "บริษัทลูกค้า", "risk": "standard"},
    {"code": "platform.company.manage", "label": "สร้างและแก้ไขบริษัทลูกค้า", "group": "companies", "group_label": "บริษัทลูกค้า", "risk": "sensitive"},
    {"code": "platform.company.lifecycle", "label": "ระงับหรือเปิดบริษัทลูกค้า", "group": "companies", "group_label": "บริษัทลูกค้า", "risk": "critical"},
    {"code": "platform.module.view", "label": "ดูโมดูลของบริษัท", "group": "companies", "group_label": "บริษัทลูกค้า", "risk": "standard"},
    {"code": "platform.module.manage", "label": "เปิดหรือปิดโมดูลของบริษัท", "group": "companies", "group_label": "บริษัทลูกค้า", "risk": "sensitive"},
    {"code": "platform.billing.view", "label": "ดู Billing", "group": "billing", "group_label": "Billing", "risk": "standard"},
    {"code": "platform.billing.manage", "label": "จัดการแผน Subscription และ Invoice", "group": "billing", "group_label": "Billing", "risk": "critical"},
    {"code": "platform.support.view", "label": "ดู Support Ticket", "group": "support", "group_label": "Privacy & Support", "risk": "standard"},
    {"code": "platform.support.respond", "label": "ตอบและจัดการ Support Ticket", "group": "support", "group_label": "Privacy & Support", "risk": "sensitive"},
    {"code": "platform.support.request_access", "label": "ขอเข้าถึงบริบทลูกค้าชั่วคราว", "group": "support", "group_label": "Privacy & Support", "risk": "critical"},
    {"code": "platform.privacy.view", "label": "ดูคำขอข้อมูลส่วนบุคคล", "group": "support", "group_label": "Privacy & Support", "risk": "sensitive"},
    {"code": "platform.privacy.manage", "label": "ดำเนินการคำขอข้อมูลส่วนบุคคล", "group": "support", "group_label": "Privacy & Support", "risk": "critical"},
    {"code": "platform.operations.view", "label": "ดูสถานะระบบและหลักฐานปฏิบัติการ", "group": "operations", "group_label": "Operations", "risk": "standard"},
    {"code": "platform.operations.manage", "label": "บันทึกสถานะและนำเข้าหลักฐาน", "group": "operations", "group_label": "Operations", "risk": "sensitive"},
    {"code": "platform.release.propose", "label": "เสนอการเปิด Release", "group": "operations", "group_label": "Operations", "risk": "critical"},
    {"code": "platform.team.view", "label": "ดูเจ้าหน้าที่และ Role", "group": "identity", "group_label": "Team & Security", "risk": "sensitive"},
    {"code": "platform.team.manage", "label": "เชิญเจ้าหน้าที่และจัดการ Role", "group": "identity", "group_label": "Team & Security", "risk": "critical"},
    {"code": "platform.security.view", "label": "ดู MFA และ Session", "group": "identity", "group_label": "Team & Security", "risk": "sensitive"},
    {"code": "platform.security.manage", "label": "จัดการนโยบายความปลอดภัย", "group": "identity", "group_label": "Team & Security", "risk": "critical"},
    {"code": "platform.security.session.revoke", "label": "เพิกถอน Session ของเจ้าหน้าที่", "group": "identity", "group_label": "Team & Security", "risk": "critical"},
    {"code": "platform.audit.view", "label": "ดู Audit Log", "group": "audit", "group_label": "Audit", "risk": "standard"},
    {"code": "platform.audit.export", "label": "ส่งออก Audit และข้อมูลบริษัท", "group": "audit", "group_label": "Audit", "risk": "critical"},
)
PLATFORM_ASSIGNABLE_PERMISSIONS = frozenset(item["code"] for item in PLATFORM_PERMISSION_CATALOG)


def platform_environment() -> str:
    return "production" if settings.environment == "production" else "uat"


def permissions_for_roles(role_codes: Iterable[str]) -> frozenset[str]:
    permissions: set[str] = set()
    for role_code in role_codes:
        permissions.update(PLATFORM_ROLE_PERMISSIONS.get(role_code, ()))
    return frozenset(permissions)


async def permissions_for_role_codes(
    db: AsyncSession,
    role_codes: Iterable[str],
    *,
    environment: str,
) -> frozenset[str]:
    codes = sorted(set(role_codes))
    permissions = set(permissions_for_roles(codes))
    custom_codes = [code for code in codes if code not in PLATFORM_ROLE_PERMISSIONS]
    if custom_codes:
        rows = (
            await db.scalars(
                select(PlatformCustomRole).where(
                    PlatformCustomRole.environment == environment,
                    PlatformCustomRole.code.in_(custom_codes),
                    PlatformCustomRole.is_active.is_(True),
                )
            )
        ).all()
        for row in rows:
            permissions.update(row.permissions or [])
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
    permissions = sorted(
        await permissions_for_role_codes(db, role_codes, environment=target_environment)
    )
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
