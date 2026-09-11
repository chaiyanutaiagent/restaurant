from __future__ import annotations

from typing import Any
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_identity_db
from app.dependencies import DeviceTokenData, TokenData, get_device_operational_db, require_device_type
from app.models.audit import AuditLog
from app.models.branch import Branch
from app.models.restaurant import KitchenTicket
from app.models.takeaway import TakeawayKitchenTicket, TakeawayOrder
from app.models.settings import BranchSettings
from app.schemas.device import (
    DeviceContextRead,
    DeviceWorkspaceBootstrapRead,
    DeviceWorkspaceBranchRead,
)
from app.schemas.restaurant import TicketStatusUpdate
from app.services.dining_service import DiningService
from app.services.staff_scope_policy import normalized_station_key
from app.services.takeaway_service import TakeawayService


router = APIRouter(prefix="/api/v1/device-workspaces", tags=["device-workspaces"])


def ok(data: Any) -> dict[str, Any]:
    return {
        "data": data,
        "meta": {
            "version": settings.app_version,
            "identity_database": settings.identity_database,
            "restaurant_service_database": settings.restaurant_service_database,
            "takeaway_service_database": settings.takeaway_service_database,
        },
        "error": None,
    }


def _device_context(current: DeviceTokenData) -> DeviceContextRead:
    return DeviceContextRead(
        device_id=current.device_id,
        company_id=current.company_id,
        brand_id=current.brand_id,
        branch_id=current.branch_id,
        device_code=current.device_code,
        name=current.name,
        device_type=current.device_type,
        station_key=current.station_key,
        business_type=current.business_type,
        target_database=current.target_database,
        credential_version=current.credential_version,
        paired_at=current.paired_at,
        last_seen_at=current.last_seen_at,
    )


async def _bootstrap(
    current: DeviceTokenData,
    identity_db: AsyncSession,
    operational_db: AsyncSession,
) -> DeviceWorkspaceBootstrapRead:
    branch = await identity_db.get(Branch, current.branch_id)
    if (
        branch is None
        or branch.company_id != current.company_id
        or branch.deleted_at is not None
        or not branch.is_active
    ):
        raise HTTPException(status_code=401, detail="Device Branch is unavailable")
    settings_row = None
    if current.business_type == "restaurant":
        settings_row = await operational_db.scalar(
            select(BranchSettings).where(
                BranchSettings.company_id == current.company_id,
                BranchSettings.branch_id == current.branch_id,
            )
        )
    queue_prefix = settings_row.fb_queue_prefix if settings_row is not None else (
        "TW" if current.business_type == "takeaway" else ""
    )
    capabilities = {
        "counter": ["staff_login", "pos_handoff"],
        "kitchen": ["ticket_view", "ticket_progress"],
        "pickup": ["queue_view", "queue_serve"],
    }[current.device_type]
    return DeviceWorkspaceBootstrapRead(
        workspace=current.device_type,
        device=_device_context(current),
        branch=DeviceWorkspaceBranchRead(id=branch.id, code=branch.code, name=branch.name),
        station_key=current.station_key,
        queue_prefix=queue_prefix or "",
        requires_staff_login=current.device_type == "counter",
        capabilities=capabilities,
    )


def _ticket_data(ticket: KitchenTicket | TakeawayKitchenTicket) -> dict[str, Any]:
    if isinstance(ticket, TakeawayKitchenTicket):
        device_status = {"queued": "pending", "preparing": "cooking", "ready": "done"}.get(
            ticket.status,
            ticket.status,
        )
        return {
            "id": str(ticket.id),
            "order_id": str(ticket.order_id),
            "product_name": ticket.item_name,
            "qty": ticket.quantity,
            "special_request": None,
            "station": ticket.station,
            "queue_number": ticket.queue_number,
            "table_name": None,
            "source_type": "quick_service",
            "status": device_status,
            "created_at": ticket.created_at.isoformat() if ticket.created_at else None,
            "done_at": ticket.ready_at.isoformat() if ticket.ready_at else None,
        }
    return {
        "id": str(ticket.id),
        "session_id": str(ticket.session_id),
        "product_name": ticket.product_name,
        "qty": ticket.qty,
        "special_request": ticket.special_request,
        "station": ticket.station,
        "queue_number": ticket.queue_number,
        "table_name": ticket.table_name,
        "source_type": "dine_in" if ticket.table_name else "quick_service",
        "status": ticket.status,
        "created_at": ticket.created_at.isoformat() if ticket.created_at else None,
        "done_at": ticket.done_at.isoformat() if ticket.done_at else None,
    }


def _audit_device_action(
    db: AsyncSession,
    current: DeviceTokenData,
    request: Request,
    *,
    action: str,
    resource: str,
    resource_id: str,
    old_value: dict[str, Any] | None,
    new_value: dict[str, Any],
) -> None:
    db.add(
        AuditLog(
            company_id=current.company_id,
            branch_id=current.branch_id,
            user_id=None,
            action=action,
            resource=resource,
            resource_id=resource_id,
            old_value=old_value,
            new_value={
                **new_value,
                "device_id": str(current.device_id),
                "device_code": current.device_code,
                "station_key": current.station_key,
            },
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    )


@router.get("/counter/bootstrap")
async def counter_bootstrap(
    current: DeviceTokenData = Depends(require_device_type("counter")),
    identity_db: AsyncSession = Depends(get_identity_db),
    operational_db: AsyncSession = Depends(get_device_operational_db),
) -> dict[str, Any]:
    result = await _bootstrap(current, identity_db, operational_db)
    return ok(result.model_dump())


@router.get("/kitchen/bootstrap")
async def kitchen_bootstrap(
    current: DeviceTokenData = Depends(require_device_type("kitchen")),
    identity_db: AsyncSession = Depends(get_identity_db),
    operational_db: AsyncSession = Depends(get_device_operational_db),
) -> dict[str, Any]:
    result = await _bootstrap(current, identity_db, operational_db)
    return ok(result.model_dump())


@router.get("/kitchen/tickets")
async def list_kitchen_tickets(
    current: DeviceTokenData = Depends(require_device_type("kitchen")),
    db: AsyncSession = Depends(get_device_operational_db),
) -> dict[str, Any]:
    if current.business_type == "takeaway":
        statement = select(TakeawayKitchenTicket).where(
            TakeawayKitchenTicket.company_id == current.company_id,
            TakeawayKitchenTicket.branch_id == current.branch_id,
            TakeawayKitchenTicket.status.in_(["queued", "preparing", "ready"]),
        )
        if current.station_key:
            statement = statement.where(TakeawayKitchenTicket.station == current.station_key)
        tickets = list(await db.scalars(statement.order_by(TakeawayKitchenTicket.queue_number)))
    else:
        tickets = await DiningService(db).list_kitchen_tickets(
            current.branch_id,
            current.station_key,
        )
    return ok([_ticket_data(ticket) for ticket in tickets])


@router.patch("/kitchen/tickets/{ticket_id}")
async def update_kitchen_ticket(
    ticket_id: uuid.UUID,
    payload: TicketStatusUpdate,
    request: Request,
    current: DeviceTokenData = Depends(require_device_type("kitchen")),
    db: AsyncSession = Depends(get_device_operational_db),
) -> dict[str, Any]:
    if current.business_type == "takeaway":
        translated = {"cooking": "preparing", "done": "ready"}.get(payload.status)
        if translated is None:
            raise HTTPException(status_code=400, detail="Takeaway kitchen device may only progress tickets")
        service = TakeawayService(db, _takeaway_token_data(current))
        updated = await service.update_kitchen_ticket(ticket_id, translated)
        return ok({"id": str(updated.id), "status": updated.status})
    ticket = await db.get(KitchenTicket, ticket_id)
    if (
        ticket is None
        or ticket.company_id != current.company_id
        or ticket.branch_id != current.branch_id
        or normalized_station_key(ticket.station) != normalized_station_key(current.station_key)
    ):
        raise HTTPException(status_code=404, detail="ไม่พบ ticket")
    if payload.status not in {"cooking", "done"}:
        raise HTTPException(status_code=400, detail="Kitchen device may only progress to cooking or done")
    old_status = ticket.status
    try:
        updated = await DiningService(db).update_ticket_status(ticket, payload.status)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _audit_device_action(
        db,
        current,
        request,
        action="device.kitchen.ticket.update",
        resource="KitchenTicket",
        resource_id=str(updated.id),
        old_value={"status": old_status},
        new_value={"status": updated.status},
    )
    await db.commit()
    return ok({"id": str(updated.id), "status": updated.status})


@router.get("/pickup/bootstrap")
async def pickup_bootstrap(
    current: DeviceTokenData = Depends(require_device_type("pickup")),
    identity_db: AsyncSession = Depends(get_identity_db),
    operational_db: AsyncSession = Depends(get_device_operational_db),
) -> dict[str, Any]:
    result = await _bootstrap(current, identity_db, operational_db)
    return ok(result.model_dump())


@router.get("/pickup/queue")
async def get_pickup_queue(
    current: DeviceTokenData = Depends(require_device_type("pickup")),
    db: AsyncSession = Depends(get_device_operational_db),
) -> dict[str, Any]:
    if current.business_type == "takeaway":
        rows = (
            await db.execute(
                select(
                    TakeawayOrder,
                    func.count(TakeawayKitchenTicket.id),
                    func.coalesce(func.sum(TakeawayKitchenTicket.quantity), 0),
                    func.max(TakeawayKitchenTicket.ready_at),
                )
                .outerjoin(TakeawayKitchenTicket, TakeawayKitchenTicket.order_id == TakeawayOrder.id)
                .where(
                    TakeawayOrder.company_id == current.company_id,
                    TakeawayOrder.branch_id == current.branch_id,
                    TakeawayOrder.fulfillment_status == "ready",
                )
                .group_by(TakeawayOrder.id)
                .order_by(TakeawayOrder.queue_number)
            )
        ).all()
        return ok([
            {
                "session_id": str(order.id),
                "queue_number": order.queue_number,
                "order_number": order.order_number,
                "customer_name": order.customer_name,
                "ticket_count": ticket_count,
                "item_count": float(item_count),
                "ready_at": ready_at.isoformat() if ready_at else None,
                "status": order.fulfillment_status,
            }
            for order, ticket_count, item_count, ready_at in rows
        ])
    rows = await DiningService(db).get_ready_pickup_queues(current.branch_id)
    return ok(rows)


@router.post("/pickup/queue/{session_id}/served")
async def mark_pickup_queue_served(
    session_id: uuid.UUID,
    request: Request,
    current: DeviceTokenData = Depends(require_device_type("pickup")),
    db: AsyncSession = Depends(get_device_operational_db),
) -> dict[str, Any]:
    if current.business_type == "takeaway":
        order = await TakeawayService(db, _takeaway_token_data(current)).mark_picked_up(session_id)
        return ok({"session_id": str(order.id), "status": order.fulfillment_status, "served_count": 1})
    try:
        result = await DiningService(db).mark_pickup_session_served(
            session_id,
            current.company_id,
            current.branch_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _audit_device_action(
        db,
        current,
        request,
        action="device.pickup.queue.serve",
        resource="DiningSession",
        resource_id=str(session_id),
        old_value={"status": "ready"},
        new_value={"status": "served", "served_count": result["served_count"]},
    )
    await db.commit()
    return ok(result)


def _takeaway_token_data(current: DeviceTokenData) -> TokenData:
    return TokenData(
        user_id=current.device_id,
        company_id=current.company_id,
        brand_id=current.brand_id,
        branch_id=current.branch_id,
        business_type=current.business_type,
        target_database=current.target_database,
        permissions=["*"],
        station_key=current.station_key,
        scope_types=["station"],
    )
