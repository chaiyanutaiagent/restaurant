from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import os
import uuid
from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.config import settings
from app.database import PlatformSessionLocal
from app.models.audit import AuditLog
from app.models.branch import Branch
from app.models.company import Company
from app.models.restaurant import Brand, BrandBranch
from app.models.role import Permission, Role
from app.models.staff_assignment import StaffRoleAssignment
from app.models.user import User, UserBranch
from app.services.role_preset_service import ROLE_PRESET_POLICIES
from app.services.staff_scope_policy import assignment_scope_key
from app.utils.security import hash_password


UAT_PROFILES = (
    ("cashier", "uat.cashier", "WP48_UAT_CASHIER_PASSWORD", "branch"),
    ("branch-manager", "uat.branch-manager", "WP48_UAT_BRANCH_MANAGER_PASSWORD", "branch"),
    ("accountant", "uat.accountant", "WP48_UAT_ACCOUNTANT_PASSWORD", "company"),
    ("purchasing", "uat.purchasing", "WP48_UAT_PURCHASING_PASSWORD", "company"),
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Prepare bounded real-role users for WP48 formal UAT")
    parser.add_argument("--company-id", type=uuid.UUID, required=True)
    parser.add_argument("--branch-id", type=uuid.UUID, required=True)
    parser.add_argument("--actor-username", required=True)
    parser.add_argument("--rotate-passwords", action="store_true")
    parser.add_argument("--disable", action="store_true")
    parser.add_argument("--yes", action="store_true")
    return parser


def require_uat(args: argparse.Namespace) -> None:
    hostname = urlsplit(settings.saas_public_base_url).hostname or ""
    if not args.yes:
        raise RuntimeError("Pass --yes to change persistent UAT identities")
    if settings.environment != "development" or not hostname.startswith("uat-"):
        raise RuntimeError("WP48 formal users are restricted to the HTTPS uat-* development environment")
    if settings.identity_database != "platform_core":
        raise RuntimeError("WP48 formal users require Platform identity")
    if settings.uat_auth_bypass_enabled:
        raise RuntimeError("Disable UAT_AUTH_BYPASS_ENABLED before preparing formal UAT users")
    if not args.disable:
        missing = [env_name for _, _, env_name, _ in UAT_PROFILES if not os.getenv(env_name)]
        if missing:
            raise RuntimeError(f"Missing password environment variables: {', '.join(missing)}")


async def _load_scope(db, args: argparse.Namespace) -> tuple[Company, Branch, Brand, User]:
    company = await db.get(Company, args.company_id)
    branch = await db.get(Branch, args.branch_id)
    brand = await db.scalar(
        select(Brand)
        .join(BrandBranch, BrandBranch.brand_id == Brand.id)
        .where(
            BrandBranch.company_id == args.company_id,
            BrandBranch.branch_id == args.branch_id,
            BrandBranch.is_active.is_(True),
            Brand.business_type == "restaurant",
            Brand.is_active.is_(True),
        )
    )
    actor = await db.scalar(
        select(User).where(
            User.company_id == args.company_id,
            User.username == args.actor_username,
            User.is_superuser.is_(True),
            User.is_active.is_(True),
            User.deleted_at.is_(None),
        )
    )
    if company is None or not company.is_active or branch is None or branch.company_id != args.company_id:
        raise RuntimeError("Active UAT Company or Branch was not found")
    if brand is None:
        raise RuntimeError("Branch is not mapped to an active Restaurant Brand")
    if actor is None:
        raise RuntimeError("Active UAT superuser actor was not found")
    return company, branch, brand, actor


async def _ensure_role(db, company_id: uuid.UUID, preset_key: str) -> Role:
    policy = next(policy for policy in ROLE_PRESET_POLICIES if policy.key == preset_key)
    permissions = (
        await db.scalars(select(Permission).where(Permission.code.in_(policy.permission_codes)))
    ).all()
    if len(permissions) != len(policy.permission_codes):
        present = {permission.code for permission in permissions}
        missing = sorted(set(policy.permission_codes) - present)
        raise RuntimeError(f"Permission catalog is incomplete for {preset_key}: {', '.join(missing)}")
    role_name = f"UAT {policy.name}"
    role = await db.scalar(
        select(Role)
        .where(Role.company_id == company_id, Role.name == role_name, Role.deleted_at.is_(None))
        .options(selectinload(Role.permissions))
    )
    if role is None:
        role = Role(
            company_id=company_id,
            name=role_name,
            description=f"WP48 formal UAT role from preset {preset_key}",
            is_system=False,
            is_branch_assignable=policy.is_branch_assignable,
            allowed_scope_types=list(policy.allowed_scopes),
        )
        db.add(role)
        await db.flush()
    role.description = f"WP48 formal UAT role from preset {preset_key}"
    role.is_branch_assignable = policy.is_branch_assignable
    role.allowed_scope_types = list(policy.allowed_scopes)
    role.permissions = list(permissions)
    return role


async def _disable_users(db, company_id: uuid.UUID, actor: User) -> int:
    usernames = [username for _, username, _, _ in UAT_PROFILES]
    users = (
        await db.scalars(
            select(User).where(User.company_id == company_id, User.username.in_(usernames))
        )
    ).all()
    now = datetime.now(timezone.utc)
    for user in users:
        user.is_active = False
        assignments = (
            await db.scalars(
                select(StaffRoleAssignment).where(
                    StaffRoleAssignment.company_id == company_id,
                    StaffRoleAssignment.user_id == user.id,
                    StaffRoleAssignment.revoked_at.is_(None),
                )
            )
        ).all()
        for assignment in assignments:
            assignment.revoked_at = now
            assignment.revoked_by = actor.id
            assignment.revocation_reason = "WP48 formal UAT user set disabled"
    db.add(AuditLog(company_id=company_id, user_id=actor.id, action="uat.wp48.users.disable", resource="User", resource_id=str(company_id), new_value={"count": len(users)}))
    await db.commit()
    return len(users)


async def prepare(args: argparse.Namespace) -> dict[str, object]:
    require_uat(args)
    async with PlatformSessionLocal() as db:
        _, branch, brand, actor = await _load_scope(db, args)
        if args.disable:
            return {"disabled": await _disable_users(db, args.company_id, actor)}

        prepared: list[dict[str, str]] = []
        for preset_key, username, password_env, scope_type in UAT_PROFILES:
            role = await _ensure_role(db, args.company_id, preset_key)
            user = await db.scalar(
                select(User).where(User.company_id == args.company_id, User.username == username)
            )
            created = user is None
            if user is None:
                user = User(
                    company_id=args.company_id,
                    username=username,
                    display_name=role.name,
                    hashed_password=hash_password(os.environ[password_env]),
                    is_active=True,
                    is_superuser=False,
                    password_changed_at=datetime.now(timezone.utc),
                )
                db.add(user)
                await db.flush()
            else:
                user.display_name = role.name
                user.is_active = True
                if args.rotate_passwords:
                    user.hashed_password = hash_password(os.environ[password_env])
                    user.password_changed_at = datetime.now(timezone.utc)

            link = await db.scalar(
                select(UserBranch).where(
                    UserBranch.user_id == user.id,
                    UserBranch.branch_id == branch.id,
                    UserBranch.deleted_at.is_(None),
                )
            )
            if link is None:
                link = UserBranch(
                    user_id=user.id,
                    branch_id=branch.id,
                    brand_id=brand.id,
                    business_type="restaurant",
                    target_database="restaurant",
                    role_id=role.id,
                    is_default=True,
                )
                db.add(link)
            else:
                link.brand_id = brand.id
                link.business_type = "restaurant"
                link.target_database = "restaurant"
                link.role_id = role.id
                link.is_default = True

            if scope_type == "company":
                scope_key = assignment_scope_key(
                    company_id=args.company_id,
                    scope_type="company",
                    brand_id=None,
                    branch_id=None,
                    station_key=None,
                )
                assignment = await db.scalar(
                    select(StaffRoleAssignment).where(
                        StaffRoleAssignment.user_id == user.id,
                        StaffRoleAssignment.role_id == role.id,
                        StaffRoleAssignment.scope_type == "company",
                        StaffRoleAssignment.scope_key == scope_key,
                        StaffRoleAssignment.revoked_at.is_(None),
                    )
                )
                if assignment is None:
                    db.add(StaffRoleAssignment(
                        company_id=args.company_id,
                        user_id=user.id,
                        role_id=role.id,
                        scope_type="company",
                        scope_key=scope_key,
                        brand_id=None,
                        branch_id=None,
                        station_key=None,
                        assignment_reason="WP48 formal permission/security UAT",
                        assigned_by=actor.id,
                    ))

            db.add(AuditLog(
                company_id=args.company_id,
                branch_id=branch.id,
                user_id=actor.id,
                action="uat.wp48.user.prepare",
                resource="User",
                resource_id=str(user.id),
                new_value={"username": username, "preset": preset_key, "scope": scope_type, "created": created},
            ))
            prepared.append({"username": username, "preset": preset_key, "scope": scope_type})

        await db.commit()
        return {"prepared": prepared, "auth_bypass": False, "branch_id": str(branch.id), "brand_id": str(brand.id)}


async def main() -> int:
    args = build_parser().parse_args()
    result = await prepare(args)
    for key, value in result.items():
        print(f"{key}={value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
