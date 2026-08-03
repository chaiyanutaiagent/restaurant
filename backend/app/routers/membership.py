from __future__ import annotations

import hashlib
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_identity_db
from app.dependencies import TokenData, get_current_user
from app.schemas.membership import (
    SaasActionRead,
    SaasCredentialRequest,
    SaasEmailRequest,
    SaasPasswordResetConfirm,
    SaasSignupRead,
    SaasSignupRequest,
)
from app.services.saas_email_service import deliver_membership_email
from app.services.saas_membership_service import SaasMembershipService
from app.services.saas_billing_service import SaasBillingService
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
    response = SaasSignupRead(
        company_id=membership.company_id,
        status=membership.status,
        message=(
            "Account created; check your email to verify the account"
            if delivered
            else "Account created; email delivery failed, use resend verification"
        ),
    )
    return ok(response.model_dump())


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
