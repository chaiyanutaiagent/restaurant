from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from typing import Any
import uuid

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.business_context import RESTAURANT, RETAIL_POS, TAKEAWAY
from app.config import settings
from app.dependencies import TokenData
from app.models.audit import AuditLog
from app.models.branch import Branch
from app.models.company import Company
from app.models.restaurant import Brand, BrandBranch
from app.schemas.company_workspace import (
    CompanyWorkspaceDirectoryRead,
    CompanyWorkspaceModuleRead,
    CompanyWorkspaceProvisionRead,
    CompanyWorkspaceProvisionRequest,
    CompanyWorkspaceRead,
    CompanyWorkspaceStatusUpdate,
)
from app.schemas.module_access import CompanyModuleAccessRead
from app.services.company_module_access_service import CompanyModuleAccessService
from app.services.platform_reference_projection import enqueue_reference_event
from app.services.tenant_control_policy import TenantControlPolicy


MODULE_BUSINESS_TYPE = {
    "restaurant_pos": RESTAURANT,
    "takeaway_pos": TAKEAWAY,
    "retail_pos": RETAIL_POS,
}
BUSINESS_TYPE_MODULE = {value: key for key, value in MODULE_BUSINESS_TYPE.items()}
MODULE_ENTRY_ROUTE = {
    "erp": "/admin",
    "central_kitchen": "/restaurant/brands",
    "restaurant_pos": "/restaurant",
    "takeaway_pos": "/takeaway",
    "retail_pos": "/pos",
    "hotel_pms": None,
}
SHARED_MODULES = {"erp", "central_kitchen"}


def require_workspace_management(current: TokenData) -> None:
    if "*" in current.permissions or "system.company.edit" in current.permissions:
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Permission required: system.company.edit",
    )


def workspace_request_fingerprint(payload: CompanyWorkspaceProvisionRequest) -> str:
    normalized = payload.model_dump(exclude={"idempotency_key"}, mode="json")
    encoded = json.dumps(normalized, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


class CompanyWorkspaceService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def directory(self, current: TokenData) -> CompanyWorkspaceDirectoryRead:
        require_workspace_management(current)
        access_rows = await CompanyModuleAccessService(self.db).list_for_company(
            current.company_id,
            permissions=current.permissions,
        )
        access_by_key = {row.module_key: row for row in access_rows}
        brands = (
            await self.db.scalars(
                select(Brand)
                .options(selectinload(Brand.branches).selectinload(BrandBranch.branch))
                .where(Brand.company_id == current.company_id)
                .order_by(Brand.name, Brand.slug)
            )
        ).all()
        workspaces_by_module: dict[str, list[CompanyWorkspaceRead]] = {
            module_key: [] for module_key in MODULE_BUSINESS_TYPE
        }
        for brand in brands:
            module_key = BUSINESS_TYPE_MODULE.get(brand.business_type)
            if module_key is None:
                continue
            access = access_by_key[module_key]
            for link in brand.branches:
                branch = link.branch
                if branch is None:
                    continue
                workspaces_by_module[module_key].append(
                    self._serialize_workspace(brand, link, branch, access)
                )
        for rows in workspaces_by_module.values():
            rows.sort(
                key=lambda row: (
                    not row.is_active,
                    row.brand_name.casefold(),
                    row.branch_name.casefold(),
                    row.branch_code.casefold(),
                )
            )

        modules: list[CompanyWorkspaceModuleRead] = []
        for access in access_rows:
            if access.module_key in SHARED_MODULES:
                kind = "shared_service"
            elif access.module_key == "hotel_pms":
                kind = "planned"
            else:
                kind = "workspace_collection"
            modules.append(
                CompanyWorkspaceModuleRead(
                    module_key=access.module_key,
                    kind=kind,
                    entry_route=MODULE_ENTRY_ROUTE[access.module_key],
                    can_provision=(
                        access.module_key in MODULE_BUSINESS_TYPE
                        and access.effective_access
                    ),
                    access=access,
                    workspaces=workspaces_by_module.get(access.module_key, []),
                )
            )
        return CompanyWorkspaceDirectoryRead(
            company_id=current.company_id,
            generated_at=datetime.now(timezone.utc),
            modules=modules,
        )

    async def provision(
        self,
        current: TokenData,
        payload: CompanyWorkspaceProvisionRequest,
        *,
        ip_address: str | None,
        user_agent: str | None,
    ) -> CompanyWorkspaceProvisionRead:
        require_workspace_management(current)
        access = await self._require_effective_module(current, payload.module_key)
        fingerprint = workspace_request_fingerprint(payload)
        await self._lock_company(current.company_id)

        replay = await self.db.scalar(
            select(AuditLog)
            .where(
                AuditLog.company_id == current.company_id,
                AuditLog.action == "company.workspace.provision",
                AuditLog.resource == "CompanyWorkspaceProvisioning",
                AuditLog.resource_id == payload.idempotency_key,
            )
            .order_by(AuditLog.created_at.desc())
            .limit(1)
        )
        if replay is not None:
            replay_value = replay.new_value if isinstance(replay.new_value, dict) else {}
            if replay_value.get("request_fingerprint") != fingerprint:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Idempotency key was already used for a different workspace request",
                )
            workspace_id = self._uuid_from_value(replay_value.get("workspace_id"))
            workspace = await self._load_workspace(
                current.company_id,
                workspace_id,
                access,
            )
            return CompanyWorkspaceProvisionRead(
                created=False,
                created_resources=[],
                workspace=workspace,
            )

        business_type = MODULE_BUSINESS_TYPE[payload.module_key]
        brand = await self.db.scalar(
            select(Brand).where(
                Brand.company_id == current.company_id,
                Brand.slug == payload.brand_slug,
            )
        )
        branch = await self.db.scalar(
            select(Branch).where(
                Branch.company_id == current.company_id,
                func.lower(Branch.code) == payload.branch_code.lower(),
            )
        )
        created_resources: list[str] = []
        controls = TenantControlPolicy(self.db)

        if brand is None:
            await controls.require_capacity(current.company_id, "brands")
            brand = Brand(
                company_id=current.company_id,
                slug=payload.brand_slug,
                name=payload.brand_name,
                business_type=business_type,
                storefront_mode=payload.storefront_mode,
                theme_config={},
                is_active=True,
            )
            self.db.add(brand)
            await self.db.flush()
            created_resources.append("brand")
        else:
            self._validate_existing_brand(brand, payload, business_type)

        if branch is None:
            await controls.require_capacity(current.company_id, "branches")
            branch = Branch(
                company_id=current.company_id,
                code=payload.branch_code,
                name=payload.branch_name,
                is_warehouse=False,
                is_active=True,
                sort_order=0,
            )
            self.db.add(branch)
            await self.db.flush()
            created_resources.append("branch")
        else:
            self._validate_existing_branch(branch, payload)

        conflicting_link = await self.db.scalar(
            select(BrandBranch).where(
                BrandBranch.company_id == current.company_id,
                BrandBranch.branch_id == branch.id,
                BrandBranch.brand_id != brand.id,
                BrandBranch.is_active.is_(True),
            )
        )
        if conflicting_link is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Branch is already assigned to another active workspace",
            )

        workspace_link = await self.db.scalar(
            select(BrandBranch).where(
                BrandBranch.company_id == current.company_id,
                BrandBranch.brand_id == brand.id,
                BrandBranch.branch_id == branch.id,
            )
        )
        if workspace_link is None:
            workspace_link = BrandBranch(
                company_id=current.company_id,
                brand_id=brand.id,
                branch_id=branch.id,
                branch_type=payload.branch_type,
                is_active=True,
            )
            self.db.add(workspace_link)
            await self.db.flush()
            created_resources.append("workspace")
        elif workspace_link.branch_type != payload.branch_type:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Workspace already exists with a different branch type",
            )

        audit = AuditLog(
            company_id=current.company_id,
            branch_id=branch.id,
            user_id=current.user_id,
            action="company.workspace.provision",
            resource="CompanyWorkspaceProvisioning",
            resource_id=payload.idempotency_key,
            new_value={
                "request_fingerprint": fingerprint,
                "module_key": payload.module_key,
                "workspace_id": str(workspace_link.id),
                "brand_id": str(brand.id),
                "branch_id": str(branch.id),
                "created_resources": created_resources,
            },
            ip_address=ip_address,
            user_agent=user_agent,
        )
        self.db.add(audit)
        if settings.identity_database == "platform_core":
            created_aggregates = {
                "brand": ("brand", brand.id),
                "branch": ("branch", branch.id),
                "workspace": ("brand_branch", workspace_link.id),
            }
            for resource_key in created_resources:
                aggregate_type, aggregate_id = created_aggregates[resource_key]
                await enqueue_reference_event(
                    self.db,
                    aggregate_type=aggregate_type,
                    aggregate_id=aggregate_id,
                    company_id=current.company_id,
                    payload={"source": "company.workspace.provision"},
                )
        try:
            await self.db.commit()
        except IntegrityError as exc:
            await self.db.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Workspace identity conflicts with existing Company data",
            ) from exc

        workspace = await self._load_workspace(
            current.company_id,
            workspace_link.id,
            access,
        )
        return CompanyWorkspaceProvisionRead(
            created=bool(created_resources),
            created_resources=created_resources,  # type: ignore[arg-type]
            workspace=workspace,
        )

    async def update_status(
        self,
        current: TokenData,
        workspace_id: uuid.UUID,
        payload: CompanyWorkspaceStatusUpdate,
        *,
        ip_address: str | None,
        user_agent: str | None,
    ) -> CompanyWorkspaceRead:
        require_workspace_management(current)
        await self._lock_company(current.company_id)
        link = await self.db.scalar(
            select(BrandBranch)
            .options(selectinload(BrandBranch.brand), selectinload(BrandBranch.branch))
            .where(
                BrandBranch.id == workspace_id,
                BrandBranch.company_id == current.company_id,
            )
            .with_for_update()
        )
        if link is None or link.brand is None or link.branch is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")
        module_key = BUSINESS_TYPE_MODULE.get(link.brand.business_type)
        if module_key is None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Unsupported workspace type")
        access = await self._module_access(current, module_key)
        if payload.active and not access.effective_access:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Module is not available: {access.reason_code}",
            )
        if payload.active and (
            not link.brand.is_active
            or not link.branch.is_active
            or link.branch.deleted_at is not None
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Brand and Branch must be active before the workspace can be restored",
            )
        if payload.active:
            conflict = await self.db.scalar(
                select(BrandBranch.id).where(
                    BrandBranch.company_id == current.company_id,
                    BrandBranch.branch_id == link.branch_id,
                    BrandBranch.id != link.id,
                    BrandBranch.is_active.is_(True),
                )
            )
            if conflict is not None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Branch is already assigned to another active workspace",
                )
        if link.is_active != payload.active:
            old_active = link.is_active
            link.is_active = payload.active
            self.db.add(
                AuditLog(
                    company_id=current.company_id,
                    branch_id=link.branch_id,
                    user_id=current.user_id,
                    action=(
                        "company.workspace.reactivate"
                        if payload.active
                        else "company.workspace.deactivate"
                    ),
                    resource="CompanyWorkspace",
                    resource_id=str(link.id),
                    old_value={"is_active": old_active},
                    new_value={"is_active": payload.active, "reason": payload.reason},
                    ip_address=ip_address,
                    user_agent=user_agent,
                )
            )
            if settings.identity_database == "platform_core":
                await enqueue_reference_event(
                    self.db,
                    aggregate_type="brand_branch",
                    aggregate_id=link.id,
                    company_id=current.company_id,
                    payload={"source": "company.workspace.status"},
                )
            await self.db.commit()
        return await self._load_workspace(current.company_id, link.id, access)

    async def _require_effective_module(
        self,
        current: TokenData,
        module_key: str,
    ) -> CompanyModuleAccessRead:
        access = await self._module_access(current, module_key)
        if not access.effective_access:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Module is not available: {access.reason_code}",
            )
        return access

    async def _module_access(
        self,
        current: TokenData,
        module_key: str,
    ) -> CompanyModuleAccessRead:
        rows = await CompanyModuleAccessService(self.db).list_for_company(
            current.company_id,
            permissions=current.permissions,
        )
        access = next((row for row in rows if row.module_key == module_key), None)
        if access is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Module not found")
        return access

    async def _lock_company(self, company_id: uuid.UUID) -> Company:
        company = await self.db.scalar(
            select(Company).where(Company.id == company_id).with_for_update()
        )
        if company is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")
        if not company.is_active:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Company is inactive")
        return company

    async def _load_workspace(
        self,
        company_id: uuid.UUID,
        workspace_id: uuid.UUID,
        access: CompanyModuleAccessRead,
    ) -> CompanyWorkspaceRead:
        link = await self.db.scalar(
            select(BrandBranch)
            .options(selectinload(BrandBranch.brand), selectinload(BrandBranch.branch))
            .where(
                BrandBranch.id == workspace_id,
                BrandBranch.company_id == company_id,
            )
        )
        if link is None or link.brand is None or link.branch is None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Workspace record is unavailable")
        return self._serialize_workspace(link.brand, link, link.branch, access)

    @staticmethod
    def _serialize_workspace(
        brand: Brand,
        link: BrandBranch,
        branch: Branch,
        access: CompanyModuleAccessRead,
    ) -> CompanyWorkspaceRead:
        module_key = BUSINESS_TYPE_MODULE[brand.business_type]
        active = (
            brand.is_active
            and link.is_active
            and branch.is_active
            and branch.deleted_at is None
        )
        return CompanyWorkspaceRead(
            workspace_id=link.id,
            module_key=module_key,  # type: ignore[arg-type]
            business_type=brand.business_type,  # type: ignore[arg-type]
            brand_id=brand.id,
            brand_slug=brand.slug,
            brand_name=brand.name,
            branch_id=branch.id,
            branch_code=branch.code,
            branch_name=branch.name,
            branch_type=link.branch_type,
            storefront_mode=brand.storefront_mode,
            is_active=active,
            can_open=active and access.effective_access,
            entry_route=MODULE_ENTRY_ROUTE[module_key] or "/admin",
        )

    @staticmethod
    def _validate_existing_brand(
        brand: Brand,
        payload: CompanyWorkspaceProvisionRequest,
        business_type: str,
    ) -> None:
        if brand.business_type != business_type:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Brand slug belongs to a different module",
            )
        if brand.name.casefold() != payload.brand_name.casefold():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Brand slug already exists with a different name",
            )
        if brand.storefront_mode != payload.storefront_mode:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Brand slug already exists with a different workspace template",
            )
        if not brand.is_active:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Brand is inactive; restore it before adding a workspace",
            )

    @staticmethod
    def _validate_existing_branch(
        branch: Branch,
        payload: CompanyWorkspaceProvisionRequest,
    ) -> None:
        if branch.deleted_at is not None or not branch.is_active:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Branch code belongs to an inactive Branch",
            )
        if branch.name.casefold() != payload.branch_name.casefold():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Branch code already exists with a different name",
            )

    @staticmethod
    def _uuid_from_value(value: Any) -> uuid.UUID:
        try:
            return uuid.UUID(str(value))
        except (TypeError, ValueError) as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Idempotency record no longer references a valid workspace",
            ) from exc
