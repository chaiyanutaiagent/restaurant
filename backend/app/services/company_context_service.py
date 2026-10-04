from __future__ import annotations

from datetime import datetime, timezone
import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.dependencies import TokenData
from app.models.branch import Branch
from app.models.company import Company
from app.models.restaurant import Brand, BrandBranch
from app.models.tax_settings import BranchTaxProfile, CompanyTaxProfile
from app.schemas.company_foundation import (
    CompanyContextEntityRead,
    CompanyContextRead,
    CompanyContextTaxRead,
    EffectiveAccessRead,
)
from app.services.company_module_access_service import (
    CompanyModuleAccessService,
    canonical_runtime_environment,
)


def default_route_for_permissions(
    permissions: list[str],
    *,
    business_type: str | None = None,
) -> str:
    permission_set = set(permissions)
    if "*" in permission_set or permission_set.intersection(
        {"system.company.view", "system.company.edit"}
    ):
        return "/company"

    # Prefer the signed business context when one exists. A cross-product role
    # can legitimately contain Restaurant and Takeaway permissions, so checking
    # permission prefixes alone can otherwise open the wrong application.
    if business_type == "takeaway" and any(
        code.startswith("takeaway.") for code in permission_set
    ):
        return "/takeaway"
    if business_type == "restaurant" and permission_set.intersection(
        {"fb.menu.view", "fb.order.create", "fb.kitchen.ticket.manage", "fb.table.manage"}
    ):
        return "/restaurant"
    if business_type == "restaurant" and any(
        code.startswith("pos.") for code in permission_set
    ):
        # Restaurant cashiers can also carry Takeaway permissions, but their
        # signed Brand/Branch context must keep them in the Restaurant POS.
        return "/pos"
    if business_type == "retail_pos" and any(
        code.startswith("pos.") for code in permission_set
    ):
        return "/pos"

    if any(code.startswith("takeaway.") for code in permission_set):
        return "/takeaway"
    if permission_set.intersection(
        {"fb.menu.view", "fb.order.create", "fb.kitchen.ticket.manage", "fb.table.manage"}
    ):
        return "/restaurant"
    if any(code.startswith("pos.") for code in permission_set):
        return "/pos"
    if permission_set.intersection(
        {"inventory.product.view", "inventory.stock.view", "accounting.report.view"}
    ):
        return "/admin"
    return "/403"


async def scoped_branch_ids(
    current: TokenData,
    operational_db: AsyncSession,
) -> list[uuid.UUID] | None:
    """Return None for Company-wide scope, otherwise the permitted branch IDs."""
    if "*" in current.permissions or "company" in current.scope_types:
        return None
    if current.branch_id is not None:
        return [current.branch_id]
    if "brand" in current.scope_types and current.brand_id is not None:
        return list(
            await operational_db.scalars(
                select(BrandBranch.branch_id).where(
                    BrandBranch.company_id == current.company_id,
                    BrandBranch.brand_id == current.brand_id,
                    BrandBranch.is_active.is_(True),
                )
            )
        )
    return []


class CompanyContextService:
    def __init__(self, identity_db: AsyncSession, operational_db: AsyncSession):
        self.identity_db = identity_db
        self.operational_db = operational_db

    async def read_context(self, current: TokenData) -> CompanyContextRead:
        company = await self.identity_db.get(Company, current.company_id)
        if company is None or not company.is_active:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Company context is unavailable",
            )

        branch = None
        if current.branch_id is not None:
            branch = await self.identity_db.scalar(
                select(Branch).where(
                    Branch.id == current.branch_id,
                    Branch.company_id == current.company_id,
                    Branch.deleted_at.is_(None),
                )
            )
            if branch is None:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Branch does not belong to the active Company context",
                )

        brand = None
        if current.brand_id is not None:
            brand = await self.operational_db.scalar(
                select(Brand).where(
                    Brand.id == current.brand_id,
                    Brand.company_id == current.company_id,
                    Brand.is_active.is_(True),
                )
            )
            if brand is None:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Brand does not belong to the active Company context",
                )

        company_tax = await self.operational_db.scalar(
            select(CompanyTaxProfile).where(CompanyTaxProfile.company_id == current.company_id)
        )
        branch_tax = None
        if current.branch_id is not None:
            branch_tax = await self.operational_db.scalar(
                select(BranchTaxProfile).where(
                    BranchTaxProfile.company_id == current.company_id,
                    BranchTaxProfile.branch_id == current.branch_id,
                )
            )

        company_scope = "*" in current.permissions or "company" in current.scope_types
        brand_scope = company_scope or "brand" in current.scope_types
        updated_candidates = [company.updated_at]
        for row in (brand, branch, company_tax, branch_tax):
            if row is not None and getattr(row, "updated_at", None) is not None:
                updated_candidates.append(row.updated_at)

        return CompanyContextRead(
            environment=canonical_runtime_environment(settings.environment),
            company=CompanyContextEntityRead(
                id=company.id,
                code=company.business_slug,
                name=company.name,
            ),
            brand=(
                CompanyContextEntityRead(id=brand.id, code=brand.slug, name=brand.name)
                if brand is not None
                else None
            ),
            branch=(
                CompanyContextEntityRead(id=branch.id, code=branch.code, name=branch.name)
                if branch is not None
                else None
            ),
            station_or_device_id=current.station_key,
            business_type=current.business_type,
            target_database=current.target_database,
            timezone=company.timezone,
            currency=company.currency,
            tax=CompanyContextTaxRead(
                scope="branch" if branch_tax is not None else "company",
                configured=company_tax is not None or branch_tax is not None,
                vat_registered=(company_tax.vat_registered if company_tax is not None else company.vat_registered),
                tax_id=(company_tax.tax_id if company_tax is not None else company.tax_id),
                tax_branch_code=(branch_tax.tax_branch_code if branch_tax is not None else None),
                price_vat_type=(
                    company_tax.default_price_vat_type if company_tax is not None else "included"
                ),
                vat_rate=float(company_tax.default_vat_rate if company_tax is not None else 7),
            ),
            all_scope_allowed={
                "brand": company_scope,
                "branch": brand_scope,
                "station": current.branch_id is not None,
            },
            updated_at=max(updated_candidates) if updated_candidates else datetime.now(timezone.utc),
        )

    async def effective_access(self, current: TokenData) -> EffectiveAccessRead:
        modules = await CompanyModuleAccessService(self.identity_db).list_for_company(
            current.company_id,
            permissions=current.permissions,
            include_audit=True,
        )
        return EffectiveAccessRead(
            company_id=current.company_id,
            user_id=current.user_id,
            scope_types=sorted(set(current.scope_types)),
            assignment_ids=current.assignment_ids,
            permissions=sorted(set(current.permissions)),
            default_route=default_route_for_permissions(
                current.permissions,
                business_type=current.business_type,
            ),
            modules=modules,
        )
