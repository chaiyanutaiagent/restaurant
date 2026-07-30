from __future__ import annotations

from decimal import Decimal
from typing import Any
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.dependencies import TokenData, get_current_user, require_permission
from app.models.company import Company
from app.schemas.pos import CloseShiftRequest, CreateSaleRequest, OpenShiftRequest, PartialRefundRequest, RefundRequest, SaleOrderRead, ShiftRead, SyncSalesRequest, VoidRequest
from app.services.sale_service import SaleService
from app.utils.promptpay import generate_promptpay_payload

router = APIRouter(prefix="/api/v1/pos", tags=["pos"])


def ok(data: Any, meta: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"data": data, "meta": {"version": settings.app_version, **(meta or {})}, "error": None}


@router.post("/shifts/open", status_code=status.HTTP_201_CREATED)
async def open_shift(
    payload: OpenShiftRequest,
    current: TokenData = Depends(require_permission("pos.cashier.open_shift")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    if current.branch_id is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Branch context required")
    shift = await SaleService(db).open_shift(current.company_id, current.branch_id, current.user_id, payload)
    return ok(ShiftRead.model_validate(shift).model_dump())


@router.get("/shifts/current")
async def get_current_shift(
    current: TokenData = Depends(require_permission("pos.cashier.open_shift")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    if current.branch_id is None:
        return ok(None)
    shift = await SaleService(db).get_open_shift(current.company_id, current.user_id, current.branch_id)
    return ok(ShiftRead.model_validate(shift).model_dump() if shift else None)


@router.post("/shifts/{shift_id}/close")
async def close_shift(
    shift_id: uuid.UUID,
    payload: CloseShiftRequest,
    current: TokenData = Depends(require_permission("pos.cashier.close_shift")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    shift = await SaleService(db).close_shift(shift_id, current.company_id, current.user_id, payload)
    return ok(ShiftRead.model_validate(shift).model_dump())


@router.get("/shifts")
async def list_shifts(
    branch_id: uuid.UUID | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    current: TokenData = Depends(require_permission("pos.sale.view")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    shifts, total = await SaleService(db).list_shifts(current.company_id, branch_id, page, limit)
    return ok([ShiftRead.model_validate(item).model_dump() for item in shifts], meta={"total": total, "page": page, "limit": limit})


@router.post("/sales", status_code=status.HTTP_201_CREATED)
async def create_sale(
    payload: CreateSaleRequest,
    response: Response,
    current: TokenData = Depends(require_permission("pos.sale.create")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    if current.branch_id is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Branch context required")
    service = SaleService(db)
    existing = await service.get_existing_sale_by_client_order_id(current.company_id, current.branch_id, payload.client_order_id)
    if existing is not None:
        response.status_code = status.HTTP_200_OK
        return ok(SaleOrderRead.model_validate(existing).model_dump())
    order = await service.create_sale(current.company_id, current.branch_id, current.user_id, payload)
    return ok(SaleOrderRead.model_validate(order).model_dump())


@router.post("/sales/sync")
async def sync_sales(
    payload: SyncSalesRequest,
    current: TokenData = Depends(require_permission("pos.sale.create")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    if current.branch_id is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Branch context required")
    orders = await SaleService(db).sync_offline_sales(current.company_id, current.branch_id, current.user_id, payload.orders)
    return ok([SaleOrderRead.model_validate(item).model_dump() for item in orders])


@router.get("/sales")
async def list_sales(
    shift_id: uuid.UUID | None = Query(default=None),
    branch_id: uuid.UUID | None = Query(default=None),
    status_value: str | None = Query(default=None, alias="status"),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    current: TokenData = Depends(require_permission("pos.sale.view")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    rows, total = await SaleService(db).list_sales(
        current.company_id,
        shift_id=shift_id,
        branch_id=branch_id,
        status_value=status_value,
        page=page,
        limit=limit,
    )
    return ok([SaleOrderRead.model_validate(item).model_dump() for item in rows], meta={"total": total, "page": page, "limit": limit})


@router.get("/sales/{order_id}")
async def get_sale(
    order_id: uuid.UUID,
    current: TokenData = Depends(require_permission("pos.sale.view")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    order = await SaleService(db).get_sale(order_id, current.company_id)
    return ok(SaleOrderRead.model_validate(order).model_dump())


@router.post("/sales/{order_id}/void")
async def void_sale(
    order_id: uuid.UUID,
    payload: VoidRequest,
    current: TokenData = Depends(require_permission("pos.sale.void")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    order = await SaleService(db).void_sale(order_id, current.company_id, current.user_id, payload)
    return ok(SaleOrderRead.model_validate(order).model_dump())


@router.post("/sales/{order_id}/refund")
async def refund_sale(
    order_id: uuid.UUID,
    payload: RefundRequest,
    current: TokenData = Depends(require_permission("pos.refund.create")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    order = await SaleService(db).refund_sale(order_id, current.company_id, current.user_id, payload.refund_reason)
    return ok(SaleOrderRead.model_validate(order).model_dump())


@router.post("/sales/{order_id}/refund/partial")
async def partial_refund_sale(
    order_id: uuid.UUID,
    payload: PartialRefundRequest,
    current: TokenData = Depends(require_permission("pos.refund.create")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    order = await SaleService(db).partial_refund_sale(order_id, current.company_id, current.user_id, payload)
    return ok(SaleOrderRead.model_validate(order).model_dump())


@router.get("/promptpay/qr")
async def get_promptpay_qr(
    amount: Decimal | None = Query(default=None, gt=0),
    target: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    company_target = target
    if not company_target:
        company = await db.scalar(select(Company).where(Company.is_active.is_(True)).order_by(Company.created_at.asc()))
        company_target = (company.phone if company and company.phone else None) or (company.tax_id if company and company.tax_id else None) or "0812345678"
    qr_amount = Decimal(amount).quantize(Decimal("0.01")) if amount is not None else None
    try:
        payload = generate_promptpay_payload(company_target, qr_amount)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="PromptPay ต้องเป็นเบอร์มือถือไทย 10 หลักหรือเลขผู้เสียภาษี 13 หลัก",
        ) from exc
    return ok({"payload": payload, "amount": f"{qr_amount:.2f}" if qr_amount is not None else None, "target": company_target})
