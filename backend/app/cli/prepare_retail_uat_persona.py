from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import os
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
from app.models.restaurant import Brand, BrandBranch
from app.models.role import Permission, Role
from app.models.staff_assignment import StaffRoleAssignment
from app.models.user import User, UserBranch
from app.services.role_preset_service import ROLE_PRESET_POLICIES
from app.services.staff_scope_policy import assignment_scope_key
from app.utils.security import hash_password


UAT_USERNAME = "uat.retail-cashier"
PASSWORD_ENV = "WP56_UAT_RETAIL_CASHIER_PASSWORD"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Prepare one bounded Retail Cashier persona for authenticated UAT.",
    )
    parser.add_argument("--company-id", type=uuid.UUID, required=True)
    parser.add_argument("--actor-username", required=True)
    parser.add_argument("--brand-slug", default="foodchain-retail-uat")
    parser.add_argument("--disable", action="store_true")
    parser.add_argument("--yes", action="store_true")
    return parser


def require_bounded_uat(args: argparse.Namespace, *, password: str) -> None:
    public_url = urlsplit(settings.saas_public_base_url)
    hostname = public_url.hostname or ""
    if not args.yes:
        raise RuntimeError("Pass --yes to change the persistent Retail UAT persona")
    if (
        settings.environment != "development"
        or public_url.scheme != "https"
        or not hostname.startswith("uat-")
    ):
        raise RuntimeError("Retail persona preparation is restricted to the HTTPS uat-* environment")
    if settings.identity_database != "platform_core":
        raise RuntimeError("Retail persona preparation requires Platform identity")
    if settings.uat_auth_bypass_enabled:
        raise RuntimeError("Disable UAT_AUTH_BYPASS_ENABLED before preparing the Retail persona")
    if not args.disable and len(password) < 16:
        raise RuntimeError("The temporary Retail UAT password must contain at least 16 characters")


async def _load_scope(
    db,
    args: argparse.Namespace,
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
    retail_scopes = (
        await db.execute(
            select(Brand, Branch)
            .select_from(Brand)
            .join(BrandBranch, BrandBranch.brand_id == Brand.id)
            .join(Branch, Branch.id == BrandBranch.branch_id)
            .where(
                Brand.company_id == args.company_id,
                Brand.slug == args.brand_slug.strip(),
                Brand.business_type == "retail_pos",
                Brand.is_active.is_(True),
                Brand.deleted_at.is_(None),
                BrandBranch.company_id == args.company_id,
                BrandBranch.is_active.is_(True),
                Branch.company_id == args.company_id,
                Branch.is_active.is_(True),
                Branch.deleted_at.is_(None),
            )
        )
    ).all()
    if company is None or not company.is_active:
        raise RuntimeError("Active UAT Company was not found")
    if actor is None:
        raise RuntimeError("Active UAT superuser actor was not found")
    if len(retail_scopes) != 1:
        raise RuntimeError("Retail UAT Brand must resolve to exactly one active Branch")
    brand, branch = retail_scopes[0]
    return company, actor, brand, branch


async def _ensure_retail_cashier_role(db, company_id: uuid.UUID) -> Role:
    policy = next(policy for policy in ROLE_PRESET_POLICIES if policy.key == "cashier")
    permissions = (
        await db.scalars(select(Permission).where(Permission.code.in_(policy.permission_codes)))
    ).all()
    if len(permissions) != len(policy.permission_codes):
        present = {permission.code for permission in permissions}
        missing = sorted(set(policy.permission_codes) - present)
        raise RuntimeError(f"Permission catalog is incomplete for cashier: {', '.join(missing)}")

    role = await db.scalar(
        select(Role)
        .where(
            Role.company_id == company_id,
            Role.name == "UAT Retail Cashier",
            Role.deleted_at.is_(None),
        )
        .options(selectinload(Role.permissions))
    )
    if role is None:
        role = Role(
            company_id=company_id,
            name="UAT Retail Cashier",
            description="Bounded WP56 Retail Cashier persona from canonical cashier preset",
            is_system=False,
            is_branch_assignable=policy.is_branch_assignable,
            allowed_scope_types=list(policy.allowed_scopes),
            permissions=list(permissions),
        )
        db.add(role)
        await db.flush()
    else:
        role.description = "Bounded WP56 Retail Cashier persona from canonical cashier preset"
        role.is_branch_assignable = policy.is_branch_assignable
        role.allowed_scope_types = list(policy.allowed_scopes)
        role.permissions = list(permissions)
    return role


async def _revoke_tokens(db, user_id: uuid.UUID, now: datetime) -> None:
    await db.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=now)
    )


async def prepare(args: argparse.Namespace) -> dict[str, object]:
    password = os.environ.get(PASSWORD_ENV, "")
    require_bounded_uat(args, password=password)
    async with PlatformSessionLocal() as db:
        _, actor, brand, branch = await _load_scope(db, args)
        user = await db.scalar(
            select(User).where(User.company_id == args.company_id, User.username == UAT_USERNAME)
        )
        now = datetime.now(timezone.utc)

        if args.disable:
            if user is None:
                return {"disabled": False, "username": UAT_USERNAME}
            user.is_active = False
            await _revoke_tokens(db, user.id, now)
            assignments = (
                await db.scalars(
                    select(StaffRoleAssignment).where(
                        StaffRoleAssignment.company_id == args.company_id,
                        StaffRoleAssignment.user_id == user.id,
                        StaffRoleAssignment.revoked_at.is_(None),
                    )
                )
            ).all()
            for assignment in assignments:
                assignment.revoked_at = now
                assignment.revoked_by = actor.id
                assignment.revocation_reason = "Retail UAT persona disabled"
            db.add(
                AuditLog(
                    company_id=args.company_id,
                    branch_id=branch.id,
                    user_id=actor.id,
                    action="uat.retail.persona.disable",
                    resource="User",
                    resource_id=str(user.id),
                    new_value={"username": UAT_USERNAME, "sessions_revoked": True},
                )
            )
            await db.commit()
            return {"disabled": True, "username": UAT_USERNAME}

        role = await _ensure_retail_cashier_role(db, args.company_id)
        if user is not None and user.deleted_at is not None:
            raise RuntimeError("Deleted Retail UAT persona cannot be reactivated automatically")
        created = user is None
        if user is None:
            user = User(
                company_id=args.company_id,
                username=UAT_USERNAME,
                display_name="UAT Retail Cashier",
                hashed_password=hash_password(password),
                is_active=True,
                is_superuser=False,
                password_changed_at=now,
            )
            db.add(user)
            await db.flush()
        else:
            user.display_name = "UAT Retail Cashier"
            user.hashed_password = hash_password(password)
            user.password_changed_at = now
            user.is_active = True
            user.is_superuser = False
        await _revoke_tokens(db, user.id, now)

        user_branch = await db.scalar(
            select(UserBranch).where(
                UserBranch.user_id == user.id,
                UserBranch.branch_id == branch.id,
                UserBranch.deleted_at.is_(None),
            )
        )
        if user_branch is None:
            user_branch = UserBranch(
                user_id=user.id,
                branch_id=branch.id,
                brand_id=brand.id,
                business_type="retail_pos",
                target_database="retail_pos",
                role_id=role.id,
                is_default=True,
            )
            db.add(user_branch)
        else:
            user_branch.brand_id = brand.id
            user_branch.business_type = "retail_pos"
            user_branch.target_database = "retail_pos"
            user_branch.role_id = role.id
            user_branch.is_default = True

        scope_key = assignment_scope_key(
            company_id=args.company_id,
            scope_type="branch",
            brand_id=brand.id,
            branch_id=branch.id,
            station_key=None,
        )
        assignment = await db.scalar(
            select(StaffRoleAssignment).where(
                StaffRoleAssignment.user_id == user.id,
                StaffRoleAssignment.role_id == role.id,
                StaffRoleAssignment.scope_type == "branch",
                StaffRoleAssignment.scope_key == scope_key,
                StaffRoleAssignment.revoked_at.is_(None),
            )
        )
        if assignment is None:
            db.add(
                StaffRoleAssignment(
                    company_id=args.company_id,
                    user_id=user.id,
                    role_id=role.id,
                    scope_type="branch",
                    scope_key=scope_key,
                    brand_id=brand.id,
                    branch_id=branch.id,
                    station_key=None,
                    assignment_reason="WP55-WP56 authenticated Retail UAT",
                    assigned_by=actor.id,
                )
            )

        db.add(
            AuditLog(
                company_id=args.company_id,
                branch_id=branch.id,
                user_id=actor.id,
                action="uat.retail.persona.prepare",
                resource="User",
                resource_id=str(user.id),
                new_value={
                    "username": UAT_USERNAME,
                    "role": "cashier",
                    "brand_id": str(brand.id),
                    "branch_id": str(branch.id),
                    "created": created,
                    "sessions_revoked": True,
                },
            )
        )
        await db.commit()
        return {
            "prepared": True,
            "username": UAT_USERNAME,
            "role": "cashier",
            "brand_id": str(brand.id),
            "branch_id": str(branch.id),
            "auth_bypass": False,
        }


async def main() -> None:
    args = build_parser().parse_args()
    result = await prepare(args)
    for key, value in result.items():
        print(f"{key}={value}")


if __name__ == "__main__":
    asyncio.run(main())
