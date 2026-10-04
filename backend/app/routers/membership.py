from __future__ import annotations

import hashlib
from datetime import date
from typing import Any
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_identity_db, get_platform_db
from app.dependencies import TokenData, get_current_user
from app.models.company import Company
from app.schemas.membership import (
    SaasActionRead,
    SaasBusinessRead,
    SaasCredentialRequest,
    SaasEmailRequest,
    SaasPasswordResetConfirm,
    SaasSignupRead,
    SaasSignupRequest,
)
from app.schemas.company_workspace import (
    CompanyWorkspaceProvisionRequest,
    CompanyWorkspaceStatusUpdate,
)
from app.schemas.shared_reporting import ReportingModuleKey
from app.services.company_module_access_service import CompanyModuleAccessService
from app.services.company_workspace_service import CompanyWorkspaceService
from app.services.shared_reporting_service import SharedReportingService
from app.services.saas_email_service import deliver_membership_email
from app.services.saas_membership_service import SaasMembershipService
from app.services.saas_billing_service import SaasBillingService
from app.services.business_directory_service import resolve_active_business
from app.utils.public_rate_limit import check_public_rate_limit


router = APIRouter(prefix="/api/v1/membership", tags=["saas-membership"])
GENERIC_EMAIL_MESSAGE = "If the account is eligible, an email has been accepted for delivery"


def ok(data: Any) -> dict[str, Any]:
    return {
        "data": data,
        "meta": {"version": settings.app_version},
        "error": None,
    }


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:24]


async def _require_rate_limit(
    key: str,
    *,
    limit: int,
    window_seconds: int,
) -> None:
    if not await check_public_rate_limit(key, limit=limit, window_seconds=window_seconds):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many account requests; try again later",
        )


@router.post("/signup", status_code=status.HTTP_201_CREATED)
async def signup(
    payload: SaasSignupRequest,
    request: Request,
    db: AsyncSession = Depends(get_identity_db),
) -> dict[str, Any]:
    client_ip = _client_ip(request)
    await _require_rate_limit(f"signup:{client_ip}", limit=5, window_seconds=3600)
    service = SaasMembershipService(db)
    membership, raw_token = await service.signup(
        payload,
        ip_address=client_ip,
        user_agent=request.headers.get("user-agent"),
    )
    delivered = await deliver_membership_email(
        recipient=membership.owner_email,
        purpose="verify_email",
        token=raw_token,
    )
    company = await db.get(Company, membership.company_id)
    if company is None:  # pragma: no cover - the signup transaction creates both rows
        raise RuntimeError("Signup Company is missing")
    response = SaasSignupRead(
        company_id=membership.company_id,
        business_slug=company.business_slug,
        status=membership.status,
        message=(
            "Account created; check your email to verify the account"
            if delivered
            else "Account created; email delivery failed, use resend verification"
        ),
    )
    return ok(response.model_dump())


@router.get("/businesses/{business_slug}")
async def get_public_business(
    business_slug: str,
    db: AsyncSession = Depends(get_identity_db),
) -> dict[str, Any]:
    company = await resolve_active_business(db, business_slug)
    return ok(
        SaasBusinessRead(
            company_id=company.id,
            business_slug=company.business_slug,
            name=company.name,
            logo_url=company.logo_url,
        ).model_dump()
    )


@router.post("/verification/request", status_code=status.HTTP_202_ACCEPTED)
async def request_verification(
    payload: SaasEmailRequest,
    request: Request,
    db: AsyncSession = Depends(get_identity_db),
) -> dict[str, Any]:
    client_ip = _client_ip(request)
    await _require_rate_limit(
        f"verify-request:{client_ip}:{_digest(payload.email)}",
        limit=5,
        window_seconds=3600,
    )
    issued = await SaasMembershipService(db).request_verification(
        payload.email,
        request_ip=client_ip,
    )
    if issued is not None:
        membership, raw_token = issued
        await deliver_membership_email(
            recipient=membership.owner_email,
            purpose="verify_email",
            token=raw_token,
        )
    return ok(SaasActionRead(message=GENERIC_EMAIL_MESSAGE).model_dump())


@router.post("/verification/confirm")
async def confirm_verification(
    payload: SaasCredentialRequest,
    request: Request,
    db: AsyncSession = Depends(get_identity_db),
) -> dict[str, Any]:
    await _require_rate_limit(
        f"verify-confirm:{_client_ip(request)}:{_digest(payload.token)}",
        limit=10,
        window_seconds=600,
    )
    service = SaasMembershipService(db)
    membership = await service.verify_email(payload.token)
    return ok(
        SaasActionRead(
            message="Email verified; the SaaS trial is active",
            membership=service.read(membership),
        ).model_dump()
    )


@router.post("/password-reset/request", status_code=status.HTTP_202_ACCEPTED)
async def request_password_reset(
    payload: SaasEmailRequest,
    request: Request,
    db: AsyncSession = Depends(get_identity_db),
) -> dict[str, Any]:
    client_ip = _client_ip(request)
    await _require_rate_limit(
        f"password-request:{client_ip}:{_digest(payload.email)}",
        limit=5,
        window_seconds=3600,
    )
    issued = await SaasMembershipService(db).request_password_reset(
        payload.email,
        request_ip=client_ip,
    )
    if issued is not None:
        membership, raw_token = issued
        await deliver_membership_email(
            recipient=membership.owner_email,
            purpose="reset_password",
            token=raw_token,
        )
    return ok(SaasActionRead(message=GENERIC_EMAIL_MESSAGE).model_dump())


@router.post("/password-reset/confirm")
async def confirm_password_reset(
    payload: SaasPasswordResetConfirm,
    request: Request,
    db: AsyncSession = Depends(get_identity_db),
) -> dict[str, Any]:
    await _require_rate_limit(
        f"password-confirm:{_client_ip(request)}:{_digest(payload.token)}",
        limit=10,
        window_seconds=600,
    )
    service = SaasMembershipService(db)
    membership = await service.reset_password(
        payload.token,
        payload.new_password,
        ip_address=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    return ok(
        SaasActionRead(
            message="Password reset; previous refresh sessions were revoked",
            membership=service.read(membership),
        ).model_dump()
    )


@router.get("/me")
async def my_membership(
    current: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_identity_db),
) -> dict[str, Any]:
    service = SaasMembershipService(db)
    membership = await service.membership_for_company(current.company_id)
    if membership is None or membership.owner_user_id != current.user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="SaaS membership not found",
        )
    return ok(service.read(membership).model_dump())


@router.get("/billing")
async def my_billing(
    current: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_identity_db),
) -> dict[str, Any]:
    membership = await SaasMembershipService(db).membership_for_company(current.company_id)
    if membership is None or membership.owner_user_id != current.user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="SaaS membership not found",
        )
    summary = await SaasBillingService(db, operator_id=None).summary(current.company_id)
    return ok(summary.model_dump(mode="json"))


@router.get("/modules")
async def my_company_modules(
    current: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_identity_db),
) -> dict[str, Any]:
    modules = await CompanyModuleAccessService(db).list_for_company(
        current.company_id,
        permissions=current.permissions,
    )
    return ok([module.model_dump(mode="json") for module in modules])


@router.get("/workspaces")
async def my_company_workspaces(
    current: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_identity_db),
) -> dict[str, Any]:
    directory = await CompanyWorkspaceService(db).directory(current)
    return ok(directory.model_dump(mode="json"))


@router.post("/workspaces")
async def provision_company_workspace(
    payload: CompanyWorkspaceProvisionRequest,
    request: Request,
    current: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_identity_db),
) -> dict[str, Any]:
    result = await CompanyWorkspaceService(db).provision(
        current,
        payload,
        ip_address=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    return ok(result.model_dump(mode="json"))


@router.patch("/workspaces/{workspace_id}")
async def update_company_workspace_status(
    workspace_id: uuid.UUID,
    payload: CompanyWorkspaceStatusUpdate,
    request: Request,
    current: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_identity_db),
) -> dict[str, Any]:
    workspace = await CompanyWorkspaceService(db).update_status(
        current,
        workspace_id,
        payload,
        ip_address=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    return ok(workspace.model_dump(mode="json"))


@router.get("/reports/shared-sales")
async def my_company_shared_sales_report(
    date_from: date = Query(...),
    date_to: date = Query(...),
    module_key: ReportingModuleKey | None = Query(default=None),
    brand_id: uuid.UUID | None = Query(default=None),
    branch_id: uuid.UUID | None = Query(default=None),
    current: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_platform_db),
) -> dict[str, Any]:
    report = await SharedReportingService(db).sales_report(
        current,
        date_from=date_from,
        date_to=date_to,
        module_key=module_key,
        brand_id=brand_id,
        branch_id=branch_id,
    )
    return ok(report.model_dump(mode="json"))
