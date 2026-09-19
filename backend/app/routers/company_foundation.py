from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_identity_db, get_restaurant_service_db
from app.dependencies import TokenData, get_current_user
from app.models.audit import AuditLog
from app.schemas.company_foundation import CompanyWorkItemActionRequest
from app.schemas.module_access import CompanyModuleKey
from app.services.company_action_center_service import CompanyActionCenterService
from app.services.company_context_service import CompanyContextService, scoped_branch_ids
from app.services.company_operational_status_service import CompanyOperationalStatusService
from app.services.company_overview_service import CompanyOverviewService


router = APIRouter(prefix="/api/v1/company", tags=["customer-company-foundation"])


def ok(data: Any) -> dict[str, Any]:
    return {
        "data": data,
        "meta": {
            "version": settings.app_version,
            "contract_version": "2026-09-19.1",
        },
        "error": None,
    }


@router.get("/context")
async def get_company_context(
    current: TokenData = Depends(get_current_user),
    identity_db: AsyncSession = Depends(get_identity_db),
    operational_db: AsyncSession = Depends(get_restaurant_service_db),
) -> dict[str, Any]:
    result = await CompanyContextService(identity_db, operational_db).read_context(current)
    return ok(result.model_dump(mode="json"))


@router.get("/access")
async def get_effective_access(
    current: TokenData = Depends(get_current_user),
    identity_db: AsyncSession = Depends(get_identity_db),
    operational_db: AsyncSession = Depends(get_restaurant_service_db),
) -> dict[str, Any]:
    result = await CompanyContextService(identity_db, operational_db).effective_access(current)
    return ok(result.model_dump(mode="json"))


@router.get("/action-center")
async def get_action_center(
    current: TokenData = Depends(get_current_user),
    identity_db: AsyncSession = Depends(get_identity_db),
    operational_db: AsyncSession = Depends(get_restaurant_service_db),
) -> dict[str, Any]:
    result = await CompanyActionCenterService(identity_db, operational_db).list_items(current)
    return ok(result.model_dump(mode="json"))


@router.post("/action-center/{work_item_id}/actions")
async def action_work_item(
    work_item_id: str,
    payload: CompanyWorkItemActionRequest,
    request: Request,
    current: TokenData = Depends(get_current_user),
    identity_db: AsyncSession = Depends(get_identity_db),
    operational_db: AsyncSession = Depends(get_restaurant_service_db),
) -> dict[str, Any]:
    result = await CompanyActionCenterService(identity_db, operational_db).record_action(
        current,
        work_item_id,
        payload,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    return ok(result.model_dump(mode="json"))


@router.get("/overview")
async def get_company_overview(
    current: TokenData = Depends(get_current_user),
    identity_db: AsyncSession = Depends(get_identity_db),
    operational_db: AsyncSession = Depends(get_restaurant_service_db),
) -> dict[str, Any]:
    result = await CompanyOverviewService(identity_db, operational_db).read(current)
    return ok(result.model_dump(mode="json"))


@router.get("/overview/{module_key}")
async def get_module_overview(
    module_key: CompanyModuleKey,
    current: TokenData = Depends(get_current_user),
    identity_db: AsyncSession = Depends(get_identity_db),
    operational_db: AsyncSession = Depends(get_restaurant_service_db),
) -> dict[str, Any]:
    result = await CompanyOverviewService(identity_db, operational_db).read(current)
    section = next((item for item in result.sections if item.module_key == module_key), None)
    if section is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Overview not found")
    return ok(section.model_dump(mode="json"))


@router.get("/operational-status")
async def get_operational_status(
    current: TokenData = Depends(get_current_user),
    identity_db: AsyncSession = Depends(get_identity_db),
    operational_db: AsyncSession = Depends(get_restaurant_service_db),
) -> dict[str, Any]:
    if (
        "*" not in current.permissions
        and not set(current.permissions).intersection(
            {"system.device.view", "pos.sale.view", "fb.kitchen.ticket.manage"}
        )
    ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission denied")
    result = await CompanyOperationalStatusService(identity_db, operational_db).read(
        current.company_id,
        branch_ids=await scoped_branch_ids(current, operational_db),
    )
    return ok(result.model_dump(mode="json"))


@router.get("/audit")
async def get_company_audit(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=50, ge=1, le=100),
    current: TokenData = Depends(get_current_user),
    identity_db: AsyncSession = Depends(get_identity_db),
    operational_db: AsyncSession = Depends(get_restaurant_service_db),
) -> dict[str, Any]:
    if (
        "*" not in current.permissions
        and not set(current.permissions).intersection(
            {"system.company.view", "system.company.edit", "accounting.report.view"}
        )
    ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission denied")
    filters = [AuditLog.company_id == current.company_id]
    if "*" not in current.permissions and "company" not in current.scope_types:
        if current.branch_id is None:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Branch context required")
        filters.append(AuditLog.branch_id == current.branch_id)
    sessions = [identity_db]
    if identity_db.bind is not operational_db.bind:
        sessions.append(operational_db)

    # Identity and operational domains can be split across databases. Read
    # both audit streams, then merge them into one stable Company timeline.
    fetch_limit = page * limit
    totals = [
        int((await session.scalar(select(func.count(AuditLog.id)).where(*filters))) or 0)
        for session in sessions
    ]
    candidates: list[AuditLog] = []
    for session in sessions:
        candidates.extend(
            (
                await session.scalars(
                    select(AuditLog)
                    .where(*filters)
                    .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
                    .limit(fetch_limit)
                )
            ).all()
        )
    candidates.sort(key=lambda row: (row.created_at, row.id), reverse=True)
    rows = candidates[(page - 1) * limit : page * limit]
    total = sum(totals)
    return ok(
        {
            "items": [
                {
                    "id": str(row.id),
                    "company_id": str(row.company_id) if row.company_id else None,
                    "branch_id": str(row.branch_id) if row.branch_id else None,
                    "user_id": str(row.user_id) if row.user_id else None,
                    "action": row.action,
                    "resource": row.resource,
                    "resource_id": row.resource_id,
                    "old_value": row.old_value,
                    "new_value": row.new_value,
                    "created_at": row.created_at.isoformat(),
                }
                for row in rows
            ],
            "total": total,
            "page": page,
            "limit": limit,
        }
    )
