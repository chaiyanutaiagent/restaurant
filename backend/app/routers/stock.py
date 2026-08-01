from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any
import uuid

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.dependencies import (
    TokenData,
    get_scoped_operational_db as get_db,
    require_any_permission,
    require_permission,
)
from app.models.audit import AuditLog
from app.models.settings import BranchSettings
from app.schemas.stock import (
    AdjustmentRequest,
    ReceiveStockRequest,
    StockBalanceRead,
    StockLocationCreate,
    StockLocationRead,
    StockLocationUpdate,
    StockMovementRead,
    StockSummaryResponse,
    TransferRequest,
)
from app.services.stock_service import StockService
from app.services.approval_service import ApprovalEvidence, ApprovalService
from app.services.stock_access_service import (
    STOCK_MANAGE_PERMISSIONS,
    STOCK_VIEW_PERMISSIONS,
    StockAccessService,
)

router = APIRouter(prefix="/api/v1/stock", tags=["stock"])


def ok(data: Any, meta: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"data": data, "meta": {"version": settings.app_version, **(meta or {})}, "error": None}


def _adjustment_approval_payload(payload: AdjustmentRequest) -> dict[str, Any]:
    return payload.model_dump(
        mode="json",
        exclude={"approval_token"},
        exclude_none=True,
        exclude_unset=True,
    )


@router.get("/locations")
async def list_locations(
    branch_id: uuid.UUID | None = Query(default=None),
    include_inactive: bool = Query(default=False),
    current: TokenData = Depends(require_any_permission(*STOCK_VIEW_PERMISSIONS)),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    service = StockService(db)
    scope = await StockAccessService(db).resolve_scope(current, requested_branch_id=branch_id)
    locations = await service.list_locations(
        current.company_id,
        scope.branch_id,
        location_ids=scope.location_ids,
        include_inactive=include_inactive,
    )
    return ok([StockLocationRead.model_validate(item).model_dump() for item in locations])


@router.post("/locations", status_code=status.HTTP_201_CREATED)
async def create_location(
    payload: StockLocationCreate,
    current: TokenData = Depends(require_permission("inventory.stock.adjust")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    if "*" not in current.permissions:
        StockAccessService(db).require_current_branch(current, payload.branch_id)
    service = StockService(db)
    location = await service.create_location(current.company_id, payload)
    db.add(
        AuditLog(
            company_id=current.company_id,
            branch_id=location.branch_id,
            user_id=current.user_id,
            action="stock.location.create",
            resource="StockLocation",
            resource_id=str(location.id),
            new_value=StockLocationRead.model_validate(location).model_dump(mode="json"),
        )
    )
    await db.commit()
    return ok(StockLocationRead.model_validate(location).model_dump())


@router.patch("/locations/{location_id}")
async def update_location(
    location_id: uuid.UUID,
    payload: StockLocationUpdate,
    current: TokenData = Depends(require_permission("inventory.stock.adjust")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    service = StockService(db)
    existing = await service.get_location(current.company_id, location_id)
    if "*" not in current.permissions:
        StockAccessService(db).require_current_branch(current, existing.branch_id)
    old_value = StockLocationRead.model_validate(existing).model_dump(mode="json")
    location = await service.update_location(current.company_id, location_id, payload)
    db.add(
        AuditLog(
            company_id=current.company_id,
            branch_id=location.branch_id,
            user_id=current.user_id,
            action="stock.location.update",
            resource="StockLocation",
            resource_id=str(location.id),
            old_value=old_value,
            new_value=StockLocationRead.model_validate(location).model_dump(mode="json"),
        )
    )
    await db.commit()
    return ok(StockLocationRead.model_validate(location).model_dump())


@router.get("/balances")
async def list_balances(
    branch_id: uuid.UUID | None = Query(default=None),
    location_id: uuid.UUID | None = Query(default=None),
    product_id: uuid.UUID | None = Query(default=None),
    low_stock_only: bool = Query(default=False),
    current: TokenData = Depends(require_any_permission(*STOCK_VIEW_PERMISSIONS)),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    service = StockService(db)
    scope = await StockAccessService(db).resolve_scope(
        current,
        requested_branch_id=branch_id,
        requested_location_id=location_id,
    )
    balances = await service.list_balances(
        company_id=current.company_id,
        branch_id=scope.branch_id,
        location_id=location_id,
        product_id=product_id,
        low_stock_only=low_stock_only,
        location_ids=scope.location_ids,
    )
    return ok([StockBalanceRead.model_validate(item).model_dump() for item in balances])


@router.get("/summary")
async def get_summary(
    branch_id: uuid.UUID | None = Query(default=None),
    current: TokenData = Depends(require_any_permission(*STOCK_VIEW_PERMISSIONS)),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    service = StockService(db)
    scope = await StockAccessService(db).resolve_scope(current, requested_branch_id=branch_id)
    summary = await service.get_stock_summary(
        current.company_id,
        scope.branch_id,
        location_ids=scope.location_ids,
    )
    return ok(StockSummaryResponse.model_validate(summary).model_dump())


@router.get("/movements")
async def list_movements(
    product_id: uuid.UUID | None = Query(default=None),
    branch_id: uuid.UUID | None = Query(default=None),
    location_id: uuid.UUID | None = Query(default=None),
    movement_type: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=50, ge=1, le=200),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    current: TokenData = Depends(require_any_permission(*STOCK_VIEW_PERMISSIONS)),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    service = StockService(db)
    scope = await StockAccessService(db).resolve_scope(
        current,
        requested_branch_id=branch_id,
        requested_location_id=location_id,
    )
    movements, total = await service.list_movements(
        company_id=current.company_id,
        product_id=product_id,
        branch_id=scope.branch_id,
        location_id=location_id,
        location_ids=scope.location_ids,
        movement_type=movement_type,
        page=page,
        limit=limit,
        date_from=date_from,
        date_to=date_to,
    )
    return ok(
        [StockMovementRead.model_validate(item).model_dump() for item in movements],
        meta={"total": total, "page": page, "limit": limit},
    )


@router.post("/adjust", status_code=status.HTTP_201_CREATED)
async def adjust_stock(
    payload: AdjustmentRequest,
    current: TokenData = Depends(
        require_any_permission(
            *STOCK_MANAGE_PERMISSIONS,
            "inventory.stock.adjust.request",
        )
    ),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    service = StockService(db)
    scope = await StockAccessService(db).resolve_scope(
        current,
        requested_location_id=payload.location_id,
        manage=True,
    )
    location = await service.get_location(current.company_id, payload.location_id)
    branch_settings = await db.scalar(
        select(BranchSettings).where(
            BranchSettings.company_id == current.company_id,
            BranchSettings.branch_id == location.branch_id,
        )
    )
    threshold = Decimal(
        branch_settings.stock_adjust_approval_threshold_qty
        if branch_settings
        else 10
    )
    approval_evidence: ApprovalEvidence | None = None
    if abs(Decimal(payload.qty)) > threshold:
        approval_evidence = await ApprovalService(db).authorize_operation(
            current=current,
            action="inventory.stock.adjust",
            request_payload=_adjustment_approval_payload(payload),
            approval_token=payload.approval_token,
            reason=payload.note or "Stock adjustment above branch threshold",
            resource_type="StockMovement",
        )
    movement = await service.adjust(current.company_id, current.user_id, payload)
    db.add(
        AuditLog(
            company_id=current.company_id,
            branch_id=movement.branch_id,
            user_id=current.user_id,
            action="stock.adjust",
            resource="StockMovement",
            resource_id=str(movement.id),
            new_value={
                "product_id": str(payload.product_id),
                "qty": str(payload.qty),
                "note": payload.note,
                "approval_threshold_qty": str(threshold),
                "approval": (
                    approval_evidence.as_audit_value()
                    if approval_evidence is not None
                    else None
                ),
            },
        )
    )
    await db.commit()
    movement = (
        await service.list_movements(
            current.company_id,
            product_id=movement.product_id,
            page=1,
            limit=1,
            location_id=payload.location_id,
            location_ids=scope.location_ids,
        )
    )[0][0]
    return ok(StockMovementRead.model_validate(movement).model_dump())


@router.post("/receive", status_code=status.HTTP_201_CREATED)
async def receive_stock(
    payload: ReceiveStockRequest,
    current: TokenData = Depends(require_any_permission(*STOCK_MANAGE_PERMISSIONS)),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    service = StockService(db)
    scope = await StockAccessService(db).resolve_scope(
        current,
        requested_location_id=payload.location_id,
        manage=True,
    )
    movements = await service.receive(current.company_id, current.user_id, payload)
    for movement in movements:
        db.add(
            AuditLog(
                company_id=current.company_id,
                branch_id=movement.branch_id,
                user_id=current.user_id,
                action="stock.receive",
                resource="StockMovement",
                resource_id=str(movement.id),
            )
        )
    await db.commit()
    detailed, _ = await service.list_movements(
        company_id=current.company_id,
        product_id=movements[0].product_id if len(movements) == 1 else None,
        location_id=payload.location_id,
        location_ids=scope.location_ids,
        page=1,
        limit=max(len(movements), 1),
    )
    detailed_map = {item.id: item for item in detailed}
    data = [StockMovementRead.model_validate(detailed_map.get(item.id, item)).model_dump() for item in movements]
    return ok(data)


@router.post("/transfer", status_code=status.HTTP_201_CREATED)
async def transfer_stock(
    payload: TransferRequest,
    current: TokenData = Depends(require_any_permission(*STOCK_MANAGE_PERMISSIONS)),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    service = StockService(db)
    access = StockAccessService(db)
    from_scope = await access.resolve_scope(
        current,
        requested_location_id=payload.from_location_id,
        manage=True,
    )
    to_scope = await access.resolve_scope(
        current,
        requested_location_id=payload.to_location_id,
        manage=True,
    )
    movements = await service.transfer(current.company_id, current.user_id, payload)
    for movement in movements:
        db.add(
            AuditLog(
                company_id=current.company_id,
                branch_id=movement.branch_id,
                user_id=current.user_id,
                action="stock.transfer",
                resource="StockMovement",
                resource_id=str(movement.id),
            )
        )
    await db.commit()
    detailed, _ = await service.list_movements(
        company_id=current.company_id,
        product_id=movements[0].product_id if len(movements) == 2 else None,
        location_ids=tuple(
            dict.fromkeys((from_scope.location_ids or ()) + (to_scope.location_ids or ()))
        ) if "*" not in current.permissions else None,
        page=1,
        limit=max(len(movements), 1),
    )
    detailed_map = {item.id: item for item in detailed}
    data = [StockMovementRead.model_validate(detailed_map.get(item.id, item)).model_dump() for item in movements]
    return ok(data)


@router.get("/products/{product_id}")
async def get_product_stock(
    product_id: uuid.UUID,
    current: TokenData = Depends(require_any_permission(*STOCK_VIEW_PERMISSIONS)),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    service = StockService(db)
    scope = await StockAccessService(db).resolve_scope(current)
    balances = await service.get_product_stock(
        product_id,
        current.company_id,
        branch_id=scope.branch_id,
        location_ids=scope.location_ids,
    )
    return ok([StockBalanceRead.model_validate(item).model_dump() for item in balances])
