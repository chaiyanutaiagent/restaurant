from __future__ import annotations

from datetime import datetime, timedelta, timezone
import uuid

from fastapi import HTTPException, status
from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.audit import AuditLog
from app.models.platform import (
    PlatformOperator,
    PlatformOperatorInvitation,
    PlatformOperatorRoleAssignment,
    PlatformSession,
)
from app.schemas.platform import (
    PlatformAccessReviewRequest,
    PlatformOperatorInvitationAccept,
    PlatformOperatorInvitationRead,
    PlatformOperatorInviteRequest,
    PlatformOperatorRead,
    PlatformOperatorStateRequest,
    PlatformRoleAssignmentRequest,
    PlatformTeamOperatorRead,
)
from app.services.platform_access_service import (
    PLATFORM_ROLE_LABELS,
    PLATFORM_ROLE_PERMISSIONS,
    active_owner_count,
    effective_platform_access,
)
from app.utils.platform_security import generate_opaque_credential, hash_opaque_credential
from app.utils.security import hash_password


ACCESS_REVIEW_DAYS = 90
STALE_ACCESS_DAYS = 90
INVITATION_HOURS = 24


class PlatformTeamService:
    def __init__(self, db: AsyncSession, *, actor_id: uuid.UUID | None):
        self.db = db
        self.actor_id = actor_id

    @staticmethod
    def role_definitions() -> list[dict[str, object]]:
        return [
            {
                "code": code,
                "label": PLATFORM_ROLE_LABELS[code],
                "permissions": sorted(PLATFORM_ROLE_PERMISSIONS[code]),
            }
            for code in PLATFORM_ROLE_LABELS
        ]

    async def list_operators(self, *, environment: str) -> list[PlatformTeamOperatorRead]:
        rows = (
            await self.db.scalars(
                select(PlatformOperator).order_by(
                    PlatformOperator.is_active.desc(),
                    PlatformOperator.display_name,
                    PlatformOperator.username,
                )
            )
        ).all()
        return [await self._operator_read(row, environment=environment) for row in rows]

    async def operator(self, operator_id: uuid.UUID, *, environment: str) -> PlatformTeamOperatorRead:
        return await self._operator_read(
            await self._operator_for_update(operator_id, lock=False),
            environment=environment,
        )

    async def list_invitations(self, *, environment: str) -> list[PlatformOperatorInvitationRead]:
        rows = (
            await self.db.scalars(
                select(PlatformOperatorInvitation)
                .where(PlatformOperatorInvitation.environment == environment)
                .order_by(PlatformOperatorInvitation.created_at.desc())
                .limit(100)
            )
        ).all()
        return [PlatformOperatorInvitationRead.model_validate(row) for row in rows]

    async def invite(
        self,
        payload: PlatformOperatorInviteRequest,
        *,
        actor_roles: list[str],
        ip_address: str | None,
        user_agent: str | None,
    ) -> PlatformOperatorInvitationRead:
        existing_request = await self.db.scalar(
            select(PlatformOperatorInvitation).where(
                PlatformOperatorInvitation.request_id == payload.request_id
            )
        )
        if existing_request is not None:
            if (
                existing_request.username != payload.username
                or existing_request.email != payload.email
                or existing_request.role_code != payload.role_code
                or existing_request.environment != payload.environment
            ):
                raise HTTPException(status_code=409, detail="Request id was already used for another invitation")
            return PlatformOperatorInvitationRead.model_validate(existing_request)
        duplicate = await self.db.scalar(
            select(PlatformOperator.id).where(
                or_(
                    PlatformOperator.username == payload.username,
                    PlatformOperator.email == payload.email,
                )
            )
        )
        if duplicate is not None:
            raise HTTPException(status_code=409, detail="Platform username or email already exists")
        raw_token = generate_opaque_credential()
        invitation = PlatformOperatorInvitation(
            username=payload.username,
            email=payload.email,
            display_name=payload.display_name,
            role_code=payload.role_code,
            environment=payload.environment,
            token_hash=hash_opaque_credential(raw_token),
            request_id=payload.request_id,
            invited_by=self._required_actor(),
            reason=payload.reason,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=INVITATION_HOURS),
        )
        self.db.add(invitation)
        await self.db.flush()
        deep_link = f"{settings.saas_public_base_url.rstrip('/')}/platform/invite?token={raw_token}"
        self._audit(
            action="platform.team.invitation.create",
            resource="PlatformOperatorInvitation",
            resource_id=invitation.id,
            reason=payload.reason,
            actor_roles=actor_roles,
            environment=payload.environment,
            request_id=payload.request_id,
            old_value=None,
            new_value={
                "username": payload.username,
                "email": payload.email,
                "role_code": payload.role_code,
                "expires_at": invitation.expires_at.isoformat(),
            },
            ip_address=ip_address,
            user_agent=user_agent,
        )
        await self.db.commit()
        read = PlatformOperatorInvitationRead.model_validate(invitation)
        return read.model_copy(update={"acceptance_token": raw_token, "deep_link": deep_link})

    async def accept_invitation(
        self,
        payload: PlatformOperatorInvitationAccept,
        *,
        ip_address: str | None,
        user_agent: str | None,
    ) -> PlatformOperatorRead:
        invitation = await self.db.scalar(
            select(PlatformOperatorInvitation)
            .where(
                PlatformOperatorInvitation.token_hash == hash_opaque_credential(payload.token)
            )
            .with_for_update()
        )
        now = datetime.now(timezone.utc)
        if (
            invitation is None
            or invitation.revoked_at is not None
            or invitation.accepted_at is not None
            or invitation.expires_at <= now
        ):
            raise HTTPException(status_code=410, detail="Platform invitation is invalid or expired")
        duplicate = await self.db.scalar(
            select(PlatformOperator.id).where(
                or_(
                    PlatformOperator.username == invitation.username,
                    PlatformOperator.email == invitation.email,
                )
            )
        )
        if duplicate is not None:
            raise HTTPException(status_code=409, detail="Platform username or email already exists")
        operator = PlatformOperator(
            username=invitation.username,
            email=invitation.email,
            display_name=invitation.display_name,
            hashed_password=hash_password(payload.password),
            is_active=True,
            is_superuser=False,
            password_changed_at=now,
            access_review_due_at=now + timedelta(days=ACCESS_REVIEW_DAYS),
        )
        self.db.add(operator)
        await self.db.flush()
        self.db.add(
            PlatformOperatorRoleAssignment(
                operator_id=operator.id,
                role_code=invitation.role_code,
                environment=invitation.environment,
                assigned_by=invitation.invited_by,
                reason=f"Accepted invitation: {invitation.reason}",
                request_id=invitation.request_id,
            )
        )
        invitation.accepted_at = now
        invitation.accepted_operator_id = operator.id
        self._audit(
            action="platform.team.invitation.accept",
            resource="PlatformOperator",
            resource_id=operator.id,
            reason="Invitation accepted",
            actor_roles=[invitation.role_code],
            environment=invitation.environment,
            request_id=invitation.request_id,
            old_value=None,
            new_value={"username": operator.username, "role_code": invitation.role_code},
            ip_address=ip_address,
            user_agent=user_agent,
            actor_id=operator.id,
        )
        await self.db.commit()
        roles, permissions = await effective_platform_access(
            self.db, operator, environment=invitation.environment
        )
        return self._basic_operator_read(operator, invitation.environment, roles, permissions)

    async def assign_role(
        self,
        operator_id: uuid.UUID,
        payload: PlatformRoleAssignmentRequest,
        *,
        actor_roles: list[str],
        ip_address: str | None,
        user_agent: str | None,
    ) -> PlatformTeamOperatorRead:
        repeated = await self.db.scalar(
            select(PlatformOperatorRoleAssignment).where(
                PlatformOperatorRoleAssignment.request_id == payload.request_id
            )
        )
        if repeated is not None:
            if (
                repeated.operator_id != operator_id
                or repeated.role_code != payload.role_code
                or repeated.environment != payload.environment
            ):
                raise HTTPException(status_code=409, detail="Request id was already used for another role assignment")
            return await self.operator(operator_id, environment=payload.environment)
        operator = await self._operator_for_update(operator_id)
        self._check_version(operator, payload.expected_credential_version)
        active = await self.db.scalar(
            select(PlatformOperatorRoleAssignment.id).where(
                PlatformOperatorRoleAssignment.operator_id == operator.id,
                PlatformOperatorRoleAssignment.environment == payload.environment,
                PlatformOperatorRoleAssignment.role_code == payload.role_code,
                PlatformOperatorRoleAssignment.revoked_at.is_(None),
            )
        )
        if active is not None or (payload.role_code == "platform_owner" and operator.is_superuser):
            raise HTTPException(status_code=409, detail="Platform role is already assigned")
        before_roles, _ = await effective_platform_access(self.db, operator, environment=payload.environment)
        self.db.add(
            PlatformOperatorRoleAssignment(
                operator_id=operator.id,
                role_code=payload.role_code,
                environment=payload.environment,
                assigned_by=self._required_actor(),
                reason=payload.reason,
                request_id=payload.request_id,
            )
        )
        await self._invalidate_access(operator, reason="role-assigned")
        after_roles = sorted(set(before_roles) | {payload.role_code})
        self._audit_change("platform.team.role.assign", operator, payload, before_roles, after_roles, actor_roles, ip_address, user_agent)
        await self.db.commit()
        return await self.operator(operator.id, environment=payload.environment)

    async def revoke_role(
        self,
        operator_id: uuid.UUID,
        payload: PlatformRoleAssignmentRequest,
        *,
        actor_roles: list[str],
        ip_address: str | None,
        user_agent: str | None,
    ) -> PlatformTeamOperatorRead:
        if await self._idempotent_replay(
            "platform.team.role.revoke", operator_id, payload.request_id
        ):
            return await self.operator(operator_id, environment=payload.environment)
        operator = await self._operator_for_update(operator_id)
        self._check_version(operator, payload.expected_credential_version)
        assignment = await self.db.scalar(
            select(PlatformOperatorRoleAssignment)
            .where(
                PlatformOperatorRoleAssignment.operator_id == operator.id,
                PlatformOperatorRoleAssignment.environment == payload.environment,
                PlatformOperatorRoleAssignment.role_code == payload.role_code,
                PlatformOperatorRoleAssignment.revoked_at.is_(None),
            )
            .with_for_update()
        )
        implicit_owner = payload.role_code == "platform_owner" and operator.is_superuser
        if assignment is None and not implicit_owner:
            raise HTTPException(status_code=404, detail="Active Platform role assignment not found")
        if payload.role_code == "platform_owner":
            await self._protect_last_owner(operator.id, payload.environment)
        before_roles, _ = await effective_platform_access(self.db, operator, environment=payload.environment)
        now = datetime.now(timezone.utc)
        if assignment is not None:
            assignment.revoked_at = now
            assignment.revoked_by = self._required_actor()
            assignment.revocation_reason = payload.reason
        if implicit_owner:
            operator.is_superuser = False
        await self._invalidate_access(operator, reason="role-revoked")
        after_roles = [value for value in before_roles if value != payload.role_code]
        self._audit_change("platform.team.role.revoke", operator, payload, before_roles, after_roles, actor_roles, ip_address, user_agent)
        await self.db.commit()
        return await self.operator(operator.id, environment=payload.environment)

    async def set_operator_state(
        self,
        operator_id: uuid.UUID,
        payload: PlatformOperatorStateRequest,
        *,
        environment: str,
        actor_roles: list[str],
        ip_address: str | None,
        user_agent: str | None,
    ) -> PlatformTeamOperatorRead:
        action_name = "platform.team.operator.reactivate" if payload.active else "platform.team.operator.deactivate"
        if await self._idempotent_replay(action_name, operator_id, payload.request_id):
            return await self.operator(operator_id, environment=environment)
        operator = await self._operator_for_update(operator_id)
        self._check_version(operator, payload.expected_credential_version)
        if operator.is_active == payload.active:
            return await self.operator(operator.id, environment=environment)
        before = {"is_active": operator.is_active, "credential_version": operator.credential_version}
        if not payload.active:
            roles, _ = await effective_platform_access(self.db, operator, environment=environment)
            if "platform_owner" in roles:
                await self._protect_last_owner(operator.id, environment)
        now = datetime.now(timezone.utc)
        operator.is_active = payload.active
        operator.deactivated_at = None if payload.active else now
        operator.deactivated_by = None if payload.active else self._required_actor()
        operator.deactivation_reason = None if payload.active else payload.reason
        await self._invalidate_access(operator, reason="operator-state-changed")
        self._audit(
            action="platform.team.operator.reactivate" if payload.active else "platform.team.operator.deactivate",
            resource="PlatformOperator",
            resource_id=operator.id,
            reason=payload.reason,
            actor_roles=actor_roles,
            environment=environment,
            request_id=payload.request_id,
            old_value=before,
            new_value={"is_active": operator.is_active, "credential_version": operator.credential_version},
            ip_address=ip_address,
            user_agent=user_agent,
        )
        await self.db.commit()
        return await self.operator(operator.id, environment=environment)

    async def certify_access(
        self,
        operator_id: uuid.UUID,
        payload: PlatformAccessReviewRequest,
        *,
        environment: str,
        actor_roles: list[str],
        ip_address: str | None,
        user_agent: str | None,
    ) -> PlatformTeamOperatorRead:
        if await self._idempotent_replay(
            "platform.team.access.certify", operator_id, payload.request_id
        ):
            return await self.operator(operator_id, environment=environment)
        operator = await self._operator_for_update(operator_id)
        self._check_version(operator, payload.expected_credential_version)
        now = datetime.now(timezone.utc)
        if payload.next_review_due_at.tzinfo is None or payload.next_review_due_at <= now:
            raise HTTPException(status_code=422, detail="Next access review must be in the future")
        before = {
            "access_reviewed_at": operator.access_reviewed_at.isoformat() if operator.access_reviewed_at else None,
            "access_review_due_at": operator.access_review_due_at.isoformat() if operator.access_review_due_at else None,
        }
        operator.access_reviewed_at = now
        operator.access_review_due_at = payload.next_review_due_at
        operator.access_reviewed_by = self._required_actor()
        self._audit(
            action="platform.team.access.certify",
            resource="PlatformOperator",
            resource_id=operator.id,
            reason=payload.reason,
            actor_roles=actor_roles,
            environment=environment,
            request_id=payload.request_id,
            old_value=before,
            new_value={
                "access_reviewed_at": now.isoformat(),
                "access_review_due_at": payload.next_review_due_at.isoformat(),
            },
            ip_address=ip_address,
            user_agent=user_agent,
        )
        await self.db.commit()
        return await self.operator(operator.id, environment=environment)

    async def revoke_operator_sessions(
        self,
        operator_id: uuid.UUID,
        *,
        reason: str,
        request_id: uuid.UUID,
        environment: str,
        actor_roles: list[str],
        ip_address: str | None,
        user_agent: str | None,
    ) -> int:
        replay = await self._idempotent_replay(
            "platform.security.sessions.revoke", operator_id, request_id, return_event=True
        )
        if replay:
            value = replay.new_value.get("value", {}) if replay.new_value else {}
            return int(value.get("revoked_session_count", 0))
        await self._operator_for_update(operator_id, lock=False)
        now = datetime.now(timezone.utc)
        result = await self.db.execute(
            update(PlatformSession)
            .where(
                PlatformSession.operator_id == operator_id,
                PlatformSession.revoked_at.is_(None),
            )
            .values(revoked_at=now, revocation_reason="security-admin-revoked")
        )
        count = int(result.rowcount or 0)
        self._audit(
            action="platform.security.sessions.revoke",
            resource="PlatformOperator",
            resource_id=operator_id,
            reason=reason,
            actor_roles=actor_roles,
            environment=environment,
            request_id=request_id,
            old_value=None,
            new_value={"revoked_session_count": count},
            ip_address=ip_address,
            user_agent=user_agent,
        )
        await self.db.commit()
        return count

    async def _operator_read(self, operator: PlatformOperator, *, environment: str) -> PlatformTeamOperatorRead:
        roles, permissions = await effective_platform_access(self.db, operator, environment=environment)
        now = datetime.now(timezone.utc)
        active_sessions = await self.db.scalar(
            select(func.count(PlatformSession.id)).where(
                PlatformSession.operator_id == operator.id,
                PlatformSession.revoked_at.is_(None),
                PlatformSession.expires_at > now,
            )
        )
        stale_cutoff = now - timedelta(days=STALE_ACCESS_DAYS)
        stale = operator.last_login_at is None or operator.last_login_at < stale_cutoff
        review_due = operator.access_review_due_at is None or operator.access_review_due_at <= now
        basic = self._basic_operator_read(operator, environment, roles, permissions)
        return PlatformTeamOperatorRead(
            **basic.model_dump(),
            active_session_count=int(active_sessions or 0),
            stale_access=stale,
            review_due=review_due,
            deactivated_at=operator.deactivated_at,
            deactivation_reason=operator.deactivation_reason,
            deep_links={
                "team": f"/platform/team?operator={operator.id}",
                "audit": f"/platform/audit?operator_id={operator.id}",
                "security": f"/platform/security?operator={operator.id}",
            },
        )

    async def _idempotent_replay(
        self,
        action: str,
        resource_id: uuid.UUID,
        request_id: uuid.UUID,
        *,
        return_event: bool = False,
    ):
        event = await self.db.scalar(
            select(AuditLog).where(
                AuditLog.action.like("platform.%"),
                AuditLog.new_value["request_id"].as_string() == str(request_id),
            )
        )
        if event is None:
            return None if return_event else False
        if event.action != action or event.resource_id != str(resource_id):
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "platform_request_id_conflict",
                    "message": "Request id was already used for another Platform mutation",
                },
            )
        return event if return_event else True

    @staticmethod
    def _basic_operator_read(operator: PlatformOperator, environment: str, roles: list[str], permissions: list[str]) -> PlatformOperatorRead:
        return PlatformOperatorRead(
            id=operator.id,
            username=operator.username,
            email=operator.email,
            display_name=operator.display_name,
            is_active=operator.is_active,
            is_superuser=operator.is_superuser,
            mfa_enabled=operator.mfa_enabled,
            last_login_at=operator.last_login_at,
            credential_version=operator.credential_version,
            role_codes=roles,
            permissions=permissions,
            environment=environment,
            access_reviewed_at=operator.access_reviewed_at,
            access_review_due_at=operator.access_review_due_at,
        )

    async def _operator_for_update(self, operator_id: uuid.UUID, *, lock: bool = True) -> PlatformOperator:
        statement = select(PlatformOperator).where(PlatformOperator.id == operator_id)
        if lock:
            statement = statement.with_for_update()
        operator = await self.db.scalar(statement)
        if operator is None:
            raise HTTPException(status_code=404, detail="Platform operator not found")
        return operator

    @staticmethod
    def _check_version(operator: PlatformOperator, expected: int) -> None:
        if operator.credential_version != expected:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "stale_operator_version",
                    "message": "Operator access changed; refresh before retrying",
                    "expected": expected,
                    "current": operator.credential_version,
                },
            )

    async def _protect_last_owner(self, operator_id: uuid.UUID, environment: str) -> None:
        if await active_owner_count(
            self.db,
            environment=environment,
            excluding_operator_id=operator_id,
        ) < 1:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "last_platform_owner",
                    "message": "The last active Platform Owner cannot be removed or deactivated",
                    "environment": environment,
                },
            )

    async def _invalidate_access(self, operator: PlatformOperator, *, reason: str) -> None:
        operator.credential_version += 1
        now = datetime.now(timezone.utc)
        await self.db.execute(
            update(PlatformSession)
            .where(
                PlatformSession.operator_id == operator.id,
                PlatformSession.revoked_at.is_(None),
            )
            .values(revoked_at=now, revocation_reason=reason)
        )

    def _audit_change(self, action, operator, payload, before_roles, after_roles, actor_roles, ip_address, user_agent) -> None:
        self._audit(
            action=action,
            resource="PlatformOperator",
            resource_id=operator.id,
            reason=payload.reason,
            actor_roles=actor_roles,
            environment=payload.environment,
            request_id=payload.request_id,
            old_value={"roles": before_roles, "credential_version": operator.credential_version - 1},
            new_value={"roles": after_roles, "credential_version": operator.credential_version},
            ip_address=ip_address,
            user_agent=user_agent,
        )

    def _audit(
        self,
        *,
        action: str,
        resource: str,
        resource_id: uuid.UUID,
        reason: str,
        actor_roles: list[str],
        environment: str,
        request_id: uuid.UUID,
        old_value,
        new_value,
        ip_address: str | None,
        user_agent: str | None,
        actor_id: uuid.UUID | None = None,
    ) -> None:
        self.db.add(
            AuditLog(
                company_id=None,
                branch_id=None,
                user_id=actor_id or self.actor_id,
                action=action,
                resource=resource,
                resource_id=str(resource_id),
                old_value={
                    "reason": reason,
                    "actor_roles": actor_roles,
                    "environment": environment,
                    "request_id": str(request_id),
                    "value": old_value,
                },
                new_value={
                    "reason": reason,
                    "actor_roles": actor_roles,
                    "environment": environment,
                    "request_id": str(request_id),
                    "value": new_value,
                },
                ip_address=ip_address,
                user_agent=user_agent,
            )
        )

    def _required_actor(self) -> uuid.UUID:
        if self.actor_id is None:
            raise HTTPException(status_code=401, detail="Platform actor is required")
        return self.actor_id
