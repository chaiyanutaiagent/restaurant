from __future__ import annotations

from datetime import datetime, timezone
import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.audit import AuditLog
from app.models.branch import Branch
from app.models.company import Company
from app.models.hr import Employee
from app.models.restaurant import Brand, BrandBranch
from app.models.role import Role
from app.models.settings import BranchSettings
from app.models.staff_assignment import StaffRoleAssignment
from app.models.user import User, UserBranch
from app.schemas.staff_assignment import (
    AssignmentBranchOption,
    AssignmentBrandOption,
    AssignmentCompanyOption,
    StaffAssignmentOptionsRead,
    StaffRoleAssignmentCreate,
    StaffRoleAssignmentRead,
)
from app.services.business_context_service import load_branch_business_context
from app.services.staff_scope_policy import (
    assignment_applies_to_context,
    assignment_scope_key,
    normalized_station_key,
)


class StaffScopeService:
    def __init__(
        self,
        db: AsyncSession,
        *,
        restaurant_db: AsyncSession | None = None,
    ):
        self.db = db
        self.restaurant_db = restaurant_db or db

    async def list_assignments(
        self,
        company_id: uuid.UUID,
        user_id: uuid.UUID,
        *,
        include_revoked: bool = False,
    ) -> list[StaffRoleAssignmentRead]:
        await self._get_user(company_id, user_id)
        statement = (
            select(StaffRoleAssignment)
            .where(
                StaffRoleAssignment.company_id == company_id,
                StaffRoleAssignment.user_id == user_id,
            )
            .options(
                selectinload(StaffRoleAssignment.role),
                selectinload(StaffRoleAssignment.brand),
                selectinload(StaffRoleAssignment.branch),
            )
            .order_by(
                StaffRoleAssignment.revoked_at.asc().nulls_first(),
                StaffRoleAssignment.assigned_at.desc(),
            )
        )
        if not include_revoked:
            statement = statement.where(StaffRoleAssignment.revoked_at.is_(None))
        rows = (await self.db.scalars(statement)).all()
        employee = await self._get_employee_for_user(company_id, user_id, required=False)
        return [self._build_read(row, employee) for row in rows]

    async def create_assignment(
        self,
        company_id: uuid.UUID,
        user_id: uuid.UUID,
        actor_id: uuid.UUID,
        data: StaffRoleAssignmentCreate,
    ) -> StaffRoleAssignmentRead:
        await self._get_user(company_id, user_id)
        employee = await self._get_employee_for_user(
            company_id,
            user_id,
            required=data.scope_type != "company",
        )
        role = await self._get_role(company_id, data.role_id)
        if data.scope_type not in role.allowed_scope_types:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Role {role.name} does not allow {data.scope_type} scope; "
                    f"allowed: {', '.join(role.allowed_scope_types)}"
                ),
            )

        brand_id: uuid.UUID | None = None
        branch_id: uuid.UUID | None = None
        station_key: str | None = None
        if data.scope_type == "brand":
            brand = await self._get_brand(company_id, data.brand_id)
            brand_id = brand.id
        elif data.scope_type in {"branch", "station"}:
            assert data.branch_id is not None
            context = await load_branch_business_context(self.db, company_id, data.branch_id)
            assert context is not None
            brand_id = context.brand_id
            branch_id = context.branch_id
            if data.scope_type == "station":
                station_key = await self._canonical_station_key(
                    company_id,
                    context.branch_id,
                    data.station_key,
                )

        scope_key = assignment_scope_key(
            company_id=company_id,
            scope_type=data.scope_type,
            brand_id=brand_id,
            branch_id=branch_id,
            station_key=station_key,
        )
        existing = await self.db.scalar(
            select(StaffRoleAssignment.id).where(
                StaffRoleAssignment.user_id == user_id,
                StaffRoleAssignment.role_id == role.id,
                StaffRoleAssignment.scope_type == data.scope_type,
                StaffRoleAssignment.scope_key == scope_key,
                StaffRoleAssignment.revoked_at.is_(None),
            )
        )
        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Active role assignment already exists",
            )

        assignment = StaffRoleAssignment(
            company_id=company_id,
            user_id=user_id,
            role_id=role.id,
            scope_type=data.scope_type,
            scope_key=scope_key,
            brand_id=brand_id,
            branch_id=branch_id,
            station_key=station_key,
            assignment_reason=data.reason,
            assigned_by=actor_id,
        )
        self.db.add(assignment)
        await self.db.flush()
        assignment.role = role
        self._audit(
            company_id=company_id,
            branch_id=branch_id,
            actor_id=actor_id,
            action="system.staff_assignment.create",
            assignment=assignment,
            old_value=None,
            new_value=self._snapshot(assignment, reason=data.reason),
        )
        await self.db.commit()
        return await self.get_assignment(company_id, user_id, assignment.id)

    async def get_assignment(
        self,
        company_id: uuid.UUID,
        user_id: uuid.UUID,
        assignment_id: uuid.UUID,
    ) -> StaffRoleAssignmentRead:
        row = await self.db.scalar(
            select(StaffRoleAssignment)
            .where(
                StaffRoleAssignment.id == assignment_id,
                StaffRoleAssignment.company_id == company_id,
                StaffRoleAssignment.user_id == user_id,
            )
            .options(
                selectinload(StaffRoleAssignment.role),
                selectinload(StaffRoleAssignment.brand),
                selectinload(StaffRoleAssignment.branch),
            )
        )
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assignment not found")
        employee = await self._get_employee_for_user(company_id, user_id, required=False)
        return self._build_read(row, employee)

    async def revoke_assignment(
        self,
        company_id: uuid.UUID,
        user_id: uuid.UUID,
        assignment_id: uuid.UUID,
        actor_id: uuid.UUID,
        reason: str,
    ) -> StaffRoleAssignmentRead:
        row = await self.db.scalar(
            select(StaffRoleAssignment)
            .where(
                StaffRoleAssignment.id == assignment_id,
                StaffRoleAssignment.company_id == company_id,
                StaffRoleAssignment.user_id == user_id,
                StaffRoleAssignment.revoked_at.is_(None),
            )
            .options(
                selectinload(StaffRoleAssignment.role),
                selectinload(StaffRoleAssignment.brand),
                selectinload(StaffRoleAssignment.branch),
            )
        )
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assignment not found")

        old_value = self._snapshot(row, reason=row.assignment_reason)
        row.revoked_by = actor_id
        row.revoked_at = datetime.now(timezone.utc)
        row.revocation_reason = reason
        self._audit(
            company_id=company_id,
            branch_id=row.branch_id,
            actor_id=actor_id,
            action="system.staff_assignment.revoke",
            assignment=row,
            old_value=old_value,
            new_value=self._snapshot(row, reason=reason),
        )
        await self.db.commit()
        employee = await self._get_employee_for_user(company_id, user_id, required=False)
        return self._build_read(row, employee)

    async def _get_employee_for_user(
        self,
        company_id: uuid.UUID,
        user_id: uuid.UUID,
        *,
        required: bool,
    ) -> Employee | None:
        employee = await self.db.scalar(
            select(Employee).where(
                Employee.company_id == company_id,
                Employee.user_id == user_id,
                Employee.deleted_at.is_(None),
                Employee.is_active.is_(True),
            )
        )
        if employee is None and required:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "active_employee_required",
                    "message": "Brand, Branch and Station assignments require an active HR Employee link",
                },
            )
        return employee

    async def list_options(self, company_id: uuid.UUID) -> StaffAssignmentOptionsRead:
        company = await self.db.scalar(
            select(Company).where(Company.id == company_id, Company.is_active.is_(True))
        )
        if company is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")
        brands = (
            await self.db.scalars(
                select(Brand)
                .where(Brand.company_id == company_id, Brand.is_active.is_(True))
                .order_by(Brand.name.asc())
            )
        ).all()
        branch_rows = (
            await self.db.execute(
                select(Branch, BrandBranch.brand_id)
                .join(
                    BrandBranch,
                    (BrandBranch.branch_id == Branch.id)
                    & (BrandBranch.company_id == company_id)
                    & BrandBranch.is_active.is_(True),
                )
                .join(
                    Brand,
                    (Brand.id == BrandBranch.brand_id)
                    & (Brand.company_id == company_id)
                    & Brand.is_active.is_(True),
                )
                .where(
                    Branch.company_id == company_id,
                    Branch.deleted_at.is_(None),
                    Branch.is_active.is_(True),
                )
                .order_by(Branch.sort_order.asc(), Branch.code.asc())
            )
        ).all()
        branch_ids = [branch.id for branch, _ in branch_rows]
        station_rows = (
            await self.restaurant_db.execute(
                select(BranchSettings.branch_id, BranchSettings.fb_kitchen_stations).where(
                    BranchSettings.company_id == company_id,
                    BranchSettings.branch_id.in_(branch_ids),
                )
            )
        ).all() if branch_ids else []
        stations_by_branch = {
            branch_id: list(stations or []) for branch_id, stations in station_rows
        }
        return StaffAssignmentOptionsRead(
            company=AssignmentCompanyOption(id=company.id, name=company.name),
            brands=[
                AssignmentBrandOption(
                    id=brand.id,
                    name=brand.name,
                    business_type=brand.business_type,
                )
                for brand in brands
            ],
            branches=[
                AssignmentBranchOption(
                    id=branch.id,
                    code=branch.code,
                    name=branch.name,
                    brand_id=brand_id,
                    stations=stations_by_branch.get(branch.id, []),
                )
                for branch, brand_id in branch_rows
            ],
        )

    async def list_accessible_branches(
        self,
        company_id: uuid.UUID,
        user_id: uuid.UUID,
        *,
        is_superuser: bool,
    ) -> list[dict]:
        legacy_rows = (
            await self.db.execute(
                select(UserBranch, Branch, Role)
                .join(Branch, Branch.id == UserBranch.branch_id)
                .join(Role, Role.id == UserBranch.role_id)
                .where(
                    UserBranch.user_id == user_id,
                    UserBranch.deleted_at.is_(None),
                    Branch.company_id == company_id,
                    Branch.deleted_at.is_(None),
                    Branch.is_active.is_(True),
                )
            )
        ).all()
        assignments = (
            await self.db.scalars(
                select(StaffRoleAssignment)
                .join(Role, Role.id == StaffRoleAssignment.role_id)
                .where(
                    StaffRoleAssignment.company_id == company_id,
                    StaffRoleAssignment.user_id == user_id,
                    StaffRoleAssignment.revoked_at.is_(None),
                    Role.deleted_at.is_(None),
                )
                .options(selectinload(StaffRoleAssignment.role))
            )
        ).all()
        context_rows = (
            await self.db.execute(
                select(Branch, Brand)
                .join(
                    BrandBranch,
                    (BrandBranch.branch_id == Branch.id)
                    & BrandBranch.is_active.is_(True),
                )
                .join(Brand, Brand.id == BrandBranch.brand_id)
                .where(
                    Branch.company_id == company_id,
                    Branch.deleted_at.is_(None),
                    Branch.is_active.is_(True),
                    Brand.company_id == company_id,
                    Brand.is_active.is_(True),
                )
                .order_by(Branch.sort_order.asc(), Branch.code.asc())
            )
        ).all()

        legacy_by_branch = {
            branch.id: (legacy, role)
            for legacy, branch, role in legacy_rows
            if "branch" in role.allowed_scope_types
        }
        result: list[dict] = []
        for branch, brand in context_rows:
            context = await load_branch_business_context(self.db, company_id, branch.id)
            assert context is not None
            legacy = legacy_by_branch.get(branch.id)
            general_roles = [
                assignment.role.name
                for assignment in assignments
                if assignment.scope_type != "station"
                and assignment.scope_type in assignment.role.allowed_scope_types
                and assignment_applies_to_context(assignment, context, None)
            ]
            if is_superuser or legacy is not None or general_roles:
                role_names = general_roles
                if legacy is not None:
                    role_names = [legacy[1].name, *role_names]
                result.append(
                    self._accessible_branch_row(
                        branch,
                        context,
                        sorted(set(role_names)) or ["Superuser"],
                        legacy[0].is_default if legacy is not None else False,
                        None,
                    )
                )
            for assignment in assignments:
                if assignment.scope_type != "station":
                    continue
                if assignment.scope_type not in assignment.role.allowed_scope_types:
                    continue
                if assignment_applies_to_context(assignment, context, assignment.station_key):
                    result.append(
                        self._accessible_branch_row(
                            branch,
                            context,
                            [assignment.role.name],
                            False,
                            assignment.station_key,
                        )
                    )
        return result

    async def _get_user(self, company_id: uuid.UUID, user_id: uuid.UUID) -> User:
        user = await self.db.scalar(
            select(User).where(
                User.id == user_id,
                User.company_id == company_id,
                User.deleted_at.is_(None),
            )
        )
        if user is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        return user

    async def _get_role(self, company_id: uuid.UUID, role_id: uuid.UUID) -> Role:
        role = await self.db.scalar(
            select(Role).where(
                Role.id == role_id,
                Role.company_id == company_id,
                Role.deleted_at.is_(None),
            )
        )
        if role is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found")
        return role

    async def _get_brand(self, company_id: uuid.UUID, brand_id: uuid.UUID | None) -> Brand:
        brand = await self.db.scalar(
            select(Brand).where(
                Brand.id == brand_id,
                Brand.company_id == company_id,
                Brand.is_active.is_(True),
            )
        )
        if brand is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Brand not found")
        return brand

    async def _canonical_station_key(
        self,
        company_id: uuid.UUID,
        branch_id: uuid.UUID,
        requested_station: str | None,
    ) -> str:
        normalized = normalized_station_key(requested_station)
        if normalized is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Station is required")
        settings = await self.restaurant_db.scalar(
            select(BranchSettings).where(
                BranchSettings.company_id == company_id,
                BranchSettings.branch_id == branch_id,
            )
        )
        stations = settings.fb_kitchen_stations if settings else []
        canonical = next(
            (station.strip() for station in stations or [] if normalized_station_key(station) == normalized),
            None,
        )
        if canonical is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Station is not configured for this branch",
            )
        return canonical

    def _build_read(
        self,
        row: StaffRoleAssignment,
        employee: Employee | None,
    ) -> StaffRoleAssignmentRead:
        scope_label = {
            "company": "Company",
            "brand": row.brand.name if row.brand else "Brand",
            "branch": row.branch.name if row.branch else "Branch",
            "station": f"{row.branch.name if row.branch else 'Branch'} / {row.station_key}",
        }[row.scope_type]
        return StaffRoleAssignmentRead(
            id=row.id,
            company_id=row.company_id,
            user_id=row.user_id,
            employee_id=employee.id if employee else None,
            employee_code=employee.employee_code if employee else None,
            employee_name=employee.full_name if employee else None,
            role_id=row.role_id,
            role_name=row.role.name,
            scope_type=row.scope_type,
            scope_key=row.scope_key,
            scope_label=scope_label,
            brand_id=row.brand_id,
            brand_name=row.brand.name if row.brand else None,
            branch_id=row.branch_id,
            branch_name=row.branch.name if row.branch else None,
            station_key=row.station_key,
            assignment_reason=row.assignment_reason,
            assigned_by=row.assigned_by,
            assigned_at=row.assigned_at,
            revoked_by=row.revoked_by,
            revoked_at=row.revoked_at,
            revocation_reason=row.revocation_reason,
        )

    @staticmethod
    def _snapshot(row: StaffRoleAssignment, *, reason: str) -> dict:
        return {
            "user_id": str(row.user_id),
            "role_id": str(row.role_id),
            "scope_type": row.scope_type,
            "scope_key": row.scope_key,
            "brand_id": str(row.brand_id) if row.brand_id else None,
            "branch_id": str(row.branch_id) if row.branch_id else None,
            "station_key": row.station_key,
            "reason": reason,
            "revoked_at": row.revoked_at.isoformat() if row.revoked_at else None,
        }

    def _audit(
        self,
        *,
        company_id: uuid.UUID,
        branch_id: uuid.UUID | None,
        actor_id: uuid.UUID,
        action: str,
        assignment: StaffRoleAssignment,
        old_value: dict | None,
        new_value: dict,
    ) -> None:
        self.db.add(
            AuditLog(
                company_id=company_id,
                branch_id=branch_id,
                user_id=actor_id,
                action=action,
                resource="StaffRoleAssignment",
                resource_id=str(assignment.id),
                old_value=old_value,
                new_value=new_value,
            )
        )

    @staticmethod
    def _accessible_branch_row(
        branch: Branch,
        context,
        role_names: list[str],
        is_default: bool,
        station_key: str | None,
    ) -> dict:
        return {
            "branch_id": branch.id,
            "branch_name": branch.name,
            "branch_code": branch.code,
            "brand_id": context.brand_id,
            "business_type": context.business_type,
            "target_database": context.target_database,
            "role_name": ", ".join(role_names),
            "is_default": is_default,
            "station_key": station_key,
        }
