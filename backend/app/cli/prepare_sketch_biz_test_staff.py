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
    workspace_key: str | None = None


TEST_STAFF_PROFILES = (
    TestStaffProfile("company-owner", "test.owner", "UAT-OWNER", "ณัฐวุฒิ", "ศรีสุข", "เจ้าของบริษัท"),
    TestStaffProfile("accountant", "test.accountant", "UAT-ACCOUNT", "สุภาวดี", "มั่นคง", "เจ้าหน้าที่บัญชี"),
    TestStaffProfile("purchasing", "test.purchasing", "UAT-PURCHASE", "กิตติพงศ์", "วงศ์ดี", "เจ้าหน้าที่จัดซื้อ"),
    TestStaffProfile("hr", "test.hr", "UAT-HR", "ชลธิชา", "พูนทรัพย์", "เจ้าหน้าที่ทรัพยากรบุคคล"),
    TestStaffProfile("auditor", "test.auditor", "UAT-AUDITOR", "รัชดา", "ธรรมรักษ์", "ผู้ตรวจสอบ"),
    TestStaffProfile("brand-manager", "test.kpp.brand-manager", "KPP-BRAND", "อรทัย", "ภูผา", "ผู้จัดการแบรนด์", "krua-pa-pla-khuen"),
    TestStaffProfile("area-manager", "test.kpp.area-manager", "KPP-AREA", "ชาญชัย", "ลำน้ำ", "ผู้จัดการเขต", "krua-pa-pla-khuen"),
    TestStaffProfile("branch-manager", "test.kpp.branch-manager", "KPP-BRANCH", "นภัสกร", "เขื่อนทอง", "ผู้จัดการสาขา", "krua-pa-pla-khuen"),
    TestStaffProfile("warehouse", "test.kpp.warehouse", "KPP-WAREHOUSE", "ประเสริฐ", "ทองคลัง", "เจ้าหน้าที่คลังสินค้า", "krua-pa-pla-khuen"),
    TestStaffProfile("service-staff", "test.kpp.service", "KPP-SERVICE", "รุ่งนภา", "ยิ้มรับ", "พนักงานบริการ", "krua-pa-pla-khuen"),
    TestStaffProfile("kitchen-manager", "test.kpp.kitchen-manager", "KPP-KITCHEN-MGR", "วิทยา", "ครัวไทย", "ผู้จัดการครัว", "krua-pa-pla-khuen"),
    TestStaffProfile("cashier", "test.kpp.cashier", "KPP-CASHIER", "มนัสวี", "เงินงาม", "พนักงานขายและแคชเชียร์", "krua-pa-pla-khuen"),
    TestStaffProfile("kitchen-staff", "test.kpp.kitchen", "KPP-KITCHEN", "สมพงษ์", "รสมือ", "พนักงานครัว", "krua-pa-pla-khuen"),
    TestStaffProfile("brand-manager", "test.tlk.brand-manager", "TLK-BRAND", "ศิรินทร์", "วัฒนศิลป์", "ผู้จัดการแบรนด์", "the-loft-kitchen"),
    TestStaffProfile("area-manager", "test.tlk.area-manager", "TLK-AREA", "ภูริณัฐ", "เมืองนนท์", "ผู้จัดการเขต", "the-loft-kitchen"),
    TestStaffProfile("branch-manager", "test.tlk.branch-manager", "TLK-BRANCH", "ชยพล", "พัฒนกิจ", "ผู้จัดการสาขา", "the-loft-kitchen"),
    TestStaffProfile("warehouse", "test.tlk.warehouse", "TLK-WAREHOUSE", "จิรายุ", "เก็บทรัพย์", "เจ้าหน้าที่คลังสินค้า", "the-loft-kitchen"),
    TestStaffProfile("service-staff", "test.tlk.service", "TLK-SERVICE", "พัชรี", "ต้อนรับ", "พนักงานบริการ", "the-loft-kitchen"),
    TestStaffProfile("kitchen-manager", "test.tlk.kitchen-manager", "TLK-KITCHEN-MGR", "ธีรภัทร", "รสเยี่ยม", "ผู้จัดการครัว", "the-loft-kitchen"),
    TestStaffProfile("cashier", "test.tlk.cashier", "TLK-CASHIER", "ณิชารีย์", "บัญชีดี", "พนักงานขายและแคชเชียร์", "the-loft-kitchen"),
    TestStaffProfile("kitchen-staff", "test.tlk.kitchen", "TLK-KITCHEN", "อาทิตย์", "ปรุงดี", "พนักงานครัว", "the-loft-kitchen"),
    TestStaffProfile("brand-manager", "test.tlm.brand-manager", "TLM-BRAND", "กมลชนก", "ค้าดี", "ผู้จัดการแบรนด์", "the-loft-mini-mart"),
    TestStaffProfile("area-manager", "test.tlm.area-manager", "TLM-AREA", "ศุภกร", "ตลาดใหม่", "ผู้จัดการเขต", "the-loft-mini-mart"),
    TestStaffProfile("branch-manager", "test.tlm.branch-manager", "TLM-BRANCH", "ธนากร", "ชูทรัพย์", "ผู้จัดการสาขา", "the-loft-mini-mart"),
    TestStaffProfile("warehouse", "test.tlm.warehouse", "TLM-WAREHOUSE", "วีระพล", "คลังทอง", "เจ้าหน้าที่คลังสินค้า", "the-loft-mini-mart"),
    TestStaffProfile("service-staff", "test.tlm.service", "TLM-SERVICE", "ลลิตา", "บริการดี", "พนักงานขาย", "the-loft-mini-mart"),
    TestStaffProfile("cashier", "test.tlm.cashier", "TLM-CASHIER", "ชุติมา", "เงินตรง", "พนักงานแคชเชียร์", "the-loft-mini-mart"),
    TestStaffProfile("brand-manager", "test.chambo.brand-manager", "CHB-BRAND", "ชนินทร์", "ปิ่นทอง", "ผู้จัดการแบรนด์", "chambo"),
    TestStaffProfile("area-manager", "test.chambo.area-manager", "CHB-AREA", "ภัทรดนัย", "เมืองกรุง", "ผู้จัดการเขต", "chambo"),
    TestStaffProfile("branch-manager", "test.chambo.branch-manager", "CHB-BRANCH", "กานต์พิชชา", "ศรีโอโซน", "ผู้จัดการสาขา", "chambo"),
    TestStaffProfile("takeaway-store-operator", "test.chambo.operator01", "CHB-OP-01", "ธัญชนก", "รับออเดอร์", "พนักงานหน้าร้าน Takeaway", "chambo"),
    TestStaffProfile("takeaway-store-operator", "test.chambo.operator02", "CHB-OP-02", "สิริมา", "เงินครบ", "พนักงานหน้าร้าน Takeaway", "chambo"),
    TestStaffProfile("takeaway-store-operator", "test.chambo.operator03", "CHB-OP-03", "พงศกร", "พร้อมขาย", "พนักงานหน้าร้าน Takeaway", "chambo"),
)


SUPERSEDED_BROAD_USERNAMES = (
    "test.brand-manager",
    "test.branch-manager",
    "test.warehouse",
    "test.area-manager",
    "test.service-staff",
    "test.kitchen-manager",
    "test.cashier",
    "test.kitchen-staff",
    "test.chambo.warehouse",
    "test.chambo.service",
    "test.chambo.kitchen-manager",
    "test.chambo.cashier",
    "test.chambo.kitchen",
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
    profile: TestStaffProfile,
    policy: RolePresetPolicy,
    company_id: uuid.UUID,
    workspaces: list[WorkspaceRow],
) -> list[tuple[str, str, uuid.UUID | None, uuid.UUID | None, str | None]]:
    if profile.workspace_key is None:
        if policy.default_scope != "company":
            raise RuntimeError(f"Shared profile must use Company scope: {profile.username}")
        return [("company", str(company_id), None, None, None)]
    matched = [row for row in workspaces if row.spec.key == profile.workspace_key]
    if len(matched) != 1:
        raise RuntimeError(f"Profile workspace is unavailable: {profile.workspace_key}")
    row = matched[0]
    if policy.default_scope == "company":
        raise RuntimeError(f"Company role cannot be branch-specific: {profile.username}")
    if policy.default_scope == "brand":
        return [("brand", str(row.brand.id), row.brand.id, None, None)]
    if policy.default_scope == "branch":
        return [("branch", str(row.branch.id), row.brand.id, row.branch.id, None)]
    if policy.default_scope == "station":
        if row.spec.business_type not in {"restaurant", "takeaway"}:
            raise RuntimeError(f"Kitchen station role cannot target {row.spec.business_type}")
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
        superseded_users = (
            await db.scalars(
                select(User).where(
                    User.company_id == args.company_id,
                    User.username.in_(SUPERSEDED_BROAD_USERNAMES),
                    User.is_active.is_(True),
                    User.deleted_at.is_(None),
                )
            )
        ).all()
        for superseded in superseded_users:
            superseded.is_active = False
            superseded.credential_version += 1
            for link in (
                await db.scalars(
                    select(UserBranch).where(
                        UserBranch.user_id == superseded.id,
                        UserBranch.deleted_at.is_(None),
                    )
                )
            ).all():
                link.deleted_at = now
                link.is_default = False
            for assignment in (
                await db.scalars(
                    select(StaffRoleAssignment).where(
                        StaffRoleAssignment.company_id == args.company_id,
                        StaffRoleAssignment.user_id == superseded.id,
                        StaffRoleAssignment.revoked_at.is_(None),
                    )
                )
            ).all():
                assignment.revoked_at = now
                assignment.revoked_by = actor.id
                assignment.revocation_reason = "Superseded by workspace-specific UAT staff"
            await enqueue_reference_event(
                db,
                aggregate_type="user",
                aggregate_id=superseded.id,
                company_id=args.company_id,
                payload={"source": "prepare_sketch_biz_test_staff", "change": "deactivate_broad_user"},
            )
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

            intended_workspaces = (
                workspaces
                if profile.workspace_key is None
                else [row for row in workspaces if row.spec.key == profile.workspace_key]
            )
            active_links = (
                await db.scalars(
                    select(UserBranch).where(
                        UserBranch.user_id == user.id,
                        UserBranch.deleted_at.is_(None),
                    )
                )
            ).all()
            link_by_branch = {link.branch_id: link for link in active_links}
            intended_branch_ids = {row.branch.id for row in intended_workspaces}
            for link in active_links:
                if link.branch_id not in intended_branch_ids:
                    link.deleted_at = now
                    link.is_default = False
            for index, row in enumerate(intended_workspaces):
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

            desired_scopes = _desired_scopes(profile, policy, args.company_id, workspaces)
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
                        "workspace": profile.workspace_key or "shared-company",
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
                    "workspace": profile.workspace_key or "shared-company",
                    "created": created,
                }
            )
        await db.commit()
    return {
        "status": "ready",
        "company_id": str(args.company_id),
        "user_count": len(prepared),
        "password_verified": len(prepared),
        "shared_company_users": sum(profile.workspace_key is None for profile in TEST_STAFF_PROFILES),
        "workspace_users": sum(profile.workspace_key is not None for profile in TEST_STAFF_PROFILES),
        "superseded_broad_users": len(superseded_users),
        "station_login_note": "Restaurant kitchen users remain station-scoped; Takeaway uses branch-scoped store operators",
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
