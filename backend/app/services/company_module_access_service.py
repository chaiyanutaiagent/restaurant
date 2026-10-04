from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal
import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.audit import AuditLog
from app.models.company import Company
from app.models.platform import PlatformTenantProfile
from app.models.saas_billing import SaasPlan
from app.schemas.module_access import (
    CompanyModuleAction,
    CompanyModuleAccessRead,
    CompanyModuleAccessUpdate,
    CompanyModuleKey,
    CompanyProductReadiness,
)


@dataclass(frozen=True)
class CompanyModuleDefinition:
    key: CompanyModuleKey
    lifecycle: Literal["active", "dark_launch", "planned"]
    readiness: CompanyProductReadiness
    legacy_keys: tuple[str, ...]
    permission_hints: tuple[str, ...]
    default_company_enabled: bool
    default_plan_included: bool


COMPANY_MODULE_CATALOG: tuple[CompanyModuleDefinition, ...] = (
    CompanyModuleDefinition("erp", "active", "production", (), (), True, True),
    CompanyModuleDefinition(
        "central_kitchen",
        "active",
        "read_only",
        ("restaurant",),
        (
            "company.kitchen.view",
            "company.kitchen.manage",
            "company.distribution.view",
            "company.distribution.manage",
            "brand.central.raw_stock.view",
            "brand.central.ready_stock.view",
            "brand.central.production.view",
            "brand.central.production.manage",
            "fb.kitchen.manage",
        ),
        True,
        False,
    ),
    CompanyModuleDefinition(
        "restaurant_pos",
        "active",
        "pilot",
        ("restaurant",),
        (
            "fb.menu.view",
            "fb.table.manage",
            "fb.order.create",
            "fb.kitchen.ticket.manage",
            "fb.kitchen.manage",
            "fb.recipe.manage",
            "fb.report.view",
            "fb.settings.manage",
            "brand.store.order.create",
        ),
        True,
        False,
    ),
    CompanyModuleDefinition(
        "takeaway_pos",
        "dark_launch",
        "dark_launch",
        ("takeaway",),
        (
            "takeaway.catalog.view",
            "takeaway.sale.create",
            "takeaway.kitchen.manage",
            "takeaway.pickup.manage",
        ),
        False,
        False,
    ),
    CompanyModuleDefinition(
        "retail_pos",
        "active",
        "pilot",
        (),
        ("pos.sale.create", "pos.sale.view", "pos.report.view"),
        False,
        False,
    ),
    CompanyModuleDefinition("hotel_pms", "planned", "planned", (), (), False, False),
)
COMPANY_MODULES_BY_KEY = {module.key: module for module in COMPANY_MODULE_CATALOG}
DEFAULT_LEGACY_FEATURE_FLAGS = {
    "restaurant": True,
    "retail_pos": False,
    "takeaway": False,
}
UNLIMITED_PLAN_LIMITS = {"brands": 0, "branches": 0, "users": 0, "devices": 0}


def company_module_definition(module_key: str) -> CompanyModuleDefinition:
    definition = COMPANY_MODULES_BY_KEY.get(module_key)
    if definition is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown Company module: {module_key}",
        )
    return definition


def synchronize_legacy_module_flags(flags: dict[str, bool]) -> dict[str, bool]:
    normalized = dict(flags)
    for canonical_key, legacy_key in (
        ("restaurant_pos", "restaurant"),
        ("takeaway_pos", "takeaway"),
    ):
        if canonical_key in normalized:
            normalized[legacy_key] = normalized[canonical_key]
    return normalized


def _flag_value(
    flags: dict[str, bool],
    definition: CompanyModuleDefinition,
    *,
    default: bool,
) -> bool:
    for key in (definition.key, *definition.legacy_keys):
        if key in flags:
            return bool(flags[key])
    return default


def _runtime_ready(definition: CompanyModuleDefinition) -> bool:
    if definition.key == "takeaway_pos":
        return settings.takeaway_feature_enabled
    if definition.key == "hotel_pms":
        return False
    return True


def canonical_runtime_environment(environment: str) -> Literal["production", "uat"]:
    return "production" if environment == "production" else "uat"


def module_readiness(definition: CompanyModuleDefinition) -> CompanyProductReadiness:
    if definition.key == "retail_pos" and settings.retail_service_database == "legacy":
        return "legacy"
    if definition.key == "central_kitchen":
        if settings.company_kitchen_writes_enabled and settings.company_distribution_writes_enabled:
            return "pilot"
        return "read_only"
    return definition.readiness


def module_data_source(definition: CompanyModuleDefinition) -> str:
    if definition.key == "retail_pos":
        return settings.retail_service_database
    if definition.key == "takeaway_pos":
        return settings.takeaway_service_database
    if definition.key == "restaurant_pos":
        return settings.restaurant_service_database
    if definition.key == "central_kitchen":
        return settings.restaurant_service_database
    return settings.identity_database


def module_allowed_actions(
    definition: CompanyModuleDefinition,
    *,
    readiness: CompanyProductReadiness,
    effective_access: bool,
    permissions: list[str] | None,
) -> list[CompanyModuleAction]:
    if not effective_access or readiness in {"planned", "dark_launch"}:
        return []

    allowed: list[CompanyModuleAction] = ["view"]
    if readiness == "read_only":
        return ["view", "export"]

    permission_set = {"*"} if permissions is None else set(permissions)
    if "*" in permission_set:
        return ["view", "create", "update", "approve", "refund", "export", "suspend", "execute"]

    if definition.key == "restaurant_pos":
        permission_set = {
            code
            for code in permission_set
            if code.startswith(("fb.", "brand.store."))
        }
    elif definition.key == "takeaway_pos":
        permission_set = {code for code in permission_set if code.startswith("takeaway.")}
    elif definition.key == "retail_pos":
        permission_set = {code for code in permission_set if code.startswith("pos.")}
    elif definition.key == "central_kitchen":
        permission_set = {
            code
            for code in permission_set
            if code.startswith(("company.kitchen.", "company.distribution.", "brand.central."))
        }
    elif definition.key == "erp":
        permission_set = {
            code
            for code in permission_set
            if not code.startswith(("fb.", "takeaway.", "brand.store.", "brand.central."))
        }

    if any(code.endswith((".create", ".manage", ".edit")) for code in permission_set):
        allowed.extend(["create", "update"])
    if any(code.endswith(".approve") for code in permission_set):
        allowed.append("approve")
    if any("refund" in code and not code.endswith(".request") for code in permission_set):
        allowed.append("refund")
    if any(code.endswith((".report.view", ".export")) for code in permission_set):
        allowed.append("export")
    if any(code.endswith(".manage") for code in permission_set):
        allowed.append("execute")
    return list(dict.fromkeys(allowed))


def _user_permitted(
    definition: CompanyModuleDefinition,
    permissions: list[str] | None,
) -> bool:
    # Platform views have no tenant permission scope and inspect Company-level state.
    if permissions is None or not definition.permission_hints:
        return True
    return "*" in permissions or any(
        permission in permissions for permission in definition.permission_hints
    )


def evaluate_company_module_access(
    definition: CompanyModuleDefinition,
    *,
    company_active: bool,
    company_flags: dict[str, bool],
    plan_flags: dict[str, bool],
    permissions: list[str] | None,
) -> tuple[bool, bool, bool, bool, str]:
    company_enabled = _flag_value(
        company_flags,
        definition,
        default=definition.default_company_enabled,
    )
    plan_included = _flag_value(
        plan_flags,
        definition,
        default=definition.default_plan_included,
    )
    runtime_ready = _runtime_ready(definition)
    user_permitted = _user_permitted(definition, permissions)

    if not company_active:
        reason = "company_inactive"
    elif definition.lifecycle == "planned":
        reason = "lifecycle_planned"
    elif not plan_included:
        reason = "not_in_plan"
    elif not company_enabled:
        reason = "company_disabled"
    elif not runtime_ready:
        reason = "runtime_unavailable"
    elif not user_permitted:
        reason = "permission_denied"
    else:
        reason = "enabled"
    return (
        company_enabled,
        plan_included,
        runtime_ready,
        user_permitted,
        reason,
    )


class CompanyModuleAccessService:
    def __init__(self, db: AsyncSession, *, operator_id: uuid.UUID | None = None):
        self.db = db
        self.operator_id = operator_id

    async def list_for_company(
        self,
        company_id: uuid.UUID,
        *,
        permissions: list[str] | None,
        include_audit: bool = False,
    ) -> list[CompanyModuleAccessRead]:
        company = await self.db.get(Company, company_id)
        if company is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")
        profile = await self.db.scalar(
            select(PlatformTenantProfile).where(
                PlatformTenantProfile.company_id == company_id
            )
        )
        plan_code = profile.plan_code if profile else "starter"
        plan = await self.db.scalar(select(SaasPlan).where(SaasPlan.code == plan_code))
        company_flags = (
            dict(profile.feature_flags) if profile else DEFAULT_LEGACY_FEATURE_FLAGS.copy()
        )
        plan_flags = (
            dict(plan.feature_flags)
            if plan is not None
            else (
                # Before SaaS plans existed, the tenant profile was the only
                # source of feature truth. Preserve those Companies until a
                # real plan is assigned instead of silently removing access.
                company_flags.copy()
                if profile is not None
                else DEFAULT_LEGACY_FEATURE_FLAGS.copy()
            )
        )
        audit_by_module = (
            await self._latest_module_audits(company_id) if include_audit else {}
        )

        result: list[CompanyModuleAccessRead] = []
        for definition in COMPANY_MODULE_CATALOG:
            (
                company_enabled,
                plan_included,
                runtime_ready,
                user_permitted,
                reason,
            ) = evaluate_company_module_access(
                definition,
                company_active=company.is_active,
                company_flags=company_flags,
                plan_flags=plan_flags,
                permissions=permissions,
            )
            audit = audit_by_module.get(definition.key)
            readiness = module_readiness(definition)
            effective_access = reason == "enabled"
            updated_at = (
                audit.created_at
                if audit is not None
                else profile.updated_at
                if profile is not None
                else company.updated_at
            )
            result.append(
                CompanyModuleAccessRead(
                    module_key=definition.key,
                    lifecycle=definition.lifecycle,
                    readiness=readiness,
                    environment=canonical_runtime_environment(settings.environment),
                    company_enabled=company_enabled,
                    plan_included=plan_included,
                    runtime_ready=runtime_ready,
                    user_permitted=user_permitted,
                    effective_access=effective_access,
                    reason_code=reason,
                    allowed_actions=module_allowed_actions(
                        definition,
                        readiness=readiness,
                        effective_access=effective_access,
                        permissions=permissions,
                    ),
                    enabled_branch_ids=[],
                    branch_scope="all" if company_enabled else "none",
                    feature_flags={
                        definition.key: company_enabled,
                        "runtime_ready": runtime_ready,
                    },
                    data_source=module_data_source(definition),
                    status_reason=(
                        (audit.new_value or {}).get("reason")
                        if audit is not None
                        else reason
                    ),
                    updated_at=updated_at,
                    updated_by=(audit.user_id if audit is not None else None),
                    audit_id=(audit.id if audit is not None else None),
                )
            )
        return result

    async def update_company_module(
        self,
        company_id: uuid.UUID,
        module_key: str,
        data: CompanyModuleAccessUpdate,
        *,
        ip_address: str | None,
        user_agent: str | None,
    ) -> CompanyModuleAccessRead:
        if self.operator_id is None:
            raise RuntimeError("Platform operator is required to update Company modules")
        definition = company_module_definition(module_key)
        company = await self.db.scalar(
            select(Company).where(Company.id == company_id).with_for_update()
        )
        if company is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")
        profile = await self.db.scalar(
            select(PlatformTenantProfile)
            .where(PlatformTenantProfile.company_id == company_id)
            .with_for_update()
        )
        if profile is None:
            profile = PlatformTenantProfile(
                company_id=company_id,
                plan_code="starter",
                feature_flags=DEFAULT_LEGACY_FEATURE_FLAGS.copy(),
                plan_limits=UNLIMITED_PLAN_LIMITS.copy(),
                created_by=self.operator_id,
            )
            self.db.add(profile)
            await self.db.flush()

        flags = dict(profile.feature_flags)
        old_enabled = _flag_value(
            flags,
            definition,
            default=definition.default_company_enabled,
        )
        flags[definition.key] = data.enabled
        # Keep operational guards that still consume legacy keys in sync.
        for legacy_key in definition.legacy_keys:
            if definition.key != "central_kitchen":
                flags[legacy_key] = data.enabled
        profile.feature_flags = flags
        audit = AuditLog(
            company_id=company_id,
            branch_id=None,
            user_id=self.operator_id,
            action="platform.company.module.update",
            resource="CompanyModuleAccess",
            resource_id=f"{company_id}:{definition.key}",
            old_value={"module_key": definition.key, "company_enabled": old_enabled},
            new_value={
                "module_key": definition.key,
                "company_enabled": data.enabled,
                "reason": data.reason,
            },
            ip_address=ip_address,
            user_agent=user_agent,
        )
        self.db.add(audit)
        await self.db.commit()

        rows = await self.list_for_company(
            company_id,
            permissions=None,
            include_audit=True,
        )
        return next(row for row in rows if row.module_key == definition.key)

    async def _latest_module_audits(
        self,
        company_id: uuid.UUID,
    ) -> dict[str, AuditLog]:
        rows = list(
            await self.db.scalars(
                select(AuditLog)
                .where(
                    AuditLog.company_id == company_id,
                    AuditLog.action == "platform.company.module.update",
                )
                .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
            )
        )
        latest: dict[str, AuditLog] = {}
        for row in rows:
            module_key = (row.new_value or {}).get("module_key")
            if module_key in COMPANY_MODULES_BY_KEY and module_key not in latest:
                latest[module_key] = row
        return latest
