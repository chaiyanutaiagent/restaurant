from __future__ import annotations

from datetime import datetime, timedelta, timezone
import uuid

from fastapi import HTTPException, status
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.audit import AuditLog
from app.models.auth import RefreshToken
from app.models.role import Role
from app.models.staff_assignment import StaffRoleAssignment
from app.models.user import User, UserBranch
from app.schemas.company_access import (
    CompanyAccessMutationRequest,
    CompanyAccessReviewRequest,
    CompanyAccessReviewUserRead,
    CompanyTenantSecurityRead,
    CompanyTenantSessionRead,
)
from app.services.company_owner_policy import CompanyOwnerPolicy


HIGH_RISK_PERMISSIONS = {
    "system.company.edit",
    "system.user.edit",
    "system.user.delete",
    "system.role.edit",
    "system.role.delete",
    "inventory.purchase.approve",
    "inventory.transfer.approve",
    "accounting.payment.approve",
    "pos.refund.approve",
}
REQUESTER_PERMISSIONS = {
    "inventory.purchase.create",
    "inventory.transfer.create",
    "accounting.payment.create",
    "pos.refund.request",
}
APPROVER_PERMISSIONS = {
    "inventory.purchase.approve",
    "inventory.transfer.approve",
    "accounting.payment.approve",
    "pos.refund.approve",
}


async def invalidate_user_access(
    db: AsyncSession,
    user: User,
    *,
    reason: str,
    now: datetime | None = None,
) -> int:
    revoked_at = now or datetime.now(timezone.utc)
    user.credential_version = getattr(user, "credential_version", 1) + 1
    result = await db.execute(
        update(RefreshToken)
        .where(
            RefreshToken.company_id == user.company_id,
            RefreshToken.user_id == user.id,
            RefreshToken.revoked_at.is_(None),
        )
        .values(revoked_at=revoked_at)
    )
    return int(getattr(result, "rowcount", 0) or 0)


class CompanyAccessService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_access_reviews(
        self,
        company_id: uuid.UUID,
        *,
        status_filter: str | None = None,
    ) -> list[CompanyAccessReviewUserRead]:
        users = (
            await self.db.scalars(
                select(User)
                .where(User.company_id == company_id, User.deleted_at.is_(None))
                .options(
                    selectinload(User.user_branches).selectinload(UserBranch.role).selectinload(Role.permissions)
                )
                .order_by(User.is_active.desc(), User.display_name.asc().nulls_last(), User.username.asc())
            )
        ).unique().all()
        user_ids = [user.id for user in users]
        scoped = (
            await self.db.scalars(
                select(StaffRoleAssignment)
                .where(
                    StaffRoleAssignment.company_id == company_id,
                    StaffRoleAssignment.user_id.in_(user_ids),
                    StaffRoleAssignment.revoked_at.is_(None),
                )
                .options(selectinload(StaffRoleAssignment.role).selectinload(Role.permissions))
            )
        ).all() if user_ids else []
        scoped_by_user: dict[uuid.UUID, list[StaffRoleAssignment]] = {}
        for assignment in scoped:
            scoped_by_user.setdefault(assignment.user_id, []).append(assignment)
        session_counts = dict(
            (
                await self.db.execute(
                    select(RefreshToken.user_id, func.count(RefreshToken.id))
                    .where(
                        RefreshToken.company_id == company_id,
                        RefreshToken.user_id.in_(user_ids),
                        RefreshToken.revoked_at.is_(None),
                        RefreshToken.expires_at > datetime.now(timezone.utc),
                    )
                    .group_by(RefreshToken.user_id)
                )
            ).all()
        ) if user_ids else {}
        now = datetime.now(timezone.utc)
        stale_before = now - timedelta(days=90)
        new_user_grace = now - timedelta(days=30)
        result: list[CompanyAccessReviewUserRead] = []
        for user in users:
            legacy_roles = [
                branch.role
                for branch in user.user_branches
                if branch.deleted_at is None and branch.role is not None and branch.role.deleted_at is None
            ]
            scoped_roles = [item.role for item in scoped_by_user.get(user.id, []) if item.role.deleted_at is None]
            roles = list({role.id: role for role in [*legacy_roles, *scoped_roles]}.values())
            permissions = {permission.code for role in roles for permission in role.permissions}
            stale = (
                (user.last_login_at is None and user.created_at < new_user_grace)
                or (user.last_login_at is not None and user.last_login_at < stale_before)
            )
            due = user.access_review_due_at is None or user.access_review_due_at <= now
            flags: list[str] = []
            if not user.is_active:
                flags.append("inactive")
            if stale:
                flags.append("stale")
            if user.is_superuser or permissions.intersection(HIGH_RISK_PERMISSIONS):
                flags.append("high_risk")
            if permissions.intersection(REQUESTER_PERMISSIONS) and permissions.intersection(APPROVER_PERMISSIONS):
                flags.append("segregation_conflict")
            if due:
                flags.append("review_due")
            item = CompanyAccessReviewUserRead(
                id=user.id,
                username=user.username,
                display_name=user.display_name or " ".join(filter(None, [user.first_name, user.last_name])) or user.username,
                email=user.email,
                is_active=user.is_active,
                is_superuser=user.is_superuser,
                credential_version=getattr(user, "credential_version", 1),
                mfa_state="enabled" if getattr(user, "mfa_enabled", False) else "not_configured",
                last_login_at=user.last_login_at,
                active_session_count=int(session_counts.get(user.id, 0)),
                role_names=sorted({role.name for role in roles}),
                risk_flags=flags,
                access_reviewed_at=user.access_reviewed_at,
                access_review_due_at=user.access_review_due_at,
                access_review_outcome=user.access_review_outcome,
                review_due=due,
                stale_access=stale,
            )
            if status_filter == "due" and not due:
                continue
            if status_filter == "stale" and not stale:
                continue
            if status_filter == "high_risk" and "high_risk" not in flags:
                continue
            if status_filter == "inactive" and user.is_active:
                continue
            result.append(item)
        return result

    async def list_sessions(
        self,
        company_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> list[CompanyTenantSessionRead]:
        await self._user(company_id, user_id)
        now = datetime.now(timezone.utc)
        rows = (
            await self.db.scalars(
                select(RefreshToken)
                .where(RefreshToken.company_id == company_id, RefreshToken.user_id == user_id)
                .order_by(RefreshToken.created_at.desc())
                .limit(50)
            )
        ).all()
        return [
            CompanyTenantSessionRead(
                id=row.id,
                created_at=row.created_at,
                expires_at=row.expires_at,
                revoked_at=row.revoked_at,
                ip_address=row.ip_address,
                user_agent=row.user_agent,
                state="revoked" if row.revoked_at else ("expired" if row.expires_at <= now else "active"),
            )
            for row in rows
        ]

    async def revoke_session(
        self,
        company_id: uuid.UUID,
        user_id: uuid.UUID,
        session_id: uuid.UUID,
        actor_id: uuid.UUID,
        payload: CompanyAccessMutationRequest,
    ) -> int:
        replay = await self._mutation_replay(company_id, "system.user.session.revoke", payload.request_id)
        if replay is not None:
            return int((replay.new_value or {}).get("revoked_session_count", 0))
        user = await self._locked_user(company_id, user_id)
        self._check_version(user, payload.expected_credential_version)
        row = await self.db.scalar(
            select(RefreshToken).where(
                RefreshToken.id == session_id,
                RefreshToken.company_id == company_id,
                RefreshToken.user_id == user_id,
            )
        )
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
        if row.revoked_at is None:
            row.revoked_at = datetime.now(timezone.utc)
            changed = 1
        else:
            changed = 0
        self._audit(
            company_id,
            actor_id,
            "system.user.session.revoke",
            "RefreshToken",
            session_id,
            payload,
            {"user_id": str(user_id), "revoked_session_count": changed},
        )
        await self.db.commit()
        return changed

    async def revoke_all_sessions(
        self,
        company_id: uuid.UUID,
        user_id: uuid.UUID,
        actor_id: uuid.UUID,
        payload: CompanyAccessMutationRequest,
    ) -> tuple[int, int]:
        replay = await self._mutation_replay(company_id, "system.user.sessions.revoke_all", payload.request_id)
        if replay is not None:
            value = replay.new_value or {}
            return int(value.get("revoked_session_count", 0)), int(value.get("credential_version", 1))
        user = await self._locked_user(company_id, user_id)
        self._check_version(user, payload.expected_credential_version)
        changed = await invalidate_user_access(self.db, user, reason=payload.reason)
        self._audit(
            company_id,
            actor_id,
            "system.user.sessions.revoke_all",
            "User",
            user_id,
            payload,
            {"revoked_session_count": changed, "credential_version": user.credential_version},
        )
        await self.db.commit()
        return changed, user.credential_version

    async def review_access(
        self,
        company_id: uuid.UUID,
        user_id: uuid.UUID,
        actor_id: uuid.UUID,
        payload: CompanyAccessReviewRequest,
    ) -> CompanyAccessReviewUserRead:
        replay = await self._mutation_replay(company_id, "system.user.access_review", payload.request_id)
        if replay is not None:
            rows = await self.list_access_reviews(company_id)
            try:
                return next(item for item in rows if item.id == user_id)
            except StopIteration as exc:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found") from exc
        user = await self._locked_user(company_id, user_id)
        self._check_version(user, payload.expected_credential_version)
        now = datetime.now(timezone.utc)
        before = {
            "is_active": user.is_active,
            "credential_version": user.credential_version,
            "access_review_due_at": user.access_review_due_at.isoformat() if user.access_review_due_at else None,
        }
        if payload.outcome == "revoke":
            await CompanyOwnerPolicy(self.db).ensure_user_can_be_deactivated(company_id, user_id)
            user.is_active = False
            user.deactivated_at = now
            user.deactivated_by = actor_id
            user.deactivation_reason = payload.reason
            await invalidate_user_access(self.db, user, reason=payload.reason, now=now)
        elif payload.outcome == "reduce":
            assignment = await self.db.scalar(
                select(StaffRoleAssignment)
                .where(
                    StaffRoleAssignment.id == payload.assignment_id,
                    StaffRoleAssignment.company_id == company_id,
                    StaffRoleAssignment.user_id == user_id,
                    StaffRoleAssignment.revoked_at.is_(None),
                )
                .options(selectinload(StaffRoleAssignment.role))
            )
            if assignment is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assignment not found")
            await CompanyOwnerPolicy(self.db).ensure_assignment_can_be_revoked(assignment)
            assignment.revoked_at = now
            assignment.revoked_by = actor_id
            assignment.revocation_reason = payload.reason
            await invalidate_user_access(self.db, user, reason=payload.reason, now=now)
        user.access_reviewed_at = now
        user.access_reviewed_by = actor_id
        user.access_review_outcome = payload.outcome
        default_days = 7 if payload.outcome == "investigate" else 90
        user.access_review_due_at = payload.next_review_due_at or (now + timedelta(days=default_days))
        if user.access_review_due_at <= now:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Next review must be in the future")
        self._audit(
            company_id,
            actor_id,
            "system.user.access_review",
            "User",
            user_id,
            payload,
            {
                "before": before,
                "outcome": payload.outcome,
                "assignment_id": str(payload.assignment_id) if payload.assignment_id else None,
                "is_active": user.is_active,
                "credential_version": user.credential_version,
                "next_review_due_at": user.access_review_due_at.isoformat(),
            },
        )
        await self.db.commit()
        rows = await self.list_access_reviews(company_id)
        return next(item for item in rows if item.id == user_id)

    @staticmethod
    def security_posture() -> CompanyTenantSecurityRead:
        return CompanyTenantSecurityRead(
            note=(
                "Tenant MFA policy is intentionally HOLD until Product Owner approves enforcement, "
                "recovery and owner-assisted reset. Session visibility and revocation are active."
            )
        )

    async def _user(self, company_id: uuid.UUID, user_id: uuid.UUID) -> User:
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

    async def _locked_user(self, company_id: uuid.UUID, user_id: uuid.UUID) -> User:
        user = await self.db.scalar(
            select(User).where(
                User.id == user_id,
                User.company_id == company_id,
                User.deleted_at.is_(None),
            ).with_for_update()
        )
        if user is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        return user

    @staticmethod
    def _check_version(user: User, expected: int) -> None:
        if getattr(user, "credential_version", 1) != expected:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"code": "stale_access_state", "message": "Access changed; reload before retrying"},
            )

    async def _mutation_replay(
        self,
        company_id: uuid.UUID,
        action: str,
        request_id: uuid.UUID,
    ) -> AuditLog | None:
        return await self.db.scalar(
            select(AuditLog).where(
                AuditLog.company_id == company_id,
                AuditLog.action == action,
                AuditLog.new_value["request_id"].as_string() == str(request_id),
            )
        )

    def _audit(
        self,
        company_id: uuid.UUID,
        actor_id: uuid.UUID,
        action: str,
        resource: str,
        resource_id: uuid.UUID,
        payload: CompanyAccessMutationRequest,
        value: dict,
    ) -> None:
        self.db.add(
            AuditLog(
                company_id=company_id,
                user_id=actor_id,
                action=action,
                resource=resource,
                resource_id=str(resource_id),
                new_value={
                    **value,
                    "reason": payload.reason,
                    "request_id": str(payload.request_id),
                    "target_user_id": str(resource_id) if resource == "User" else None,
                },
            )
        )
