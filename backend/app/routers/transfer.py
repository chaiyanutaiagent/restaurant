from __future__ import annotations

from typing import Any
import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.dependencies import TokenData, require_permission
from app.schemas.transfer import (
    ApproveTORequest,
    CancelTORequest,
    CreateTORequest,
    MultiBranchStockResponse,
    ReceiveTORequest,
    ShipTORequest,
    TOListItem,
    TransferOrderRead,
)
from app.services.transfer_service import TransferService

router = APIRouter(prefix="/api/v1/transfer", tags=["transfer"])


def ok(data: Any, meta: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"data": data, "meta": {"version": settings.app_version, **(meta or {})}, "error": None}


@router.get("/orders")
async def list_transfer_orders(
    from_branch_id: uuid.UUID | None = Query(default=None),
    to_branch_id: uuid.UUID | None = Query(default=None),
    status_value: str | None = Query(default=None, alias="status"),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=200),
    current: TokenData = Depends(require_permission("inventory.transfer.view")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    service = TransferService(db)
    orders, total = await service.list_tos(
        company_id=current.company_id,
        from_branch_id=from_branch_id,
        to_branch_id=to_branch_id,
        status_value=status_value,
        page=page,
        limit=limit,
    )
    return ok(
        [TOListItem.model_validate(item).model_dump() for item in orders],
        meta={"total": total, "page": page, "limit": limit},
    )


@router.post("/orders", status_code=status.HTTP_201_CREATED)
async def create_transfer_order(
    payload: CreateTORequest,
    current: TokenData = Depends(require_permission("inventory.transfer.create")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    order = await TransferService(db).create_to(current.company_id, current.user_id, payload)
    return ok(TransferOrderRead.model_validate(order).model_dump())


@router.get("/orders/{to_id}")
async def get_transfer_order(
    to_id: uuid.UUID,
    current: TokenData = Depends(require_permission("inventory.transfer.view")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    order = await TransferService(db).get_to(to_id, current.company_id)
    return ok(TransferOrderRead.model_validate(order).model_dump())


@router.post("/orders/{to_id}/submit")
async def submit_transfer_order(
    to_id: uuid.UUID,
    current: TokenData = Depends(require_permission("inventory.transfer.create")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    order = await TransferService(db).submit_to(to_id, current.company_id, current.user_id)
    return ok(TransferOrderRead.model_validate(order).model_dump())


@router.post("/orders/{to_id}/approve")
async def approve_transfer_order(
    to_id: uuid.UUID,
    payload: ApproveTORequest,
    current: TokenData = Depends(require_permission("inventory.transfer.approve")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    order = await TransferService(db).approve_to(to_id, current.company_id, current.user_id, payload)
    return ok(TransferOrderRead.model_validate(order).model_dump())


@router.post("/orders/{to_id}/ship")
async def ship_transfer_order(
    to_id: uuid.UUID,
    payload: ShipTORequest,
    current: TokenData = Depends(require_permission("inventory.transfer.approve")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    order = await TransferService(db).ship_to(to_id, current.company_id, current.user_id, payload)
    return ok(TransferOrderRead.model_validate(order).model_dump())


@router.post("/orders/{to_id}/receive")
async def receive_transfer_order(
    to_id: uuid.UUID,
    payload: ReceiveTORequest,
    current: TokenData = Depends(require_permission("inventory.transfer.create")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    order = await TransferService(db).receive_to(to_id, current.company_id, current.user_id, payload)
    return ok(TransferOrderRead.model_validate(order).model_dump())


@router.post("/orders/{to_id}/cancel")
async def cancel_transfer_order(
    to_id: uuid.UUID,
    payload: CancelTORequest,
    current: TokenData = Depends(require_permission("inventory.transfer.create")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    order = await TransferService(db).cancel_to(to_id, current.company_id, current.user_id, payload.reason)
    return ok(TransferOrderRead.model_validate(order).model_dump())


@router.get("/stock/multi-branch")
async def get_multi_branch_stock(
    current: TokenData = Depends(require_permission("inventory.stock.view")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    response = await TransferService(db).get_multi_branch_stock(current.company_id)
    return ok(MultiBranchStockResponse.model_validate(response).model_dump())
