from __future__ import annotations

from typing import Any
import uuid

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.dependencies import TokenData, require_any_permission
from app.schemas.tax_operations import TaxExportCreate, TaxIssueResolve, TaxLedgerIngest, TaxPeriodAction
from app.services.tax_operations_service import TaxOperationsService


router = APIRouter(prefix="/api/v1/tax-operations", tags=["tax-operations"])
view_tax = require_any_permission("accounting.tax.view", "accounting.report.view", "system.company.edit")
manage_tax = require_any_permission("accounting.tax.manage", "system.company.edit")


def ok(data: Any) -> dict[str, Any]:
    return {"data": data, "meta": {"version": settings.app_version}, "error": None}


@router.get("/dashboard")
async def dashboard(
    year: int = Query(..., ge=2000, le=2200),
    month: int = Query(..., ge=1, le=12),
    branch_id: uuid.UUID | None = Query(default=None),
    current: TokenData = Depends(view_tax),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    return ok(await TaxOperationsService(db).dashboard(current.company_id, year, month, branch_id))


@router.post("/sync/legacy")
async def sync_legacy(
    payload: TaxPeriodAction,
    current: TokenData = Depends(manage_tax),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    return ok(await TaxOperationsService(db).sync_legacy(current.company_id, current.user_id, payload.year, payload.month))


@router.post("/ledger")
async def ingest_ledger(
    payload: TaxLedgerIngest,
    current: TokenData = Depends(manage_tax),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    row = await TaxOperationsService(db).ingest(current.company_id, current.user_id, payload)
    return ok(TaxOperationsService._ledger_dict(row))


@router.post("/reconcile")
async def reconcile(
    payload: TaxPeriodAction,
    current: TokenData = Depends(manage_tax),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    return ok(await TaxOperationsService(db).reconcile(current.company_id, current.user_id, payload.year, payload.month, payload.branch_id))


@router.post("/periods/{action}")
async def change_period(
    action: str,
    payload: TaxPeriodAction,
    current: TokenData = Depends(manage_tax),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    if action not in {"review", "close", "reopen"}:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="ไม่พบคำสั่งงวดภาษี")
    row = await TaxOperationsService(db).change_period(current.company_id, current.user_id, action, payload)
    return ok(TaxOperationsService._period_dict(row))


@router.patch("/issues/{issue_id}")
async def resolve_issue(
    issue_id: uuid.UUID,
    payload: TaxIssueResolve,
    current: TokenData = Depends(manage_tax),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    row = await TaxOperationsService(db).resolve_issue(current.company_id, current.user_id, issue_id, payload.status, payload.note)
    return ok(TaxOperationsService._issue_dict(row))


@router.post("/exports")
async def create_export(
    payload: TaxExportCreate,
    current: TokenData = Depends(manage_tax),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    row = await TaxOperationsService(db).create_export(current.company_id, current.user_id, payload)
    return ok(TaxOperationsService._export_dict(row))


@router.get("/exports/{export_id}/download")
async def download_export(
    export_id: uuid.UUID,
    current: TokenData = Depends(view_tax),
    db: AsyncSession = Depends(get_db),
) -> Response:
    row = await TaxOperationsService(db).get_export(current.company_id, export_id)
    content = str((row.payload or {}).get("content", ""))
    return Response(content=content.encode("utf-8"), media_type=row.content_type, headers={"Content-Disposition": f'attachment; filename="{row.filename}"', "X-Content-SHA256": row.content_sha256})
