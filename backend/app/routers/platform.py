from __future__ import annotations

from typing import Any
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_identity_db, get_restaurant_service_db
from app.dependencies import PlatformTokenData, get_current_platform_operator
from app.models.platform import PlatformOperator
from app.schemas.platform import (
    PlatformCompanyCreate,
    PlatformLifecycleAction,
    PlatformLoginRequest,
    PlatformOperatorRead,
    PlatformTenantControlsUpdate,
    PlatformTenantExportRequest,
)
from app.services.platform_service import PlatformAuthService, PlatformTenantService


router = APIRouter(prefix="/api/v1/platform", tags=["platform"])


def ok(data: Any, *, pagination: dict[str, int] | None = None) -> dict[str, Any]:
    meta: dict[str, Any] = {
        "version": settings.app_version,
        "identity_database": settings.identity_database,
    }
    if pagination is not None:
        meta["pagination"] = pagination
    return {"data": data, "meta": meta, "error": None}


def _require_platform_owner(current: PlatformTokenData) -> None:
    if not current.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Platform Owner access is required",
        )


def _client(request: Request) -> tuple[str | None, str | None]:
    return (
        request.client.host if request.client else None,
        request.headers.get("user-agent"),
    )


def _tenant_service(
    db: AsyncSession,
    restaurant_db: AsyncSession,
    current: PlatformTokenData,
) -> PlatformTenantService:
    _require_platform_owner(current)
    return PlatformTenantService(
        db,
        restaurant_db=restaurant_db,
        operator_id=current.operator_id,
        emit_reference_events=settings.identity_database == "platform_core",
    )


@router.post("/auth/login")
async def login(
    payload: PlatformLoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_identity_db),
) -> dict[str, Any]:
    ip_address, user_agent = _client(request)
    result = await PlatformAuthService(db).login(
        payload.username,
        payload.password,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    return ok(result.model_dump(mode="json"))


@router.get("/auth/me")
async def me(
    current: PlatformTokenData = Depends(get_current_platform_operator),
    db: AsyncSession = Depends(get_identity_db),
) -> dict[str, Any]:
    _require_platform_owner(current)
    operator = await db.get(PlatformOperator, current.operator_id)
    if operator is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Operator not found")
    return ok(PlatformOperatorRead.model_validate(operator).model_dump(mode="json"))


@router.get("/dashboard")
async def dashboard(
    current: PlatformTokenData = Depends(get_current_platform_operator),
    db: AsyncSession = Depends(get_identity_db),
    restaurant_db: AsyncSession = Depends(get_restaurant_service_db),
) -> dict[str, Any]:
    summary = await _tenant_service(db, restaurant_db, current).dashboard()
    return ok(summary.model_dump(mode="json"))


@router.get("/companies")
async def list_companies(
    search: str | None = Query(default=None, max_length=255),
    active: bool | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=25, ge=1, le=100),
    current: PlatformTokenData = Depends(get_current_platform_operator),
    db: AsyncSession = Depends(get_identity_db),
    restaurant_db: AsyncSession = Depends(get_restaurant_service_db),
) -> dict[str, Any]:
    service = _tenant_service(db, restaurant_db, current)
    companies, total = await service.list_companies(
        search=search,
        active=active,
        offset=(page - 1) * limit,
        limit=limit,
    )
    return ok(
        [company.model_dump(mode="json") for company in companies],
        pagination={"page": page, "limit": limit, "total": total},
    )


@router.post("/companies", status_code=status.HTTP_201_CREATED)
async def create_company(
    payload: PlatformCompanyCreate,
    request: Request,
    current: PlatformTokenData = Depends(get_current_platform_operator),
    db: AsyncSession = Depends(get_identity_db),
    restaurant_db: AsyncSession = Depends(get_restaurant_service_db),
) -> dict[str, Any]:
    ip_address, user_agent = _client(request)
    company = await _tenant_service(db, restaurant_db, current).create_company(
        payload,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    return ok(company.model_dump(mode="json"))


@router.get("/companies/{company_id}")
async def get_company(
    company_id: uuid.UUID,
    current: PlatformTokenData = Depends(get_current_platform_operator),
    db: AsyncSession = Depends(get_identity_db),
    restaurant_db: AsyncSession = Depends(get_restaurant_service_db),
) -> dict[str, Any]:
    company = await _tenant_service(db, restaurant_db, current).get_company(company_id)
    return ok(company.model_dump(mode="json"))


@router.post("/companies/{company_id}/suspend")
async def suspend_company(
    company_id: uuid.UUID,
    payload: PlatformLifecycleAction,
    request: Request,
    current: PlatformTokenData = Depends(get_current_platform_operator),
    db: AsyncSession = Depends(get_identity_db),
    restaurant_db: AsyncSession = Depends(get_restaurant_service_db),
) -> dict[str, Any]:
    ip_address, user_agent = _client(request)
    company = await _tenant_service(db, restaurant_db, current).suspend_company(
        company_id,
        payload,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    return ok(company.model_dump(mode="json"))


@router.post("/companies/{company_id}/reactivate")
async def reactivate_company(
    company_id: uuid.UUID,
    payload: PlatformLifecycleAction,
    request: Request,
    current: PlatformTokenData = Depends(get_current_platform_operator),
    db: AsyncSession = Depends(get_identity_db),
    restaurant_db: AsyncSession = Depends(get_restaurant_service_db),
) -> dict[str, Any]:
    ip_address, user_agent = _client(request)
    company = await _tenant_service(db, restaurant_db, current).reactivate_company(
        company_id,
        payload,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    return ok(company.model_dump(mode="json"))


@router.put("/companies/{company_id}/controls")
async def update_controls(
    company_id: uuid.UUID,
    payload: PlatformTenantControlsUpdate,
    request: Request,
    current: PlatformTokenData = Depends(get_current_platform_operator),
    db: AsyncSession = Depends(get_identity_db),
    restaurant_db: AsyncSession = Depends(get_restaurant_service_db),
) -> dict[str, Any]:
    ip_address, user_agent = _client(request)
    company = await _tenant_service(db, restaurant_db, current).update_controls(
        company_id,
        payload,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    return ok(company.model_dump(mode="json"))


@router.post("/companies/{company_id}/export")
async def export_company(
    company_id: uuid.UUID,
    payload: PlatformTenantExportRequest,
    request: Request,
    current: PlatformTokenData = Depends(get_current_platform_operator),
    db: AsyncSession = Depends(get_identity_db),
    restaurant_db: AsyncSession = Depends(get_restaurant_service_db),
) -> dict[str, Any]:
    ip_address, user_agent = _client(request)
    artifact = await _tenant_service(db, restaurant_db, current).export_company(
        company_id,
        payload,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    return ok(artifact)


@router.get("/audit")
async def audit_events(
    company_id: uuid.UUID | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    current: PlatformTokenData = Depends(get_current_platform_operator),
    db: AsyncSession = Depends(get_identity_db),
    restaurant_db: AsyncSession = Depends(get_restaurant_service_db),
) -> dict[str, Any]:
    rows = await _tenant_service(db, restaurant_db, current).list_audit_events(
        company_id=company_id,
        limit=limit,
    )
    return ok(rows)
