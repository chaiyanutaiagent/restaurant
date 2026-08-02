from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
import uuid

from fastapi import HTTPException, status
from sqlalchemy import func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.audit import AuditLog
from app.models.auth import RefreshToken
from app.models.branch import Branch
from app.models.company import Company
from app.models.device import DeviceRegistration
from app.models.payment_gateway import PaymentGatewayConfig
from app.models.platform import PlatformOperator, PlatformTenantProfile
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
    PlatformOnboardingRead,
    PlatformOnboardingStepRead,
    PlatformOperatorRead,
    PlatformTenantControlsRead,
    PlatformTenantControlsUpdate,
    PlatformTenantExportRequest,
    PlatformTokenResponse,
)
from app.services.platform_reference_projection import enqueue_reference_event
from app.services.tenant_export_service import TenantExportBoundary, build_tenant_export
from app.utils.security import create_platform_access_token, decode_token, hash_password, verify_password


DEFAULT_FEATURE_FLAGS = {"restaurant": True, "retail_pos": False, "takeaway": False}
DEFAULT_PLAN_LIMITS = {"brands": 1, "branches": 1, "users": 10, "devices": 3}
UNLIMITED_PLAN_LIMITS = {"brands": 0, "branches": 0, "users": 0, "devices": 0}


class PlatformAuthService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def login(
        self,
        username: str,
        password: str,
        *,
        ip_address: str | None,
        user_agent: str | None,
    ) -> PlatformTokenResponse:
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
            if operator is not None:
                operator.failed_login_attempts += 1
                if operator.failed_login_attempts >= settings.platform_login_max_failed_attempts:
                    operator.locked_until = now + timedelta(
                        minutes=settings.platform_login_lock_minutes
                    )
                await self.db.commit()
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid username or password",
            )

        operator.failed_login_attempts = 0
        operator.locked_until = None
        operator.last_login_at = now
        token = create_platform_access_token(
            operator_id=operator.id,
            credential_version=operator.credential_version,
            is_superuser=operator.is_superuser,
        )
        self.db.add(
            AuditLog(
                company_id=None,
                branch_id=None,
                user_id=operator.id,
                action="platform.operator.login",
                resource="PlatformOperator",
                resource_id=str(operator.id),
                ip_address=ip_address,
                user_agent=user_agent,
            )
        )
        await self.db.commit()
        claims = decode_token(token)
        expires_in = max(int(claims["exp"] - now.timestamp()), 0)
        return PlatformTokenResponse(
            access_token=token,
            expires_in=expires_in,
            operator=PlatformOperatorRead.model_validate(operator),
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
            BranchSettings.promptpay_target.is_not(None),
        )
        gateway_payment_counts = await grouped_counts(
            self.restaurant_db,
            PaymentGatewayConfig,
            or_(
                PaymentGatewayConfig.promptpay_target.is_not(None),
                PaymentGatewayConfig.omise_enabled.is_(True),
                PaymentGatewayConfig.twoc2p_enabled.is_(True),
                PaymentGatewayConfig.scb_enabled.is_(True),
            ),
        )

        onboarding_by_company: dict[uuid.UUID, tuple[int, int]] = {}
        for company, _profile in company_rows:
            completed_steps = sum(
                (
                    1,
                    int(brand_counts.get(company.id, 0) > 0),
                    int(branch_counts.get(company.id, 0) > 0),
                    int(menu_counts.get(company.id, 0) > 0),
                    int(
                        branch_payment_counts.get(company.id, 0)
                        + gateway_payment_counts.get(company.id, 0)
                        > 0
                    ),
                    int(user_counts.get(company.id, 0) > 0),
                    int(paired_device_counts.get(company.id, 0) > 0),
                )
            )
            onboarding_by_company[company.id] = (completed_steps, 7)

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
                )
            )

        recent_events = await self.list_audit_events(company_id=None, limit=6)
        active_companies = len(active_rows)
        return PlatformDashboardRead(
            generated_at=datetime.now(timezone.utc),
            totals=PlatformDashboardTotalsRead(
                companies=len(company_rows),
                active_companies=active_companies,
                suspended_companies=len(company_rows) - active_companies,
                brands=sum(brand_counts.values()),
                branches=sum(branch_counts.values()),
                active_users=sum(user_counts.values()),
                devices=sum(device_counts.values()),
                paired_devices=sum(paired_device_counts.values()),
            ),
            onboarding=PlatformDashboardOnboardingRead(
                ready_companies=ready_companies,
                pending_companies=active_companies - ready_companies,
                total_active_companies=active_companies,
            ),
            feature_usage=feature_usage,
            plan_usage=dict(sorted(plan_usage.items())),
            recent_companies=recent_companies,
            recent_events=recent_events,
        )

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
        company = Company(
            name=data.name,
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
        onboarding = await self._onboarding(company)
        controls = self._controls(profile)
        return PlatformCompanyDetailRead(
            **self._list_item(company, profile).model_dump(),
            phone=company.phone,
            currency=company.currency,
            timezone=company.timezone,
            controls=controls,
            onboarding=onboarding,
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

    async def _onboarding(self, company: Company) -> PlatformOnboardingRead:
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
                    BranchSettings.promptpay_target.is_not(None),
                )
            )
            or 0
        )
        gateway_payment_count = int(
            await self.restaurant_db.scalar(
                select(func.count()).select_from(PaymentGatewayConfig).where(
                    PaymentGatewayConfig.company_id == company_id,
                    or_(
                        PaymentGatewayConfig.promptpay_target.is_not(None),
                        PaymentGatewayConfig.omise_enabled.is_(True),
                        PaymentGatewayConfig.twoc2p_enabled.is_(True),
                        PaymentGatewayConfig.scb_enabled.is_(True),
                    ),
                )
            )
            or 0
        )
        counts = {
            **identity_counts,
            "menu": menu_count,
            "payment": branch_payment_count + gateway_payment_count,
        }
        labels = (
            ("company", "Company"),
            ("brand", "Brand"),
            ("branch", "Branch"),
            ("menu", "Menu"),
            ("payment", "Payment"),
            ("staff", "Staff"),
            ("device", "Device"),
        )
        steps = [
            PlatformOnboardingStepRead(
                key=key,
                label=label,
                complete=counts[key] >= 1,
                count=counts[key],
                target=1,
            )
            for key, label in labels
        ]
        completed = sum(int(step.complete) for step in steps)
        return PlatformOnboardingRead(
            complete=completed == len(steps),
            completed_steps=completed,
            total_steps=len(steps),
            steps=steps,
        )

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
        company_id: uuid.UUID,
        action: str,
        resource_id: uuid.UUID,
        reason: str,
        old_value: dict[str, Any] | None,
        new_value: dict[str, Any],
        ip_address: str | None,
        user_agent: str | None,
    ) -> None:
        self.db.add(
            AuditLog(
                company_id=company_id,
                branch_id=None,
                user_id=self.operator_id,
                action=action,
                resource="Company",
                resource_id=str(resource_id),
                old_value=old_value,
                new_value={**new_value, "reason": reason},
                ip_address=ip_address,
                user_agent=user_agent,
            )
        )
