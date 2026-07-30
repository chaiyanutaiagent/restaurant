from __future__ import annotations

from typing import Any
import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.dependencies import TokenData, require_permission
from app.schemas.accounting import AccountCreate, AccountUpdate, CreateJournalEntryRequest
from app.services.accounting_service import AccountingService

router = APIRouter(prefix="/api/v1/accounting", tags=["accounting"])


def ok(data: Any, meta: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"data": data, "meta": {"version": settings.app_version, **(meta or {})}, "error": None}


@router.get("/accounts")
async def list_accounts(
    account_type: str | None = Query(default=None),
    tree: bool = Query(default=False),
    current: TokenData = Depends(require_permission("accounting.report.view")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    service = AccountingService(db)
    accounts = await service.list_accounts(current.company_id, account_type=account_type, tree=tree)
    return ok([service.serialize_account(account) for account in accounts])


@router.post("/accounts", status_code=status.HTTP_201_CREATED)
async def create_account(
    payload: AccountCreate,
    current: TokenData = Depends(require_permission("accounting.invoice.create")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    service = AccountingService(db)
    account = await service.create_account(current.company_id, payload)
    return ok(service.serialize_account(account))


@router.get("/accounts/{account_id}")
async def get_account(
    account_id: uuid.UUID,
    current: TokenData = Depends(require_permission("accounting.report.view")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    service = AccountingService(db)
    account = await service.get_account(account_id, current.company_id)
    return ok(service.serialize_account(account))


@router.patch("/accounts/{account_id}")
async def update_account(
    account_id: uuid.UUID,
    payload: AccountUpdate,
    current: TokenData = Depends(require_permission("accounting.invoice.create")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    service = AccountingService(db)
    account = await service.update_account(account_id, current.company_id, payload)
    return ok(service.serialize_account(account))


@router.get("/entries")
async def list_entries(
    entry_type: str | None = Query(default=None),
    period_year: int | None = Query(default=None),
    period_month: int | None = Query(default=None),
    account_id: uuid.UUID | None = Query(default=None),
    reference_type: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=50, ge=1, le=100),
    current: TokenData = Depends(require_permission("accounting.report.view")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    service = AccountingService(db)
    entries, total = await service.list_entries(
        current.company_id,
        entry_type=entry_type,
        period_year=period_year,
        period_month=period_month,
        account_id=account_id,
        reference_type=reference_type,
        page=page,
        limit=limit,
    )
    return ok([service.serialize_entry_list_item(entry) for entry in entries], meta={"total": total, "page": page, "limit": limit})


@router.post("/entries", status_code=status.HTTP_201_CREATED)
async def create_entry(
    payload: CreateJournalEntryRequest,
    current: TokenData = Depends(require_permission("accounting.invoice.create")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    service = AccountingService(db)
    entry = await service.create_manual_entry(current.company_id, current.branch_id, current.user_id, payload)
    return ok(service.serialize_entry(entry))


@router.get("/entries/{entry_id}")
async def get_entry(
    entry_id: uuid.UUID,
    current: TokenData = Depends(require_permission("accounting.report.view")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    service = AccountingService(db)
    entry = await service.get_entry(entry_id, current.company_id)
    return ok(service.serialize_entry(entry))


@router.post("/entries/{entry_id}/reverse")
async def reverse_entry(
    entry_id: uuid.UUID,
    current: TokenData = Depends(require_permission("accounting.invoice.create")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    service = AccountingService(db)
    entry = await service.reverse_entry(entry_id, current.company_id, current.user_id)
    return ok(service.serialize_entry(entry))


@router.get("/reports/trial-balance")
async def get_trial_balance(
    period_year: int = Query(...),
    period_month: int = Query(..., ge=1, le=12),
    current: TokenData = Depends(require_permission("accounting.report.view")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    service = AccountingService(db)
    return ok(await service.get_trial_balance(current.company_id, period_year, period_month))


@router.get("/reports/profit-loss")
async def get_profit_loss(
    period_year: int = Query(...),
    period_month: int = Query(..., ge=1, le=12),
    cumulative: bool = Query(default=False),
    current: TokenData = Depends(require_permission("accounting.report.view")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    service = AccountingService(db)
    return ok(await service.get_profit_loss(current.company_id, period_year, period_month, cumulative))


@router.get("/accounts/{account_id}/ledger")
async def get_account_ledger(
    account_id: uuid.UUID,
    period_year: int = Query(...),
    period_month: int = Query(..., ge=1, le=12),
    current: TokenData = Depends(require_permission("accounting.report.view")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    service = AccountingService(db)
    ledger = await service.get_account_ledger(account_id, current.company_id, period_year, period_month)
    return ok(ledger.model_dump())
