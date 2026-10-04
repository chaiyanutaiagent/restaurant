"""UAT-only, company-scoped role preparation; preview unless --apply is supplied."""
from __future__ import annotations
import argparse
import asyncio
import json
import uuid
from urllib.parse import urlsplit
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from app.config import settings
from app.database import active_identity_session_factory
from app.models.audit import AuditLog
from app.models.company import Company
from app.models.role import Role, Permission
from app.services.role_preset_service import ROLE_PRESET_POLICIES
from app.utils.seed_permissions import seed_default_permissions

STORE_PRESETS = {"takeaway-cashier", "takeaway-branch-manager", "takeaway-stock-receiving", "takeaway-central-kitchen"}

async def prepare(company_id: uuid.UUID, apply: bool):
    if settings.environment != "development" or not (urlsplit(settings.saas_public_base_url).hostname or "").startswith("uat-"):
        raise RuntimeError("Store role preparation is restricted to UAT")
    async with active_identity_session_factory()() as db:
        company = await db.get(Company, company_id)
        if company is None or not company.is_active:
            raise RuntimeError("Active company not found")
        plan = {"company_id": str(company_id), "business_code": company.business_slug,
                "create_or_update_roles": sorted(STORE_PRESETS),
                "add_store_access_if_existing": ["Company Owner", "Takeaway Store Operator"],
                "users_changed": 0, "applied": apply}
        if not apply:
            return plan
        await seed_default_permissions(db)
        permissions = {p.code: p for p in await db.scalars(select(Permission))}
        for policy in ROLE_PRESET_POLICIES:
            if policy.key not in STORE_PRESETS | {"company-owner", "takeaway-store-operator"}:
                continue
            role = await db.scalar(select(Role).where(Role.company_id == company_id, Role.name == policy.name,
                Role.deleted_at.is_(None)).options(selectinload(Role.permissions)))
            if policy.key not in STORE_PRESETS:
                if role is not None and "takeaway.store.access" not in {p.code for p in role.permissions}:
                    role.permissions.append(permissions["takeaway.store.access"])
                continue
            if role is None:
                role = Role(company_id=company_id, name=policy.name, permissions=[])
                db.add(role)
            role.description = policy.description
            role.is_system = True
            role.is_branch_assignable = policy.is_branch_assignable
            role.allowed_scope_types = list(policy.allowed_scopes)
            role.permissions = [permissions[code] for code in policy.permission_codes]
        db.add(AuditLog(company_id=company_id, action="mobile_store.roles.prepare", resource="Company",
            resource_id=str(company_id), new_value=plan))
        await db.commit()
        return plan

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--company-id", required=True, type=uuid.UUID)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    print(json.dumps(asyncio.run(prepare(args.company_id, args.apply)), ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
