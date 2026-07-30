from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any
import uuid

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.dependencies import TokenData, require_permission
from app.schemas.logistics import (
    CarrierRead,
    CreateShipmentRequest,
    EstimateRequest,
    ShipmentListItem,
    ShipmentRead,
    ShipmentStatusUpdateRequest,
    UpdateShipmentRequest,
)
from app.services.logistics_service import LogisticsService
from app.utils.pdf_generator import generate_shipping_label_pdf

router = APIRouter(prefix="/api/v1/logistics", tags=["logistics"])


def ok(data: Any, meta: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"data": data, "meta": {"version": settings.app_version, **(meta or {})}, "error": None}


def serialize_shipment(shipment) -> dict[str, Any]:
    carrier = shipment.carrier
    tracking_url = None
    if carrier and carrier.tracking_url and shipment.tracking_number:
        tracking_url = carrier.tracking_url.format(tracking_no=shipment.tracking_number)
    payload = ShipmentRead(
        id=shipment.id,
        shipment_number=shipment.shipment_number,
        status=shipment.status,
        branch_id=shipment.branch_id,
        carrier_id=shipment.carrier_id,
        sale_order_id=shipment.sale_order_id,
        external_order_id=shipment.external_order_id,
        sender_name=shipment.sender_name,
        sender_phone=shipment.sender_phone,
        sender_address=shipment.sender_address,
        recipient_name=shipment.recipient_name,
        recipient_phone=shipment.recipient_phone,
        recipient_address=shipment.recipient_address,
        weight_grams=shipment.weight_grams,
        width_cm=shipment.width_cm,
        height_cm=shipment.height_cm,
        depth_cm=shipment.depth_cm,
        service_name=shipment.service_name,
        is_cod=shipment.is_cod,
        cod_amount=shipment.cod_amount,
        shipping_cost=shipment.shipping_cost,
        tracking_number=shipment.tracking_number,
        picked_up_at=shipment.picked_up_at,
        delivered_at=shipment.delivered_at,
        note=shipment.note,
        created_at=shipment.created_at,
        updated_at=shipment.updated_at,
        carrier_name=carrier.name if carrier else "-",
        carrier_code=carrier.code if carrier else "-",
        tracking_url=tracking_url,
        items=shipment.items,
        events=shipment.events,
    )
    return payload.model_dump(mode="json")


def serialize_shipment_list_item(shipment) -> dict[str, Any]:
    carrier = shipment.carrier
    return ShipmentListItem(
        id=shipment.id,
        shipment_number=shipment.shipment_number,
        status=shipment.status,
        carrier_name=carrier.name if carrier else "-",
        carrier_code=carrier.code if carrier else "-",
        recipient_name=shipment.recipient_name,
        recipient_phone=shipment.recipient_phone,
        tracking_number=shipment.tracking_number,
        is_cod=shipment.is_cod,
        cod_amount=shipment.cod_amount,
        shipping_cost=shipment.shipping_cost,
        weight_grams=shipment.weight_grams,
        created_at=shipment.created_at,
    ).model_dump(mode="json")


@router.get("/carriers")
async def list_carriers(
    current: TokenData = Depends(require_permission("pos.sale.view")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    rows = await LogisticsService(db).list_carriers(current.company_id)
    return ok([CarrierRead.model_validate(row).model_dump(mode="json") for row in rows])


@router.post("/estimate")
async def estimate_shipping(
    payload: EstimateRequest,
    current: TokenData = Depends(require_permission("pos.sale.view")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    rows = await LogisticsService(db).estimate_shipping(current.company_id, payload)
    return ok([row.model_dump(mode="json") for row in rows])


@router.get("/shipments")
async def list_shipments(
    status_value: str | None = Query(default=None, alias="status"),
    carrier_id: uuid.UUID | None = Query(default=None),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    search: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    current: TokenData = Depends(require_permission("pos.sale.view")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    rows, total = await LogisticsService(db).list_shipments(
        current.company_id,
        status=status_value,
        carrier_id=carrier_id,
        date_from=date_from,
        date_to=date_to,
        search=search,
        page=page,
        limit=limit,
    )
    return ok([serialize_shipment_list_item(row) for row in rows], meta={"total": total, "page": page, "limit": limit})


@router.post("/shipments", status_code=status.HTTP_201_CREATED)
async def create_shipment(
    payload: CreateShipmentRequest,
    current: TokenData = Depends(require_permission("pos.sale.create")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    shipment = await LogisticsService(db).create_shipment(current.company_id, current.user_id, payload)
    return ok(serialize_shipment(shipment))


@router.get("/shipments/{shipment_id}")
async def get_shipment(
    shipment_id: uuid.UUID,
    current: TokenData = Depends(require_permission("pos.sale.view")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    shipment = await LogisticsService(db).get_shipment(shipment_id, current.company_id)
    return ok(serialize_shipment(shipment))


@router.patch("/shipments/{shipment_id}")
async def update_shipment(
    shipment_id: uuid.UUID,
    payload: UpdateShipmentRequest,
    current: TokenData = Depends(require_permission("pos.sale.create")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    service = LogisticsService(db)
    shipment = await service.get_shipment(shipment_id, current.company_id)
    if payload.tracking_number is not None:
        shipment = await service.update_tracking(shipment_id, current.company_id, payload.tracking_number)
    if payload.note is not None and payload.status is None:
        shipment.note = payload.note
        await db.commit()
        shipment = await service.get_shipment(shipment_id, current.company_id)
    if payload.status is not None and payload.status != shipment.status:
        shipment = await service.update_shipment_status(
            shipment_id,
            current.company_id,
            current.user_id,
            payload.status,
            note=payload.note,
        )
    return ok(serialize_shipment(shipment))


@router.post("/shipments/{shipment_id}/status")
async def update_shipment_status(
    shipment_id: uuid.UUID,
    payload: ShipmentStatusUpdateRequest,
    current: TokenData = Depends(require_permission("pos.sale.create")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    shipment = await LogisticsService(db).update_shipment_status(
        shipment_id,
        current.company_id,
        current.user_id,
        payload.status,
        payload.location,
        payload.note,
    )
    return ok(serialize_shipment(shipment))


@router.get("/shipments/{shipment_id}/label")
async def get_shipment_label(
    shipment_id: uuid.UUID,
    current: TokenData = Depends(require_permission("pos.sale.view")),
    db: AsyncSession = Depends(get_db),
) -> Response:
    shipment = await LogisticsService(db).get_shipment(shipment_id, current.company_id)
    content, media_type = await generate_shipping_label_pdf(shipment, shipment.carrier.name if shipment.carrier else "-")
    ext = "pdf" if media_type == "application/pdf" else "html"
    filename = f"label_{shipment.shipment_number}.{ext}"
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{Path(filename).name}"'},
    )
