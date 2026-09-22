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
    PlatformAccessReviewRequest,
    PlatformOperatorInvitationAccept,
    PlatformOperatorInviteRequest,
    PlatformOperatorRead,
    PlatformOperatorSessionsRevokeRequest,
    PlatformOperatorStateRequest,
    PlatformRoleAssignmentRequest,
    PlatformOperationsEvidenceImport,
    PlatformPasswordChangeRequest,
    PlatformTenantControlsUpdate,
    PlatformTenantExportRequest,
)
from app.schemas.module_access import CompanyModuleAccessUpdate
from app.schemas.saas_billing import (
    SaasBillingEventImport,
    SaasInvoiceCreate,
    SaasPlanUpsert,
    SaasSubscriptionUpdate,
)
from app.schemas.saas_privacy_support import (
    PrivacyRequestUpdate,
    RetentionDecisionCreate,
    RetentionDecisionUpdate,
    SupportAccessRequest,
    SupportAccessRevoke,
    SupportMessageCreate,
    SupportTicketUpdate,
)
from app.services.saas_billing_service import SaasBillingService
from app.services.company_module_access_service import CompanyModuleAccessService
from app.services.saas_privacy_support_service import SaasPrivacySupportService
from app.services.platform_service import PlatformAuthService, PlatformTenantService
from app.services.platform_operations_service import PlatformOperationsService
from app.services.platform_access_service import require_platform_permission
from app.services.platform_team_service import PlatformTeamService


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
    permission: str = "platform.company.view",
) -> PlatformTenantService:
    require_platform_permission(current, permission)
    return PlatformTenantService(
        db,
        restaurant_db=restaurant_db,
        operator_id=current.operator_id,
        emit_reference_events=settings.identity_database == "platform_core",
    )


def _operations_service(
    db: AsyncSession,
    current: PlatformTokenData,
    permission: str = "platform.operations.view",
) -> PlatformOperationsService:
    require_platform_permission(current, permission)
    return PlatformOperationsService(db, operator_id=current.operator_id)


def _billing_service(db: AsyncSession, current: PlatformTokenData, permission: str = "platform.billing.view") -> SaasBillingService:
    require_platform_permission(current, permission)
    return SaasBillingService(db, operator_id=current.operator_id)


def _privacy_support_service(
    db: AsyncSession,
    current: PlatformTokenData,
    *,
    restaurant_db: AsyncSession | None = None,
    permission: str | None = None,
) -> SaasPrivacySupportService:
    require_platform_permission(
        current,
        permission or ("platform.support.view" if restaurant_db is not None else "platform.privacy.view"),
    )
    return SaasPrivacySupportService(
        db,
        operator_id=current.operator_id,
        restaurant_db=restaurant_db,
    )


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


@router.post("/team/invitations/accept", status_code=status.HTTP_201_CREATED)
async def accept_team_invitation(
    payload: PlatformOperatorInvitationAccept,
    request: Request,
    db: AsyncSession = Depends(get_identity_db),
) -> dict[str, Any]:
    ip_address, user_agent = _client(request)
    operator = await PlatformTeamService(db, actor_id=None).accept_invitation(
        payload,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    return ok(operator.model_dump(mode="json"))


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
    operator = await db.get(PlatformOperator, current.operator_id)
    if operator is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Operator not found")
    return ok(
        PlatformOperatorRead(
            id=operator.id,
            username=operator.username,
            email=operator.email,
            display_name=operator.display_name,
            is_active=operator.is_active,
            is_superuser=operator.is_superuser,
            mfa_enabled=operator.mfa_enabled,
            last_login_at=operator.last_login_at,
            credential_version=operator.credential_version,
            role_codes=current.role_codes,
            permissions=current.permissions,
            environment=current.environment,
            access_reviewed_at=operator.access_reviewed_at,
            access_review_due_at=operator.access_review_due_at,
        ).model_dump(mode="json")
    )


def _same_platform_environment(current: PlatformTokenData, environment: str) -> None:
    if current.environment != environment:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "cross_environment_access_denied",
                "message": "Platform access assignments are isolated by environment",
                "current_environment": current.environment,
                "requested_environment": environment,
            },
        )


@router.get("/team/roles")
async def team_roles(
    current: PlatformTokenData = Depends(get_current_platform_operator),
) -> dict[str, Any]:
    require_platform_permission(current, "platform.team.view")
    return ok(PlatformTeamService.role_definitions())


@router.get("/team/operators")
async def team_operators(
    environment: str | None = Query(default=None, pattern="^(uat|production)$"),
    current: PlatformTokenData = Depends(get_current_platform_operator),
    db: AsyncSession = Depends(get_identity_db),
) -> dict[str, Any]:
    require_platform_permission(current, "platform.team.view")
    environment = environment or current.environment
    _same_platform_environment(current, environment)
    rows = await PlatformTeamService(db, actor_id=current.operator_id).list_operators(
        environment=environment
    )
    return ok([row.model_dump(mode="json") for row in rows])


@router.get("/team/operators/{operator_id}")
async def team_operator(
    operator_id: uuid.UUID,
    environment: str | None = Query(default=None, pattern="^(uat|production)$"),
    current: PlatformTokenData = Depends(get_current_platform_operator),
    db: AsyncSession = Depends(get_identity_db),
) -> dict[str, Any]:
    require_platform_permission(current, "platform.team.view")
    environment = environment or current.environment
    _same_platform_environment(current, environment)
    row = await PlatformTeamService(db, actor_id=current.operator_id).operator(
        operator_id, environment=environment
    )
    return ok(row.model_dump(mode="json"))


@router.get("/team/invitations")
async def team_invitations(
    environment: str | None = Query(default=None, pattern="^(uat|production)$"),
    current: PlatformTokenData = Depends(get_current_platform_operator),
    db: AsyncSession = Depends(get_identity_db),
) -> dict[str, Any]:
    require_platform_permission(current, "platform.team.view")
    environment = environment or current.environment
    _same_platform_environment(current, environment)
    rows = await PlatformTeamService(db, actor_id=current.operator_id).list_invitations(
        environment=environment
    )
    return ok([row.model_dump(mode="json") for row in rows])


@router.post("/team/invitations", status_code=status.HTTP_201_CREATED)
async def invite_team_operator(
    payload: PlatformOperatorInviteRequest,
    request: Request,
    current: PlatformTokenData = Depends(get_current_platform_operator),
    db: AsyncSession = Depends(get_identity_db),
) -> dict[str, Any]:
    require_platform_permission(current, "platform.team.manage")
    _same_platform_environment(current, payload.environment)
    ip_address, user_agent = _client(request)
    row = await PlatformTeamService(db, actor_id=current.operator_id).invite(
        payload,
        actor_roles=current.role_codes,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    return ok(row.model_dump(mode="json"))


@router.post("/team/operators/{operator_id}/roles")
async def assign_team_role(
    operator_id: uuid.UUID,
    payload: PlatformRoleAssignmentRequest,
    request: Request,
    current: PlatformTokenData = Depends(get_current_platform_operator),
    db: AsyncSession = Depends(get_identity_db),
) -> dict[str, Any]:
    require_platform_permission(current, "platform.team.manage")
    _same_platform_environment(current, payload.environment)
    ip_address, user_agent = _client(request)
    row = await PlatformTeamService(db, actor_id=current.operator_id).assign_role(
        operator_id,
        payload,
        actor_roles=current.role_codes,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    return ok(row.model_dump(mode="json"))


@router.delete("/team/operators/{operator_id}/roles")
async def revoke_team_role(
    operator_id: uuid.UUID,
    payload: PlatformRoleAssignmentRequest,
    request: Request,
    current: PlatformTokenData = Depends(get_current_platform_operator),
    db: AsyncSession = Depends(get_identity_db),
) -> dict[str, Any]:
    require_platform_permission(current, "platform.team.manage")
    _same_platform_environment(current, payload.environment)
    ip_address, user_agent = _client(request)
    row = await PlatformTeamService(db, actor_id=current.operator_id).revoke_role(
        operator_id,
        payload,
        actor_roles=current.role_codes,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    return ok(row.model_dump(mode="json"))


@router.put("/team/operators/{operator_id}/state")
async def set_team_operator_state(
    operator_id: uuid.UUID,
    payload: PlatformOperatorStateRequest,
    request: Request,
    current: PlatformTokenData = Depends(get_current_platform_operator),
    db: AsyncSession = Depends(get_identity_db),
) -> dict[str, Any]:
    require_platform_permission(current, "platform.team.manage")
    ip_address, user_agent = _client(request)
    row = await PlatformTeamService(db, actor_id=current.operator_id).set_operator_state(
        operator_id,
        payload,
        environment=current.environment,
        actor_roles=current.role_codes,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    return ok(row.model_dump(mode="json"))


@router.post("/team/operators/{operator_id}/access-review")
async def certify_team_operator_access(
    operator_id: uuid.UUID,
    payload: PlatformAccessReviewRequest,
    request: Request,
    current: PlatformTokenData = Depends(get_current_platform_operator),
    db: AsyncSession = Depends(get_identity_db),
) -> dict[str, Any]:
    require_platform_permission(current, "platform.team.manage")
    ip_address, user_agent = _client(request)
    row = await PlatformTeamService(db, actor_id=current.operator_id).certify_access(
        operator_id,
        payload,
        environment=current.environment,
        actor_roles=current.role_codes,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    return ok(row.model_dump(mode="json"))


@router.post("/team/operators/{operator_id}/sessions/revoke")
async def revoke_team_operator_sessions(
    operator_id: uuid.UUID,
    payload: PlatformOperatorSessionsRevokeRequest,
    request: Request,
    current: PlatformTokenData = Depends(get_current_platform_operator),
    db: AsyncSession = Depends(get_identity_db),
) -> dict[str, Any]:
    require_platform_permission(current, "platform.security.session.revoke")
    _same_platform_environment(current, payload.environment)
    ip_address, user_agent = _client(request)
    count = await PlatformTeamService(db, actor_id=current.operator_id).revoke_operator_sessions(
        operator_id,
        reason=payload.reason,
        request_id=payload.request_id,
        environment=payload.environment,
        actor_roles=current.role_codes,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    return ok({"operator_id": str(operator_id), "revoked_session_count": count})


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
    snapshots = await _tenant_service(db, restaurant_db, current, "platform.operations.manage").capture_usage_snapshots(
        ip_address=ip_address,
        user_agent=user_agent,
    )
    return ok([snapshot.model_dump(mode="json") for snapshot in snapshots])


@router.get("/billing/overview")
async def billing_overview(
    current: PlatformTokenData = Depends(get_current_platform_operator),
    db: AsyncSession = Depends(get_identity_db),
) -> dict[str, Any]:
    result = await _billing_service(db, current).overview()
    return ok(result.model_dump(mode="json"))


@router.post("/billing/plans")
async def upsert_billing_plan(
    payload: SaasPlanUpsert,
    request: Request,
    current: PlatformTokenData = Depends(get_current_platform_operator),
    db: AsyncSession = Depends(get_identity_db),
) -> dict[str, Any]:
    ip_address, user_agent = _client(request)
    result = await _billing_service(db, current, "platform.billing.manage").upsert_plan(
        payload, ip_address=ip_address, user_agent=user_agent
    )
    return ok(result.model_dump(mode="json"))


@router.post("/billing/events")
async def import_billing_event(
    payload: SaasBillingEventImport,
    request: Request,
    current: PlatformTokenData = Depends(get_current_platform_operator),
    db: AsyncSession = Depends(get_identity_db),
) -> dict[str, Any]:
    ip_address, user_agent = _client(request)
    result = await _billing_service(db, current, "platform.billing.manage").apply_event(
        payload, ip_address=ip_address, user_agent=user_agent
    )
    return ok(result.model_dump(mode="json"))


@router.get("/privacy/requests")
async def platform_privacy_requests(
    limit: int = Query(default=200, ge=1, le=500),
    current: PlatformTokenData = Depends(get_current_platform_operator),
    db: AsyncSession = Depends(get_identity_db),
) -> dict[str, Any]:
    rows = await _privacy_support_service(db, current).platform_privacy_requests(limit)
    return ok([row.model_dump(mode="json") for row in rows])


@router.put("/privacy/requests/{request_id}")
async def update_platform_privacy_request(
    request_id: uuid.UUID,
    payload: PrivacyRequestUpdate,
    request: Request,
    current: PlatformTokenData = Depends(get_current_platform_operator),
    db: AsyncSession = Depends(get_identity_db),
) -> dict[str, Any]:
    ip_address, user_agent = _client(request)
    row = await _privacy_support_service(db, current, permission="platform.privacy.manage").update_privacy_request(request_id, payload, ip_address=ip_address, user_agent=user_agent)
    return ok(row.model_dump(mode="json"))


@router.get("/privacy/requests/{request_id}/retention")
async def list_retention_decisions(
    request_id: uuid.UUID,
    current: PlatformTokenData = Depends(get_current_platform_operator),
    db: AsyncSession = Depends(get_identity_db),
) -> dict[str, Any]:
    rows = await _privacy_support_service(db, current).retention_decisions(request_id)
    return ok([row.model_dump(mode="json") for row in rows])


@router.post("/privacy/requests/{request_id}/retention", status_code=status.HTTP_201_CREATED)
async def create_retention_decision(
    request_id: uuid.UUID,
    payload: RetentionDecisionCreate,
    request: Request,
    current: PlatformTokenData = Depends(get_current_platform_operator),
    db: AsyncSession = Depends(get_identity_db),
) -> dict[str, Any]:
    ip_address, user_agent = _client(request)
    row = await _privacy_support_service(db, current, permission="platform.privacy.manage").create_retention_decision(request_id, payload, ip_address=ip_address, user_agent=user_agent)
    return ok(row.model_dump(mode="json"))


@router.put("/privacy/retention/{decision_id}")
async def update_retention_decision(
    decision_id: uuid.UUID,
    payload: RetentionDecisionUpdate,
    request: Request,
    current: PlatformTokenData = Depends(get_current_platform_operator),
    db: AsyncSession = Depends(get_identity_db),
) -> dict[str, Any]:
    ip_address, user_agent = _client(request)
    row = await _privacy_support_service(db, current, permission="platform.privacy.manage").update_retention_decision(decision_id, payload, ip_address=ip_address, user_agent=user_agent)
    return ok(row.model_dump(mode="json"))


@router.get("/support/tickets")
async def platform_support_tickets(
    limit: int = Query(default=200, ge=1, le=500),
    current: PlatformTokenData = Depends(get_current_platform_operator),
    db: AsyncSession = Depends(get_identity_db),
) -> dict[str, Any]:
    rows = await _privacy_support_service(db, current, permission="platform.support.view").tickets(limit=limit)
    return ok([row.model_dump(mode="json") for row in rows])


@router.put("/support/tickets/{ticket_id}")
async def update_support_ticket(
    ticket_id: uuid.UUID,
    payload: SupportTicketUpdate,
    request: Request,
    current: PlatformTokenData = Depends(get_current_platform_operator),
    db: AsyncSession = Depends(get_identity_db),
) -> dict[str, Any]:
    ip_address, user_agent = _client(request)
    row = await _privacy_support_service(db, current, permission="platform.support.respond").update_ticket(ticket_id, payload, ip_address=ip_address, user_agent=user_agent)
    return ok(row.model_dump(mode="json"))


@router.post("/support/tickets/{ticket_id}/messages", status_code=status.HTTP_201_CREATED)
async def add_platform_support_message(
    ticket_id: uuid.UUID,
    payload: SupportMessageCreate,
    request: Request,
    current: PlatformTokenData = Depends(get_current_platform_operator),
    db: AsyncSession = Depends(get_identity_db),
) -> dict[str, Any]:
    ip_address, user_agent = _client(request)
    row = await _privacy_support_service(db, current, permission="platform.support.respond").add_message(ticket_id, payload, company_id=None, ip_address=ip_address, user_agent=user_agent)
    return ok(row.model_dump(mode="json"))


@router.post("/support/tickets/{ticket_id}/access", status_code=status.HTTP_201_CREATED)
async def request_support_access(
    ticket_id: uuid.UUID,
    payload: SupportAccessRequest,
    request: Request,
    current: PlatformTokenData = Depends(get_current_platform_operator),
    db: AsyncSession = Depends(get_identity_db),
) -> dict[str, Any]:
    ip_address, user_agent = _client(request)
    row = await _privacy_support_service(db, current, permission="platform.support.request_access").request_access(ticket_id, payload, ip_address=ip_address, user_agent=user_agent)
    return ok(row.model_dump(mode="json"))


@router.post("/support/access/{grant_id}/revoke")
async def revoke_platform_support_access(
    grant_id: uuid.UUID,
    payload: SupportAccessRevoke,
    request: Request,
    current: PlatformTokenData = Depends(get_current_platform_operator),
    db: AsyncSession = Depends(get_identity_db),
) -> dict[str, Any]:
    ip_address, user_agent = _client(request)
    row = await _privacy_support_service(db, current, permission="platform.support.request_access").revoke_access(grant_id, payload.reason, company_id=None, ip_address=ip_address, user_agent=user_agent)
    return ok(row.model_dump(mode="json"))


@router.get("/support/access/{grant_id}/context")
async def view_support_context(
    grant_id: uuid.UUID,
    request: Request,
    current: PlatformTokenData = Depends(get_current_platform_operator),
    db: AsyncSession = Depends(get_identity_db),
    restaurant_db: AsyncSession = Depends(get_restaurant_service_db),
) -> dict[str, Any]:
    ip_address, user_agent = _client(request)
    row = await _privacy_support_service(db, current, restaurant_db=restaurant_db, permission="platform.support.view").support_context(grant_id, ip_address=ip_address, user_agent=user_agent)
    return ok(row.model_dump(mode="json"))


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
    row = await _operations_service(db, current, "platform.operations.manage").capture_runtime(
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
    row = await _operations_service(db, current, "platform.operations.manage").import_evidence(
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
    company = await _tenant_service(db, restaurant_db, current, "platform.company.manage").create_company(
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


@router.get("/companies/{company_id}/modules")
async def get_company_modules(
    company_id: uuid.UUID,
    current: PlatformTokenData = Depends(get_current_platform_operator),
    db: AsyncSession = Depends(get_identity_db),
) -> dict[str, Any]:
    require_platform_permission(current, "platform.module.view")
    modules = await CompanyModuleAccessService(
        db,
        operator_id=current.operator_id,
    ).list_for_company(company_id, permissions=None, include_audit=True)
    return ok([module.model_dump(mode="json") for module in modules])


@router.put("/companies/{company_id}/modules/{module_key}")
async def update_company_module(
    company_id: uuid.UUID,
    module_key: str,
    payload: CompanyModuleAccessUpdate,
    request: Request,
    current: PlatformTokenData = Depends(get_current_platform_operator),
    db: AsyncSession = Depends(get_identity_db),
) -> dict[str, Any]:
    require_platform_permission(current, "platform.module.manage")
    ip_address, user_agent = _client(request)
    module = await CompanyModuleAccessService(
        db,
        operator_id=current.operator_id,
    ).update_company_module(
        company_id,
        module_key,
        payload,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    return ok(module.model_dump(mode="json"))


@router.get("/companies/{company_id}/usage")
async def get_company_usage(
    company_id: uuid.UUID,
    current: PlatformTokenData = Depends(get_current_platform_operator),
    db: AsyncSession = Depends(get_identity_db),
    restaurant_db: AsyncSession = Depends(get_restaurant_service_db),
) -> dict[str, Any]:
    usage = await _tenant_service(db, restaurant_db, current).current_usage(company_id)
    return ok(usage.model_dump(mode="json"))


@router.get("/companies/{company_id}/billing")
async def get_company_billing(
    company_id: uuid.UUID,
    current: PlatformTokenData = Depends(get_current_platform_operator),
    db: AsyncSession = Depends(get_identity_db),
) -> dict[str, Any]:
    result = await _billing_service(db, current).summary(company_id)
    return ok(result.model_dump(mode="json"))


@router.put("/companies/{company_id}/billing/subscription")
async def update_company_subscription(
    company_id: uuid.UUID,
    payload: SaasSubscriptionUpdate,
    request: Request,
    current: PlatformTokenData = Depends(get_current_platform_operator),
    db: AsyncSession = Depends(get_identity_db),
) -> dict[str, Any]:
    ip_address, user_agent = _client(request)
    result = await _billing_service(db, current, "platform.billing.manage").update_subscription(
        company_id, payload, ip_address=ip_address, user_agent=user_agent
    )
    return ok(result.model_dump(mode="json"))


@router.post("/companies/{company_id}/billing/invoices", status_code=status.HTTP_201_CREATED)
async def create_company_invoice(
    company_id: uuid.UUID,
    payload: SaasInvoiceCreate,
    request: Request,
    current: PlatformTokenData = Depends(get_current_platform_operator),
    db: AsyncSession = Depends(get_identity_db),
) -> dict[str, Any]:
    ip_address, user_agent = _client(request)
    result = await _billing_service(db, current, "platform.billing.manage").create_invoice(
        company_id, payload, ip_address=ip_address, user_agent=user_agent
    )
    return ok(result.model_dump(mode="json"))


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
    company = await _tenant_service(db, restaurant_db, current, "platform.company.lifecycle").suspend_company(
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
    company = await _tenant_service(db, restaurant_db, current, "platform.company.lifecycle").reactivate_company(
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
    company = await _tenant_service(db, restaurant_db, current, "platform.company.manage").update_controls(
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
    artifact = await _tenant_service(db, restaurant_db, current, "platform.audit.export").export_company(
        company_id,
        payload,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    return ok(artifact)


@router.get("/audit")
async def audit_events(
    company_id: uuid.UUID | None = Query(default=None),
    operator_id: uuid.UUID | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    current: PlatformTokenData = Depends(get_current_platform_operator),
    db: AsyncSession = Depends(get_identity_db),
    restaurant_db: AsyncSession = Depends(get_restaurant_service_db),
) -> dict[str, Any]:
    rows = await _tenant_service(db, restaurant_db, current, "platform.audit.view").list_audit_events(
        company_id=company_id,
        operator_id=operator_id,
        limit=limit,
    )
    return ok(rows)
