from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditLog
from app.models.auth import RefreshToken
from app.models.branch import Branch
from app.models.role import Permission, Role, role_permissions_table
from app.models.user import User, UserBranch
from app.utils.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    verify_password,
)


class AuthService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def authenticate_user(
        self,
        company_id: uuid.UUID,
        username: str,
        password: str,
    ) -> User:
        statement = select(User).where(
            User.company_id == company_id,
            User.username == username,
            User.deleted_at.is_(None),
            User.is_active.is_(True),
        )
        user = await self.db.scalar(statement)
        if user is None or not verify_password(password, user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid username or password",
            )

        user.last_login_at = datetime.now(timezone.utc)
        await self.db.flush()
        return user

    async def get_user_permissions(
        self,
        user: User,
        branch_id: uuid.UUID | None,
    ) -> tuple[list[str], uuid.UUID | None]:
        if user.is_superuser:
            return ["*"], branch_id

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
            return [], None

        statement = (
            select(Permission.code)
            .join(role_permissions_table, Permission.id == role_permissions_table.c.permission_id)
            .join(Role, Role.id == role_permissions_table.c.role_id)
            .join(UserBranch, UserBranch.role_id == Role.id)
            .where(
                UserBranch.user_id == user.id,
                UserBranch.branch_id == resolved_branch_id,
                UserBranch.deleted_at.is_(None),
                Role.deleted_at.is_(None),
            )
        )
        rows = await self.db.scalars(statement)
        return sorted(set(rows.all())), resolved_branch_id

    async def create_session(
        self,
        user: User,
        branch_id: uuid.UUID | None,
        ip_address: str | None,
        user_agent: str | None,
    ) -> tuple[str, str]:
        permissions, resolved_branch_id = await self.get_user_permissions(user, branch_id)
        access_token = create_access_token(
            subject=str(user.id),
            company_id=str(user.company_id),
            branch_id=str(resolved_branch_id) if resolved_branch_id else None,
            permissions=permissions,
        )
        refresh_token = create_refresh_token(
            subject=str(user.id),
            company_id=str(user.company_id),
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

        user = await self.db.scalar(
            select(User).where(
                User.id == refresh_record.user_id,
                User.deleted_at.is_(None),
                User.is_active.is_(True),
            )
        )
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found",
            )

        refresh_record.revoked_at = now
        permissions, resolved_branch_id = await self.get_user_permissions(user, None)
        access_token = create_access_token(
            subject=str(user.id),
            company_id=str(user.company_id),
            branch_id=str(resolved_branch_id) if resolved_branch_id else None,
            permissions=permissions,
        )
        new_refresh_token = create_refresh_token(
            subject=str(user.id),
            company_id=str(user.company_id),
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
    ) -> tuple[str, str]:
        assignment = await self.db.scalar(
            select(UserBranch).where(
                UserBranch.user_id == user.id,
                UserBranch.branch_id == new_branch_id,
                UserBranch.deleted_at.is_(None),
            )
        )
        if assignment is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User is not assigned to this branch",
            )

        access_token, refresh_token = await self.create_session(
            user=user,
            branch_id=new_branch_id,
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
