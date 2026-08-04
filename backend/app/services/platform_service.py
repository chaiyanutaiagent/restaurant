from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
import hmac
import uuid

from fastapi import HTTPException, status
from sqlalchemy import func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.config import settings
from app.models.audit import AuditLog
from app.models.auth import RefreshToken
from app.models.branch import Branch
from app.models.company import Company
from app.models.device import DeviceRegistration
from app.models.payment_gateway import PaymentGatewayConfig
from app.models.platform import (
    PlatformOperator,
    PlatformSession,
    PlatformTenantProfile,
    PlatformTenantUsageSnapshot,
    SaasTenantMembership,
)
from app.models.product import Product
from app.models.restaurant import Brand
from app.models.role import Permission, Role
from app.models.settings import BranchSettings
from app.models.staff_assignment import StaffRoleAssignment
from app.models.user import User
from app.schemas.platform import (
    PlatformCompanyCreate,
    PlatformCompanyDetailRead,
    PlatformCompanyListItem,
    PlatformDashboardCompanyRead,
    PlatformDashboardOnboardingRead,
    PlatformDashboardRead,
    PlatformDashboardTotalsRead,
    PlatformLifecycleAction,
    PlatformLimitStateRead,
    PlatformMfaConfirmRead,
    PlatformMfaSetupRead,
    PlatformOnboardingRead,
    PlatformOnboardingStepRead,
    PlatformOperatorRead,
    PlatformSessionRead,
    PlatformTenantControlsRead,
    PlatformTenantControlsUpdate,
    PlatformTenantExportRequest,
    PlatformTenantUsageRead,
    PlatformTenantUsageSnapshotRead,
    PlatformTokenResponse,
)
from app.services.platform_reference_projection import enqueue_reference_event
from app.services.business_directory_service import allocate_business_slug
from app.services.saas_membership_service import SaasMembershipService
from app.services.tenant_export_service import TenantExportBoundary, build_tenant_export
from app.utils.platform_security import (
    build_totp_uri,
    decrypt_totp_secret,
    encrypt_totp_secret,
    generate_opaque_credential,
    generate_recovery_codes,
    generate_totp_secret,
    hash_opaque_credential,
    hash_recovery_code,
    matching_totp_step,
)
from app.utils.security import create_platform_access_token, decode_token, hash_password, verify_password


DEFAULT_FEATURE_FLAGS = {"restaurant": True, "retail_pos": False, "takeaway": False}
DEFAULT_PLAN_LIMITS = {"brands": 1, "branches": 1, "users": 10, "devices": 3}
UNLIMITED_PLAN_LIMITS = {"brands": 0, "branches": 0, "users": 0, "devices": 0}
PRODUCT_RELEASE_STATUS = {
    "restaurant": "pilot",
    "takeaway": "planned",
    "retail_pos": "planned",
}


class PlatformAuthService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def login(
        self,
        username: str,
        password: str,
        *,
        mfa_code: str | None,
        ip_address: str | None,
        user_agent: str | None,
    ) -> tuple[PlatformTokenResponse, str]:
        now = datetime.now(timezone.utc)
        operator = await self.db.scalar(
            select(PlatformOperator).where(
                PlatformOperator.username == username,
                PlatformOperator.is_active.is_(True),
            )
        )
        if operator is not None and operator.locked_until is not None and operator.locked_until > now:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Platform login is temporarily locked",
            )
        if operator is None or not verify_password(password, operator.hashed_password):
            await self._record_failed_login(operator, now)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid username or password",
            )

        mfa_verified = False
        if operator.mfa_enabled:
            if not mfa_code:
                raise HTTPException(
                    status_code=status.HTTP_428_PRECONDITION_REQUIRED,
                    detail="MFA code is required",
                )
            if not self._consume_mfa_code(operator, mfa_code):
                await self._record_failed_login(operator, now)
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid MFA or recovery code",
                )
            mfa_verified = True

        operator.failed_login_attempts = 0
        operator.locked_until = None
        operator.last_login_at = now
        token_response, refresh_token = await self._issue_session(
            operator,
            mfa_verified=mfa_verified,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        self.db.add(
            AuditLog(
                company_id=None,
                branch_id=None,
                user_id=operator.id,
                action="platform.operator.login",
                resource="PlatformOperator",
                resource_id=str(operator.id),
                new_value={
                    "session_id": str(token_response.session_id),
                    "mfa_verified": mfa_verified,
                },
                ip_address=ip_address,
                user_agent=user_agent,
            )
        )
        await self.db.commit()
        return token_response, refresh_token

    async def refresh(
        self,
        raw_refresh_token: str,
        csrf_token: str,
        *,
        ip_address: str | None,
        user_agent: str | None,
    ) -> tuple[PlatformTokenResponse, str]:
        now = datetime.now(timezone.utc)
        session = await self.db.scalar(
            select(PlatformSession)
            .where(
                PlatformSession.refresh_token_hash
                == hash_opaque_credential(raw_refresh_token)
            )
            .with_for_update()
        )
        if session is None or session.revoked_at is not None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Platform session is invalid or revoked",
            )
        if not hmac.compare_digest(
            session.csrf_token_hash,
            hash_opaque_credential(csrf_token),
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Platform CSRF validation failed",
            )
        if session.expires_at <= now:
            session.revoked_at = now
            session.revocation_reason = "expired"
            await self.db.commit()
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Platform session has expired",
            )
        operator = await self.db.get(PlatformOperator, session.operator_id)
        if (
            operator is None
            or not operator.is_active
            or operator.credential_version != session.credential_version
            or (operator.mfa_enabled and session.mfa_verified_at is None)
        ):
            session.revoked_at = now
            session.revocation_reason = "operator-credential-changed"
            await self.db.commit()
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Platform operator credential is no longer valid",
            )

        refresh_token = generate_opaque_credential()
        next_csrf_token = generate_opaque_credential()
        session.refresh_token_hash = hash_opaque_credential(refresh_token)
        session.csrf_token_hash = hash_opaque_credential(next_csrf_token)
        session.last_seen_at = now
        session.ip_address = ip_address
        session.user_agent = user_agent
        token_response = self._token_response(operator, session, next_csrf_token)
        await self.db.commit()
        return token_response, refresh_token

    async def logout(self, *, operator_id: uuid.UUID, session_id: uuid.UUID) -> None:
        await self._revoke_session(
            operator_id=operator_id,
            session_id=session_id,
            reason="operator-logout",
        )
        self._audit(
            operator_id=operator_id,
            action="platform.operator.logout",
            resource="PlatformSession",
            resource_id=session_id,
        )
        await self.db.commit()

    async def logout_all(self, *, operator_id: uuid.UUID) -> None:
        now = datetime.now(timezone.utc)
        await self.db.execute(
            update(PlatformSession)
            .where(
                PlatformSession.operator_id == operator_id,
                PlatformSession.revoked_at.is_(None),
            )
            .values(revoked_at=now, revocation_reason="operator-logout-all")
        )
        self._audit(
            operator_id=operator_id,
            action="platform.operator.logout_all",
            resource="PlatformSession",
            resource_id=None,
        )
        await self.db.commit()

    async def list_sessions(
        self,
        *,
        operator_id: uuid.UUID,
        current_session_id: uuid.UUID,
    ) -> list[PlatformSessionRead]:
        rows = (
            await self.db.scalars(
                select(PlatformSession)
                .where(PlatformSession.operator_id == operator_id)
                .order_by(PlatformSession.created_at.desc())
                .limit(50)
            )
        ).all()
        return [
            PlatformSessionRead(
                id=row.id,
                current=row.id == current_session_id,
                created_at=row.created_at,
                last_seen_at=row.last_seen_at,
                expires_at=row.expires_at,
                mfa_verified_at=row.mfa_verified_at,
                revoked_at=row.revoked_at,
                ip_address=row.ip_address,
                user_agent=row.user_agent,
            )
            for row in rows
        ]

    async def revoke_session(
        self,
        *,
        operator_id: uuid.UUID,
        session_id: uuid.UUID,
    ) -> None:
        revoked = await self._revoke_session(
            operator_id=operator_id,
            session_id=session_id,
            reason="operator-revoked",
        )
        if not revoked:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Platform session not found",
            )
        self._audit(
            operator_id=operator_id,
            action="platform.operator.session.revoke",
            resource="PlatformSession",
            resource_id=session_id,
        )
        await self.db.commit()

    async def setup_mfa(self, *, operator_id: uuid.UUID) -> PlatformMfaSetupRead:
        operator = await self._operator(operator_id)
        if operator.mfa_enabled:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Platform MFA is already enabled",
            )
        secret = generate_totp_secret()
        operator.mfa_secret_ciphertext = encrypt_totp_secret(secret)
        operator.mfa_last_verified_step = None
        operator.mfa_recovery_code_hashes = []
        await self.db.commit()
        return PlatformMfaSetupRead(
            secret=secret,
            provisioning_uri=build_totp_uri(secret=secret, username=operator.username),
        )

    async def confirm_mfa(
        self,
        *,
        operator_id: uuid.UUID,
        session_id: uuid.UUID,
        code: str,
    ) -> PlatformMfaConfirmRead:
        operator = await self._operator(operator_id)
        if operator.mfa_enabled or not operator.mfa_secret_ciphertext:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Platform MFA setup is not pending",
            )
        secret = decrypt_totp_secret(operator.mfa_secret_ciphertext)
        verified_step = matching_totp_step(secret, code)
        if verified_step is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid MFA code",
            )
        now = datetime.now(timezone.utc)
        recovery_codes = generate_recovery_codes()
        operator.mfa_enabled_at = now
        operator.mfa_last_verified_step = verified_step
        operator.mfa_recovery_code_hashes = [
            hash_recovery_code(item) for item in recovery_codes
        ]
        session = await self.db.get(PlatformSession, session_id)
        if session is None or session.operator_id != operator_id or session.revoked_at is not None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Platform session is invalid or revoked",
            )
        session.mfa_verified_at = now
        self._audit(
            operator_id=operator_id,
            action="platform.operator.mfa.enable",
            resource="PlatformOperator",
            resource_id=operator_id,
        )
        await self.db.commit()
        return PlatformMfaConfirmRead(
            recovery_codes=recovery_codes,
            operator=PlatformOperatorRead.model_validate(operator),
        )

    async def regenerate_recovery_codes(
        self,
        *,
        operator_id: uuid.UUID,
        code: str,
    ) -> list[str]:
        operator = await self._operator(operator_id)
        if not operator.mfa_enabled or not self._consume_mfa_code(operator, code):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid MFA or recovery code",
            )
        recovery_codes = generate_recovery_codes()
        operator.mfa_recovery_code_hashes = [
            hash_recovery_code(item) for item in recovery_codes
        ]
        self._audit(
            operator_id=operator_id,
            action="platform.operator.mfa.recovery_codes.rotate",
            resource="PlatformOperator",
            resource_id=operator_id,
        )
        await self.db.commit()
        return recovery_codes

    async def disable_mfa(
        self,
        *,
        operator_id: uuid.UUID,
        password: str,
        code: str,
        current_session_id: uuid.UUID,
    ) -> PlatformOperatorRead:
        operator = await self._operator(operator_id)
        if (
            not operator.mfa_enabled
            or not verify_password(password, operator.hashed_password)
            or not self._consume_mfa_code(operator, code)
        ):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Password and MFA verification failed",
            )
        operator.mfa_secret_ciphertext = None
        operator.mfa_enabled_at = None
        operator.mfa_last_verified_step = None
        operator.mfa_recovery_code_hashes = []
        now = datetime.now(timezone.utc)
        await self.db.execute(
            update(PlatformSession)
            .where(
                PlatformSession.operator_id == operator_id,
                PlatformSession.id != current_session_id,
                PlatformSession.revoked_at.is_(None),
            )
            .values(revoked_at=now, revocation_reason="mfa-disabled")
        )
        self._audit(
            operator_id=operator_id,
            action="platform.operator.mfa.disable",
            resource="PlatformOperator",
            resource_id=operator_id,
        )
        await self.db.commit()
        return PlatformOperatorRead.model_validate(operator)

    async def change_password(
        self,
        *,
        operator_id: uuid.UUID,
        current_password: str,
        new_password: str,
        mfa_code: str | None,
    ) -> None:
        operator = await self._operator(operator_id)
        if not verify_password(current_password, operator.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Current password is invalid",
            )
        if operator.mfa_enabled and (
            not mfa_code or not self._consume_mfa_code(operator, mfa_code)
        ):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="MFA verification failed",
            )
        operator.hashed_password = hash_password(new_password)
        operator.password_changed_at = datetime.now(timezone.utc)
        operator.credential_version += 1
        await self.db.execute(
            update(PlatformSession)
            .where(
                PlatformSession.operator_id == operator_id,
                PlatformSession.revoked_at.is_(None),
            )
            .values(
                revoked_at=datetime.now(timezone.utc),
                revocation_reason="password-changed",
            )
        )
        self._audit(
            operator_id=operator_id,
            action="platform.operator.password.change",
            resource="PlatformOperator",
            resource_id=operator_id,
        )
        await self.db.commit()

    async def _issue_session(
        self,
        operator: PlatformOperator,
        *,
        mfa_verified: bool,
        ip_address: str | None,
        user_agent: str | None,
    ) -> tuple[PlatformTokenResponse, str]:
        now = datetime.now(timezone.utc)
        refresh_token = generate_opaque_credential()
        csrf_token = generate_opaque_credential()
        session = PlatformSession(
            operator_id=operator.id,
            credential_version=operator.credential_version,
            refresh_token_hash=hash_opaque_credential(refresh_token),
            csrf_token_hash=hash_opaque_credential(csrf_token),
            expires_at=now + timedelta(days=settings.refresh_token_expire_days),
            last_seen_at=now,
            mfa_verified_at=now if mfa_verified else None,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        self.db.add(session)
        await self.db.flush()
        return self._token_response(operator, session, csrf_token), refresh_token

    @staticmethod
    def _token_response(
        operator: PlatformOperator,
        session: PlatformSession,
        csrf_token: str,
    ) -> PlatformTokenResponse:
        now = datetime.now(timezone.utc)
        token = create_platform_access_token(
            operator_id=operator.id,
            session_id=session.id,
            credential_version=operator.credential_version,
            is_superuser=operator.is_superuser,
        )
        claims = decode_token(token)
        return PlatformTokenResponse(
            access_token=token,
            expires_in=max(int(claims["exp"] - now.timestamp()), 0),
            csrf_token=csrf_token,
            session_id=session.id,
            operator=PlatformOperatorRead.model_validate(operator),
        )

    async def _record_failed_login(
        self,
        operator: PlatformOperator | None,
        now: datetime,
    ) -> None:
        if operator is None:
            return
        operator.failed_login_attempts += 1
        if operator.failed_login_attempts >= settings.platform_login_max_failed_attempts:
            operator.locked_until = now + timedelta(
                minutes=settings.platform_login_lock_minutes
            )
        await self.db.commit()

    @staticmethod
    def _consume_mfa_code(operator: PlatformOperator, code: str) -> bool:
        if not operator.mfa_secret_ciphertext:
            return False
        secret = decrypt_totp_secret(operator.mfa_secret_ciphertext)
        verified_step = matching_totp_step(secret, code)
        if verified_step is not None:
            last_step = operator.mfa_last_verified_step
            if last_step is None or verified_step > last_step:
                operator.mfa_last_verified_step = verified_step
                return True
        candidate = hash_recovery_code(code)
        hashes = list(operator.mfa_recovery_code_hashes or [])
        for index, stored in enumerate(hashes):
            if hmac.compare_digest(stored, candidate):
                hashes.pop(index)
                operator.mfa_recovery_code_hashes = hashes
                return True
        return False

    async def _operator(self, operator_id: uuid.UUID) -> PlatformOperator:
        operator = await self.db.get(PlatformOperator, operator_id)
        if operator is None or not operator.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Platform operator is inactive or no longer exists",
            )
        return operator

    async def _revoke_session(
        self,
        *,
        operator_id: uuid.UUID,
        session_id: uuid.UUID,
        reason: str,
    ) -> bool:
        session = await self.db.scalar(
            select(PlatformSession).where(
                PlatformSession.id == session_id,
                PlatformSession.operator_id == operator_id,
            )
        )
        if session is None:
            return False
        if session.revoked_at is None:
            session.revoked_at = datetime.now(timezone.utc)
            session.revocation_reason = reason
        return True

    def _audit(
        self,
        *,
        operator_id: uuid.UUID,
        action: str,
        resource: str,
        resource_id: uuid.UUID | None,
    ) -> None:
        self.db.add(
            AuditLog(
                company_id=None,
                branch_id=None,
                user_id=operator_id,
                action=action,
                resource=resource,
                resource_id=str(resource_id) if resource_id else None,
            )
        )


class PlatformTenantService:
    def __init__(
        self,
        db: AsyncSession,
        *,
        restaurant_db: AsyncSession,
        operator_id: uuid.UUID,
        emit_reference_events: bool = False,
    ):
        self.db = db
        self.restaurant_db = restaurant_db
        self.operator_id = operator_id
        self.emit_reference_events = emit_reference_events

    async def dashboard(self) -> PlatformDashboardRead:
        company_rows = (
            await self.db.execute(
                select(Company, PlatformTenantProfile)
                .outerjoin(
                    PlatformTenantProfile,
                    PlatformTenantProfile.company_id == Company.id,
                )
                .order_by(Company.created_at.desc(), Company.id)
            )
        ).all()

        async def grouped_counts(session: AsyncSession, model, *filters) -> dict[uuid.UUID, int]:
            rows = (
                await session.execute(
                    select(model.company_id, func.count())
                    .where(*filters)
                    .group_by(model.company_id)
                )
            ).all()
            return {company_id: int(count) for company_id, count in rows}

        async def grouped_max(
            session: AsyncSession,
            model,
            column,
            *filters,
        ) -> dict[uuid.UUID, datetime]:
            rows = (
                await session.execute(
                    select(model.company_id, func.max(column))
                    .where(*filters)
                    .group_by(model.company_id)
                )
            ).all()
            return {company_id: value for company_id, value in rows if value is not None}

        brand_counts = await grouped_counts(self.db, Brand, Brand.is_active.is_(True))
        branch_counts = await grouped_counts(
            self.db,
            Branch,
            Branch.deleted_at.is_(None),
            Branch.is_active.is_(True),
        )
        user_counts = await grouped_counts(
            self.db,
            User,
            User.deleted_at.is_(None),
            User.is_active.is_(True),
        )
        device_counts = await grouped_counts(
            self.db,
            DeviceRegistration,
            DeviceRegistration.revoked_at.is_(None),
        )
        paired_device_counts = await grouped_counts(
            self.db,
            DeviceRegistration,
            DeviceRegistration.revoked_at.is_(None),
            DeviceRegistration.paired_at.is_not(None),
        )
        menu_counts = await grouped_counts(
            self.restaurant_db,
            Product,
            Product.deleted_at.is_(None),
            Product.is_active.is_(True),
            Product.is_for_sale.is_(True),
        )
        branch_payment_counts = await grouped_counts(
            self.restaurant_db,
            BranchSettings,
        )
        gateway_payment_counts = await grouped_counts(
            self.restaurant_db,
            PaymentGatewayConfig,
        )
        audit_activity = await grouped_max(
            self.db,
            AuditLog,
            AuditLog.created_at,
            AuditLog.company_id.is_not(None),
        )
        user_activity = await grouped_max(
            self.db,
            User,
            User.last_login_at,
            User.deleted_at.is_(None),
            User.last_login_at.is_not(None),
        )
        device_activity = await grouped_max(
            self.db,
            DeviceRegistration,
            DeviceRegistration.last_seen_at,
            DeviceRegistration.revoked_at.is_(None),
            DeviceRegistration.last_seen_at.is_not(None),
        )
        menu_activity = await grouped_max(
            self.restaurant_db,
            Product,
            Product.updated_at,
            Product.deleted_at.is_(None),
        )

        onboarding_by_company: dict[uuid.UUID, tuple[int, int]] = {}
        last_activity_by_company: dict[uuid.UUID, datetime | None] = {}
        attention_by_company: dict[uuid.UUID, list[str]] = {}
        for company, profile in company_rows:
            controls = self._controls(profile)
            counts = {
                "company": 1,
                "brand": brand_counts.get(company.id, 0),
                "branch": branch_counts.get(company.id, 0),
                "menu": menu_counts.get(company.id, 0),
                "payment": (
                    branch_payment_counts.get(company.id, 0)
                    + gateway_payment_counts.get(company.id, 0)
                ),
                "staff": user_counts.get(company.id, 0),
                "device": paired_device_counts.get(company.id, 0),
            }
            steps = self._build_onboarding_steps(
                controls=controls,
                counts=counts,
                has_payment_configuration=counts["payment"] > 0,
                registered_device_count=device_counts.get(company.id, 0),
            )
            onboarding_by_company[company.id] = (
                sum(int(step.complete) for step in steps),
                len(steps),
            )
            usage = self._usage_counts(
                brands=brand_counts.get(company.id, 0),
                branches=branch_counts.get(company.id, 0),
                users=user_counts.get(company.id, 0),
                devices=device_counts.get(company.id, 0),
                paired_devices=paired_device_counts.get(company.id, 0),
                menu_items=menu_counts.get(company.id, 0),
            )
            last_activity = self._latest_activity(
                company.updated_at,
                audit_activity.get(company.id),
                user_activity.get(company.id),
                device_activity.get(company.id),
                menu_activity.get(company.id),
            )
            last_activity_by_company[company.id] = last_activity
            attention_by_company[company.id] = self._attention_codes(
                company=company,
                controls=controls,
                usage=usage,
                onboarding=onboarding_by_company[company.id],
                last_activity_at=last_activity,
                now=datetime.now(timezone.utc),
            )

        active_rows = [(company, profile) for company, profile in company_rows if company.is_active]
        ready_companies = sum(
            int(onboarding_by_company[company.id][0] == onboarding_by_company[company.id][1])
            for company, _profile in active_rows
        )

        feature_keys = set(DEFAULT_FEATURE_FLAGS)
        for _company, profile in company_rows:
            if profile:
                feature_keys.update(profile.feature_flags)
        feature_usage = {
            key: sum(
                int(self._controls(profile).feature_flags.get(key, False))
                for company, profile in active_rows
            )
            for key in sorted(feature_keys)
        }

        plan_usage: dict[str, int] = {}
        for company, profile in active_rows:
            plan_code = self._controls(profile).plan_code
            plan_usage[plan_code] = plan_usage.get(plan_code, 0) + 1

        recent_companies = []
        for company, profile in company_rows[:6]:
            completed_steps, total_steps = onboarding_by_company[company.id]
            recent_companies.append(
                PlatformDashboardCompanyRead(
                    **self._list_item(company, profile).model_dump(),
                    onboarding_complete=completed_steps == total_steps,
                    completed_steps=completed_steps,
                    total_steps=total_steps,
                    last_activity_at=last_activity_by_company[company.id],
                    attention_codes=attention_by_company[company.id],
                )
            )

        recent_events = await self.list_audit_events(company_id=None, limit=6)
        active_companies = len(active_rows)
        attention_summary: dict[str, int] = {
            "companies": sum(int(bool(attention_by_company[company.id])) for company, _ in company_rows)
        }
        for codes in attention_by_company.values():
            for code in codes:
                attention_summary[code] = attention_summary.get(code, 0) + 1
        return PlatformDashboardRead(
            generated_at=datetime.now(timezone.utc),
            totals=PlatformDashboardTotalsRead(
                companies=len(company_rows),
                active_companies=active_companies,
                suspended_companies=len(company_rows) - active_companies,
                brands=sum(brand_counts.values()),
                branches=sum(branch_counts.values()),
                enabled_user_accounts=sum(user_counts.values()),
                devices=sum(device_counts.values()),
                paired_devices=sum(paired_device_counts.values()),
            ),
            onboarding=PlatformDashboardOnboardingRead(
                ready_companies=ready_companies,
                pending_companies=active_companies - ready_companies,
                total_active_companies=active_companies,
            ),
            product_status=PRODUCT_RELEASE_STATUS,
            attention_summary=dict(sorted(attention_summary.items())),
            feature_usage=feature_usage,
            plan_usage=dict(sorted(plan_usage.items())),
            recent_companies=recent_companies,
            recent_events=recent_events,
        )

    async def current_usage(self, company_id: uuid.UUID) -> PlatformTenantUsageRead:
        row = (
            await self.db.execute(
                select(Company, PlatformTenantProfile)
                .outerjoin(
                    PlatformTenantProfile,
                    PlatformTenantProfile.company_id == Company.id,
                )
                .where(Company.id == company_id)
            )
        ).one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")
        company, profile = row

        async def count(session: AsyncSession, model, *filters) -> int:
            return int(
                await session.scalar(
                    select(func.count()).select_from(model).where(*filters)
                )
                or 0
            )

        brands = await count(
            self.db,
            Brand,
            Brand.company_id == company_id,
            Brand.is_active.is_(True),
        )
        branches = await count(
            self.db,
            Branch,
            Branch.company_id == company_id,
            Branch.deleted_at.is_(None),
            Branch.is_active.is_(True),
        )
        users = await count(
            self.db,
            User,
            User.company_id == company_id,
            User.deleted_at.is_(None),
            User.is_active.is_(True),
        )
        devices = await count(
            self.db,
            DeviceRegistration,
            DeviceRegistration.company_id == company_id,
            DeviceRegistration.revoked_at.is_(None),
        )
        paired_devices = await count(
            self.db,
            DeviceRegistration,
            DeviceRegistration.company_id == company_id,
            DeviceRegistration.revoked_at.is_(None),
            DeviceRegistration.paired_at.is_not(None),
        )
        menu_items = await count(
            self.restaurant_db,
            Product,
            Product.company_id == company_id,
            Product.deleted_at.is_(None),
            Product.is_active.is_(True),
            Product.is_for_sale.is_(True),
        )
        payment_configurations = (
            await count(
                self.restaurant_db,
                BranchSettings,
                BranchSettings.company_id == company_id,
            )
            + await count(
                self.restaurant_db,
                PaymentGatewayConfig,
                PaymentGatewayConfig.company_id == company_id,
            )
        )
        usage = self._usage_counts(
            brands=brands,
            branches=branches,
            users=users,
            devices=devices,
            paired_devices=paired_devices,
            menu_items=menu_items,
        )
        controls = self._controls(profile)
        steps = self._build_onboarding_steps(
            controls=controls,
            counts={
                "company": 1,
                "brand": brands,
                "branch": branches,
                "menu": menu_items,
                "payment": payment_configurations,
                "staff": users,
                "device": paired_devices,
            },
            has_payment_configuration=payment_configurations > 0,
            registered_device_count=devices,
        )
        onboarding = (
            sum(int(step.complete) for step in steps),
            len(steps),
        )
        audit_activity = await self.db.scalar(
            select(func.max(AuditLog.created_at)).where(AuditLog.company_id == company_id)
        )
        user_activity = await self.db.scalar(
            select(func.max(User.last_login_at)).where(
                User.company_id == company_id,
                User.deleted_at.is_(None),
            )
        )
        device_activity = await self.db.scalar(
            select(func.max(DeviceRegistration.last_seen_at)).where(
                DeviceRegistration.company_id == company_id,
                DeviceRegistration.revoked_at.is_(None),
            )
        )
        menu_activity = await self.restaurant_db.scalar(
            select(func.max(Product.updated_at)).where(
                Product.company_id == company_id,
                Product.deleted_at.is_(None),
            )
        )
        generated_at = datetime.now(timezone.utc)
        last_activity = self._latest_activity(
            company.updated_at,
            audit_activity,
            user_activity,
            device_activity,
            menu_activity,
        )
        return PlatformTenantUsageRead(
            company_id=company_id,
            generated_at=generated_at,
            plan_code=controls.plan_code,
            feature_flags=controls.feature_flags,
            plan_limits=controls.plan_limits,
            usage=usage,
            limit_state=self._limit_state(controls=controls, usage=usage),
            attention_codes=self._attention_codes(
                company=company,
                controls=controls,
                usage=usage,
                onboarding=onboarding,
                last_activity_at=last_activity,
                now=generated_at,
            ),
            last_activity_at=last_activity,
            onboarding_completed_steps=onboarding[0],
            onboarding_total_steps=onboarding[1],
        )

    async def capture_usage_snapshots(
        self,
        *,
        ip_address: str | None,
        user_agent: str | None,
    ) -> list[PlatformTenantUsageSnapshotRead]:
        company_ids = list(await self.db.scalars(select(Company.id).order_by(Company.id)))
        captured_on = datetime.now(timezone.utc).date()
        snapshots: list[PlatformTenantUsageSnapshot] = []
        for company_id in company_ids:
            current = await self.current_usage(company_id)
            limit_state = {
                key: value.model_dump(mode="json")
                for key, value in current.limit_state.items()
            }
            values = {
                "company_id": company_id,
                "captured_on": captured_on,
                "plan_code": current.plan_code,
                "feature_flags": current.feature_flags,
                "plan_limits": current.plan_limits,
                "usage": current.usage,
                "limit_state": limit_state,
                "attention_codes": current.attention_codes,
                "last_activity_at": current.last_activity_at,
                "onboarding_completed_steps": current.onboarding_completed_steps,
                "onboarding_total_steps": current.onboarding_total_steps,
                "captured_by": self.operator_id,
            }
            statement = pg_insert(PlatformTenantUsageSnapshot).values(**values)
            snapshot_id = await self.db.scalar(
                statement.on_conflict_do_update(
                    index_elements=["company_id", "captured_on"],
                    set_={**values, "updated_at": func.now()},
                ).returning(PlatformTenantUsageSnapshot.id)
            )
            snapshot = await self.db.get(PlatformTenantUsageSnapshot, snapshot_id)
            if snapshot is None:
                raise RuntimeError("Captured Platform usage snapshot could not be reloaded")
            snapshots.append(snapshot)
        self._audit(
            company_id=None,
            action="platform.usage.snapshot.capture",
            resource_id=None,
            reason=f"Captured {len(snapshots)} aggregate Tenant usage snapshots for {captured_on}",
            old_value=None,
            new_value={
                "captured_on": captured_on.isoformat(),
                "company_count": len(snapshots),
                "aggregate_only": True,
            },
            ip_address=ip_address,
            user_agent=user_agent,
            resource="PlatformTenantUsageSnapshot",
        )
        await self.db.commit()
        return [self._usage_snapshot_read(snapshot) for snapshot in snapshots]

    async def usage_history(
        self,
        company_id: uuid.UUID,
        *,
        limit: int = 31,
    ) -> list[PlatformTenantUsageSnapshotRead]:
        if await self.db.get(Company, company_id) is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")
        rows = (
            await self.db.scalars(
                select(PlatformTenantUsageSnapshot)
                .where(PlatformTenantUsageSnapshot.company_id == company_id)
                .order_by(
                    PlatformTenantUsageSnapshot.captured_on.desc(),
                    PlatformTenantUsageSnapshot.created_at.desc(),
                )
                .limit(limit)
            )
        ).all()
        return [self._usage_snapshot_read(row) for row in rows]

    async def list_companies(
        self,
        *,
        search: str | None,
        active: bool | None,
        offset: int,
        limit: int,
    ) -> tuple[list[PlatformCompanyListItem], int]:
        filters = []
        if search and search.strip():
            pattern = f"%{search.strip()}%"
            filters.append(
                or_(
                    Company.name.ilike(pattern),
                    Company.business_slug.ilike(pattern),
                    Company.name_en.ilike(pattern),
                    Company.tax_id.ilike(pattern),
                    Company.email.ilike(pattern),
                )
            )
        if active is not None:
            filters.append(Company.is_active.is_(active))

        total = int(
            await self.db.scalar(select(func.count()).select_from(Company).where(*filters)) or 0
        )
        rows = (
            await self.db.execute(
                select(Company, PlatformTenantProfile)
                .outerjoin(
                    PlatformTenantProfile,
                    PlatformTenantProfile.company_id == Company.id,
                )
                .where(*filters)
                .order_by(Company.created_at.desc(), Company.id)
                .offset(offset)
                .limit(limit)
            )
        ).all()
        return [self._list_item(company, profile) for company, profile in rows], total

    async def create_company(self, data: PlatformCompanyCreate, *, ip_address: str | None, user_agent: str | None) -> PlatformCompanyDetailRead:
        company_id = uuid.uuid4()
        business_slug = await allocate_business_slug(
            self.db,
            requested_slug=data.business_slug,
            business_name=data.name,
            company_id=company_id,
        )
        company = Company(
            id=company_id,
            name=data.name,
            business_slug=business_slug,
            name_en=data.name_en,
            tax_id=data.tax_id,
            email=data.email,
            phone=data.phone,
            currency=data.currency,
            timezone=data.timezone,
            is_active=True,
            credential_version=1,
        )
        self.db.add(company)
        try:
            await self.db.flush()
            owner_role = Role(
                company_id=company.id,
                name="Company Owner",
                description="Initial Company-wide owner role created by Platform onboarding",
                is_system=True,
                is_branch_assignable=False,
                allowed_scope_types=["company"],
            )
            permissions = (await self.db.scalars(select(Permission).order_by(Permission.code))).all()
            owner_role.permissions = list(permissions)
            self.db.add(owner_role)
            await self.db.flush()

            owner = User(
                company_id=company.id,
                username=data.owner.username,
                email=data.owner.email,
                display_name=data.owner.display_name,
                hashed_password=hash_password(data.owner.password),
                is_active=True,
                is_superuser=False,
                password_changed_at=datetime.now(timezone.utc),
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
                    assignment_reason="Initial Company Owner created during Platform onboarding",
                    assigned_by=owner.id,
                )
            )
            profile = PlatformTenantProfile(
                company_id=company.id,
                plan_code=data.plan_code,
                feature_flags=data.feature_flags,
                plan_limits=data.plan_limits,
                created_by=self.operator_id,
            )
            self.db.add(profile)
            self._audit(
                company_id=company.id,
                action="platform.company.create",
                resource_id=company.id,
                reason=data.reason,
                old_value=None,
                new_value={
                    "name": company.name,
                    "business_slug": company.business_slug,
                    "tax_id": company.tax_id,
                    "owner_username": owner.username,
                    "plan_code": profile.plan_code,
                    "feature_flags": profile.feature_flags,
                    "plan_limits": profile.plan_limits,
                    "reason": data.reason,
                },
                ip_address=ip_address,
                user_agent=user_agent,
            )
            if self.emit_reference_events:
                await enqueue_reference_event(
                    self.db,
                    aggregate_type="company",
                    aggregate_id=company.id,
                    company_id=company.id,
                    payload={"source": "platform.company.create"},
                )
                await enqueue_reference_event(
                    self.db,
                    aggregate_type="user",
                    aggregate_id=owner.id,
                    company_id=company.id,
                    payload={"source": "platform.company.create"},
                )
            await self.db.commit()
        except IntegrityError as exc:
            await self.db.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Company or owner identity conflicts with existing data",
            ) from exc
        return await self.get_company(company.id)

    async def get_company(self, company_id: uuid.UUID) -> PlatformCompanyDetailRead:
        row = (
            await self.db.execute(
                select(Company, PlatformTenantProfile)
                .outerjoin(
                    PlatformTenantProfile,
                    PlatformTenantProfile.company_id == Company.id,
                )
                .where(Company.id == company_id)
            )
        ).one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")
        company, profile = row
        membership = await self.db.scalar(
            select(SaasTenantMembership).where(
                SaasTenantMembership.company_id == company_id
            )
        )
        onboarding = await self._onboarding(company, profile)
        controls = self._controls(profile)
        return PlatformCompanyDetailRead(
            **self._list_item(company, profile).model_dump(),
            phone=company.phone,
            currency=company.currency,
            timezone=company.timezone,
            controls=controls,
            onboarding=onboarding,
            membership=(
                SaasMembershipService.read(membership) if membership is not None else None
            ),
            suspension_reason=profile.suspension_reason if profile else None,
            reactivated_at=profile.reactivated_at if profile else None,
            reactivation_reason=profile.reactivation_reason if profile else None,
            updated_at=company.updated_at,
        )

    async def suspend_company(
        self,
        company_id: uuid.UUID,
        data: PlatformLifecycleAction,
        *,
        ip_address: str | None,
        user_agent: str | None,
    ) -> PlatformCompanyDetailRead:
        company = await self._locked_company(company_id)
        if not company.is_active:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Company is already suspended")
        now = datetime.now(timezone.utc)
        old_value = {"is_active": company.is_active, "credential_version": company.credential_version}
        company.is_active = False
        company.credential_version += 1
        profile = await self._ensure_profile(company.id)
        profile.suspended_at = now
        profile.suspended_by = self.operator_id
        profile.suspension_reason = data.reason
        profile.reactivated_at = None
        profile.reactivated_by = None
        profile.reactivation_reason = None
        await self.db.execute(
            update(RefreshToken)
            .where(
                RefreshToken.company_id == company.id,
                RefreshToken.revoked_at.is_(None),
            )
            .values(revoked_at=now)
        )
        await self.db.execute(
            update(DeviceRegistration)
            .where(DeviceRegistration.company_id == company.id)
            .values(
                credential_version=DeviceRegistration.credential_version + 1,
                refresh_credential_hash=None,
                refresh_credential_issued_at=None,
                pairing_pin_hash=None,
                pairing_expires_at=None,
                pairing_locked_until=None,
                failed_pairing_attempts=0,
                paired_at=None,
                last_seen_at=None,
            )
        )
        self._audit(
            company_id=company.id,
            action="platform.company.suspend",
            resource_id=company.id,
            reason=data.reason,
            old_value=old_value,
            new_value={
                "is_active": False,
                "credential_version": company.credential_version,
                "device_credentials_revoked": True,
                "reason": data.reason,
            },
            ip_address=ip_address,
            user_agent=user_agent,
        )
        await self._enqueue_company_event(company, "platform.company.suspend")
        await self.db.commit()
        return await self.get_company(company.id)

    async def reactivate_company(
        self,
        company_id: uuid.UUID,
        data: PlatformLifecycleAction,
        *,
        ip_address: str | None,
        user_agent: str | None,
    ) -> PlatformCompanyDetailRead:
        company = await self._locked_company(company_id)
        if company.is_active:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Company is already active")
        company.is_active = True
        profile = await self._ensure_profile(company.id)
        profile.reactivated_at = datetime.now(timezone.utc)
        profile.reactivated_by = self.operator_id
        profile.reactivation_reason = data.reason
        self._audit(
            company_id=company.id,
            action="platform.company.reactivate",
            resource_id=company.id,
            reason=data.reason,
            old_value={"is_active": False, "credential_version": company.credential_version},
            new_value={
                "is_active": True,
                "credential_version": company.credential_version,
                "devices_require_repairing": True,
                "reason": data.reason,
            },
            ip_address=ip_address,
            user_agent=user_agent,
        )
        await self._enqueue_company_event(company, "platform.company.reactivate")
        await self.db.commit()
        return await self.get_company(company.id)

    async def update_controls(
        self,
        company_id: uuid.UUID,
        data: PlatformTenantControlsUpdate,
        *,
        ip_address: str | None,
        user_agent: str | None,
    ) -> PlatformCompanyDetailRead:
        company = await self._locked_company(company_id)
        profile = await self._ensure_profile(company.id)
        old_value = self._controls(profile).model_dump()
        profile.plan_code = data.plan_code
        profile.feature_flags = data.feature_flags
        profile.plan_limits = data.plan_limits
        self._audit(
            company_id=company.id,
            action="platform.company.controls.update",
            resource_id=company.id,
            reason=data.reason,
            old_value=old_value,
            new_value={
                **self._controls(profile).model_dump(),
                "reason": data.reason,
            },
            ip_address=ip_address,
            user_agent=user_agent,
        )
        await self.db.commit()
        return await self.get_company(company.id)

    async def export_company(
        self,
        company_id: uuid.UUID,
        data: PlatformTenantExportRequest,
        *,
        ip_address: str | None,
        user_agent: str | None,
    ) -> dict[str, Any]:
        company = await self.db.get(Company, company_id)
        if company is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")
        artifact = await build_tenant_export(
            company_id,
            [
                TenantExportBoundary("identity", self.db),
                TenantExportBoundary("restaurant", self.restaurant_db),
            ],
            reason=data.reason,
            requested_by=f"platform-operator:{self.operator_id}",
        )
        self._audit(
            company_id=company.id,
            action="platform.company.export",
            resource_id=company.id,
            reason=data.reason,
            old_value=None,
            new_value={
                "format": artifact["format"],
                "format_version": artifact["format_version"],
                "content_sha256": artifact["content_sha256"],
                "boundary_count": artifact["summary"]["boundary_count"],
                "table_count": artifact["summary"]["table_count"],
                "row_count": artifact["summary"]["row_count"],
                "redacted_cells": artifact["redaction"]["redacted_cells"],
            },
            ip_address=ip_address,
            user_agent=user_agent,
        )
        await self.db.commit()
        return artifact

    async def list_audit_events(
        self,
        *,
        company_id: uuid.UUID | None,
        limit: int,
    ) -> list[dict[str, Any]]:
        statement = select(AuditLog).where(AuditLog.action.like("platform.%"))
        if company_id is not None:
            statement = statement.where(AuditLog.company_id == company_id)
        rows = (
            await self.db.scalars(
                statement.order_by(AuditLog.created_at.desc(), AuditLog.id.desc()).limit(limit)
            )
        ).all()
        return [
            {
                "id": str(row.id),
                "company_id": str(row.company_id) if row.company_id else None,
                "operator_id": str(row.user_id) if row.user_id else None,
                "action": row.action,
                "resource": row.resource,
                "resource_id": row.resource_id,
                "old_value": row.old_value,
                "new_value": row.new_value,
                "ip_address": row.ip_address,
                "created_at": row.created_at.isoformat(),
            }
            for row in rows
        ]

    async def _locked_company(self, company_id: uuid.UUID) -> Company:
        company = await self.db.scalar(
            select(Company).where(Company.id == company_id).with_for_update()
        )
        if company is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")
        return company

    async def _ensure_profile(self, company_id: uuid.UUID) -> PlatformTenantProfile:
        profile = await self.db.scalar(
            select(PlatformTenantProfile).where(PlatformTenantProfile.company_id == company_id)
        )
        if profile is None:
            profile = PlatformTenantProfile(
                company_id=company_id,
                plan_code="starter",
                feature_flags=DEFAULT_FEATURE_FLAGS.copy(),
                # Existing Companies stay unrestricted until Platform explicitly
                # assigns limits. Zero is the documented unlimited sentinel.
                plan_limits=UNLIMITED_PLAN_LIMITS.copy(),
                created_by=self.operator_id,
            )
            self.db.add(profile)
            await self.db.flush()
        return profile

    async def _enqueue_company_event(self, company: Company, source: str) -> None:
        if not self.emit_reference_events:
            return
        await self.db.flush()
        await enqueue_reference_event(
            self.db,
            aggregate_type="company",
            aggregate_id=company.id,
            company_id=company.id,
            payload={"source": source},
        )

    async def _onboarding(
        self,
        company: Company,
        profile: PlatformTenantProfile | None,
    ) -> PlatformOnboardingRead:
        company_id = company.id
        identity_counts = {
            "company": 1,
            "brand": int(
                await self.db.scalar(
                    select(func.count()).select_from(Brand).where(
                        Brand.company_id == company_id,
                        Brand.is_active.is_(True),
                    )
                )
                or 0
            ),
            "branch": int(
                await self.db.scalar(
                    select(func.count()).select_from(Branch).where(
                        Branch.company_id == company_id,
                        Branch.deleted_at.is_(None),
                        Branch.is_active.is_(True),
                    )
                )
                or 0
            ),
            "staff": int(
                await self.db.scalar(
                    select(func.count()).select_from(User).where(
                        User.company_id == company_id,
                        User.deleted_at.is_(None),
                        User.is_active.is_(True),
                    )
                )
                or 0
            ),
            "registered_device": int(
                await self.db.scalar(
                    select(func.count()).select_from(DeviceRegistration).where(
                        DeviceRegistration.company_id == company_id,
                        DeviceRegistration.revoked_at.is_(None),
                    )
                )
                or 0
            ),
            "device": int(
                await self.db.scalar(
                    select(func.count()).select_from(DeviceRegistration).where(
                        DeviceRegistration.company_id == company_id,
                        DeviceRegistration.revoked_at.is_(None),
                        DeviceRegistration.paired_at.is_not(None),
                    )
                )
                or 0
            ),
        }
        menu_count = int(
            await self.restaurant_db.scalar(
                select(func.count()).select_from(Product).where(
                    Product.company_id == company_id,
                    Product.deleted_at.is_(None),
                    Product.is_active.is_(True),
                    Product.is_for_sale.is_(True),
                )
            )
            or 0
        )
        branch_payment_count = int(
            await self.restaurant_db.scalar(
                select(func.count()).select_from(BranchSettings).where(
                    BranchSettings.company_id == company_id,
                )
            )
            or 0
        )
        gateway_payment_count = int(
            await self.restaurant_db.scalar(
                select(func.count()).select_from(PaymentGatewayConfig).where(
                    PaymentGatewayConfig.company_id == company_id,
                )
            )
            or 0
        )
        counts = {
            **identity_counts,
            "menu": menu_count,
            "payment": branch_payment_count + gateway_payment_count,
        }
        steps = self._build_onboarding_steps(
            controls=self._controls(profile),
            counts=counts,
            has_payment_configuration=counts["payment"] > 0,
            registered_device_count=identity_counts["registered_device"],
        )
        completed = sum(int(step.complete) for step in steps)
        return PlatformOnboardingRead(
            complete=completed == len(steps),
            completed_steps=completed,
            total_steps=len(steps),
            steps=steps,
        )

    @staticmethod
    def _build_onboarding_steps(
        *,
        controls: PlatformTenantControlsRead,
        counts: dict[str, int],
        has_payment_configuration: bool,
        registered_device_count: int,
    ) -> list[PlatformOnboardingStepRead]:
        labels = [
            ("product", "Restaurant pilot"),
            ("company", "Company"),
            ("brand", "Brand"),
            ("branch", "Branch"),
            ("menu", "Menu"),
            ("staff", "Staff"),
        ]
        if has_payment_configuration:
            labels.append(("payment", "Payment configuration"))
        if registered_device_count > 0:
            labels.append(("device", "Paired device"))

        normalized_counts = {
            **counts,
            "product": int(controls.feature_flags.get("restaurant", False)),
        }
        return [
            PlatformOnboardingStepRead(
                key=key,
                label=label,
                complete=normalized_counts[key] >= 1,
                count=normalized_counts[key],
                target=1,
            )
            for key, label in labels
        ]

    @staticmethod
    def _usage_counts(
        *,
        brands: int,
        branches: int,
        users: int,
        devices: int,
        paired_devices: int,
        menu_items: int,
    ) -> dict[str, int]:
        return {
            "brands": brands,
            "branches": branches,
            "enabled_user_accounts": users,
            "registered_devices": devices,
            "paired_devices": paired_devices,
            "active_menu_items": menu_items,
        }

    @staticmethod
    def _limit_state(
        *,
        controls: PlatformTenantControlsRead,
        usage: dict[str, int],
    ) -> dict[str, PlatformLimitStateRead]:
        resources = {
            "brands": "brands",
            "branches": "branches",
            "users": "enabled_user_accounts",
            "devices": "registered_devices",
        }
        result: dict[str, PlatformLimitStateRead] = {}
        for limit_key, resource_key in resources.items():
            current = int(usage.get(resource_key, 0))
            configured_limit = int(controls.plan_limits.get(limit_key, 0))
            unlimited = configured_limit == 0
            result[limit_key] = PlatformLimitStateRead(
                resource_key=resource_key,
                current=current,
                limit=None if unlimited else configured_limit,
                unlimited=unlimited,
                exceeded=False if unlimited else current > configured_limit,
                remaining=None if unlimited else max(configured_limit - current, 0),
                utilization_percent=(
                    None
                    if unlimited
                    else round((current / configured_limit) * 100)
                    if configured_limit > 0
                    else None
                ),
            )
        return result

    @staticmethod
    def _latest_activity(*values: datetime | None) -> datetime | None:
        normalized = [
            value.replace(tzinfo=timezone.utc)
            if value is not None and value.tzinfo is None
            else value.astimezone(timezone.utc)
            for value in values
            if value is not None
        ]
        return max(normalized) if normalized else None

    @classmethod
    def _attention_codes(
        cls,
        *,
        company: Company,
        controls: PlatformTenantControlsRead,
        usage: dict[str, int],
        onboarding: tuple[int, int],
        last_activity_at: datetime | None,
        now: datetime,
    ) -> list[str]:
        codes: list[str] = []
        if not company.is_active:
            codes.append("suspended")
        if onboarding[0] < onboarding[1]:
            codes.append("onboarding_pending")
        for key, state in cls._limit_state(controls=controls, usage=usage).items():
            if state.exceeded:
                codes.append(f"limit_exceeded:{key}")
        if usage.get("registered_devices", 0) > usage.get("paired_devices", 0):
            codes.append("unpaired_devices")
        planned_enabled = any(
            lifecycle == "planned" and controls.feature_flags.get(key, False)
            for key, lifecycle in PRODUCT_RELEASE_STATUS.items()
        )
        if planned_enabled:
            codes.append("planned_feature_configured")
        stale_before = now - timedelta(days=14)
        created_at = cls._latest_activity(company.created_at)
        if (
            created_at is not None
            and created_at <= stale_before
            and (last_activity_at is None or last_activity_at <= stale_before)
        ):
            codes.append("stale_activity")
        return sorted(codes)

    @staticmethod
    def _usage_snapshot_read(
        snapshot: PlatformTenantUsageSnapshot,
    ) -> PlatformTenantUsageSnapshotRead:
        return PlatformTenantUsageSnapshotRead.model_validate(snapshot)

    @staticmethod
    def _controls(profile: PlatformTenantProfile | None) -> PlatformTenantControlsRead:
        return PlatformTenantControlsRead(
            plan_code=profile.plan_code if profile else "starter",
            feature_flags=dict(profile.feature_flags) if profile else DEFAULT_FEATURE_FLAGS.copy(),
            plan_limits=dict(profile.plan_limits) if profile else UNLIMITED_PLAN_LIMITS.copy(),
        )

    @classmethod
    def _list_item(
        cls,
        company: Company,
        profile: PlatformTenantProfile | None,
    ) -> PlatformCompanyListItem:
        controls = cls._controls(profile)
        return PlatformCompanyListItem(
            id=company.id,
            name=company.name,
            business_slug=company.business_slug,
            name_en=company.name_en,
            tax_id=company.tax_id,
            email=company.email,
            is_active=company.is_active,
            credential_version=company.credential_version,
            plan_code=controls.plan_code,
            created_at=company.created_at,
            suspended_at=profile.suspended_at if profile else None,
        )

    def _audit(
        self,
        *,
        company_id: uuid.UUID | None,
        action: str,
        resource_id: uuid.UUID | None,
        reason: str,
        old_value: dict[str, Any] | None,
        new_value: dict[str, Any],
        ip_address: str | None,
        user_agent: str | None,
        resource: str = "Company",
    ) -> None:
        self.db.add(
            AuditLog(
                company_id=company_id,
                branch_id=None,
                user_id=self.operator_id,
                action=action,
                resource=resource,
                resource_id=str(resource_id) if resource_id else None,
                old_value=old_value,
                new_value={**new_value, "reason": reason},
                ip_address=ip_address,
                user_agent=user_agent,
            )
        )
