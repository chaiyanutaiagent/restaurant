from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_identity_db
from app.dependencies import TokenData, get_current_user, get_current_user_db
from app.models.user import User
from app.schemas.approval import ApprovalSessionRequest, ManagerPinSetRequest
from app.services.approval_service import ApprovalService


router = APIRouter(prefix="/api/v1/approvals", tags=["approvals"])


def ok(data: Any) -> dict[str, Any]:
    return {
        "data": data,
        "meta": {
            "version": settings.app_version,
            "identity_database": settings.identity_database,
        },
        "error": None,
    }


@router.get("/manager-pin")
async def get_manager_pin_status(
    current: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_identity_db),
) -> dict[str, Any]:
    result = await ApprovalService(db).get_manager_pin_status(
        current.company_id,
        current.user_id,
    )
    return ok(result.model_dump())


@router.put("/manager-pin")
async def set_manager_pin(
    payload: ManagerPinSetRequest,
    request: Request,
    current: TokenData = Depends(get_current_user),
    user: User = Depends(get_current_user_db),
    db: AsyncSession = Depends(get_identity_db),
) -> dict[str, Any]:
    result = await ApprovalService(db).set_manager_pin(
        current=current,
        user=user,
        data=payload,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    return ok(result.model_dump())


@router.post("/sessions")
async def create_approval_session(
    payload: ApprovalSessionRequest,
    request: Request,
    current: TokenData = Depends(get_current_user),
    requester: User = Depends(get_current_user_db),
    db: AsyncSession = Depends(get_identity_db),
) -> dict[str, Any]:
    result = await ApprovalService(db).create_session(
        current=current,
        requester=requester,
        data=payload,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    return ok(result.model_dump())
