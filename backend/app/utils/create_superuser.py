from __future__ import annotations

import asyncio
import uuid

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import AsyncSessionLocal
from app.models.branch import Branch
from app.models.company import Company
from app.models.role import Permission, Role
from app.models.settings import BranchSettings
from app.models.user import User, UserBranch
from app.utils.seed_accounts import seed_default_accounts
from app.utils.seed_catalog import seed_default_catalog, seed_default_stock_location
from app.utils.seed_hr import seed_default_hr_components, seed_default_leave_types, seed_default_work_schedule, seed_public_holidays_2026
from app.utils.seed_crm import seed_default_tiers, seed_loyalty_settings
from app.utils.seed_logistics import seed_default_carriers, seed_default_shipping_rates
from app.utils.seed_permissions import PERMISSIONS
from app.utils.security import hash_password

DEFAULT_COMPANY_ID = uuid.UUID("1b8a1818-44d6-4d5f-9d22-e5e17b23c081")
DEFAULT_BRANCHES = (
    {"code": "BKK-01", "name": "สาขากรุงเทพ", "sort_order": 1},
)
STORE_CASHIER_PERMISSIONS = (
    "brand.store.order.create",
    "brand.store.shift.close",
    "brand.store.replenishment.submit",
    "brand.store.delivery.receive",
    "brand.store.stock.view",
    "fb.order.create",
)


def get_default_admin_password() -> str:
    if not settings.default_admin_password:
        raise RuntimeError("Set DEFAULT_ADMIN_PASSWORD in .env before seeding the default admin user.")
    return settings.default_admin_password


def _ensure_existing_admin_access(user: User) -> None:
    """Keep bootstrap access flags current without replacing the user's password."""
    user.is_superuser = True
    user.is_active = True


async def ensure_default_company_seed() -> None:
    async with AsyncSessionLocal() as db:
        await ensure_default_company_seed_in_session(db)


async def ensure_default_company_seed_in_session(db: AsyncSession) -> None:
    company = await db.get(Company, DEFAULT_COMPANY_ID)
    if company is None:
        # FIX S3-D-verify: create the documented verification tenant and admin seed automatically on a fresh database
        company = Company(
            id=DEFAULT_COMPANY_ID,
            name="Test Company",
            tax_id="0000000000000",
            currency="THB",
        )
        db.add(company)
        await db.flush()

    branches: list[Branch] = []
    for branch_data in DEFAULT_BRANCHES:
        branch = await db.scalar(
            select(Branch).where(
                Branch.company_id == company.id,
                Branch.code == branch_data["code"],
                Branch.deleted_at.is_(None),
            )
        )
        if branch is None:
            branch = Branch(
                company_id=company.id,
                code=branch_data["code"],
                name=branch_data["name"],
                is_active=True,
                is_warehouse=False,
                sort_order=branch_data["sort_order"],
            )
            db.add(branch)
            await db.flush()
        branches.append(branch)

    admin_role = await db.scalar(
        select(Role).where(
            Role.company_id == company.id,
            Role.name == "admin",
            Role.deleted_at.is_(None),
        )
    )
    if admin_role is None:
        admin_role = Role(
            company_id=company.id,
            name="admin",
            description="Initial admin role",
            is_system=True,
        )
        db.add(admin_role)
        await db.flush()

    system_role = await db.scalar(
        select(Role).where(
            Role.company_id == company.id,
            Role.name == "system",
            Role.deleted_at.is_(None),
        )
    )
    if system_role is None:
        system_role = Role(
            company_id=company.id,
            name="system",
            description="Reserved system role",
            is_system=True,
        )
        db.add(system_role)
        await db.flush()

    all_permissions = (
        await db.scalars(
            select(Permission).where(Permission.code.in_([item["code"] for item in PERMISSIONS]))
        )
    ).all()
    await db.refresh(admin_role, attribute_names=["permissions"])
    await db.refresh(system_role, attribute_names=["permissions"])
    admin_role.permissions = all_permissions
    system_role.permissions = all_permissions

    store_cashier_role = await db.scalar(
        select(Role).where(
            Role.company_id == company.id,
            Role.name == "store_cashier",
            Role.deleted_at.is_(None),
        )
    )
    if store_cashier_role is None:
        store_cashier_role = Role(
            company_id=company.id,
            name="store_cashier",
            description="Brand storefront cashier role",
            is_system=True,
            is_branch_assignable=True,
        )
        db.add(store_cashier_role)
        await db.flush()
    store_cashier_role.is_branch_assignable = True
    store_cashier_permissions = (
        await db.scalars(select(Permission).where(Permission.code.in_(STORE_CASHIER_PERMISSIONS)))
    ).all()
    await db.refresh(store_cashier_role, attribute_names=["permissions"])
    store_cashier_role.permissions = store_cashier_permissions

    user = await db.scalar(
        select(User).where(
            User.company_id == company.id,
            User.username == "admin",
            User.deleted_at.is_(None),
        )
    )
    if user is None:
        user = User(
            company_id=company.id,
            username="admin",
            hashed_password=hash_password(get_default_admin_password()),
            display_name="System Admin",
            is_active=True,
            is_superuser=True,
        )
        db.add(user)
        await db.flush()
    else:
        _ensure_existing_admin_access(user)

    for index, branch in enumerate(branches):
        user_branch = await db.scalar(
            select(UserBranch).where(
                UserBranch.user_id == user.id,
                UserBranch.branch_id == branch.id,
            )
        )
        if user_branch is None:
            db.add(
                UserBranch(
                    user_id=user.id,
                    branch_id=branch.id,
                    role_id=admin_role.id,
                    is_default=index == 0,
                )
            )
        else:
            user_branch.deleted_at = None
            user_branch.role_id = admin_role.id
            user_branch.is_default = index == 0

        settings = await db.scalar(
            select(BranchSettings).where(
                BranchSettings.company_id == company.id,
                BranchSettings.branch_id == branch.id,
            )
        )
        if settings is None:
            # FIX S3-D-verify: seed the verification branches with default settings so the system APIs work on a fresh database
            db.add(
                BranchSettings(
                    company_id=company.id,
                    branch_id=branch.id,
                    pos_receipt_footer="ขอบคุณที่ใช้บริการ",
                )
            )
        await seed_default_stock_location(db, company.id, branch.id)

    await seed_default_catalog(db, company.id)
    accounts_table_exists = await db.scalar(
        text("SELECT 1 FROM information_schema.tables WHERE table_name = 'accounts' LIMIT 1")
    )
    if accounts_table_exists:
        await seed_default_accounts(db, company.id)
    salary_components_table_exists = await db.scalar(
        text("SELECT 1 FROM information_schema.tables WHERE table_name = 'salary_components' LIMIT 1")
    )
    if salary_components_table_exists:
        await seed_default_hr_components(db, company.id)
    work_schedules_table_exists = await db.scalar(
        text("SELECT 1 FROM information_schema.tables WHERE table_name = 'work_schedules' LIMIT 1")
    )
    leave_types_table_exists = await db.scalar(
        text("SELECT 1 FROM information_schema.tables WHERE table_name = 'leave_types' LIMIT 1")
    )
    public_holidays_table_exists = await db.scalar(
        text("SELECT 1 FROM information_schema.tables WHERE table_name = 'public_holidays' LIMIT 1")
    )
    if leave_types_table_exists:
        await seed_default_leave_types(db, company.id)
    if work_schedules_table_exists and branches:
        await seed_default_work_schedule(db, company.id, branches[0].id)
    if public_holidays_table_exists:
        await seed_public_holidays_2026(db, company.id)
    customer_tiers_table_exists = await db.scalar(
        text("SELECT 1 FROM information_schema.tables WHERE table_name = 'customer_tiers' LIMIT 1")
    )
    loyalty_settings_table_exists = await db.scalar(
        text("SELECT 1 FROM information_schema.tables WHERE table_name = 'loyalty_settings' LIMIT 1")
    )
    if customer_tiers_table_exists:
        await seed_default_tiers(db, company.id)
    if loyalty_settings_table_exists:
        await seed_loyalty_settings(db, company.id)
    carriers_table_exists = await db.scalar(
        text("SELECT 1 FROM information_schema.tables WHERE table_name = 'carriers' LIMIT 1")
    )
    shipping_rates_table_exists = await db.scalar(
        text("SELECT 1 FROM information_schema.tables WHERE table_name = 'shipping_rates' LIMIT 1")
    )
    if carriers_table_exists:
        await seed_default_carriers(db, company.id)
    if shipping_rates_table_exists:
        await seed_default_shipping_rates(db, company.id)
    await db.commit()


async def create_superuser() -> None:
    async with AsyncSessionLocal() as db:
        await ensure_default_company_seed_in_session(db)
        print(f"Company UUID: {DEFAULT_COMPANY_ID}")
        print("Username: admin")
        print("Password: set by DEFAULT_ADMIN_PASSWORD in .env")


if __name__ == "__main__":
    asyncio.run(create_superuser())
