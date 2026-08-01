from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.audit import AuditLog
from app.models.auth import RefreshToken
from app.models.company import Company
from app.models.role import Role
from app.models.staff_assignment import StaffRoleAssignment
from app.models.user import User, UserBranch
from app.services.business_context_service import resolve_user_branch_context
from app.services.platform_reference_projection import enqueue_reference_event
from app.business_context import CanonicalBusinessContext
from app.services.staff_scope_policy import assignment_applies_to_context, normalized_station_key
from app.utils.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    verify_password,
)


class AuthService:
    def __init__(self, db: AsyncSession, *, emit_reference_events: bool = False):
        self.db = db
        self.emit_reference_events = emit_reference_events

    async def authenticate_user(
        self,
        company_id: uuid.UUID,
        username: str,
        password: str,
    ) -> User:
        statement = (
            select(User)
            .join(Company, Company.id == User.company_id)
            .where(
                User.company_id == company_id,
                User.username == username,
                User.deleted_at.is_(None),
                User.is_active.is_(True),
                Company.is_active.is_(True),
            )
        )
        user = await self.db.scalar(statement)
        if user is None or not verify_password(password, user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid username or password",
            )

        user.last_login_at = datetime.now(timezone.utc)
        await self.db.flush()
        if self.emit_reference_events:
            await enqueue_reference_event(
                self.db,
                aggregate_type="user",
                aggregate_id=user.id,
                company_id=user.company_id,
                payload={"source": "auth.login"},
            )
        return user

    async def get_user_permissions(
        self,
        user: User,
        branch_id: uuid.UUID | None,
        station_key: str | None = None,
    ) -> tuple[
        list[str],
        uuid.UUID | None,
        CanonicalBusinessContext | None,
        str | None,
        list[uuid.UUID],
        list[str],
    ]:
        resolved_branch_id = branch_id
        if resolved_branch_id is None:
            default_branch = await self.db.scalar(
                select(UserBranch.branch_id).where(
                    UserBranch.user_id == user.id,
                    UserBranch.is_default.is_(True),
                    UserBranch.deleted_at.is_(None),
                )
            )
            resolved_branch_id = default_branch

        if resolved_branch_id is None:
            context = None
        else:
            context = await resolve_user_branch_context(
                self.db,
                user,
                resolved_branch_id,
                station_key=station_key,
            )

        if user.is_superuser:
            return ["*"], resolved_branch_id, context, None, [], ["company"]

        permission_codes: set[str] = set()
        if resolved_branch_id is not None:
            legacy_role = await self.db.scalar(
                select(Role)
                .join(UserBranch, UserBranch.role_id == Role.id)
                .where(
                    UserBranch.user_id == user.id,
                    UserBranch.branch_id == resolved_branch_id,
                    UserBranch.deleted_at.is_(None),
                    Role.deleted_at.is_(None),
                )
                .options(selectinload(Role.permissions))
            )
            if legacy_role is not None and "branch" in legacy_role.allowed_scope_types:
                permission_codes.update(
                    permission.code for permission in legacy_role.permissions
                )

        scoped_assignments = (
            await self.db.scalars(
                select(StaffRoleAssignment)
                .where(
                    StaffRoleAssignment.company_id == user.company_id,
                    StaffRoleAssignment.user_id == user.id,
                    StaffRoleAssignment.revoked_at.is_(None),
                )
                .options(selectinload(StaffRoleAssignment.role).selectinload(Role.permissions))
            )
        ).all()
        applicable: list[StaffRoleAssignment] = []
        for assignment in scoped_assignments:
            if assignment.scope_type not in assignment.role.allowed_scope_types:
                continue
            if context is None:
                applies = assignment.scope_type == "company"
            else:
                applies = assignment_applies_to_context(assignment, context, station_key)
            if not applies:
                continue
            applicable.append(assignment)
            permission_codes.update(permission.code for permission in assignment.role.permissions)

        canonical_station = next(
            (
                assignment.station_key
                for assignment in applicable
                if assignment.scope_type == "station"
                and normalized_station_key(assignment.station_key)
                == normalized_station_key(station_key)
            ),
            None,
        )
        return (
            sorted(permission_codes),
            resolved_branch_id,
            context,
            canonical_station,
            [assignment.id for assignment in applicable],
            sorted({assignment.scope_type for assignment in applicable}),
        )

    async def create_session(
        self,
        user: User,
        branch_id: uuid.UUID | None,
        ip_address: str | None,
        user_agent: str | None,
        station_key: str | None = None,
    ) -> tuple[str, str]:
        company = await self.db.get(Company, user.company_id)
        if company is None or not company.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Company is inactive or no longer exists",
            )
        (
            permissions,
            resolved_branch_id,
            context,
            resolved_station_key,
            assignment_ids,
            scope_types,
        ) = await self.get_user_permissions(user, branch_id, station_key)
        access_token = create_access_token(
            subject=str(user.id),
            company_id=str(user.company_id),
            branch_id=str(resolved_branch_id) if resolved_branch_id else None,
            permissions=permissions,
            brand_id=str(context.brand_id) if context else None,
            business_type=context.business_type if context else None,
            target_database=context.target_database if context else None,
            station_key=resolved_station_key,
            assignment_ids=[str(value) for value in assignment_ids],
            scope_types=scope_types,
            company_credential_version=company.credential_version,
        )
        refresh_token = create_refresh_token(
            subject=str(user.id),
            company_id=str(user.company_id),
            branch_id=str(resolved_branch_id) if resolved_branch_id else None,
            station_key=resolved_station_key,
            company_credential_version=company.credential_version,
        )
        expires_at = self._extract_expiration(refresh_token)
        self.db.add(
            RefreshToken(
                user_id=user.id,
                company_id=user.company_id,
                token_hash=self._hash_token(refresh_token),
                expires_at=expires_at,
                ip_address=ip_address,
                user_agent=user_agent,
            )
        )
        self.db.add(
            AuditLog(
                company_id=user.company_id,
                branch_id=resolved_branch_id,
                user_id=user.id,
                action="user.login",
                resource="User",
                resource_id=str(user.id),
                ip_address=ip_address,
                user_agent=user_agent,
            )
        )
        await self.db.commit()
        return access_token, refresh_token

    async def refresh_session(
        self,
        raw_refresh_token: str,
        ip_address: str | None,
    ) -> tuple[str, str]:
        payload = decode_token(raw_refresh_token)
        if payload.get("type") != "refresh":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token type",
            )

        token_hash = self._hash_token(raw_refresh_token)
        refresh_record = await self.db.scalar(
            select(RefreshToken).where(RefreshToken.token_hash == token_hash)
        )
        now = datetime.now(timezone.utc)
        if (
            refresh_record is None
            or refresh_record.revoked_at is not None
            or refresh_record.expires_at <= now
        ):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Refresh token is invalid",
            )

        row = (
            await self.db.execute(
                select(User, Company)
                .join(Company, Company.id == User.company_id)
                .where(
                    User.id == refresh_record.user_id,
                    User.deleted_at.is_(None),
                    User.is_active.is_(True),
                    Company.is_active.is_(True),
                )
            )
        ).one_or_none()
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found",
            )
        user, company = row
        if int(payload.get("company_credential_version", 1)) != company.credential_version:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Refresh token has been revoked",
            )

        refresh_record.revoked_at = now
        refresh_branch_id = (
            uuid.UUID(payload["branch_id"]) if payload.get("branch_id") else None
        )
        (
            permissions,
            resolved_branch_id,
            context,
            resolved_station_key,
            assignment_ids,
            scope_types,
        ) = await self.get_user_permissions(
            user,
            refresh_branch_id,
            payload.get("station_key"),
        )
        access_token = create_access_token(
            subject=str(user.id),
            company_id=str(user.company_id),
            branch_id=str(resolved_branch_id) if resolved_branch_id else None,
            permissions=permissions,
            brand_id=str(context.brand_id) if context else None,
            business_type=context.business_type if context else None,
            target_database=context.target_database if context else None,
            station_key=resolved_station_key,
            assignment_ids=[str(value) for value in assignment_ids],
            scope_types=scope_types,
            company_credential_version=company.credential_version,
        )
        new_refresh_token = create_refresh_token(
            subject=str(user.id),
            company_id=str(user.company_id),
            branch_id=str(resolved_branch_id) if resolved_branch_id else None,
            station_key=resolved_station_key,
            company_credential_version=company.credential_version,
        )
        self.db.add(
            RefreshToken(
                user_id=user.id,
                company_id=user.company_id,
                token_hash=self._hash_token(new_refresh_token),
                expires_at=self._extract_expiration(new_refresh_token),
                ip_address=ip_address,
                user_agent=refresh_record.user_agent,
            )
        )
        self.db.add(
            AuditLog(
                company_id=user.company_id,
                branch_id=None,
                user_id=user.id,
                action="user.token_refresh",
                resource="User",
                resource_id=str(user.id),
                ip_address=ip_address,
            )
        )
        await self.db.commit()
        return access_token, new_refresh_token

    async def logout(self, raw_refresh_token: str) -> None:
        token_hash = self._hash_token(raw_refresh_token)
        refresh_record = await self.db.scalar(
            select(RefreshToken).where(RefreshToken.token_hash == token_hash)
        )
        if refresh_record is None:
            return

        refresh_record.revoked_at = datetime.now(timezone.utc)
        self.db.add(
            AuditLog(
                company_id=refresh_record.company_id,
                branch_id=None,
                user_id=refresh_record.user_id,
                action="user.logout",
                resource="RefreshToken",
                resource_id=str(refresh_record.id),
            )
        )
        await self.db.commit()

    async def switch_branch(
        self,
        user: User,
        new_branch_id: uuid.UUID,
        *,
        station_key: str | None = None,
    ) -> tuple[str, str]:
        access_token, refresh_token = await self.create_session(
            user=user,
            branch_id=new_branch_id,
            station_key=station_key,
            ip_address=None,
            user_agent=None,
        )
        self.db.add(
            AuditLog(
                company_id=user.company_id,
                branch_id=new_branch_id,
                user_id=user.id,
                action="user.switch_branch",
                resource="Branch",
                resource_id=str(new_branch_id),
            )
        )
        await self.db.commit()
        return access_token, refresh_token

    @staticmethod
    def _hash_token(raw_token: str) -> str:
        return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()

    @staticmethod
    def _extract_expiration(raw_token: str) -> datetime:
        payload = decode_token(raw_token)
        return datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
