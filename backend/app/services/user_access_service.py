from __future__ import annotations

from datetime import datetime, timedelta, timezone
import secrets
import uuid

from fastapi import HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.audit import AuditLog
from app.models.branch import Branch
from app.models.hr import Employee
from app.models.restaurant import Brand, BrandBranch
from app.models.role import Role
from app.models.settings import UserInvitation
from app.models.user import User, UserBranch
from app.models.user_access import UserAccessRequest
from app.business_context import RESTAURANT
from app.schemas.user_access import (
    UserAccessApproveRequest,
    UserAccessRequestCreate,
    UserAccessRequestRead,
)
from app.schemas.user_mgmt import AcceptInvitationRequest
from app.services.business_context_service import load_branch_business_context
from app.utils.security import hash_password, verify_password


OPEN_REQUEST_STATUSES = ("pending", "approved")


class UserAccessService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_branch_assignable_roles(self, company_id: uuid.UUID) -> list[Role]:
        return list(
            (
                await self.db.scalars(
                    select(Role)
                    .where(
                        Role.company_id == company_id,
                        Role.deleted_at.is_(None),
                        Role.is_branch_assignable.is_(True),
                    )
                    .order_by(Role.name.asc())
                )
            ).all()
        )

    async def create_request(
        self,
        company_id: uuid.UUID,
        branch_id: uuid.UUID,
        requester_id: uuid.UUID,
        data: UserAccessRequestCreate,
    ) -> UserAccessRequestRead:
        await self._get_active_branch(company_id, branch_id)
        await self._ensure_user_branch(company_id, requester_id, branch_id)
        brand = await self._get_active_brand_for_branch(company_id, branch_id, data.brand_slug)
        await self._get_branch_assignable_role(company_id, data.requested_role_id)
        employee = await self._validate_employee(company_id, branch_id, data.employee_id)
        employee_code = data.employee_code or (employee.employee_code if employee else None)
        await self._ensure_username_available(company_id, data.username)
        await self._ensure_no_duplicate_identity(
            company_id,
            username=data.username,
            email=data.email,
            phone=data.phone,
            employee_code=employee_code,
            employee_id=data.employee_id,
        )

        row = UserAccessRequest(
            company_id=company_id,
            branch_id=branch_id,
            brand_id=brand.id,
            requested_role_id=data.requested_role_id,
            employee_id=data.employee_id,
            employee_code=employee_code,
            requested_username=data.username,
            initial_password_hash=hash_password(data.password),
            first_name=data.first_name,
            last_name=data.last_name,
            email=data.email,
            phone=data.phone,
            request_note=data.request_note,
            status="pending",
            requested_by=requester_id,
        )
        self.db.add(row)
        try:
            await self.db.flush()
            self._audit(
                company_id,
                branch_id,
                requester_id,
                "system.user_access.requested",
                row.id,
                {
                    "brand_id": str(brand.id),
                    "requested_role_id": str(row.requested_role_id),
                    "requested_username": row.requested_username,
                    "status": row.status,
                },
            )
            await self.db.commit()
        except IntegrityError as exc:
            await self.db.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Username or employee request already exists",
            ) from exc
        return await self.get_request_read(row.id, company_id)

    async def list_requests(
        self,
        company_id: uuid.UUID,
        *,
        branch_id: uuid.UUID | None = None,
        brand_id: uuid.UUID | None = None,
        request_status: str | None = None,
        search: str | None = None,
        page: int = 1,
        limit: int = 20,
    ) -> tuple[list[UserAccessRequestRead], int]:
        filters = [UserAccessRequest.company_id == company_id]
        if branch_id is not None:
            filters.append(UserAccessRequest.branch_id == branch_id)
        if brand_id is not None:
            filters.append(UserAccessRequest.brand_id == brand_id)
        if request_status:
            filters.append(UserAccessRequest.status == request_status)
        if search and search.strip():
            pattern = f"%{search.strip()}%"
            filters.append(
                or_(
                    UserAccessRequest.first_name.ilike(pattern),
                    UserAccessRequest.last_name.ilike(pattern),
                    UserAccessRequest.email.ilike(pattern),
                    UserAccessRequest.phone.ilike(pattern),
                    UserAccessRequest.employee_code.ilike(pattern),
                )
            )

        total = int(
            (await self.db.scalar(select(func.count(UserAccessRequest.id)).where(*filters))) or 0
        )
        rows = (
            await self.db.scalars(
                select(UserAccessRequest)
                .where(*filters)
                .options(*self._read_options())
                .order_by(UserAccessRequest.created_at.desc())
                .offset((page - 1) * limit)
                .limit(limit)
            )
        ).all()
        return [self.serialize_request(row) for row in rows], total

    async def get_request_read(
        self,
        request_id: uuid.UUID,
        company_id: uuid.UUID,
    ) -> UserAccessRequestRead:
        row = await self._get_request(request_id, company_id)
        return self.serialize_request(row)

    async def approve_request(
        self,
        request_id: uuid.UUID,
        company_id: uuid.UUID,
        reviewer_id: uuid.UUID,
        data: UserAccessApproveRequest,
        *,
        allow_self_approval: bool = False,
        reviewer_branch_id: uuid.UUID | None = None,
        is_superuser: bool = False,
    ) -> tuple[UserAccessRequestRead, UserInvitation | None, str | None]:
        row = await self._get_request(request_id, company_id, for_update=True)
        self._require_review_scope(row, reviewer_branch_id, is_superuser)
        self._require_status(row, "pending")
        if row.requested_by == reviewer_id and not allow_self_approval:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="ผู้ส่งคำขอไม่สามารถอนุมัติคำขอของตนเองได้",
            )

        await self._get_active_branch(company_id, row.branch_id)
        role = await self._get_branch_assignable_role(company_id, data.approved_role_id)
        employee = await self._validate_employee(company_id, row.branch_id, row.employee_id)
        if row.requested_username:
            await self._ensure_username_available(company_id, row.requested_username)
        await self._ensure_no_duplicate_identity(
            company_id,
            username=row.requested_username,
            email=row.email,
            phone=row.phone,
            employee_code=row.employee_code,
            employee_id=row.employee_id,
            exclude_request_id=row.id,
        )

        now = self._now()
        row.status = "approved"
        row.approved_role_id = role.id
        row.reviewed_by = reviewer_id
        row.reviewed_at = now
        row.review_note = self._clean_text(data.review_note)
        self._audit(
            company_id,
            row.branch_id,
            reviewer_id,
            "system.user_access.approved",
            row.id,
            {
                "status": row.status,
                "requested_role_id": str(row.requested_role_id),
                "approved_role_id": str(role.id),
            },
        )
        invitation: UserInvitation | None = None
        plain_otp: str | None = None
        try:
            if row.requested_username and row.initial_password_hash:
                await self._activate_request_user(row, role, employee, reviewer_id, now)
            else:
                invitation, plain_otp = self._build_invitation(row, reviewer_id, role.id)
                self.db.add(invitation)
            await self.db.flush()
            invitation_id = invitation.id if invitation else None
            await self.db.commit()
        except IntegrityError as exc:
            await self.db.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Username or employee identity already exists",
            ) from exc
        refreshed = await self.get_request_read(row.id, company_id)
        saved_invitation = (
            await self.db.get(UserInvitation, invitation_id) if invitation_id else None
        )
        if invitation_id and saved_invitation is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Invitation not found",
            )
        return refreshed, saved_invitation, plain_otp

    async def reject_request(
        self,
        request_id: uuid.UUID,
        company_id: uuid.UUID,
        reviewer_id: uuid.UUID,
        reason: str,
        *,
        reviewer_branch_id: uuid.UUID | None = None,
        is_superuser: bool = False,
    ) -> UserAccessRequestRead:
        row = await self._get_request(request_id, company_id, for_update=True)
        self._require_review_scope(row, reviewer_branch_id, is_superuser)
        self._require_status(row, "pending")
        row.status = "rejected"
        row.reviewed_by = reviewer_id
        row.reviewed_at = self._now()
        row.review_note = reason.strip()
        row.initial_password_hash = None
        self._audit(
            company_id,
            row.branch_id,
            reviewer_id,
            "system.user_access.rejected",
            row.id,
            {"status": row.status, "reason": row.review_note},
        )
        await self.db.commit()
        return await self.get_request_read(row.id, company_id)

    async def cancel_request(
        self,
        request_id: uuid.UUID,
        company_id: uuid.UUID,
        branch_id: uuid.UUID,
        actor_id: uuid.UUID,
        brand_slug: str,
        reason: str | None,
    ) -> UserAccessRequestRead:
        row = await self._get_request(request_id, company_id, for_update=True)
        brand = await self._get_active_brand_for_branch(company_id, branch_id, brand_slug)
        if row.branch_id != branch_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Request not found")
        if row.brand_id != brand.id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Request not found")
        self._require_status(row, "pending")
        row.status = "cancelled"
        row.review_note = self._clean_text(reason)
        row.initial_password_hash = None
        self._audit(
            company_id,
            branch_id,
            actor_id,
            "system.user_access.cancelled",
            row.id,
            {"status": row.status, "reason": row.review_note},
        )
        await self.db.commit()
        return await self.get_request_read(row.id, company_id)

    async def resend_invitation(
        self,
        request_id: uuid.UUID,
        company_id: uuid.UUID,
        actor_id: uuid.UUID,
        *,
        reviewer_branch_id: uuid.UUID | None = None,
        is_superuser: bool = False,
    ) -> tuple[UserAccessRequestRead, UserInvitation, str]:
        row = await self._get_request(request_id, company_id, for_update=True)
        self._require_review_scope(row, reviewer_branch_id, is_superuser)
        self._require_status(row, "approved")
        await self._get_active_branch(company_id, row.branch_id)
        if row.approved_role_id is None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Approved role is missing")
        await self._get_branch_assignable_role(company_id, row.approved_role_id)

        now = self._now()
        active_invitations = (
            await self.db.scalars(
                select(UserInvitation)
                .where(
                    UserInvitation.access_request_id == row.id,
                    UserInvitation.used_at.is_(None),
                    UserInvitation.revoked_at.is_(None),
                )
                .with_for_update()
            )
        ).all()
        for invitation in active_invitations:
            invitation.revoked_at = now

        invitation, plain_otp = self._build_invitation(row, actor_id, row.approved_role_id)
        self.db.add(invitation)
        self._audit(
            company_id,
            row.branch_id,
            actor_id,
            "system.user_access.invitation_resent",
            row.id,
            {"revoked_invitations": len(active_invitations)},
        )
        await self.db.flush()
        invitation_id = invitation.id
        await self.db.commit()
        refreshed = await self.get_request_read(row.id, company_id)
        saved_invitation = await self.db.get(UserInvitation, invitation_id)
        if saved_invitation is None:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Invitation not found")
        return refreshed, saved_invitation, plain_otp

    async def accept_invitation(
        self,
        company_id: uuid.UUID,
        data: AcceptInvitationRequest,
    ) -> User:
        invitation = await self._find_invitation(company_id, data.invitation_id, data.otp_code)
        now = self._now()
        if invitation.expires_at <= now:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invitation expired")
        if not verify_password(data.otp_code.strip().upper(), invitation.otp_hash):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invitation not found")

        username = data.username.strip()
        await self._ensure_username_available(company_id, username)
        branch = await self._get_active_branch(company_id, invitation.branch_id)
        role = await self._get_role(company_id, invitation.role_id)

        request_row: UserAccessRequest | None = None
        employee: Employee | None = None
        if invitation.access_request_id is not None:
            request_row = await self._get_request(
                invitation.access_request_id,
                company_id,
                for_update=True,
            )
            self._require_status(request_row, "approved")
            if request_row.approved_role_id != invitation.role_id:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Invitation role mismatch")
            if not role.is_branch_assignable:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="บทบาทนี้ไม่เปิดให้สาขาใช้งานแล้ว กรุณาติดต่อแอดมิน",
                )
            employee = await self._validate_employee(company_id, branch.id, request_row.employee_id)
            await self._ensure_no_duplicate_identity(
                company_id,
                email=request_row.email,
                phone=request_row.phone,
                employee_code=request_row.employee_code,
                employee_id=request_row.employee_id,
                exclude_request_id=request_row.id,
            )

        user = User(
            company_id=company_id,
            username=username,
            email=self._normalize_email(invitation.email),
            phone=self._normalize_phone(invitation.phone),
            employee_code=request_row.employee_code if request_row else None,
            first_name=invitation.first_name,
            last_name=invitation.last_name,
            display_name=" ".join(
                part for part in [invitation.first_name or "", invitation.last_name or ""] if part
            )
            or None,
            hashed_password=hash_password(data.password),
            is_active=True,
        )
        self.db.add(user)

        try:
            await self.db.flush()
            context = await load_branch_business_context(
                self.db,
                company_id,
                branch.id,
            )
            assert context is not None
            if request_row is not None and request_row.brand_id != context.brand_id:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Invitation Brand context is no longer active for this Branch",
                )
            self.db.add(
                UserBranch(
                    user_id=user.id,
                    branch_id=branch.id,
                    role_id=role.id,
                    brand_id=context.brand_id,
                    business_type=context.business_type,
                    target_database=context.target_database,
                    is_default=True,
                )
            )
            if employee is not None:
                employee.user_id = user.id
                user.employee_code = employee.employee_code

            invitation.used_at = now
            invitation.created_user_id = user.id
            if request_row is not None:
                request_row.status = "activated"
                request_row.activated_user_id = user.id
                request_row.activated_at = now
                self._audit(
                    company_id,
                    branch.id,
                    user.id,
                    "system.user_access.activated",
                    request_row.id,
                    {"status": request_row.status, "user_id": str(user.id)},
                )
            else:
                self._audit(
                    company_id,
                    branch.id,
                    user.id,
                    "system.user.invitation_accepted",
                    user.id,
                    {"invitation_id": str(invitation.id)},
                )
            await self.db.commit()
        except IntegrityError as exc:
            await self.db.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="ข้อมูลบัญชีซ้ำกับผู้ใช้งานที่มีอยู่",
            ) from exc

        await self.db.refresh(user)
        return user

    async def _activate_request_user(
        self,
        row: UserAccessRequest,
        role: Role,
        employee: Employee | None,
        reviewer_id: uuid.UUID,
        now: datetime,
    ) -> User:
        if not row.requested_username or not row.initial_password_hash:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Requested credentials are incomplete",
            )
        user = User(
            company_id=row.company_id,
            username=row.requested_username,
            email=self._normalize_email(row.email),
            phone=self._normalize_phone(row.phone),
            employee_code=row.employee_code,
            first_name=row.first_name,
            last_name=row.last_name,
            display_name=" ".join(
                part for part in [row.first_name or "", row.last_name or ""] if part
            )
            or None,
            hashed_password=row.initial_password_hash,
            is_active=True,
        )
        self.db.add(user)
        await self.db.flush()
        context = await load_branch_business_context(
            self.db,
            row.company_id,
            row.branch_id,
        )
        assert context is not None
        if row.brand_id != context.brand_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Access request Brand context is no longer active for this Branch",
            )
        self.db.add(
            UserBranch(
                user_id=user.id,
                branch_id=row.branch_id,
                role_id=role.id,
                brand_id=context.brand_id,
                business_type=context.business_type,
                target_database=context.target_database,
                is_default=True,
            )
        )
        if employee is not None:
            employee.user_id = user.id
            user.employee_code = employee.employee_code

        row.status = "activated"
        row.activated_user_id = user.id
        row.activated_at = now
        row.initial_password_hash = None
        self._audit(
            row.company_id,
            row.branch_id,
            reviewer_id,
            "system.user_access.activated",
            row.id,
            {
                "status": row.status,
                "user_id": str(user.id),
                "activation_mode": "direct_credentials",
            },
        )
        return user

    def serialize_request(self, row: UserAccessRequest) -> UserAccessRequestRead:
        latest_invitation = max(row.invitations, key=lambda item: item.created_at, default=None)
        return UserAccessRequestRead(
            id=row.id,
            company_id=row.company_id,
            brand_id=row.brand_id,
            brand_slug=row.brand.slug if row.brand else None,
            brand_name=row.brand.name if row.brand else None,
            branch_id=row.branch_id,
            branch_code=row.branch.code,
            branch_name=row.branch.name,
            requested_role_id=row.requested_role_id,
            requested_role_name=row.requested_role.name,
            approved_role_id=row.approved_role_id,
            approved_role_name=row.approved_role.name if row.approved_role else None,
            employee_id=row.employee_id,
            employee_code=row.employee_code,
            requested_username=row.requested_username,
            first_name=row.first_name,
            last_name=row.last_name,
            email=row.email,
            phone=row.phone,
            request_note=row.request_note,
            status=row.status,
            requested_by=row.requested_by,
            requester_name=self._user_name(row.requester),
            requested_at=row.requested_at,
            reviewed_by=row.reviewed_by,
            reviewer_name=self._user_name(row.reviewer) if row.reviewer else None,
            reviewed_at=row.reviewed_at,
            review_note=row.review_note,
            activated_user_id=row.activated_user_id,
            activated_username=row.activated_user.username if row.activated_user else None,
            activated_at=row.activated_at,
            invitation_id=latest_invitation.id if latest_invitation else None,
            invitation_expires_at=latest_invitation.expires_at if latest_invitation else None,
            invitation_used_at=latest_invitation.used_at if latest_invitation else None,
            invitation_revoked_at=latest_invitation.revoked_at if latest_invitation else None,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    async def _get_request(
        self,
        request_id: uuid.UUID,
        company_id: uuid.UUID,
        *,
        for_update: bool = False,
    ) -> UserAccessRequest:
        statement = (
            select(UserAccessRequest)
            .where(
                UserAccessRequest.id == request_id,
                UserAccessRequest.company_id == company_id,
            )
            .options(*self._read_options())
            .execution_options(populate_existing=True)
        )
        if for_update:
            statement = statement.with_for_update()
        row = await self.db.scalar(statement)
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Request not found")
        return row

    async def _get_active_branch(self, company_id: uuid.UUID, branch_id: uuid.UUID) -> Branch:
        branch = await self.db.scalar(
            select(Branch).where(
                Branch.id == branch_id,
                Branch.company_id == company_id,
                Branch.deleted_at.is_(None),
                Branch.is_active.is_(True),
            )
        )
        if branch is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Active branch not found")
        return branch

    async def _get_active_brand(self, company_id: uuid.UUID, brand_slug: str) -> Brand:
        brand = await self.db.scalar(
            select(Brand).where(
                Brand.company_id == company_id,
                Brand.slug == brand_slug,
                Brand.business_type == RESTAURANT,
                Brand.is_active.is_(True),
            )
        )
        if brand is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Active brand not found")
        return brand

    async def _get_active_brand_for_branch(
        self,
        company_id: uuid.UUID,
        branch_id: uuid.UUID,
        brand_slug: str,
    ) -> Brand:
        brand = await self._get_active_brand(company_id, brand_slug)
        membership = await self.db.scalar(
            select(BrandBranch.id).where(
                BrandBranch.company_id == company_id,
                BrandBranch.brand_id == brand.id,
                BrandBranch.branch_id == branch_id,
                BrandBranch.is_active.is_(True),
            )
        )
        if membership is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Branch is not active for this brand",
            )
        return brand

    async def _ensure_user_branch(
        self,
        company_id: uuid.UUID,
        user_id: uuid.UUID,
        branch_id: uuid.UUID,
    ) -> None:
        assignment = await self.db.scalar(
            select(UserBranch.id)
            .join(User, User.id == UserBranch.user_id)
            .where(
                UserBranch.user_id == user_id,
                UserBranch.branch_id == branch_id,
                UserBranch.deleted_at.is_(None),
                User.company_id == company_id,
                User.deleted_at.is_(None),
                User.is_active.is_(True),
            )
        )
        if assignment is None:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Branch access denied")

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

    async def _get_branch_assignable_role(self, company_id: uuid.UUID, role_id: uuid.UUID) -> Role:
        role = await self._get_role(company_id, role_id)
        if not role.is_branch_assignable:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Role is not available for branch requests",
            )
        return role

    async def _validate_employee(
        self,
        company_id: uuid.UUID,
        branch_id: uuid.UUID,
        employee_id: uuid.UUID | None,
    ) -> Employee | None:
        if employee_id is None:
            return None
        employee = await self.db.scalar(
            select(Employee).where(
                Employee.id == employee_id,
                Employee.company_id == company_id,
                Employee.branch_id == branch_id,
                Employee.deleted_at.is_(None),
                Employee.is_active.is_(True),
            )
        )
        if employee is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Active employee not found")
        if employee.user_id is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Employee already has a user")
        return employee

    async def _ensure_no_duplicate_identity(
        self,
        company_id: uuid.UUID,
        *,
        username: str | None = None,
        email: str | None,
        phone: str | None,
        employee_code: str | None,
        employee_id: uuid.UUID | None,
        exclude_request_id: uuid.UUID | None = None,
    ) -> None:
        normalized_email = self._normalize_email(email)
        normalized_phone = self._normalize_phone(phone)
        normalized_employee_code = employee_code.strip() if employee_code else None

        user_filters = []
        if username:
            user_filters.append(func.lower(User.username) == username.strip().lower())
        if normalized_email:
            user_filters.append(func.lower(User.email) == normalized_email)
        if normalized_phone:
            user_filters.append(User.phone == normalized_phone)
        if normalized_employee_code:
            user_filters.append(func.lower(User.employee_code) == normalized_employee_code.lower())
        if user_filters:
            existing_user = await self.db.scalar(
                select(User.id).where(
                    User.company_id == company_id,
                    User.deleted_at.is_(None),
                    or_(*user_filters),
                )
            )
            if existing_user is not None:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="User identity already exists")

        request_filters = []
        if username:
            request_filters.append(
                func.lower(UserAccessRequest.requested_username) == username.strip().lower()
            )
        if normalized_email:
            request_filters.append(func.lower(UserAccessRequest.email) == normalized_email)
        if normalized_phone:
            request_filters.append(UserAccessRequest.phone == normalized_phone)
        if normalized_employee_code:
            request_filters.append(
                func.lower(UserAccessRequest.employee_code) == normalized_employee_code.lower()
            )
        if employee_id:
            request_filters.append(UserAccessRequest.employee_id == employee_id)
        if request_filters:
            statement = select(UserAccessRequest.id).where(
                UserAccessRequest.company_id == company_id,
                UserAccessRequest.status.in_(OPEN_REQUEST_STATUSES),
                or_(*request_filters),
            )
            if exclude_request_id:
                statement = statement.where(UserAccessRequest.id != exclude_request_id)
            existing_request = await self.db.scalar(statement)
            if existing_request is not None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="An open access request already exists for this employee",
                )

    async def _ensure_username_available(self, company_id: uuid.UUID, username: str) -> None:
        if not username:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Username is required")
        existing = await self.db.scalar(
            select(User.id).where(
                User.company_id == company_id,
                func.lower(User.username) == username.lower(),
                User.deleted_at.is_(None),
            )
        )
        if existing is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username already exists")

    async def _find_invitation(
        self,
        company_id: uuid.UUID,
        invitation_id: uuid.UUID | None,
        otp_code: str,
    ) -> UserInvitation:
        base_filters = (
            UserInvitation.company_id == company_id,
            UserInvitation.used_at.is_(None),
            UserInvitation.revoked_at.is_(None),
        )
        if invitation_id is not None:
            invitation = await self.db.scalar(
                select(UserInvitation)
                .where(UserInvitation.id == invitation_id, *base_filters)
                .with_for_update()
            )
            if invitation is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invitation not found")
            return invitation

        invitations = (
            await self.db.scalars(
                select(UserInvitation)
                .where(*base_filters)
                .order_by(UserInvitation.created_at.desc())
            )
        ).all()
        normalized_otp = otp_code.strip().upper()
        for invitation in invitations:
            if verify_password(normalized_otp, invitation.otp_hash):
                return invitation
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invitation not found")

    def _build_invitation(
        self,
        row: UserAccessRequest,
        inviter_id: uuid.UUID,
        role_id: uuid.UUID,
    ) -> tuple[UserInvitation, str]:
        plain_otp = secrets.token_urlsafe(6)[:8].upper()
        invitation = UserInvitation(
            company_id=row.company_id,
            branch_id=row.branch_id,
            role_id=role_id,
            invited_by=inviter_id,
            access_request_id=row.id,
            email=self._normalize_email(row.email),
            phone=self._normalize_phone(row.phone),
            otp_code=None,
            otp_hash=hash_password(plain_otp),
            first_name=row.first_name,
            last_name=row.last_name,
            expires_at=self._now() + timedelta(hours=72),
        )
        return invitation, plain_otp

    @staticmethod
    def _read_options() -> tuple:
        return (
            selectinload(UserAccessRequest.branch),
            selectinload(UserAccessRequest.brand),
            selectinload(UserAccessRequest.requested_role),
            selectinload(UserAccessRequest.approved_role),
            selectinload(UserAccessRequest.requester),
            selectinload(UserAccessRequest.reviewer),
            selectinload(UserAccessRequest.activated_user),
            selectinload(UserAccessRequest.invitations),
        )

    @staticmethod
    def _require_status(row: UserAccessRequest, expected: str) -> None:
        if row.status != expected:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Request status must be {expected}",
            )

    async def get_brand_for_central_access(
        self,
        company_id: uuid.UUID,
        brand_slug: str,
        branch_id: uuid.UUID | None,
        *,
        is_superuser: bool,
    ) -> Brand:
        brand = await self._get_active_brand(company_id, brand_slug)
        if not is_superuser and (branch_id is None or brand.central_branch_id != branch_id):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Brand center access denied")
        return brand

    async def get_brand_for_branch_access(
        self,
        company_id: uuid.UUID,
        branch_id: uuid.UUID,
        brand_slug: str,
    ) -> Brand:
        return await self._get_active_brand_for_branch(company_id, branch_id, brand_slug)

    async def ensure_request_review_access(
        self,
        request_id: uuid.UUID,
        company_id: uuid.UUID,
        branch_id: uuid.UUID | None,
        *,
        is_superuser: bool,
    ) -> None:
        row = await self._get_request(request_id, company_id)
        self._require_review_scope(row, branch_id, is_superuser)

    @staticmethod
    def _require_review_scope(
        row: UserAccessRequest,
        reviewer_branch_id: uuid.UUID | None,
        is_superuser: bool,
    ) -> None:
        if is_superuser:
            return
        if row.brand is None or reviewer_branch_id is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Request not found")
        if row.brand.central_branch_id != reviewer_branch_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Request not found")

    def _audit(
        self,
        company_id: uuid.UUID,
        branch_id: uuid.UUID,
        user_id: uuid.UUID,
        action: str,
        resource_id: uuid.UUID,
        new_value: dict,
    ) -> None:
        self.db.add(
            AuditLog(
                company_id=company_id,
                branch_id=branch_id,
                user_id=user_id,
                action=action,
                resource="UserAccessRequest",
                resource_id=str(resource_id),
                new_value=new_value,
            )
        )

    @staticmethod
    def _normalize_email(value: str | None) -> str | None:
        return value.strip().lower() if value and value.strip() else None

    @staticmethod
    def _normalize_phone(value: str | None) -> str | None:
        return value.strip() if value and value.strip() else None

    @staticmethod
    def _clean_text(value: str | None) -> str | None:
        return value.strip() if value and value.strip() else None

    @staticmethod
    def _user_name(user: User) -> str:
        return user.display_name or " ".join(
            part for part in [user.first_name or "", user.last_name or ""] if part
        ) or user.username

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)
