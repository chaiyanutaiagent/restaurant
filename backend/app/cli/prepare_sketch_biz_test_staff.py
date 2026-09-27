from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from typing import Any, Sequence
import uuid
from urllib.parse import urlsplit

from sqlalchemy import select

from app.cli.prepare_sketch_biz_uat import SKETCH_BIZ_COMPANY_ID, WORKSPACES, WorkspaceSpec
from app.config import settings
from app.database import PlatformSessionLocal
from app.models.audit import AuditLog
from app.models.branch import Branch
from app.models.restaurant import Brand, BrandBranch
from app.models.role import Role
from app.models.staff_assignment import StaffRoleAssignment
from app.models.user import User, UserBranch
from app.services.platform_reference_projection import enqueue_reference_event
from app.services.role_preset_service import ROLE_PRESET_POLICIES, RolePresetPolicy
from app.services.staff_scope_policy import assignment_scope_key
from app.utils.security import hash_password, verify_password


PASSWORD_ENV = "SKETCH_BIZ_TEST_PASSWORD"


@dataclass(frozen=True)
class TestStaffProfile:
    preset_key: str
    username: str
    employee_code: str
    first_name: str
    last_name: str
    position_th: str


TEST_STAFF_PROFILES = (
    TestStaffProfile("company-owner", "test.owner", "UAT-OWNER", "ณัฐวุฒิ", "ศรีสุข", "เจ้าของบริษัท"),
    TestStaffProfile("brand-manager", "test.brand-manager", "UAT-BRAND-MGR", "พิมพ์ชนก", "วัฒนกิจ", "ผู้จัดการแบรนด์"),
    TestStaffProfile("branch-manager", "test.branch-manager", "UAT-BRANCH-MGR", "ธนภัทร", "เจริญผล", "ผู้จัดการสาขา"),
    TestStaffProfile("accountant", "test.accountant", "UAT-ACCOUNT", "สุภาวดี", "มั่นคง", "เจ้าหน้าที่บัญชี"),
    TestStaffProfile("purchasing", "test.purchasing", "UAT-PURCHASE", "กิตติพงศ์", "วงศ์ดี", "เจ้าหน้าที่จัดซื้อ"),
    TestStaffProfile("warehouse", "test.warehouse", "UAT-WAREHOUSE", "อนุชา", "ใจมั่น", "เจ้าหน้าที่คลังสินค้า"),
    TestStaffProfile("hr", "test.hr", "UAT-HR", "ชลธิชา", "พูนทรัพย์", "เจ้าหน้าที่ทรัพยากรบุคคล"),
    TestStaffProfile("auditor", "test.auditor", "UAT-AUDITOR", "รัชดา", "ธรรมรักษ์", "ผู้ตรวจสอบ"),
    TestStaffProfile("area-manager", "test.area-manager", "UAT-AREA-MGR", "วรเมธ", "ตั้งใจ", "ผู้จัดการเขต"),
    TestStaffProfile("service-staff", "test.service-staff", "UAT-SERVICE", "กัญญารัตน์", "ยิ้มแย้ม", "พนักงานบริการ"),
    TestStaffProfile("kitchen-manager", "test.kitchen-manager", "UAT-KITCHEN-MGR", "สมชาย", "รสเลิศ", "ผู้จัดการครัว"),
    TestStaffProfile("cashier", "test.cashier", "UAT-CASHIER", "ปวีณา", "เงินดี", "พนักงานขายและแคชเชียร์"),
    TestStaffProfile("kitchen-staff", "test.kitchen-staff", "UAT-KITCHEN", "เอกชัย", "ครัวดี", "พนักงานครัว"),
)


@dataclass(frozen=True)
class WorkspaceRow:
    spec: WorkspaceSpec
    brand: Brand
    branch: Branch


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Prepare one named Sketch Biz UAT user for every role preset")
    parser.add_argument("--company-id", type=uuid.UUID, required=True)
    parser.add_argument("--actor-username", required=True)
    parser.add_argument("--yes", action="store_true")
    return parser


def require_uat(args: argparse.Namespace) -> str:
    hostname = urlsplit(settings.saas_public_base_url).hostname or ""
    if not args.yes:
        raise RuntimeError("Pass --yes to prepare persistent Sketch Biz UAT test staff")
    if args.company_id != SKETCH_BIZ_COMPANY_ID:
        raise RuntimeError("The command is pinned to the approved Sketch Biz UAT Company")
    if settings.environment != "development" or not hostname.startswith("uat-"):
        raise RuntimeError("Test staff preparation is restricted to the uat-* development environment")
    if settings.identity_database != "platform_core":
        raise RuntimeError("Test staff preparation requires Platform identity")
    password = os.getenv(PASSWORD_ENV)
    if not password:
        raise RuntimeError(f"{PASSWORD_ENV} is required")
    return password


async def _load_workspaces(db, company_id: uuid.UUID) -> list[WorkspaceRow]:
    result: list[WorkspaceRow] = []
    for spec in WORKSPACES:
        row = (
            await db.execute(
                select(Brand, Branch)
                .join(BrandBranch, BrandBranch.brand_id == Brand.id)
                .join(Branch, Branch.id == BrandBranch.branch_id)
                .where(
                    Brand.company_id == company_id,
                    Brand.slug == spec.brand_slug,
                    Brand.is_active.is_(True),
                    Branch.company_id == company_id,
                    Branch.code == spec.branch_code,
                    Branch.is_active.is_(True),
                    BrandBranch.is_active.is_(True),
                )
            )
        ).one_or_none()
        if row is None:
            raise RuntimeError(f"Active workspace is missing: {spec.key}")
        result.append(WorkspaceRow(spec=spec, brand=row[0], branch=row[1]))
    return result


def _desired_scopes(
    policy: RolePresetPolicy,
    company_id: uuid.UUID,
    workspaces: list[WorkspaceRow],
) -> list[tuple[str, str, uuid.UUID | None, uuid.UUID | None, str | None]]:
    if policy.default_scope == "company":
        return [("company", str(company_id), None, None, None)]
    if policy.default_scope == "brand":
        return [("brand", str(row.brand.id), row.brand.id, None, None) for row in workspaces]
    if policy.default_scope == "branch":
        return [("branch", str(row.branch.id), row.brand.id, row.branch.id, None) for row in workspaces]
    if policy.default_scope == "station":
        return [
            (
                "station",
                assignment_scope_key(
                    company_id=company_id,
                    scope_type="station",
                    brand_id=row.brand.id,
                    branch_id=row.branch.id,
                    station_key="kitchen",
                ),
                row.brand.id,
                row.branch.id,
                "kitchen",
            )
            for row in workspaces
            if row.spec.business_type in {"restaurant", "takeaway"}
        ]
    raise RuntimeError(f"Unsupported role scope: {policy.default_scope}")


async def prepare(args: argparse.Namespace) -> dict[str, Any]:
    password = require_uat(args)
    policies = {policy.key: policy for policy in ROLE_PRESET_POLICIES}
    now = datetime.now(timezone.utc)
    async with PlatformSessionLocal() as db:
        actor = await db.scalar(
            select(User).where(
                User.company_id == args.company_id,
                User.username == args.actor_username,
                User.is_superuser.is_(True),
                User.is_active.is_(True),
                User.deleted_at.is_(None),
            )
        )
        if actor is None:
            raise RuntimeError("Active Sketch Biz UAT superuser actor was not found")
        workspaces = await _load_workspaces(db, args.company_id)
        roles = {
            role.name: role
            for role in (
                await db.scalars(
                    select(Role).where(Role.company_id == args.company_id, Role.deleted_at.is_(None))
                )
            ).all()
        }
        prepared: list[dict[str, Any]] = []
        for profile in TEST_STAFF_PROFILES:
            policy = policies[profile.preset_key]
            role = roles.get(policy.name)
            if role is None:
                raise RuntimeError(f"Canonical role is missing: {policy.name}")
            user = await db.scalar(
                select(User).where(
                    User.company_id == args.company_id,
                    User.username == profile.username,
                )
            )
            created = user is None
            if user is None:
                user = User(
                    company_id=args.company_id,
                    username=profile.username,
                    employee_code=profile.employee_code,
                    first_name=profile.first_name,
                    last_name=profile.last_name,
                    display_name=f"{profile.first_name} {profile.last_name}",
                    hashed_password=hash_password(password),
                    password_changed_at=now,
                    is_active=True,
                    is_superuser=False,
                )
                db.add(user)
                await db.flush()
            else:
                user.employee_code = profile.employee_code
                user.first_name = profile.first_name
                user.last_name = profile.last_name
                user.display_name = f"{profile.first_name} {profile.last_name}"
                user.is_active = True
                user.is_superuser = False
                user.deleted_at = None
                if not verify_password(password, user.hashed_password):
                    user.hashed_password = hash_password(password)
                    user.password_changed_at = now
                    user.credential_version += 1

            active_links = (
                await db.scalars(
                    select(UserBranch).where(
                        UserBranch.user_id == user.id,
                        UserBranch.deleted_at.is_(None),
                    )
                )
            ).all()
            link_by_branch = {link.branch_id: link for link in active_links}
            intended_branch_ids = {row.branch.id for row in workspaces}
            for link in active_links:
                if link.branch_id not in intended_branch_ids:
                    link.deleted_at = now
                    link.is_default = False
            for index, row in enumerate(workspaces):
                link = link_by_branch.get(row.branch.id)
                if link is None:
                    link = UserBranch(user_id=user.id, branch_id=row.branch.id, role_id=role.id)
                    db.add(link)
                link.brand_id = row.brand.id
                link.business_type = row.spec.business_type
                link.target_database = row.spec.business_type
                link.role_id = role.id
                link.is_default = index == 0
                link.deleted_at = None

            desired_scopes = _desired_scopes(policy, args.company_id, workspaces)
            desired_keys = {(role.id, scope_type, scope_key) for scope_type, scope_key, _, _, _ in desired_scopes}
            active_assignments = (
                await db.scalars(
                    select(StaffRoleAssignment).where(
                        StaffRoleAssignment.company_id == args.company_id,
                        StaffRoleAssignment.user_id == user.id,
                        StaffRoleAssignment.revoked_at.is_(None),
                    )
                )
            ).all()
            assignment_by_key = {
                (assignment.role_id, assignment.scope_type, assignment.scope_key): assignment
                for assignment in active_assignments
            }
            for assignment in active_assignments:
                if (assignment.role_id, assignment.scope_type, assignment.scope_key) not in desired_keys:
                    assignment.revoked_at = now
                    assignment.revoked_by = actor.id
                    assignment.revocation_reason = "Replaced by canonical Sketch Biz UAT test role"
            for scope_type, scope_key, brand_id, branch_id, station_key in desired_scopes:
                key = (role.id, scope_type, scope_key)
                if key not in assignment_by_key:
                    db.add(
                        StaffRoleAssignment(
                            company_id=args.company_id,
                            user_id=user.id,
                            role_id=role.id,
                            scope_type=scope_type,
                            scope_key=scope_key,
                            brand_id=brand_id,
                            branch_id=branch_id,
                            station_key=station_key,
                            assignment_reason="Sketch Biz named UAT test staff",
                            assigned_by=actor.id,
                        )
                    )

            if not verify_password(password, user.hashed_password):
                raise RuntimeError(f"Password verification failed for {profile.username}")
            await enqueue_reference_event(
                db,
                aggregate_type="user",
                aggregate_id=user.id,
                company_id=args.company_id,
                payload={"source": "prepare_sketch_biz_test_staff"},
            )
            db.add(
                AuditLog(
                    company_id=args.company_id,
                    user_id=actor.id,
                    action="uat.sketch_biz.test_staff.prepare",
                    resource="User",
                    resource_id=str(user.id),
                    new_value={
                        "username": profile.username,
                        "position": profile.position_th,
                        "preset": profile.preset_key,
                        "scope_count": len(desired_scopes),
                        "created": created,
                    },
                    user_agent="prepare_sketch_biz_test_staff",
                )
            )
            prepared.append(
                {
                    "username": profile.username,
                    "name": f"{profile.first_name} {profile.last_name}",
                    "position": profile.position_th,
                    "role": policy.name,
                    "scope": policy.default_scope,
                    "scope_count": len(desired_scopes),
                    "created": created,
                }
            )
        await db.commit()
    return {
        "status": "ready",
        "company_id": str(args.company_id),
        "user_count": len(prepared),
        "password_verified": len(prepared),
        "default_branch": "KPP-01",
        "station_login_note": "test.kitchen-staff uses station_key=kitchen",
        "users": prepared,
        "production_activated": False,
    }


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = asyncio.run(prepare(args))
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
