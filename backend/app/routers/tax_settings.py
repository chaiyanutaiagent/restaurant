from __future__ import annotations

from typing import Any
import uuid

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.dependencies import TokenData, require_any_permission, require_permission
from app.schemas.tax_settings import (
    BranchTaxProfileUpdate,
    CompanyTaxProfileUpdate,
    TaxRateRuleCreate,
    TaxRateRuleUpdate,
)
from app.services.tax_settings_service import TaxSettingsService


router = APIRouter(prefix="/api/v1/tax-settings", tags=["tax-settings"])


def ok(data: Any) -> dict[str, Any]:
    return {"data": data, "meta": {"version": settings.app_version}, "error": None}


@router.get("")
async def get_tax_settings(
    current: TokenData = Depends(
        require_any_permission("system.company.view", "system.company.edit", "accounting.report.view")
    ),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    row = await TaxSettingsService(db).get_settings(current.company_id)
    return ok(row.model_dump(mode="json"))


@router.put("/company")
async def update_company_tax_profile(
    payload: CompanyTaxProfileUpdate,
    request: Request,
    current: TokenData = Depends(require_permission("system.company.edit")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    row = await TaxSettingsService(db).update_company_profile(
        current.company_id,
        current.user_id,
        payload,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    return ok(row.model_dump(mode="json"))


@router.put("/branches/{branch_id}")
async def update_branch_tax_profile(
    branch_id: uuid.UUID,
    payload: BranchTaxProfileUpdate,
    request: Request,
    current: TokenData = Depends(require_permission("system.company.edit")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    row = await TaxSettingsService(db).update_branch_profile(
        current.company_id,
        branch_id,
        current.user_id,
        payload,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    return ok(row.model_dump(mode="json"))


@router.post("/rates", status_code=status.HTTP_201_CREATED)
async def create_tax_rate(
    payload: TaxRateRuleCreate,
    request: Request,
    current: TokenData = Depends(require_permission("system.company.edit")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    row = await TaxSettingsService(db).create_rate(
        current.company_id,
        current.user_id,
        payload,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    return ok(row.model_dump(mode="json"))


@router.patch("/rates/{rule_id}")
async def update_tax_rate(
    rule_id: uuid.UUID,
    payload: TaxRateRuleUpdate,
    request: Request,
    current: TokenData = Depends(require_permission("system.company.edit")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    row = await TaxSettingsService(db).update_rate(
        current.company_id,
        rule_id,
        current.user_id,
        payload,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    return ok(row.model_dump(mode="json"))
