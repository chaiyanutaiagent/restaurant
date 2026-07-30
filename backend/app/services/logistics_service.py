from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time, timezone
from decimal import Decimal
import logging
import uuid

from fastapi import HTTPException, status
from sqlalchemy import func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.api_integration import ExternalOrder
from app.models.audit import AuditLog
from app.models.branch import Branch
from app.models.logistics import Carrier, Shipment, ShipmentEvent, ShipmentItem, ShippingRate
from app.models.pos import SaleOrder
from app.models.settings import BranchSettings
from app.schemas.logistics import CreateShipmentRequest, EstimateRequest, ShipmentItemCreate, ShippingEstimate
from app.utils.shipping_calculator import calc_shipping_cost, estimate_all_carriers, generate_tracking_number
from app.utils.webhook_dispatcher import trigger_event

logger = logging.getLogger(__name__)

ALLOWED_TRANSITIONS = {
    "pending": {"packed", "cancelled"},
    "packed": {"picked_up", "cancelled"},
    "picked_up": {"in_transit", "delivered", "returned"},
    "in_transit": {"delivered", "returned"},
    "delivered": set(),
    "returned": set(),
    "cancelled": set(),
}


class LogisticsService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_carriers(self, company_id: uuid.UUID) -> list[Carrier]:
        rows = await self.db.scalars(
            select(Carrier)
            .where(Carrier.company_id == company_id, Carrier.is_active.is_(True))
            .order_by(Carrier.sort_order.asc(), Carrier.name.asc())
        )
        return rows.all()

    async def estimate_shipping(
        self,
        company_id: uuid.UUID,
        data: EstimateRequest,
    ) -> list[ShippingEstimate]:
        rates = (
            await self.db.scalars(
                select(ShippingRate)
                .where(ShippingRate.company_id == company_id, ShippingRate.is_active.is_(True))
                .options(selectinload(ShippingRate.carrier))
            )
        ).all()
        grouped: dict[str, list[ShippingRate]] = defaultdict(list)
        carrier_id_by_code: dict[str, str] = {}
        for rate in rates:
            if rate.carrier is None or not rate.carrier.is_active:
                continue
            grouped[rate.carrier.code].append(rate)
            carrier_id_by_code[rate.carrier.code] = str(rate.carrier.id)
        estimates = estimate_all_carriers(grouped, data.weight_grams, data.zone, data.is_cod)
        return [
            ShippingEstimate(
                carrier_id=carrier_id_by_code[item["carrier_code"]],
                carrier_code=item["carrier_code"],
                carrier_name=item["carrier_name"],
                service_name=item["service_name"],
                cost=item["cost"],
                cod_fee=item["cod_fee"],
            )
            for item in estimates
        ]

    async def create_shipment(
        self,
        company_id: uuid.UUID,
        user_id: uuid.UUID,
        data: CreateShipmentRequest,
    ) -> Shipment:
        if data.sale_order_id and data.external_order_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only one source order can be selected")

        carrier = await self.db.scalar(
            select(Carrier).where(
                Carrier.id == data.carrier_id,
                Carrier.company_id == company_id,
                Carrier.is_active.is_(True),
            )
        )
        if carrier is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Carrier not found")

        branch = await self.db.scalar(
            select(Branch).where(
                Branch.id == data.branch_id,
                Branch.company_id == company_id,
                Branch.deleted_at.is_(None),
            )
        )
        if branch is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Branch not found")
        settings = await self.db.scalar(
            select(BranchSettings).where(
                BranchSettings.company_id == company_id,
                BranchSettings.branch_id == branch.id,
            )
        )

        sale_order: SaleOrder | None = None
        external_order: ExternalOrder | None = None
        source_items: list[ShipmentItemCreate] = list(data.items)
        if data.sale_order_id is not None:
            sale_order = await self.db.scalar(
                select(SaleOrder)
                .where(SaleOrder.id == data.sale_order_id, SaleOrder.company_id == company_id)
                .options(selectinload(SaleOrder.items))
            )
            if sale_order is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sale order not found")
            if not source_items:
                source_items = [
                    ShipmentItemCreate(
                        product_id=item.product_id,
                        product_name=item.product_name,
                        sku=item.sku,
                        qty=item.qty,
                        unit_price=item.unit_price,
                    )
                    for item in sale_order.items
                ]
        if data.external_order_id is not None:
            external_order = await self.db.scalar(
                select(ExternalOrder).where(
                    ExternalOrder.id == data.external_order_id,
                    ExternalOrder.company_id == company_id,
                )
            )
            if external_order is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="External order not found")
            if not source_items:
                source_items = [
                    ShipmentItemCreate(
                        product_name=str(item.get("product_name") or item.get("sku") or "External Item"),
                        sku=item.get("sku"),
                        qty=Decimal(str(item.get("qty", 0) or 0)),
                        unit_price=Decimal(str(item.get("unit_price"))) if item.get("unit_price") is not None else None,
                    )
                    for item in (external_order.items_json or [])
                ]

        tracking_number = data.tracking_number or generate_tracking_number(carrier.code)
        day_prefix = datetime.now().strftime("%Y%m%d")
        shipment_number = await self._generate_shipment_number(company_id, day_prefix)

        shipment = Shipment(
            company_id=company_id,
            branch_id=branch.id,
            carrier_id=carrier.id,
            shipment_number=shipment_number,
            status="pending",
            sale_order_id=sale_order.id if sale_order else None,
            external_order_id=external_order.id if external_order else None,
            sender_name=branch.name,
            sender_phone=(branch.phone or (settings.promptpay_target if settings else None) or "-"),
            sender_address=branch.address or "-",
            recipient_name=data.recipient_name,
            recipient_phone=data.recipient_phone,
            recipient_address=data.recipient_address,
            weight_grams=data.weight_grams,
            width_cm=data.width_cm,
            height_cm=data.height_cm,
            depth_cm=data.depth_cm,
            service_name=data.service_name,
            is_cod=data.is_cod,
            cod_amount=data.cod_amount,
            shipping_cost=data.shipping_cost,
            tracking_number=tracking_number,
            note=data.note,
            created_by=user_id,
        )
        self.db.add(shipment)
        await self.db.flush()

        for item in source_items:
            self.db.add(
                ShipmentItem(
                    shipment_id=shipment.id,
                    product_id=item.product_id,
                    product_name=item.product_name,
                    sku=item.sku,
                    qty=item.qty,
                    unit_price=item.unit_price,
                )
            )

        self.db.add(
            ShipmentEvent(
                shipment_id=shipment.id,
                status="pending",
                note="สร้างรายการจัดส่ง",
                created_by=user_id,
            )
        )

        if external_order is not None:
            external_order.status = "processing"

        self.db.add(
            AuditLog(
                company_id=company_id,
                branch_id=branch.id,
                user_id=user_id,
                action="logistics.shipment.created",
                resource="Shipment",
                resource_id=str(shipment.id),
                new_value={"shipment_number": shipment.shipment_number, "tracking_number": tracking_number},
            )
        )

        try:
            await trigger_event(
                self.db,
                company_id,
                "shipment.created",
                {
                    "shipment_number": shipment.shipment_number,
                    "tracking_number": tracking_number,
                    "carrier_code": carrier.code,
                    "recipient_name": shipment.recipient_name,
                    "status": shipment.status,
                },
            )
        except Exception as exc:
            logger.warning("shipment.created webhook failed: %s", exc)

        await self.db.commit()
        return await self.get_shipment(shipment.id, company_id)

    async def update_shipment_status(
        self,
        shipment_id: uuid.UUID,
        company_id: uuid.UUID,
        user_id: uuid.UUID,
        new_status: str,
        location: str | None = None,
        note: str | None = None,
    ) -> Shipment:
        shipment = await self.get_shipment(shipment_id, company_id)
        current_status = shipment.status
        allowed = ALLOWED_TRANSITIONS.get(current_status, set())
        if new_status not in allowed:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid status transition")

        shipment.status = new_status
        now = datetime.now(timezone.utc)
        if new_status == "picked_up":
            shipment.picked_up_at = now
        elif new_status == "delivered":
            shipment.delivered_at = now
        elif new_status == "returned":
            shipment.returned_at = now

        self.db.add(
            ShipmentEvent(
                shipment_id=shipment.id,
                status=new_status,
                location=location,
                note=note,
                created_by=user_id,
            )
        )

        if new_status == "delivered" and shipment.external_order_id is not None:
            external_order = await self.db.get(ExternalOrder, shipment.external_order_id)
            if external_order is not None:
                external_order.status = "fulfilled"

        self.db.add(
            AuditLog(
                company_id=company_id,
                branch_id=shipment.branch_id,
                user_id=user_id,
                action="logistics.shipment.status_updated",
                resource="Shipment",
                resource_id=str(shipment.id),
                old_value={"status": current_status},
                new_value={"status": new_status, "location": location, "note": note},
            )
        )
        try:
            await trigger_event(
                self.db,
                company_id,
                "shipment.status_updated",
                {
                    "shipment_number": shipment.shipment_number,
                    "tracking_number": shipment.tracking_number,
                    "status": new_status,
                    "location": location,
                },
            )
        except Exception as exc:
            logger.warning("shipment.status_updated webhook failed: %s", exc)

        await self.db.commit()
        return await self.get_shipment(shipment.id, company_id)

    async def update_tracking(
        self,
        shipment_id: uuid.UUID,
        company_id: uuid.UUID,
        tracking_number: str,
    ) -> Shipment:
        shipment = await self.get_shipment(shipment_id, company_id)
        shipment.tracking_number = tracking_number
        await self.db.commit()
        return await self.get_shipment(shipment.id, company_id)

    async def list_shipments(
        self,
        company_id: uuid.UUID,
        status: str | None = None,
        carrier_id: uuid.UUID | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        search: str | None = None,
        page: int = 1,
        limit: int = 20,
    ) -> tuple[list[Shipment], int]:
        filters = [Shipment.company_id == company_id]
        if status:
            filters.append(Shipment.status == status)
        if carrier_id:
            filters.append(Shipment.carrier_id == carrier_id)
        if date_from:
            filters.append(Shipment.created_at >= datetime.combine(date_from, time.min, tzinfo=timezone.utc))
        if date_to:
            filters.append(Shipment.created_at <= datetime.combine(date_to, time.max, tzinfo=timezone.utc))
        if search:
            pattern = f"%{search.strip()}%"
            filters.append(
                or_(
                    Shipment.tracking_number.ilike(pattern),
                    Shipment.recipient_name.ilike(pattern),
                    Shipment.shipment_number.ilike(pattern),
                )
            )
        total = int((await self.db.scalar(select(func.count(Shipment.id)).where(*filters))) or 0)
        rows = (
            await self.db.scalars(
                select(Shipment)
                .where(*filters)
                .options(selectinload(Shipment.carrier))
                .order_by(Shipment.created_at.desc())
                .offset((page - 1) * limit)
                .limit(limit)
            )
        ).all()
        return rows, total

    async def get_shipment(
        self,
        shipment_id: uuid.UUID,
        company_id: uuid.UUID,
    ) -> Shipment:
        self.db.expire_all()
        shipment = await self.db.scalar(
            select(Shipment)
            .where(Shipment.id == shipment_id, Shipment.company_id == company_id)
            .execution_options(populate_existing=True)
            .options(
                selectinload(Shipment.carrier),
                selectinload(Shipment.items),
                selectinload(Shipment.events),
            )
        )
        if shipment is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shipment not found")
        return shipment

    async def get_possible_next_statuses(
        self,
        shipment_id: uuid.UUID,
        company_id: uuid.UUID,
    ) -> list[str]:
        shipment = await self.get_shipment(shipment_id, company_id)
        return sorted(ALLOWED_TRANSITIONS.get(shipment.status, set()))

    async def calculate_default_shipping_cost(
        self,
        company_id: uuid.UUID,
        carrier_id: uuid.UUID,
        weight_grams: int,
        zone: str = "all",
        is_cod: bool = False,
    ) -> Decimal:
        rates = (
            await self.db.scalars(
                select(ShippingRate)
                .where(
                    ShippingRate.company_id == company_id,
                    ShippingRate.carrier_id == carrier_id,
                    ShippingRate.is_active.is_(True),
                )
                .options(selectinload(ShippingRate.carrier))
            )
        ).all()
        return calc_shipping_cost(rates, weight_grams, zone, is_cod)

    async def _generate_shipment_number(
        self,
        company_id: uuid.UUID,
        date_str: str,
    ) -> str:
        lock_key = hash(str(company_id) + date_str + "LOGISTICS") % (2**31)
        await self.db.execute(text(f"SELECT pg_advisory_xact_lock({lock_key})"))
        count = (
            await self.db.scalar(
                select(func.count(Shipment.id)).where(
                    Shipment.company_id == company_id,
                    Shipment.shipment_number.like(f"SHP{date_str}-%"),
                )
            )
        ) or 0
        return f"SHP{date_str}-{int(count) + 1:04d}"
