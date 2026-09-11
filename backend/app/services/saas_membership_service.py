from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import secrets
import uuid

from fastapi import HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.audit import AuditLog
from app.models.auth import RefreshToken
from app.models.company import Company
from app.models.platform import (
    PlatformTenantProfile,
    SaasAccountCredential,
    SaasTenantMembership,
)
from app.models.role import Permission, Role
from app.models.staff_assignment import StaffRoleAssignment
from app.models.user import User
from app.schemas.membership import SaasMembershipRead, SaasSignupRequest
from app.utils.security import hash_password
from app.services.business_directory_service import allocate_business_slug
from app.services.platform_reference_projection import enqueue_reference_event
from app.services.saas_billing_service import ensure_starter_subscription


TERMS_VERSION = "2026-08-03"
PRIVACY_VERSION = "2026-08-03"
DEFAULT_FEATURE_FLAGS = {"restaurant": True, "retail_pos": False, "takeaway": False}
DEFAULT_PLAN_LIMITS = {"brands": 1, "branches": 1, "users": 10, "devices": 3}


def hash_account_credential(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def effective_membership_status(
    membership: SaasTenantMembership,
    *,
    now: datetime | None = None,
) -> str:
    current = now or datetime.now(timezone.utc)
    trial_end = membership.trial_ends_at
    if trial_end is not None and trial_end.tzinfo is None:
        trial_end = trial_end.replace(tzinfo=timezone.utc)
    if membership.status == "trial_active" and trial_end is not None and trial_end <= current:
        return "trial_expired"
    return membership.status


def membership_access_error(membership: SaasTenantMembership) -> str | None:
    status_value = effective_membership_status(membership)
    return {
        "pending_verification": "Email verification is required",
        "trial_expired": "SaaS trial has expired",
        "suspended": "SaaS membership is suspended",
        "cancelled": "SaaS membership is cancelled",
    }.get(status_value)


class SaasMembershipService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def signup(
        self,
        data: SaasSignupRequest,
        *,
        ip_address: str | None,
        user_agent: str | None,
    ) -> tuple[SaasTenantMembership, str]:
        now = datetime.now(timezone.utc)
        company_id = uuid.uuid4()
        business_slug = await allocate_business_slug(
            self.db,
            requested_slug=data.business_slug,
            business_name=data.company_name,
            company_id=company_id,
        )
        company = Company(
            id=company_id,
            name=data.company_name,
            business_slug=business_slug,
            email=data.owner_email,
            phone=data.phone,
            is_active=True,
            credential_version=1,
        )
        self.db.add(company)
        try:
            await self.db.flush()
            owner_role = Role(
                company_id=company.id,
                name="Company Owner",
                description="Self-service Restaurant SaaS owner",
                is_system=True,
                is_branch_assignable=False,
                allowed_scope_types=["company"],
            )
            owner_role.permissions = list(
                (await self.db.scalars(select(Permission).order_by(Permission.code))).all()
            )
            self.db.add(owner_role)
            await self.db.flush()
            owner = User(
                company_id=company.id,
                username=data.username,
                email=data.owner_email,
                display_name=data.owner_display_name,
                hashed_password=hash_password(data.password),
                is_active=True,
                is_superuser=False,
                password_changed_at=now,
            )
            self.db.add(owner)
            await self.db.flush()
            self.db.add(
                StaffRoleAssignment(
                    company_id=company.id,
                    user_id=owner.id,
                    role_id=owner_role.id,
                    scope_type="company",
                    scope_key=str(company.id),
                    assignment_reason="Self-service SaaS Company Owner signup",
                    assigned_by=owner.id,
                )
            )
            self.db.add(
                PlatformTenantProfile(
                    company_id=company.id,
                    plan_code="starter",
                    feature_flags=DEFAULT_FEATURE_FLAGS.copy(),
                    plan_limits=DEFAULT_PLAN_LIMITS.copy(),
                    created_by=None,
                )
            )
            membership = SaasTenantMembership(
                company_id=company.id,
                owner_user_id=owner.id,
                owner_email=data.owner_email,
                status="pending_verification",
                onboarding_state="awaiting_verification",
                terms_version=TERMS_VERSION,
                privacy_version=PRIVACY_VERSION,
                accepted_at=now,
            )
            self.db.add(membership)
            await self.db.flush()
            await ensure_starter_subscription(
                self.db,
                company_id=company.id,
                subscription_status="incomplete",
            )
            raw_token = await self._issue_credential(
                membership,
                purpose="verify_email",
                expires_at=now + timedelta(hours=settings.saas_verification_expire_hours),
                request_ip=ip_address,
            )
            self.db.add(
                AuditLog(
                    company_id=company.id,
                    user_id=owner.id,
                    action="saas.membership.signup",
                    resource="SaasTenantMembership",
                    resource_id=str(membership.id),
                    new_value={
                        "status": membership.status,
                        "business_slug": company.business_slug,
                        "terms_version": TERMS_VERSION,
                        "privacy_version": PRIVACY_VERSION,
                    },
                    ip_address=ip_address,
                    user_agent=user_agent,
                )
            )
            if settings.identity_database == "platform_core":
                await enqueue_reference_event(
                    self.db,
                    aggregate_type="company",
                    aggregate_id=company.id,
                    company_id=company.id,
                    payload={"source": "saas.membership.signup"},
                )
                await enqueue_reference_event(
                    self.db,
                    aggregate_type="user",
                    aggregate_id=owner.id,
                    company_id=company.id,
                    payload={"source": "saas.membership.signup"},
                )
            await self.db.commit()
            return membership, raw_token
        except IntegrityError as exc:
            await self.db.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A SaaS owner account with these identifiers already exists",
            ) from exc

    async def request_verification(
        self,
        email: str,
        *,
        request_ip: str | None,
    ) -> tuple[SaasTenantMembership, str] | None:
        membership = await self.db.scalar(
            select(SaasTenantMembership).where(SaasTenantMembership.owner_email == email)
        )
        if membership is None or membership.status != "pending_verification":
            return None
        now = datetime.now(timezone.utc)
        raw_token = await self._issue_credential(
            membership,
            purpose="verify_email",
            expires_at=now + timedelta(hours=settings.saas_verification_expire_hours),
            request_ip=request_ip,
        )
        await self.db.commit()
        return membership, raw_token

    async def verify_email(self, raw_token: str) -> SaasTenantMembership:
        credential = await self._valid_credential(raw_token, purpose="verify_email")
        membership = await self.db.scalar(
            select(SaasTenantMembership).where(
                SaasTenantMembership.company_id == credential.company_id
            )
        )
        if membership is None:
            raise self._invalid_credential()
        now = datetime.now(timezone.utc)
        if membership.email_verified_at is not None:
            raise self._invalid_credential()
        credential.used_at = now
        membership.email_verified_at = now
        membership.trial_started_at = now
        membership.trial_ends_at = now + timedelta(days=settings.saas_trial_days)
        membership.status = "trial_active"
        membership.onboarding_state = "setup_required"
        subscription = await ensure_starter_subscription(
            self.db,
            company_id=membership.company_id,
        )
        subscription.status = "trialing"
        subscription.trial_started_at = membership.trial_started_at
        subscription.trial_ends_at = membership.trial_ends_at
        subscription.current_period_start = membership.trial_started_at
        subscription.current_period_end = membership.trial_ends_at
        self.db.add(
            AuditLog(
                company_id=membership.company_id,
                user_id=membership.owner_user_id,
                action="saas.membership.email_verified",
                resource="SaasTenantMembership",
                resource_id=str(membership.id),
                new_value={
                    "status": membership.status,
                    "trial_ends_at": membership.trial_ends_at.isoformat(),
                },
            )
        )
        await self.db.commit()
        return membership

    async def request_password_reset(
        self,
        email: str,
        *,
        request_ip: str | None,
    ) -> tuple[SaasTenantMembership, str] | None:
        membership = await self.db.scalar(
            select(SaasTenantMembership).where(SaasTenantMembership.owner_email == email)
        )
        if membership is None or membership.email_verified_at is None:
            return None
        if effective_membership_status(membership) in {"cancelled"}:
            return None
        now = datetime.now(timezone.utc)
        raw_token = await self._issue_credential(
            membership,
            purpose="reset_password",
            expires_at=now + timedelta(minutes=settings.saas_password_reset_expire_minutes),
            request_ip=request_ip,
        )
        await self.db.commit()
        return membership, raw_token

    async def reset_password(
        self,
        raw_token: str,
        new_password: str,
        *,
        ip_address: str | None,
        user_agent: str | None,
    ) -> SaasTenantMembership:
        credential = await self._valid_credential(raw_token, purpose="reset_password")
        membership = await self.db.scalar(
            select(SaasTenantMembership).where(
                SaasTenantMembership.company_id == credential.company_id
            )
        )
        user = await self.db.get(User, credential.owner_user_id)
        if membership is None or user is None:
            raise self._invalid_credential()
        if new_password.lower() in {user.username.lower(), membership.owner_email.lower()}:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Password must not match account identifiers",
            )
        now = datetime.now(timezone.utc)
        credential.used_at = now
        user.hashed_password = hash_password(new_password)
        user.password_changed_at = now
        await self.db.execute(
            update(RefreshToken)
            .where(
                RefreshToken.user_id == user.id,
                RefreshToken.revoked_at.is_(None),
            )
            .values(revoked_at=now)
        )
        self.db.add(
            AuditLog(
                company_id=membership.company_id,
                user_id=user.id,
                action="saas.membership.password_reset",
                resource="User",
                resource_id=str(user.id),
                ip_address=ip_address,
                user_agent=user_agent,
            )
        )
        await self.db.commit()
        return membership

    async def membership_for_company(
        self,
        company_id: uuid.UUID,
    ) -> SaasTenantMembership | None:
        return await self.db.scalar(
            select(SaasTenantMembership).where(SaasTenantMembership.company_id == company_id)
        )

    @staticmethod
    def read(membership: SaasTenantMembership) -> SaasMembershipRead:
        status_value = effective_membership_status(membership)
        remaining: int | None = None
        if membership.trial_ends_at is not None:
            trial_end = membership.trial_ends_at
            if trial_end.tzinfo is None:
                trial_end = trial_end.replace(tzinfo=timezone.utc)
            seconds = (trial_end - datetime.now(timezone.utc)).total_seconds()
            remaining = max(0, int((seconds + 86_399) // 86_400))
        return SaasMembershipRead(
            company_id=membership.company_id,
            owner_email=membership.owner_email,
            status=status_value,
            onboarding_state=membership.onboarding_state,
            email_verified_at=membership.email_verified_at,
            trial_started_at=membership.trial_started_at,
            trial_ends_at=membership.trial_ends_at,
            trial_days_remaining=remaining,
        )

    async def _issue_credential(
        self,
        membership: SaasTenantMembership,
        *,
        purpose: str,
        expires_at: datetime,
        request_ip: str | None,
    ) -> str:
        now = datetime.now(timezone.utc)
        await self.db.execute(
            update(SaasAccountCredential)
            .where(
                SaasAccountCredential.company_id == membership.company_id,
                SaasAccountCredential.purpose == purpose,
                SaasAccountCredential.used_at.is_(None),
            )
            .values(used_at=now)
        )
        raw_token = secrets.token_urlsafe(32)
        self.db.add(
            SaasAccountCredential(
                company_id=membership.company_id,
                owner_user_id=membership.owner_user_id,
                purpose=purpose,
                token_hash=hash_account_credential(raw_token),
                expires_at=expires_at,
                request_ip=request_ip,
            )
        )
        await self.db.flush()
        return raw_token

    async def _valid_credential(
        self,
        raw_token: str,
        *,
        purpose: str,
    ) -> SaasAccountCredential:
        now = datetime.now(timezone.utc)
        credential = await self.db.scalar(
            select(SaasAccountCredential)
            .where(
                SaasAccountCredential.token_hash == hash_account_credential(raw_token),
                SaasAccountCredential.purpose == purpose,
                SaasAccountCredential.used_at.is_(None),
                SaasAccountCredential.expires_at > now,
            )
            .with_for_update()
        )
        if credential is None:
            raise self._invalid_credential()
        return credential

    @staticmethod
    def _invalid_credential() -> HTTPException:
        return HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Account credential is invalid or expired",
        )
