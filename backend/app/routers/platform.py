from __future__ import annotations

from typing import Any
import uuid

from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Query, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_identity_db, get_restaurant_service_db
from app.dependencies import PlatformTokenData, get_current_platform_operator
from app.models.platform import PlatformOperator
from app.schemas.platform import (
    PlatformCompanyCreate,
    PlatformLifecycleAction,
    PlatformLoginRequest,
    PlatformMfaCodeRequest,
    PlatformMfaDisableRequest,
    PlatformOperatorRead,
    PlatformOperationsEvidenceImport,
    PlatformPasswordChangeRequest,
    PlatformTenantControlsUpdate,
    PlatformTenantExportRequest,
)
from app.services.platform_service import PlatformAuthService, PlatformTenantService
from app.services.platform_operations_service import PlatformOperationsService


router = APIRouter(prefix="/api/v1/platform", tags=["platform"])
PLATFORM_REFRESH_COOKIE = "platform_refresh_token"


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


def _set_refresh_cookie(response: Response, refresh_token: str) -> None:
    response.set_cookie(
        key=PLATFORM_REFRESH_COOKIE,
        value=refresh_token,
        max_age=settings.refresh_token_expire_days * 86_400,
        path="/api/v1/platform/auth",
        secure=settings.is_production,
        httponly=True,
        samesite="strict",
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(
        key=PLATFORM_REFRESH_COOKIE,
        path="/api/v1/platform/auth",
        secure=settings.is_production,
        httponly=True,
        samesite="strict",
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


def _operations_service(
    db: AsyncSession,
    current: PlatformTokenData,
) -> PlatformOperationsService:
    _require_platform_owner(current)
    return PlatformOperationsService(db, operator_id=current.operator_id)


@router.post("/auth/login")
async def login(
    payload: PlatformLoginRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_identity_db),
) -> dict[str, Any]:
    ip_address, user_agent = _client(request)
    result, refresh_token = await PlatformAuthService(db).login(
        payload.username,
        payload.password,
        mfa_code=payload.mfa_code,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    _set_refresh_cookie(response, refresh_token)
    return ok(result.model_dump(mode="json"))


@router.post("/auth/refresh")
async def refresh(
    request: Request,
    response: Response,
    refresh_token: str | None = Cookie(default=None, alias=PLATFORM_REFRESH_COOKIE),
    csrf_token: str | None = Header(default=None, alias="X-Platform-CSRF"),
    db: AsyncSession = Depends(get_identity_db),
) -> dict[str, Any]:
    if not refresh_token or not csrf_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Platform refresh credential is required",
        )
    ip_address, user_agent = _client(request)
    result, next_refresh_token = await PlatformAuthService(db).refresh(
        refresh_token,
        csrf_token,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    _set_refresh_cookie(response, next_refresh_token)
    return ok(result.model_dump(mode="json"))


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    response: Response,
    current: PlatformTokenData = Depends(get_current_platform_operator),
    db: AsyncSession = Depends(get_identity_db),
) -> Response:
    await PlatformAuthService(db).logout(
        operator_id=current.operator_id,
        session_id=current.session_id,
    )
    _clear_refresh_cookie(response)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.post("/auth/logout-all", status_code=status.HTTP_204_NO_CONTENT)
async def logout_all(
    response: Response,
    current: PlatformTokenData = Depends(get_current_platform_operator),
    db: AsyncSession = Depends(get_identity_db),
) -> Response:
    await PlatformAuthService(db).logout_all(operator_id=current.operator_id)
    _clear_refresh_cookie(response)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.get("/auth/sessions")
async def list_sessions(
    current: PlatformTokenData = Depends(get_current_platform_operator),
    db: AsyncSession = Depends(get_identity_db),
) -> dict[str, Any]:
    sessions = await PlatformAuthService(db).list_sessions(
        operator_id=current.operator_id,
        current_session_id=current.session_id,
    )
    return ok([item.model_dump(mode="json") for item in sessions])


@router.delete("/auth/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_session(
    session_id: uuid.UUID,
    response: Response,
    current: PlatformTokenData = Depends(get_current_platform_operator),
    db: AsyncSession = Depends(get_identity_db),
) -> Response:
    await PlatformAuthService(db).revoke_session(
        operator_id=current.operator_id,
        session_id=session_id,
    )
    if session_id == current.session_id:
        _clear_refresh_cookie(response)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.post("/auth/mfa/setup")
async def setup_mfa(
    current: PlatformTokenData = Depends(get_current_platform_operator),
    db: AsyncSession = Depends(get_identity_db),
) -> dict[str, Any]:
    result = await PlatformAuthService(db).setup_mfa(operator_id=current.operator_id)
    return ok(result.model_dump(mode="json"))


@router.post("/auth/mfa/confirm")
async def confirm_mfa(
    payload: PlatformMfaCodeRequest,
    current: PlatformTokenData = Depends(get_current_platform_operator),
    db: AsyncSession = Depends(get_identity_db),
) -> dict[str, Any]:
    result = await PlatformAuthService(db).confirm_mfa(
        operator_id=current.operator_id,
        session_id=current.session_id,
        code=payload.code,
    )
    return ok(result.model_dump(mode="json"))


@router.post("/auth/mfa/recovery-codes")
async def regenerate_recovery_codes(
    payload: PlatformMfaCodeRequest,
    current: PlatformTokenData = Depends(get_current_platform_operator),
    db: AsyncSession = Depends(get_identity_db),
) -> dict[str, Any]:
    codes = await PlatformAuthService(db).regenerate_recovery_codes(
        operator_id=current.operator_id,
        code=payload.code,
    )
    return ok({"recovery_codes": codes})


@router.post("/auth/mfa/disable")
async def disable_mfa(
    payload: PlatformMfaDisableRequest,
    current: PlatformTokenData = Depends(get_current_platform_operator),
    db: AsyncSession = Depends(get_identity_db),
) -> dict[str, Any]:
    operator = await PlatformAuthService(db).disable_mfa(
        operator_id=current.operator_id,
        password=payload.password,
        code=payload.code,
        current_session_id=current.session_id,
    )
    return ok(operator.model_dump(mode="json"))


@router.post("/auth/password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(
    payload: PlatformPasswordChangeRequest,
    response: Response,
    current: PlatformTokenData = Depends(get_current_platform_operator),
    db: AsyncSession = Depends(get_identity_db),
) -> Response:
    await PlatformAuthService(db).change_password(
        operator_id=current.operator_id,
        current_password=payload.current_password,
        new_password=payload.new_password,
        mfa_code=payload.mfa_code,
    )
    _clear_refresh_cookie(response)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


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


@router.post("/usage/snapshots")
async def capture_usage_snapshots(
    request: Request,
    current: PlatformTokenData = Depends(get_current_platform_operator),
    db: AsyncSession = Depends(get_identity_db),
    restaurant_db: AsyncSession = Depends(get_restaurant_service_db),
) -> dict[str, Any]:
    ip_address, user_agent = _client(request)
    snapshots = await _tenant_service(db, restaurant_db, current).capture_usage_snapshots(
        ip_address=ip_address,
        user_agent=user_agent,
    )
    return ok([snapshot.model_dump(mode="json") for snapshot in snapshots])


@router.get("/operations/summary")
async def operations_summary(
    current: PlatformTokenData = Depends(get_current_platform_operator),
    db: AsyncSession = Depends(get_identity_db),
) -> dict[str, Any]:
    summary = await _operations_service(db, current).summary()
    return ok(summary.model_dump(mode="json"))


@router.get("/operations/history")
async def operations_history(
    limit: int = Query(default=50, ge=1, le=366),
    current: PlatformTokenData = Depends(get_current_platform_operator),
    db: AsyncSession = Depends(get_identity_db),
) -> dict[str, Any]:
    rows = await _operations_service(db, current).history(limit=limit)
    return ok([row.model_dump(mode="json") for row in rows])


@router.post("/operations/capture")
async def capture_operations(
    request: Request,
    current: PlatformTokenData = Depends(get_current_platform_operator),
    db: AsyncSession = Depends(get_identity_db),
) -> dict[str, Any]:
    ip_address, user_agent = _client(request)
    row = await _operations_service(db, current).capture_runtime(
        ip_address=ip_address,
        user_agent=user_agent,
    )
    return ok(row.model_dump(mode="json"))


@router.post("/operations/evidence")
async def import_operations_evidence(
    payload: PlatformOperationsEvidenceImport,
    request: Request,
    current: PlatformTokenData = Depends(get_current_platform_operator),
    db: AsyncSession = Depends(get_identity_db),
) -> dict[str, Any]:
    ip_address, user_agent = _client(request)
    row = await _operations_service(db, current).import_evidence(
        payload,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    return ok(row.model_dump(mode="json"))


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


@router.get("/companies/{company_id}/usage")
async def get_company_usage(
    company_id: uuid.UUID,
    current: PlatformTokenData = Depends(get_current_platform_operator),
    db: AsyncSession = Depends(get_identity_db),
    restaurant_db: AsyncSession = Depends(get_restaurant_service_db),
) -> dict[str, Any]:
    usage = await _tenant_service(db, restaurant_db, current).current_usage(company_id)
    return ok(usage.model_dump(mode="json"))


@router.get("/companies/{company_id}/usage/history")
async def get_company_usage_history(
    company_id: uuid.UUID,
    limit: int = Query(default=31, ge=1, le=366),
    current: PlatformTokenData = Depends(get_current_platform_operator),
    db: AsyncSession = Depends(get_identity_db),
    restaurant_db: AsyncSession = Depends(get_restaurant_service_db),
) -> dict[str, Any]:
    history = await _tenant_service(db, restaurant_db, current).usage_history(
        company_id,
        limit=limit,
    )
    return ok([snapshot.model_dump(mode="json") for snapshot in history])


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
