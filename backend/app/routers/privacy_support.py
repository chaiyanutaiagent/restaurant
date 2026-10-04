from __future__ import annotations

from typing import Any
import uuid

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_identity_db
from app.dependencies import TokenData, get_current_user
from app.schemas.saas_privacy_support import (
    PrivacyRequestCreate,
    SupportAccessDecision,
    SupportAccessRevoke,
    SupportMessageCreate,
    SupportTicketCreate,
)
from app.services.saas_privacy_support_service import SaasPrivacySupportService


router = APIRouter(prefix="/api/v1/privacy-support", tags=["saas-privacy-support"])


def ok(data: Any) -> dict[str, Any]:
    return {"data": data, "meta": {"version": settings.app_version}, "error": None}


def _client(request: Request) -> tuple[str | None, str | None]:
    return (request.client.host if request.client else None, request.headers.get("user-agent"))


def _service(db: AsyncSession, current: TokenData) -> SaasPrivacySupportService:
    return SaasPrivacySupportService(db, user_id=current.user_id)


@router.post("/privacy-requests", status_code=status.HTTP_201_CREATED)
async def create_privacy_request(
    payload: PrivacyRequestCreate,
    request: Request,
    current: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_identity_db),
) -> dict[str, Any]:
    ip_address, user_agent = _client(request)
    row = await _service(db, current).create_privacy_request(current.company_id, payload, ip_address=ip_address, user_agent=user_agent)
    return ok(row.model_dump(mode="json"))


@router.get("/privacy-requests")
async def list_privacy_requests(
    current: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_identity_db),
) -> dict[str, Any]:
    rows = await _service(db, current).list_privacy_requests(current.company_id)
    return ok([row.model_dump(mode="json") for row in rows])


@router.post("/tickets", status_code=status.HTTP_201_CREATED)
async def create_ticket(
    payload: SupportTicketCreate,
    request: Request,
    current: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_identity_db),
) -> dict[str, Any]:
    ip_address, user_agent = _client(request)
    row = await _service(db, current).create_ticket(current.company_id, payload, ip_address=ip_address, user_agent=user_agent)
    return ok(row.model_dump(mode="json"))


@router.get("/tickets")
async def list_tickets(
    current: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_identity_db),
) -> dict[str, Any]:
    rows = await _service(db, current).tickets(current.company_id)
    return ok([row.model_dump(mode="json") for row in rows])


@router.post("/tickets/{ticket_id}/messages", status_code=status.HTTP_201_CREATED)
async def add_ticket_message(
    ticket_id: uuid.UUID,
    payload: SupportMessageCreate,
    request: Request,
    current: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_identity_db),
) -> dict[str, Any]:
    ip_address, user_agent = _client(request)
    row = await _service(db, current).add_message(ticket_id, payload, company_id=current.company_id, ip_address=ip_address, user_agent=user_agent)
    return ok(row.model_dump(mode="json"))


@router.post("/access/{grant_id}/decision")
async def decide_support_access(
    grant_id: uuid.UUID,
    payload: SupportAccessDecision,
    request: Request,
    current: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_identity_db),
) -> dict[str, Any]:
    ip_address, user_agent = _client(request)
    row = await _service(db, current).decide_access(current.company_id, grant_id, payload, ip_address=ip_address, user_agent=user_agent)
    return ok(row.model_dump(mode="json"))


@router.post("/access/{grant_id}/revoke")
async def revoke_support_access(
    grant_id: uuid.UUID,
    payload: SupportAccessRevoke,
    request: Request,
    current: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_identity_db),
) -> dict[str, Any]:
    ip_address, user_agent = _client(request)
    row = await _service(db, current).revoke_access(grant_id, payload.reason, company_id=current.company_id, ip_address=ip_address, user_agent=user_agent)
    return ok(row.model_dump(mode="json"))
