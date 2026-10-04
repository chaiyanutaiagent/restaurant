from __future__ import annotations

from typing import Any
import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db, get_identity_db
from app.dependencies import TokenData, require_permission
from app.schemas.physical_uat import (
    PhysicalUATCheckUpdate,
    PhysicalUATSessionCreate,
    PhysicalUATSessionRead,
    PhysicalUATSignoffRequest,
)
from app.services.physical_uat_service import PhysicalUATService


router = APIRouter(prefix="/api/v1/uat/device-readiness", tags=["uat-device-readiness"])


def ok(data: Any) -> dict[str, Any]:
    return {"data": data, "meta": {"version": settings.app_version, "environment": "uat"}, "error": None}


@router.get("")
async def list_sessions(
    current: TokenData = Depends(require_permission("system.device.view")),
    db: AsyncSession = Depends(get_db),
    identity_db: AsyncSession = Depends(get_identity_db),
) -> dict[str, Any]:
    service = PhysicalUATService(db, identity_db)
    sessions = await service.list(current)
    return ok([PhysicalUATSessionRead(**(await service.serialize(item))).model_dump() for item in sessions])


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_session(
    payload: PhysicalUATSessionCreate,
    current: TokenData = Depends(require_permission("system.device.manage")),
    db: AsyncSession = Depends(get_db),
    identity_db: AsyncSession = Depends(get_identity_db),
) -> dict[str, Any]:
    service = PhysicalUATService(db, identity_db)
    session = await service.create(current, payload)
    return ok(PhysicalUATSessionRead(**(await service.serialize(session))).model_dump())


@router.get("/{session_id}")
async def get_session(
    session_id: uuid.UUID,
    current: TokenData = Depends(require_permission("system.device.view")),
    db: AsyncSession = Depends(get_db),
    identity_db: AsyncSession = Depends(get_identity_db),
) -> dict[str, Any]:
    service = PhysicalUATService(db, identity_db)
    session = await service.get(current, session_id)
    return ok(PhysicalUATSessionRead(**(await service.serialize(session))).model_dump())


@router.put("/{session_id}/checks/{check_key}")
async def update_check(
    session_id: uuid.UUID,
    check_key: str,
    payload: PhysicalUATCheckUpdate,
    current: TokenData = Depends(require_permission("system.device.manage")),
    db: AsyncSession = Depends(get_db),
    identity_db: AsyncSession = Depends(get_identity_db),
) -> dict[str, Any]:
    service = PhysicalUATService(db, identity_db)
    session = await service.update_check(current, session_id, check_key, payload)
    return ok(PhysicalUATSessionRead(**(await service.serialize(session))).model_dump())


@router.post("/{session_id}/submit")
async def submit_session(
    session_id: uuid.UUID,
    current: TokenData = Depends(require_permission("system.device.manage")),
    db: AsyncSession = Depends(get_db),
    identity_db: AsyncSession = Depends(get_identity_db),
) -> dict[str, Any]:
    service = PhysicalUATService(db, identity_db)
    session = await service.submit(current, session_id)
    return ok(PhysicalUATSessionRead(**(await service.serialize(session))).model_dump())


@router.post("/{session_id}/signoff")
async def signoff_session(
    session_id: uuid.UUID,
    payload: PhysicalUATSignoffRequest,
    current: TokenData = Depends(require_permission("system.device.manage")),
    db: AsyncSession = Depends(get_db),
    identity_db: AsyncSession = Depends(get_identity_db),
) -> dict[str, Any]:
    service = PhysicalUATService(db, identity_db)
    session = await service.signoff(current, session_id, role=payload.role, note=payload.note)
    return ok(PhysicalUATSessionRead(**(await service.serialize(session))).model_dump())
