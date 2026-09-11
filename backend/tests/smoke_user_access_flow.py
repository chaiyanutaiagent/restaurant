from __future__ import annotations

import asyncio
import uuid

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.branch import Branch
from app.models.company import Company
from app.models.restaurant import Brand, BrandBranch
from app.models.role import Role
from app.models.user import User, UserBranch
from app.models.user_access import UserAccessRequest
from app.schemas.user_access import UserAccessApproveRequest, UserAccessRequestCreate
from app.services.user_access_service import UserAccessService
from app.utils.security import hash_password


async def run() -> None:
    marker = uuid.uuid4().hex[:8]
    async with AsyncSessionLocal() as db:
        company = Company(name=f"User Access Smoke {marker}", business_slug=f"user-access-{marker}")
        db.add(company)
        await db.flush()

        branch = Branch(
            company_id=company.id,
            code=f"UA-{marker}",
            name="User Access Smoke Branch",
            is_active=True,
        )
        requested_role = Role(
            company_id=company.id,
            name=f"cashier-{marker}",
            is_branch_assignable=True,
        )
        manager_role = Role(
            company_id=company.id,
            name=f"manager-{marker}",
            is_branch_assignable=False,
        )
        db.add_all([branch, requested_role, manager_role])
        await db.flush()

        brand = Brand(
            company_id=company.id,
            central_branch_id=branch.id,
            slug=f"brand-{marker}",
            name="User Access Smoke Brand",
            is_active=True,
        )
        db.add(brand)
        await db.flush()
        db.add(
            BrandBranch(
                company_id=company.id,
                brand_id=brand.id,
                branch_id=branch.id,
                is_active=True,
            )
        )

        manager = User(
            company_id=company.id,
            username=f"manager-{marker}",
            hashed_password=hash_password("ManagerPass123!"),
            display_name="Branch Manager",
            is_active=True,
        )
        admin = User(
            company_id=company.id,
            username=f"admin-{marker}",
            hashed_password=hash_password("AdminPass123!"),
            display_name="Central Admin",
            is_active=True,
            is_superuser=True,
        )
        db.add_all([manager, admin])
        await db.flush()
        db.add(
            UserBranch(
                user_id=manager.id,
                branch_id=branch.id,
                role_id=manager_role.id,
                is_default=True,
            )
        )
        await db.commit()

        service = UserAccessService(db)
        created = await service.create_request(
            company.id,
            branch.id,
            manager.id,
            UserAccessRequestCreate(
                brand_slug=brand.slug,
                requested_role_id=requested_role.id,
                username=f"cashier-{marker}",
                password="CashierPass123!",
                first_name="Smoke",
                last_name="Cashier",
                email=f"cashier-{marker}@example.com",
            ),
        )
        if created.status != "pending":
            raise RuntimeError(f"Expected pending request, got {created.status}")

        approved, invitation, plain_otp = await service.approve_request(
            created.id,
            company.id,
            admin.id,
            UserAccessApproveRequest(approved_role_id=requested_role.id),
            is_superuser=True,
        )
        if approved.status != "activated" or invitation is not None or plain_otp is not None:
            raise RuntimeError("Approval did not activate the requested credentials")

        user = await db.scalar(
            select(User).where(
                User.company_id == company.id,
                User.username == f"cashier-{marker}",
            )
        )
        if user is None:
            raise RuntimeError("Approval did not create the requested user")
        activated = await db.scalar(
            select(UserAccessRequest).where(UserAccessRequest.id == created.id)
        )
        assignment = await db.scalar(
            select(UserBranch).where(
                UserBranch.user_id == user.id,
                UserBranch.branch_id == branch.id,
                UserBranch.role_id == requested_role.id,
            )
        )
        if activated is None or activated.status != "activated" or assignment is None:
            raise RuntimeError("Activation did not create the expected user branch assignment")

        print(
            f"user_access_smoke=ok request={created.id} user={user.id} branch={branch.id}"
        )


if __name__ == "__main__":
    asyncio.run(run())
