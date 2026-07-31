from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
import secrets
import uuid

from fastapi import HTTPException, status
from sqlalchemy import String, cast, distinct, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.dependencies import TokenData
from app.business_context import CanonicalBusinessContext
from app.models.audit import AuditLog
from app.models.auth import RefreshToken
from app.models.branch import Branch
from app.models.product import BranchProductReplacementRule, Product
from app.models.role import Permission, Role, role_permissions_table
from app.models.settings import BranchSettings, UserInvitation
from app.models.stock import StockLocation
from app.models.user import User, UserBranch
from app.services.business_context_service import load_branch_business_context
from app.schemas.role import PermissionRead
from app.schemas.product import BranchProductReplacementRuleCreate, BranchProductReplacementRuleRead
from app.schemas.user_mgmt import (
    AcceptInvitationRequest,
    AssignBranchRequest,
    BranchCreateFull,
    BranchDetailRead,
    BranchSettingsRead,
    BranchSettingsUpdate,
    BranchUpdateFull,
    ChangePasswordRequest,
    InviteUserRequest,
    RoleCreateFull,
    RoleDetailRead,
    RoleUpdateFull,
    UserBranchDetail,
    UserCreateFull,
    UserDetailRead,
    UserUpdateFull,
)
from app.utils.security import hash_password, verify_password

DEFAULT_RECEIPT_FOOTER = "ขอบคุณที่ใช้บริการ"

BRANCH_ROLE_FORBIDDEN_PERMISSIONS = {
    "system.company.edit",
    "system.branch.create",
    "system.branch.edit",
    "system.user.create",
    "system.user.edit",
    "system.user.delete",
    "system.user.approve",
    "system.role.create",
    "system.role.edit",
    "system.role.delete",
    "inventory.purchase.approve",
    "inventory.transfer.approve",
}


def forbidden_branch_role_permissions(permission_codes: list[str] | set[str]) -> list[str]:
    return sorted(BRANCH_ROLE_FORBIDDEN_PERMISSIONS.intersection(permission_codes))


class AdminService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_users(
        self,
        company_id: uuid.UUID,
        branch_id: uuid.UUID | None = None,
        is_active: bool | None = None,
        search: str | None = None,
        page: int = 1,
        limit: int = 20,
    ) -> tuple[list[User], int]:
        filters = [
            User.company_id == company_id,
            User.deleted_at.is_(None),
            UserBranch.deleted_at.is_(None),
            Branch.deleted_at.is_(None),
            Branch.company_id == company_id,
        ]
        if branch_id is not None:
            filters.append(UserBranch.branch_id == branch_id)
        if is_active is not None:
            filters.append(User.is_active.is_(is_active))
        if search:
            pattern = f"%{search.strip()}%"
            filters.append(
                or_(
                    User.username.ilike(pattern),
                    User.email.ilike(pattern),
                    User.first_name.ilike(pattern),
                    User.last_name.ilike(pattern),
                    User.display_name.ilike(pattern),
                )
            )

        total_statement = (
            select(func.count(distinct(User.id)))
            .select_from(User)
            .join(UserBranch, UserBranch.user_id == User.id)
            .join(Branch, Branch.id == UserBranch.branch_id)
            .where(*filters)
        )
        total = int((await self.db.scalar(total_statement)) or 0)

        statement = (
            select(User)
            .join(UserBranch, UserBranch.user_id == User.id)
            .join(Branch, Branch.id == UserBranch.branch_id)
            .where(*filters)
            .options(
                selectinload(User.user_branches).selectinload(UserBranch.branch),
                selectinload(User.user_branches).selectinload(UserBranch.role),
            )
            .order_by(User.created_at.desc())
            .offset((page - 1) * limit)
            .limit(limit)
        )
        users = (await self.db.execute(statement)).scalars().unique().all()
        return users, total

    async def get_user_detail(self, user_id: uuid.UUID, company_id: uuid.UUID) -> UserDetailRead:
        user = await self.db.scalar(
            select(User)
            .where(
                User.id == user_id,
                User.company_id == company_id,
                User.deleted_at.is_(None),
            )
            .options(
                selectinload(User.user_branches).selectinload(UserBranch.branch),
                selectinload(User.user_branches).selectinload(UserBranch.role),
            )
        )
        if user is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        return self._build_user_detail(user)

    async def create_user(
        self,
        company_id: uuid.UUID,
        creator_id: uuid.UUID,
        data: UserCreateFull,
    ) -> User:
        await self._ensure_username_available(company_id, data.username)
        await self._get_branch(company_id, data.branch_id)
        await self._get_role(company_id, data.role_id)
        context = await load_branch_business_context(self.db, company_id, data.branch_id)
        assert context is not None

        user = User(
            company_id=company_id,
            username=data.username,
            email=data.email,
            phone=data.phone,
            first_name=data.first_name,
            last_name=data.last_name,
            display_name=data.display_name,
            hashed_password=hash_password(data.password),
            is_active=True,
        )
        self.db.add(user)
        await self.db.flush()

        self.db.add(
            UserBranch(
                user_id=user.id,
                branch_id=data.branch_id,
                brand_id=context.brand_id,
                business_type=context.business_type,
                target_database=context.target_database,
                role_id=data.role_id,
                is_default=True,
            )
        )
        self._audit(company_id, creator_id, "system.user.create", "User", user.id)
        await self.db.commit()
        await self.db.refresh(user)
        return user

    async def update_user(
        self,
        user_id: uuid.UUID,
        company_id: uuid.UUID,
        data: UserUpdateFull,
    ) -> User:
        user = await self._get_user(company_id, user_id)
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(user, field, value)
        self._audit(company_id, None, "system.user.update", "User", user.id)
        await self.db.commit()
        await self.db.refresh(user)
        return user

    async def deactivate_user(
        self,
        user_id: uuid.UUID,
        company_id: uuid.UUID,
        actor_id: uuid.UUID,
    ) -> User:
        user = await self._get_user(company_id, user_id)
        user.is_active = False
        await self._revoke_refresh_tokens(user.id)
        self._audit(company_id, actor_id, "system.user.deactivate", "User", user.id)
        await self.db.commit()
        await self.db.refresh(user)
        return user

    async def assign_branch(
        self,
        user_id: uuid.UUID,
        company_id: uuid.UUID,
        data: AssignBranchRequest,
    ) -> UserBranch:
        await self._get_user(company_id, user_id)
        await self._get_branch(company_id, data.branch_id)
        await self._get_role(company_id, data.role_id)
        context = await load_branch_business_context(self.db, company_id, data.branch_id)
        assert context is not None

        existing = await self.db.scalar(
            select(UserBranch)
            .join(Branch, Branch.id == UserBranch.branch_id)
            .where(
                UserBranch.user_id == user_id,
                UserBranch.branch_id == data.branch_id,
                Branch.company_id == company_id,
            )
        )
        if existing is not None and existing.deleted_at is None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Branch already assigned")

        if data.is_default:
            await self._unset_default_branches(user_id)

        if existing is not None:
            existing.deleted_at = None
            existing.role_id = data.role_id
            existing.brand_id = context.brand_id
            existing.business_type = context.business_type
            existing.target_database = context.target_database
            existing.is_default = data.is_default
            assignment = existing
        else:
            assignment = UserBranch(
                user_id=user_id,
                branch_id=data.branch_id,
                brand_id=context.brand_id,
                business_type=context.business_type,
                target_database=context.target_database,
                role_id=data.role_id,
                is_default=data.is_default,
            )
            self.db.add(assignment)

        self._audit(company_id, None, "system.user.branch_assigned", "User", user_id)
        await self.db.commit()
        await self.db.refresh(assignment)
        return assignment

    async def remove_branch(
        self,
        user_id: uuid.UUID,
        company_id: uuid.UUID,
        data: uuid.UUID | Branch | object,
    ) -> None:
        branch_id = data if isinstance(data, uuid.UUID) else getattr(data, "branch_id")
        assignment = await self.db.scalar(
            select(UserBranch)
            .join(Branch, Branch.id == UserBranch.branch_id)
            .where(
                UserBranch.user_id == user_id,
                UserBranch.branch_id == branch_id,
                UserBranch.deleted_at.is_(None),
                Branch.company_id == company_id,
            )
        )
        if assignment is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Branch assignment not found")

        active_assignments = (
            await self.db.scalars(
                select(UserBranch)
                .join(Branch, Branch.id == UserBranch.branch_id)
                .where(
                    UserBranch.user_id == user_id,
                    UserBranch.deleted_at.is_(None),
                    Branch.company_id == company_id,
                )
                .order_by(UserBranch.created_at.asc())
            )
        ).all()
        if len(active_assignments) <= 1:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot remove last branch")

        assignment.deleted_at = self._now()
        was_default = assignment.is_default
        assignment.is_default = False

        if was_default:
            next_assignment = next(item for item in active_assignments if item.id != assignment.id)
            next_assignment.is_default = True

        self._audit(company_id, None, "system.user.branch_removed", "User", user_id)
        await self.db.commit()

    async def change_user_password(
        self,
        user_id: uuid.UUID,
        company_id: uuid.UUID,
        actor_id: uuid.UUID,
        data: ChangePasswordRequest,
    ) -> None:
        user = await self._get_user(company_id, user_id)
        user.hashed_password = hash_password(data.new_password)
        user.password_changed_at = self._now()
        await self._revoke_refresh_tokens(user.id)
        self._audit(company_id, actor_id, "system.user.password_changed", "User", user.id)
        await self.db.commit()

    async def list_roles(self, company_id: uuid.UUID) -> list[RoleDetailRead]:
        roles = (
            await self.db.scalars(
                select(Role)
                .where(Role.company_id == company_id, Role.deleted_at.is_(None))
                .options(selectinload(Role.permissions))
                .order_by(Role.is_system.desc(), Role.name.asc())
            )
        ).all()
        counts = await self._role_user_counts(company_id)
        return [self._build_role_detail(role, counts.get(role.id, 0)) for role in roles]

    async def create_role(self, company_id: uuid.UUID, data: RoleCreateFull) -> Role:
        existing = await self.db.scalar(
            select(Role).where(
                Role.company_id == company_id,
                func.lower(Role.name) == data.name.lower(),
                Role.deleted_at.is_(None),
            )
        )
        if existing is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Role name already exists")

        permissions = await self._get_permissions(data.permission_ids)
        self._validate_branch_assignable_role(data.is_branch_assignable, permissions)
        role = Role(
            company_id=company_id,
            name=data.name,
            description=data.description,
            is_branch_assignable=data.is_branch_assignable,
        )
        role.permissions = permissions
        self.db.add(role)
        await self.db.flush()
        self._audit(company_id, None, "system.role.create", "Role", role.id)
        await self.db.commit()
        await self.db.refresh(role)
        return role

    async def update_role(
        self,
        role_id: uuid.UUID,
        company_id: uuid.UUID,
        data: RoleUpdateFull,
    ) -> Role:
        role = await self._get_role(company_id, role_id)
        if role.is_system:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="System role cannot be modified")

        if data.name is not None:
            name_conflict = await self.db.scalar(
                select(Role).where(
                    Role.company_id == company_id,
                    func.lower(Role.name) == data.name.lower(),
                    Role.id != role_id,
                    Role.deleted_at.is_(None),
                )
            )
            if name_conflict is not None:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Role name already exists")
            role.name = data.name
        if data.description is not None:
            role.description = data.description
        next_permissions = role.permissions
        if data.permission_ids is not None:
            next_permissions = await self._get_permissions(data.permission_ids)
        next_branch_assignable = (
            data.is_branch_assignable
            if data.is_branch_assignable is not None
            else role.is_branch_assignable
        )
        self._validate_branch_assignable_role(next_branch_assignable, next_permissions)
        role.permissions = next_permissions
        role.is_branch_assignable = next_branch_assignable

        self._audit(company_id, None, "system.role.update", "Role", role.id)
        await self.db.commit()
        await self.db.refresh(role)
        return role

    async def delete_role(self, role_id: uuid.UUID, company_id: uuid.UUID) -> None:
        role = await self._get_role(company_id, role_id)
        if role.is_system:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="System role cannot be deleted")

        in_use = await self.db.scalar(
            select(func.count(UserBranch.id)).where(
                UserBranch.role_id == role_id,
                UserBranch.deleted_at.is_(None),
            )
        )
        if in_use:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Role is in use")

        role.deleted_at = self._now()
        self._audit(company_id, None, "system.role.delete", "Role", role.id)
        await self.db.commit()

    async def list_branches(
        self,
        company_id: uuid.UUID,
        current_user: TokenData,
    ) -> list[BranchDetailRead]:
        statement = (
            select(Branch)
            .where(Branch.company_id == company_id, Branch.deleted_at.is_(None))
            .order_by(Branch.sort_order.asc(), Branch.name.asc())
        )
        if "*" not in current_user.permissions:
            statement = statement.join(
                UserBranch,
                (UserBranch.branch_id == Branch.id)
                & (UserBranch.user_id == current_user.user_id)
                & (UserBranch.deleted_at.is_(None)),
            )

        branches = (await self.db.execute(statement)).scalars().unique().all()
        counts = await self._branch_user_counts(company_id)
        settings_map = await self._branch_settings_map([branch.id for branch in branches])
        context_map = {
            branch.id: await load_branch_business_context(
                self.db,
                company_id,
                branch.id,
                required=False,
            )
            for branch in branches
        }
        return [
            self._build_branch_detail(
                branch,
                counts.get(branch.id, 0),
                settings_map.get(branch.id),
                context_map.get(branch.id),
            )
            for branch in branches
        ]

    async def create_branch(self, company_id: uuid.UUID, data: BranchCreateFull) -> Branch:
        existing = await self.db.scalar(
            select(Branch).where(
                Branch.company_id == company_id,
                func.lower(Branch.code) == data.code.lower(),
                Branch.deleted_at.is_(None),
            )
        )
        if existing is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Branch code already exists")

        branch = Branch(
            company_id=company_id,
            code=data.code,
            name=data.name,
            name_en=data.name_en,
            address=data.address,
            landmark=data.landmark,
            phone=data.phone,
            email=data.email,
            latitude=data.latitude,
            longitude=data.longitude,
            google_maps_url=data.google_maps_url,
            is_warehouse=data.is_warehouse,
            sort_order=data.sort_order,
            is_active=True,
        )
        self.db.add(branch)
        await self.db.flush()

        self.db.add(
            BranchSettings(
                company_id=company_id,
                branch_id=branch.id,
                pos_receipt_footer=DEFAULT_RECEIPT_FOOTER,
            )
        )
        self.db.add(
            StockLocation(
                company_id=company_id,
                branch_id=branch.id,
                code="MAIN",
                name="คลังหลัก",
                is_active=True,
            )
        )
        self._audit(company_id, None, "system.branch.create", "Branch", branch.id)
        await self.db.commit()
        await self.db.refresh(branch)
        return branch

    async def update_branch(
        self,
        branch_id: uuid.UUID,
        company_id: uuid.UUID,
        data: BranchUpdateFull,
    ) -> Branch:
        branch = await self._get_branch(company_id, branch_id)
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(branch, field, value)
        self._audit(company_id, None, "system.branch.update", "Branch", branch.id)
        await self.db.commit()
        await self.db.refresh(branch)
        return branch

    async def get_branch_detail(self, branch_id: uuid.UUID, company_id: uuid.UUID) -> BranchDetailRead:
        branch = await self._get_branch(company_id, branch_id)
        settings = await self.get_branch_settings(branch_id, company_id)
        counts = await self._branch_user_counts(company_id)
        context = await load_branch_business_context(
            self.db,
            company_id,
            branch_id,
            required=False,
        )
        return self._build_branch_detail(branch, counts.get(branch.id, 0), settings, context)

    async def get_branch_settings(self, branch_id: uuid.UUID, company_id: uuid.UUID) -> BranchSettings:
        await self._get_branch(company_id, branch_id)
        settings = await self.db.scalar(
            select(BranchSettings).where(
                BranchSettings.company_id == company_id,
                BranchSettings.branch_id == branch_id,
            )
        )
        if settings is None:
            settings = BranchSettings(
                company_id=company_id,
                branch_id=branch_id,
                pos_receipt_footer=DEFAULT_RECEIPT_FOOTER,
            )
            self.db.add(settings)
            await self.db.commit()
            await self.db.refresh(settings)
        return settings

    async def update_branch_settings(
        self,
        branch_id: uuid.UUID,
        company_id: uuid.UUID,
        data: BranchSettingsUpdate,
    ) -> BranchSettings:
        settings = await self.get_branch_settings(branch_id, company_id)
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(settings, field, value)
        self._audit(company_id, None, "system.branch.settings_updated", "Branch", branch_id)
        await self.db.commit()
        await self.db.refresh(settings)
        return settings

    async def list_branch_replacement_rules(
        self,
        branch_id: uuid.UUID,
        company_id: uuid.UUID,
    ) -> list[BranchProductReplacementRuleRead]:
        await self._get_branch(company_id, branch_id)
        rows = (
            await self.db.scalars(
                select(BranchProductReplacementRule)
                .where(
                    BranchProductReplacementRule.company_id == company_id,
                    BranchProductReplacementRule.branch_id == branch_id,
                )
                .options(
                    selectinload(BranchProductReplacementRule.source_product),
                    selectinload(BranchProductReplacementRule.replacement_product),
                )
                .order_by(BranchProductReplacementRule.created_at.desc())
            )
        ).all()
        return [self.serialize_branch_replacement_rule(item) for item in rows]

    async def upsert_branch_replacement_rule(
        self,
        branch_id: uuid.UUID,
        company_id: uuid.UUID,
        actor_id: uuid.UUID,
        data: BranchProductReplacementRuleCreate,
    ) -> BranchProductReplacementRule:
        await self._get_branch(company_id, branch_id)
        source_product = await self._get_product(company_id, data.source_product_id)
        replacement_product = await self._get_product(company_id, data.replacement_product_id)
        existing = await self.db.scalar(
            select(BranchProductReplacementRule).where(
                BranchProductReplacementRule.company_id == company_id,
                BranchProductReplacementRule.branch_id == branch_id,
                BranchProductReplacementRule.source_product_id == data.source_product_id,
            )
        )
        if existing is None:
            existing = BranchProductReplacementRule(
                company_id=company_id,
                branch_id=branch_id,
                source_product_id=source_product.id,
                replacement_product_id=replacement_product.id,
            )
            self.db.add(existing)
        else:
            existing.replacement_product_id = replacement_product.id
        self._audit(company_id, actor_id, "system.branch.replacement_rule_upsert", "Branch", branch_id)
        await self.db.commit()
        await self.db.refresh(existing)
        return existing

    async def delete_branch_replacement_rule(
        self,
        branch_id: uuid.UUID,
        company_id: uuid.UUID,
        actor_id: uuid.UUID,
        source_product_id: uuid.UUID,
    ) -> None:
        await self._get_branch(company_id, branch_id)
        rule = await self.db.scalar(
            select(BranchProductReplacementRule).where(
                BranchProductReplacementRule.company_id == company_id,
                BranchProductReplacementRule.branch_id == branch_id,
                BranchProductReplacementRule.source_product_id == source_product_id,
            )
        )
        if rule is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Replacement rule not found")
        await self.db.delete(rule)
        self._audit(company_id, actor_id, "system.branch.replacement_rule_delete", "Branch", branch_id)
        await self.db.commit()

    def serialize_branch_replacement_rule(
        self,
        rule: BranchProductReplacementRule,
    ) -> BranchProductReplacementRuleRead:
        return BranchProductReplacementRuleRead(
            id=rule.id,
            branch_id=rule.branch_id,
            source_product_id=rule.source_product_id,
            source_product_name=rule.source_product.name if rule.source_product else "-",
            replacement_product_id=rule.replacement_product_id,
            replacement_product_name=rule.replacement_product.name if rule.replacement_product else "-",
            created_at=rule.created_at,
        )

    async def create_invitation(
        self,
        company_id: uuid.UUID,
        inviter_id: uuid.UUID,
        data: InviteUserRequest,
    ) -> tuple[UserInvitation, str]:
        # FIX S3-D-verify: allow branch-role invitations without contact details because the acceptance flow uses the OTP directly
        await self._get_branch(company_id, data.branch_id)
        await self._get_role(company_id, data.role_id)
        await load_branch_business_context(self.db, company_id, data.branch_id)

        plain_otp = secrets.token_urlsafe(6)[:8].upper()
        invitation = UserInvitation(
            company_id=company_id,
            branch_id=data.branch_id,
            role_id=data.role_id,
            invited_by=inviter_id,
            email=data.email,
            phone=data.phone,
            otp_code=None,
            otp_hash=hash_password(plain_otp),
            first_name=data.first_name,
            last_name=data.last_name,
            expires_at=self._now() + timedelta(hours=72),
        )
        self.db.add(invitation)
        await self.db.flush()
        self._audit(company_id, inviter_id, "system.user.invited", "UserInvitation", invitation.id)
        await self.db.commit()
        await self.db.refresh(invitation)
        return invitation, plain_otp

    async def accept_invitation(
        self,
        otp_code: str,
        company_id: uuid.UUID,
        data: AcceptInvitationRequest,
    ) -> User:
        await self._ensure_username_available(company_id, data.username)
        invitations = (
            await self.db.scalars(
                select(UserInvitation)
                .where(
                    UserInvitation.company_id == company_id,
                    UserInvitation.used_at.is_(None),
                    UserInvitation.revoked_at.is_(None),
                )
                .order_by(UserInvitation.created_at.desc())
            )
        ).all()
        now = self._now()
        matched: UserInvitation | None = None
        expired_match = False
        for invitation in invitations:
            if verify_password(otp_code.upper(), invitation.otp_hash):
                if invitation.expires_at <= now:
                    expired_match = True
                    break
                matched = invitation
                break

        if expired_match:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invitation expired")
        if matched is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invitation not found")

        user = User(
            company_id=company_id,
            username=data.username,
            email=matched.email,
            phone=matched.phone,
            first_name=matched.first_name,
            last_name=matched.last_name,
            display_name=" ".join(
                part for part in [matched.first_name or "", matched.last_name or ""] if part
            )
            or None,
            hashed_password=hash_password(data.password),
            is_active=True,
        )
        self.db.add(user)
        await self.db.flush()
        context = await load_branch_business_context(
            self.db,
            company_id,
            matched.branch_id,
        )
        assert context is not None
        self.db.add(
            UserBranch(
                user_id=user.id,
                branch_id=matched.branch_id,
                brand_id=context.brand_id,
                business_type=context.business_type,
                target_database=context.target_database,
                role_id=matched.role_id,
                is_default=True,
            )
        )
        matched.used_at = now
        matched.created_user_id = user.id
        self._audit(company_id, user.id, "system.user.invitation_accepted", "User", user.id)
        await self.db.commit()
        await self.db.refresh(user)
        return user

    async def serialize_users(self, users: list[User]) -> list[UserDetailRead]:
        return [self._build_user_detail(user) for user in users]

    async def get_role_detail(self, role_id: uuid.UUID, company_id: uuid.UUID) -> RoleDetailRead:
        role = await self.db.scalar(
            select(Role)
            .where(Role.id == role_id, Role.company_id == company_id, Role.deleted_at.is_(None))
            .options(selectinload(Role.permissions))
        )
        if role is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found")
        counts = await self._role_user_counts(company_id)
        return self._build_role_detail(role, counts.get(role.id, 0))

    async def can_access_branch(self, company_id: uuid.UUID, user_id: uuid.UUID, branch_id: uuid.UUID) -> bool:
        assignment = await self.db.scalar(
            select(UserBranch.id)
            .join(Branch, Branch.id == UserBranch.branch_id)
            .where(
                UserBranch.user_id == user_id,
                UserBranch.branch_id == branch_id,
                UserBranch.deleted_at.is_(None),
                Branch.company_id == company_id,
                Branch.deleted_at.is_(None),
            )
        )
        return assignment is not None

    def serialize_branch_settings(self, settings: BranchSettings) -> BranchSettingsRead:
        return BranchSettingsRead.model_validate(settings)

    def _build_user_detail(self, user: User) -> UserDetailRead:
        assignments = sorted(
            [
                assignment
                for assignment in user.user_branches
                if assignment.deleted_at is None
                and assignment.branch is not None
                and assignment.branch.deleted_at is None
                and assignment.role is not None
                and assignment.role.deleted_at is None
            ],
            key=lambda item: (not item.is_default, item.branch.name.lower()),
        )
        branches = [
            UserBranchDetail(
                branch_id=assignment.branch_id,
                branch_name=assignment.branch.name,
                branch_code=assignment.branch.code,
                brand_id=assignment.brand_id,
                business_type=assignment.business_type,
                target_database=assignment.target_database,
                role_id=assignment.role_id,
                role_name=assignment.role.name,
                is_default=assignment.is_default,
            )
            for assignment in assignments
        ]
        return UserDetailRead(
            id=user.id,
            company_id=user.company_id,
            username=user.username,
            email=user.email,
            phone=user.phone,
            first_name=user.first_name,
            last_name=user.last_name,
            display_name=user.display_name,
            is_active=user.is_active,
            is_superuser=user.is_superuser,
            last_login_at=user.last_login_at,
            created_at=user.created_at,
            branches=branches,
        )

    def _build_role_detail(self, role: Role, user_count: int) -> RoleDetailRead:
        permissions = sorted(role.permissions, key=lambda item: (item.module, item.code))
        return RoleDetailRead(
            id=role.id,
            company_id=role.company_id,
            name=role.name,
            description=role.description,
            is_system=role.is_system,
            is_branch_assignable=role.is_branch_assignable,
            created_at=role.created_at,
            permissions=[PermissionRead.model_validate(permission) for permission in permissions],
            user_count=user_count,
        )

    def _build_branch_detail(
        self,
        branch: Branch,
        user_count: int,
        settings: BranchSettings | None,
        context: CanonicalBusinessContext | None,
    ) -> BranchDetailRead:
        return BranchDetailRead(
            id=branch.id,
            company_id=branch.company_id,
            brand_id=context.brand_id if context else None,
            business_type=context.business_type if context else None,
            target_database=context.target_database if context else None,
            code=branch.code,
            name=branch.name,
            name_en=branch.name_en,
            address=branch.address,
            landmark=branch.landmark,
            phone=branch.phone,
            email=branch.email,
            latitude=float(branch.latitude) if branch.latitude is not None else None,
            longitude=float(branch.longitude) if branch.longitude is not None else None,
            google_maps_url=branch.google_maps_url,
            is_warehouse=branch.is_warehouse,
            is_active=branch.is_active,
            sort_order=branch.sort_order,
            created_at=branch.created_at,
            user_count=user_count,
            settings=BranchSettingsRead.model_validate(settings) if settings else None,
        )

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

    async def _get_branch(self, company_id: uuid.UUID, branch_id: uuid.UUID) -> Branch:
        branch = await self.db.scalar(
            select(Branch).where(
                Branch.id == branch_id,
                Branch.company_id == company_id,
                Branch.deleted_at.is_(None),
            )
        )
        if branch is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Branch not found")
        return branch

    async def _get_role(self, company_id: uuid.UUID, role_id: uuid.UUID) -> Role:
        role = await self.db.scalar(
            select(Role)
            .where(Role.id == role_id, Role.company_id == company_id, Role.deleted_at.is_(None))
            .options(selectinload(Role.permissions))
        )
        if role is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found")
        return role

    async def _get_product(self, company_id: uuid.UUID, product_id: uuid.UUID) -> Product:
        product = await self.db.scalar(
            select(Product).where(
                Product.id == product_id,
                Product.company_id == company_id,
                Product.deleted_at.is_(None),
            )
        )
        if product is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
        return product

    async def _get_permissions(self, permission_ids: list[uuid.UUID]) -> list[Permission]:
        if not permission_ids:
            return []
        permissions = (
            await self.db.scalars(
                select(Permission).where(Permission.id.in_(permission_ids)).order_by(Permission.code.asc())
            )
        ).all()
        if len(permissions) != len(set(permission_ids)):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Permission not found")
        return permissions

    @staticmethod
    def _validate_branch_assignable_role(
        is_branch_assignable: bool,
        permissions: list[Permission],
    ) -> None:
        if not is_branch_assignable:
            return
        forbidden = forbidden_branch_role_permissions({item.code for item in permissions})
        if forbidden:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Branch-assignable role contains restricted permissions: {', '.join(forbidden)}",
            )

    async def _ensure_username_available(self, company_id: uuid.UUID, username: str) -> None:
        existing = await self.db.scalar(
            select(User).where(
                User.company_id == company_id,
                func.lower(User.username) == username.lower(),
                User.deleted_at.is_(None),
            )
        )
        if existing is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username already exists")

    async def _revoke_refresh_tokens(self, user_id: uuid.UUID) -> None:
        tokens = (
            await self.db.scalars(
                select(RefreshToken).where(
                    RefreshToken.user_id == user_id,
                    RefreshToken.revoked_at.is_(None),
                )
            )
        ).all()
        now = self._now()
        for token in tokens:
            token.revoked_at = now

    async def _unset_default_branches(self, user_id: uuid.UUID) -> None:
        assignments = (
            await self.db.scalars(
                select(UserBranch).where(
                    UserBranch.user_id == user_id,
                    UserBranch.deleted_at.is_(None),
                    UserBranch.is_default.is_(True),
                )
            )
        ).all()
        for assignment in assignments:
            assignment.is_default = False

    async def _role_user_counts(self, company_id: uuid.UUID) -> dict[uuid.UUID, int]:
        rows = await self.db.execute(
            select(UserBranch.role_id, func.count(distinct(UserBranch.user_id)))
            .join(User, User.id == UserBranch.user_id)
            .where(
                User.company_id == company_id,
                User.deleted_at.is_(None),
                UserBranch.deleted_at.is_(None),
            )
            .group_by(UserBranch.role_id)
        )
        return {role_id: int(count) for role_id, count in rows.all()}

    async def _branch_user_counts(self, company_id: uuid.UUID) -> dict[uuid.UUID, int]:
        rows = await self.db.execute(
            select(UserBranch.branch_id, func.count(distinct(UserBranch.user_id)))
            .join(User, User.id == UserBranch.user_id)
            .where(
                User.company_id == company_id,
                User.deleted_at.is_(None),
                UserBranch.deleted_at.is_(None),
            )
            .group_by(UserBranch.branch_id)
        )
        return {branch_id: int(count) for branch_id, count in rows.all()}

    async def _branch_settings_map(
        self,
        branch_ids: list[uuid.UUID],
    ) -> dict[uuid.UUID, BranchSettings]:
        if not branch_ids:
            return {}
        settings = (
            await self.db.scalars(
                select(BranchSettings).where(BranchSettings.branch_id.in_(branch_ids))
            )
        ).all()
        return {item.branch_id: item for item in settings}

    def _audit(
        self,
        company_id: uuid.UUID,
        user_id: uuid.UUID | None,
        action: str,
        resource: str,
        resource_id: uuid.UUID | None,
    ) -> None:
        self.db.add(
            AuditLog(
                company_id=company_id,
                user_id=user_id,
                action=action,
                resource=resource,
                resource_id=str(resource_id) if resource_id else None,
            )
        )

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)
