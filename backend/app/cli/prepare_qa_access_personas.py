from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
import secrets
import uuid
from urllib.parse import urlsplit

from sqlalchemy import select, update
from sqlalchemy.orm import selectinload

from app.config import settings
from app.database import PlatformSessionLocal
from app.models.audit import AuditLog
from app.models.auth import RefreshToken
from app.models.branch import Branch
from app.models.company import Company
from app.models.platform import PlatformOperator, PlatformOperatorRoleAssignment, PlatformSession
from app.models.restaurant import Brand, BrandBranch
from app.models.role import Permission, Role
from app.models.staff_assignment import StaffRoleAssignment
from app.models.user import User, UserBranch
from app.services.role_preset_service import ROLE_PRESET_POLICIES
from app.services.staff_scope_policy import assignment_scope_key
from app.utils.security import hash_password


@dataclass(frozen=True)
class TenantPersona:
    key: str
    username: str
    preset_key: str | None
    scope_type: str
    business_type: str = "restaurant"


@dataclass(frozen=True)
class PlatformPersona:
    key: str
    username: str
    role_code: str


TENANT_PERSONAS = (
    TenantPersona("company_admin", "admin", None, "company"),
    TenantPersona("branch_manager", "uat.branch-manager", "branch-manager", "branch"),
    TenantPersona("cashier_service", "uat.cashier", "cashier", "branch"),
    TenantPersona("kitchen", "qa.kitchen", "kitchen-manager", "branch"),
    TenantPersona("accountant", "uat.accountant", "accountant", "company"),
    TenantPersona("purchasing", "uat.purchasing", "purchasing", "company"),
    TenantPersona("warehouse", "qa.warehouse", "warehouse", "branch"),
    TenantPersona("auditor", "qa.auditor", "auditor", "company"),
    TenantPersona("retail_cashier", "qa.retail-cashier", "cashier", "branch", "retail_pos"),
)

PLATFORM_PERSONAS = (
    PlatformPersona("platform_admin", "qa.platform-admin", "platform_owner"),
    PlatformPersona("platform_operator", "qa.platform-operator", "operations"),
    PlatformPersona("platform_auditor", "qa.platform-auditor", "auditor"),
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Prepare least-privilege identities referenced by Local/UAT QA Access Mode.",
    )
    parser.add_argument("--company-id", type=uuid.UUID, required=True)
    parser.add_argument("--actor-username", required=True)
    parser.add_argument("--restaurant-brand-slug", required=True)
    parser.add_argument("--branch-code", required=True)
    parser.add_argument("--retail-brand-slug", default="foodchain-retail-uat")
    parser.add_argument("--retail-branch-code", default="RTL-01")
    parser.add_argument("--yes", action="store_true")
    return parser


def require_bounded_qa_uat(args: argparse.Namespace) -> None:
    public_url = urlsplit(settings.saas_public_base_url)
    if not args.yes:
        raise RuntimeError("Pass --yes to prepare persistent QA identities")
    if (
        settings.environment != "development"
        or public_url.scheme != "https"
        or public_url.hostname is None
        or not public_url.hostname.startswith("uat-")
    ):
        raise RuntimeError("QA persona preparation is restricted to HTTPS uat-* development")
    if settings.identity_database != "platform_core":
        raise RuntimeError("QA persona preparation requires Platform identity")
    if not settings.qa_access_mode_enabled:
        raise RuntimeError("Enable QA_ACCESS_MODE_ENABLED before preparing QA personas")
    if settings.uat_auth_bypass_enabled:
        raise RuntimeError("Legacy UAT credentialless auth bypass must remain disabled")
    if settings.qa_access_company_id != args.company_id:
        raise RuntimeError("QA persona Company must match QA_ACCESS_COMPANY_ID")


async def _load_scope(
    db,
    args: argparse.Namespace,
    *,
    business_type: str = "restaurant",
) -> tuple[Company, User, Brand, Branch]:
    company = await db.get(Company, args.company_id)
    actor = await db.scalar(
        select(User).where(
            User.company_id == args.company_id,
            User.username == args.actor_username.strip().lower(),
            User.is_superuser.is_(True),
            User.is_active.is_(True),
            User.deleted_at.is_(None),
        )
    )
    brand_slug = (
        args.restaurant_brand_slug
        if business_type == "restaurant"
        else args.retail_brand_slug
    )
    branch_code = args.branch_code if business_type == "restaurant" else args.retail_branch_code
    scope = (
        await db.execute(
            select(Brand, Branch)
            .select_from(Brand)
            .join(BrandBranch, BrandBranch.brand_id == Brand.id)
            .join(Branch, Branch.id == BrandBranch.branch_id)
            .where(
                Brand.company_id == args.company_id,
                Brand.slug == brand_slug.strip(),
                Brand.business_type == business_type,
                Brand.is_active.is_(True),
                BrandBranch.company_id == args.company_id,
                BrandBranch.is_active.is_(True),
                Branch.company_id == args.company_id,
                Branch.code == branch_code.strip(),
                Branch.is_active.is_(True),
                Branch.deleted_at.is_(None),
            )
        )
    ).all()
    if company is None or not company.is_active:
        raise RuntimeError("Active QA Company was not found")
    if actor is None:
        raise RuntimeError("Active Company superuser actor was not found")
    if len(scope) != 1:
        raise RuntimeError(
            f"{business_type} QA Brand and Branch code must resolve to exactly one active Branch"
        )
    brand, branch = scope[0]
    return company, actor, brand, branch


async def _ensure_role(db, company_id: uuid.UUID, preset_key: str) -> Role:
    policy = next(item for item in ROLE_PRESET_POLICIES if item.key == preset_key)
    permissions = list(
        (
            await db.scalars(
                select(Permission).where(Permission.code.in_(policy.permission_codes))
            )
        ).all()
    )
    present = {permission.code for permission in permissions}
    missing = sorted(set(policy.permission_codes) - present)
    if missing:
        raise RuntimeError(f"Permission catalog is incomplete for {preset_key}: {', '.join(missing)}")
    role_name = f"QA {policy.name}"
    role = await db.scalar(
        select(Role)
        .where(
            Role.company_id == company_id,
            Role.name == role_name,
            Role.deleted_at.is_(None),
        )
        .options(selectinload(Role.permissions))
    )
    if role is None:
        role = Role(
            company_id=company_id,
            name=role_name,
            description=f"QA Access Mode role from canonical preset {preset_key}",
            is_system=False,
            is_branch_assignable=policy.is_branch_assignable,
            allowed_scope_types=list(policy.allowed_scopes),
            permissions=permissions,
        )
        db.add(role)
        await db.flush()
    else:
        role.description = f"QA Access Mode role from canonical preset {preset_key}"
        role.is_branch_assignable = policy.is_branch_assignable
        role.allowed_scope_types = list(policy.allowed_scopes)
        role.permissions = permissions
    return role


async def _ensure_assignment(
    db,
    *,
    company_id: uuid.UUID,
    actor_id: uuid.UUID,
    user: User,
    role: Role,
    scope_type: str,
    brand: Brand,
    branch: Branch,
) -> None:
    brand_id = brand.id if scope_type == "branch" else None
    branch_id = branch.id if scope_type == "branch" else None
    scope_key = assignment_scope_key(
        company_id=company_id,
        scope_type=scope_type,
        brand_id=brand_id,
        branch_id=branch_id,
        station_key=None,
    )
    assignment = await db.scalar(
        select(StaffRoleAssignment).where(
            StaffRoleAssignment.user_id == user.id,
            StaffRoleAssignment.role_id == role.id,
            StaffRoleAssignment.scope_type == scope_type,
            StaffRoleAssignment.scope_key == scope_key,
            StaffRoleAssignment.revoked_at.is_(None),
        )
    )
    if assignment is None:
        db.add(
            StaffRoleAssignment(
                company_id=company_id,
                user_id=user.id,
                role_id=role.id,
                scope_type=scope_type,
                scope_key=scope_key,
                brand_id=brand_id,
                branch_id=branch_id,
                station_key=None,
                assignment_reason="QA Access Mode persona",
                assigned_by=actor_id,
            )
        )


async def _ensure_tenant_persona(
    db,
    *,
    persona: TenantPersona,
    company: Company,
    actor: User,
    brand: Brand,
    branch: Branch,
) -> User:
    user = await db.scalar(
        select(User).where(
            User.company_id == company.id,
            User.username == persona.username,
            User.deleted_at.is_(None),
        )
    )
    if persona.preset_key is None:
        if user is None or not user.is_active or not user.is_superuser:
            raise RuntimeError("Configured Company Admin persona is not an active superuser")
        return user

    role = await _ensure_role(db, company.id, persona.preset_key)
    created = user is None
    if user is None:
        user = User(
            company_id=company.id,
            username=persona.username,
            display_name=role.name,
            hashed_password=hash_password(secrets.token_urlsafe(48)),
            is_active=True,
            is_superuser=False,
            password_changed_at=datetime.now(timezone.utc),
        )
        db.add(user)
        await db.flush()
    else:
        user.display_name = role.name
        user.is_active = True
        user.is_superuser = False

    now = datetime.now(timezone.utc)
    user.credential_version += 1
    await db.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=now)
    )

    link = await db.scalar(
        select(UserBranch).where(
            UserBranch.user_id == user.id,
            UserBranch.branch_id == branch.id,
        )
    )
    if link is None:
        db.add(
            UserBranch(
                user_id=user.id,
                branch_id=branch.id,
                brand_id=brand.id,
                business_type=persona.business_type,
                target_database=persona.business_type,
                role_id=role.id,
                is_default=True,
            )
        )
    else:
        link.deleted_at = None
        link.brand_id = brand.id
        link.business_type = persona.business_type
        link.target_database = persona.business_type
        link.role_id = role.id
        link.is_default = True

    await _ensure_assignment(
        db,
        company_id=company.id,
        actor_id=actor.id,
        user=user,
        role=role,
        scope_type=persona.scope_type,
        brand=brand,
        branch=branch,
    )
    stale_assignments = (
        await db.scalars(
            select(StaffRoleAssignment).where(
                StaffRoleAssignment.company_id == company.id,
                StaffRoleAssignment.user_id == user.id,
                StaffRoleAssignment.role_id != role.id,
                StaffRoleAssignment.revoked_at.is_(None),
            )
        )
    ).all()
    for stale in stale_assignments:
        stale.revoked_at = now
        stale.revoked_by = actor.id
        stale.revocation_reason = "Replaced by bounded QA Access Mode persona"
    db.add(
        AuditLog(
            company_id=company.id,
            branch_id=branch.id if persona.scope_type == "branch" else None,
            user_id=actor.id,
            action="uat.qa.persona.prepare",
            resource="User",
            resource_id=str(user.id),
            new_value={
                "persona": persona.key,
                "username": persona.username,
                "preset": persona.preset_key,
                "scope": persona.scope_type,
                "business_type": persona.business_type,
                "created": created,
            },
        )
    )
    return user


async def _ensure_platform_persona(db, persona: PlatformPersona) -> PlatformOperator:
    operator = await db.scalar(
        select(PlatformOperator).where(PlatformOperator.username == persona.username)
    )
    created = operator is None
    if operator is None:
        operator = PlatformOperator(
            username=persona.username,
            email=None,
            display_name=persona.key.replace("_", " ").title(),
            hashed_password=hash_password(secrets.token_urlsafe(48)),
            is_active=True,
            is_superuser=False,
            password_changed_at=datetime.now(timezone.utc),
        )
        db.add(operator)
        await db.flush()
    else:
        operator.display_name = persona.key.replace("_", " ").title()
        operator.is_active = True
        operator.is_superuser = False

    now = datetime.now(timezone.utc)
    operator.credential_version += 1
    await db.execute(
        update(PlatformSession)
        .where(
            PlatformSession.operator_id == operator.id,
            PlatformSession.revoked_at.is_(None),
        )
        .values(revoked_at=now, revocation_reason="qa-persona-reprepared")
    )

    assignment = await db.scalar(
        select(PlatformOperatorRoleAssignment).where(
            PlatformOperatorRoleAssignment.operator_id == operator.id,
            PlatformOperatorRoleAssignment.environment == "uat",
            PlatformOperatorRoleAssignment.role_code == persona.role_code,
            PlatformOperatorRoleAssignment.revoked_at.is_(None),
        )
    )
    if assignment is None:
        db.add(
            PlatformOperatorRoleAssignment(
                operator_id=operator.id,
                role_code=persona.role_code,
                environment="uat",
                assigned_by=operator.id,
                reason="QA Access Mode persona",
                request_id=uuid.uuid4(),
            )
        )
    stale_assignments = (
        await db.scalars(
            select(PlatformOperatorRoleAssignment).where(
                PlatformOperatorRoleAssignment.operator_id == operator.id,
                PlatformOperatorRoleAssignment.environment == "uat",
                PlatformOperatorRoleAssignment.role_code != persona.role_code,
                PlatformOperatorRoleAssignment.revoked_at.is_(None),
            )
        )
    ).all()
    for stale in stale_assignments:
        stale.revoked_at = now
        stale.revoked_by = operator.id
        stale.revocation_reason = "Replaced by bounded QA Access Mode persona"
    db.add(
        AuditLog(
            company_id=None,
            branch_id=None,
            user_id=operator.id,
            action="uat.qa.platform_persona.prepare",
            resource="PlatformOperator",
            resource_id=str(operator.id),
            new_value={
                "persona": persona.key,
                "username": persona.username,
                "role_code": persona.role_code,
                "created": created,
            },
        )
    )
    return operator


async def prepare(args: argparse.Namespace) -> dict[str, object]:
    require_bounded_qa_uat(args)
    async with PlatformSessionLocal() as db:
        company, actor, brand, branch = await _load_scope(db, args)
        _, _, retail_brand, retail_branch = await _load_scope(
            db,
            args,
            business_type="retail_pos",
        )
        tenant_rows = []
        for persona in TENANT_PERSONAS:
            persona_brand, persona_branch = (
                (retail_brand, retail_branch)
                if persona.business_type == "retail_pos"
                else (brand, branch)
            )
            await _ensure_tenant_persona(
                db,
                persona=persona,
                company=company,
                actor=actor,
                brand=persona_brand,
                branch=persona_branch,
            )
            tenant_rows.append({
                "persona": persona.key,
                "username": persona.username,
                "business_type": persona.business_type,
            })

        platform_rows = []
        for persona in PLATFORM_PERSONAS:
            await _ensure_platform_persona(db, persona)
            platform_rows.append({"persona": persona.key, "username": persona.username})

        await db.commit()
        return {
            "company_id": str(company.id),
            "branch_id": str(branch.id),
            "tenant_personas": tenant_rows,
            "platform_personas": platform_rows,
            "credentials_emitted": False,
        }


async def main() -> int:
    args = build_parser().parse_args()
    result = await prepare(args)
    for key, value in result.items():
        print(f"{key}={value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
