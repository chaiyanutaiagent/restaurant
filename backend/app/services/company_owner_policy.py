from __future__ import annotations

import uuid

from fastapi import HTTPException, status
from sqlalchemy import distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.company import Company
from app.models.role import Role
from app.models.staff_assignment import StaffRoleAssignment
from app.models.user import User


class CompanyOwnerPolicy:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def ensure_user_can_be_deactivated(
        self,
        company_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> None:
        await self._lock_company(company_id)
        if not await self._is_active_owner(company_id, user_id):
            return
        if await self._active_owner_count(company_id) <= 1:
            self._raise_last_owner()

    async def ensure_assignment_can_be_revoked(
        self,
        assignment: StaffRoleAssignment,
    ) -> None:
        if (
            assignment.scope_type != "company"
            or assignment.role is None
            or assignment.role.name != "Company Owner"
        ):
            return
        await self._lock_company(assignment.company_id)
        if await self._active_owner_count(assignment.company_id) <= 1:
            self._raise_last_owner()

    async def _lock_company(self, company_id: uuid.UUID) -> None:
        company = await self.db.scalar(
            select(Company.id).where(Company.id == company_id).with_for_update()
        )
        if company is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")

    async def _is_active_owner(self, company_id: uuid.UUID, user_id: uuid.UUID) -> bool:
        owner = await self.db.scalar(
            select(StaffRoleAssignment.id)
            .join(Role, Role.id == StaffRoleAssignment.role_id)
            .join(User, User.id == StaffRoleAssignment.user_id)
            .where(
                StaffRoleAssignment.company_id == company_id,
                StaffRoleAssignment.user_id == user_id,
                StaffRoleAssignment.scope_type == "company",
                StaffRoleAssignment.revoked_at.is_(None),
                Role.name == "Company Owner",
                Role.deleted_at.is_(None),
                User.is_active.is_(True),
                User.deleted_at.is_(None),
            )
        )
        return owner is not None

    async def _active_owner_count(self, company_id: uuid.UUID) -> int:
        count = await self.db.scalar(
            select(func.count(distinct(StaffRoleAssignment.user_id)))
            .join(Role, Role.id == StaffRoleAssignment.role_id)
            .join(User, User.id == StaffRoleAssignment.user_id)
            .where(
                StaffRoleAssignment.company_id == company_id,
                StaffRoleAssignment.scope_type == "company",
                StaffRoleAssignment.revoked_at.is_(None),
                Role.name == "Company Owner",
                Role.deleted_at.is_(None),
                User.is_active.is_(True),
                User.deleted_at.is_(None),
            )
        )
        return int(count or 0)

    @staticmethod
    def _raise_last_owner() -> None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "last_company_owner",
                "message": "ต้องแต่งตั้ง Company Owner คนใหม่ก่อนลดสิทธิ์หรือปิดบัญชี Owner คนสุดท้าย",
            },
        )
