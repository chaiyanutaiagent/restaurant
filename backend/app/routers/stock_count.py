from __future__ import annotations

from typing import Any
import uuid

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.dependencies import TokenData, require_any_permission
from app.schemas.stock_count import (
    BatchUpdateCountRequest,
    CompleteSessionRequest,
    CountItemRead,
    CountSessionListItem,
    CountSessionRead,
    CreateCountSessionRequest,
    UpdateCountItemRequest,
)
from app.services.stock_count_service import StockCountService
from app.services.stock_access_service import (
    STOCK_MANAGE_PERMISSIONS,
    STOCK_VIEW_PERMISSIONS,
    StockAccessService,
)
from app.utils.pdf_generator import generate_count_sheet_pdf, generate_variance_report_pdf

router = APIRouter(prefix="/api/v1/stock-count", tags=["stock-count"])


def ok(data: Any, meta: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"data": data, "meta": {"version": settings.app_version, **(meta or {})}, "error": None}


async def ensure_session_access(
    db: AsyncSession,
    current: TokenData,
    session_id: uuid.UUID,
    *,
    manage: bool = False,
) -> None:
    session = await StockCountService(db).get_session(session_id, current.company_id)
    await StockAccessService(db).resolve_scope(
        current,
        requested_branch_id=session.branch_id,
        requested_location_id=session.location_id,
        manage=manage,
    )


@router.get("/sessions")
async def list_sessions(
    branch_id: uuid.UUID | None = Query(default=None),
    location_id: uuid.UUID | None = Query(default=None),
    status_value: str | None = Query(default=None, alias="status"),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=200),
    current: TokenData = Depends(require_any_permission(*STOCK_VIEW_PERMISSIONS)),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    service = StockCountService(db)
    scope = await StockAccessService(db).resolve_scope(
        current,
        requested_branch_id=branch_id,
        requested_location_id=location_id,
    )
    sessions, total = await service.list_sessions(
        company_id=current.company_id,
        branch_id=scope.branch_id,
        location_id=location_id,
        location_ids=scope.location_ids,
        status=status_value,
        page=page,
        limit=limit,
    )
    return ok(
        [CountSessionListItem.model_validate(item).model_dump() for item in sessions],
        meta={"total": total, "page": page, "limit": limit},
    )


@router.post("/sessions", status_code=status.HTTP_201_CREATED)
async def create_session(
    payload: CreateCountSessionRequest,
    current: TokenData = Depends(require_any_permission(*STOCK_MANAGE_PERMISSIONS)),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await StockAccessService(db).resolve_scope(
        current,
        requested_branch_id=payload.branch_id,
        requested_location_id=payload.location_id,
        manage=True,
    )
    session = await StockCountService(db).create_session(current.company_id, current.user_id, payload)
    return ok(CountSessionRead.model_validate(session).model_dump())


@router.get("/sessions/{session_id}")
async def get_session(
    session_id: uuid.UUID,
    current: TokenData = Depends(require_any_permission(*STOCK_VIEW_PERMISSIONS)),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await ensure_session_access(db, current, session_id)
    session = await StockCountService(db).get_session(session_id, current.company_id)
    return ok(CountSessionRead.model_validate(session).model_dump())


@router.post("/sessions/{session_id}/start")
async def start_session(
    session_id: uuid.UUID,
    current: TokenData = Depends(require_any_permission(*STOCK_MANAGE_PERMISSIONS)),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await ensure_session_access(db, current, session_id, manage=True)
    session = await StockCountService(db).start_session(session_id, current.company_id, current.user_id)
    return ok(CountSessionRead.model_validate(session).model_dump())


@router.patch("/sessions/{session_id}/items/{item_id}")
async def update_count_item(
    session_id: uuid.UUID,
    item_id: uuid.UUID,
    payload: UpdateCountItemRequest,
    current: TokenData = Depends(require_any_permission(*STOCK_MANAGE_PERMISSIONS)),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await ensure_session_access(db, current, session_id, manage=True)
    item = await StockCountService(db).update_count_item(session_id, item_id, current.company_id, current.user_id, payload)
    return ok(CountItemRead.model_validate(item).model_dump())


@router.post("/sessions/{session_id}/items/batch")
async def batch_update_items(
    session_id: uuid.UUID,
    payload: BatchUpdateCountRequest,
    current: TokenData = Depends(require_any_permission(*STOCK_MANAGE_PERMISSIONS)),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await ensure_session_access(db, current, session_id, manage=True)
    items = await StockCountService(db).batch_update_items(session_id, current.company_id, current.user_id, payload)
    return ok([CountItemRead.model_validate(item).model_dump() for item in items])


@router.post("/sessions/{session_id}/complete")
async def complete_session(
    session_id: uuid.UUID,
    payload: CompleteSessionRequest,
    current: TokenData = Depends(require_any_permission(*STOCK_MANAGE_PERMISSIONS)),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await ensure_session_access(db, current, session_id, manage=True)
    session = await StockCountService(db).complete_session(session_id, current.company_id, current.user_id, payload)
    return ok(CountSessionRead.model_validate(session).model_dump())


@router.post("/sessions/{session_id}/cancel")
async def cancel_session(
    session_id: uuid.UUID,
    current: TokenData = Depends(require_any_permission(*STOCK_MANAGE_PERMISSIONS)),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await ensure_session_access(db, current, session_id, manage=True)
    session = await StockCountService(db).cancel_session(session_id, current.company_id, current.user_id)
    return ok(CountSessionRead.model_validate(session).model_dump())


@router.get("/sessions/{session_id}/variance-report")
async def get_variance_report(
    session_id: uuid.UUID,
    current: TokenData = Depends(require_any_permission(*STOCK_VIEW_PERMISSIONS)),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await ensure_session_access(db, current, session_id)
    report = await StockCountService(db).get_variance_report(session_id, current.company_id)
    return ok(report.model_dump())


@router.get("/sessions/{session_id}/sheet")
async def download_count_sheet(
    session_id: uuid.UUID,
    current: TokenData = Depends(require_any_permission(*STOCK_VIEW_PERMISSIONS)),
    db: AsyncSession = Depends(get_db),
) -> Response:
    await ensure_session_access(db, current, session_id)
    service = StockCountService(db)
    data = await service.get_count_sheet_data(session_id, current.company_id)
    content, media_type = await generate_count_sheet_pdf(
        session=data["session"],
        items=data["items"],
        branch_name=data["branch_name"],
        location_name=data["location_name"],
        company_name=data["company_name"],
    )
    filename = f"count_sheet_{data['session'].session_number}.{'pdf' if media_type == 'application/pdf' else 'html'}"
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/sessions/{session_id}/variance-report/pdf")
async def download_variance_report(
    session_id: uuid.UUID,
    current: TokenData = Depends(require_any_permission(*STOCK_VIEW_PERMISSIONS)),
    db: AsyncSession = Depends(get_db),
) -> Response:
    await ensure_session_access(db, current, session_id)
    service = StockCountService(db)
    report = await service.get_variance_report(session_id, current.company_id)
    content, media_type = await generate_variance_report_pdf(report)
    filename = f"variance_report_{report.session_number}.{'pdf' if media_type == 'application/pdf' else 'html'}"
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
