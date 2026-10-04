from __future__ import annotations

from datetime import date, datetime, time, timezone
from decimal import Decimal, ROUND_HALF_UP
import hashlib
import json
import uuid
from zoneinfo import ZoneInfo

from fastapi import HTTPException, status
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.audit import AuditLog
from app.models.branch import Branch
from app.models.distribution import CompanyDistributionDemand, CompanyDistributionEvent, CompanyDistributionShipment
from app.models.product import Product
from app.models.restaurant import Brand, BrandBranch
from app.models.stock import StockBalance, StockLocation
from app.models.transfer import TransferOrder
from app.schemas.distribution import (
    DistributionActionRequest,
    DistributionDemandCreateRequest,
    DistributionReceiveRequest,
    DistributionRejectRequest,
    DistributionReturnRequest,
    DistributionShipmentPlanRequest,
)
from app.schemas.transfer import ApproveTORequest, CreateTORequest, ReceiveTORequest, ShipTORequest, TOItemApprove, TOItemCreate, TOItemReceive
from app.services.transfer_service import TransferService


BANGKOK = ZoneInfo("Asia/Bangkok")
FOURPLACES = Decimal("0.0001")
MODULE_BUSINESS_TYPE = {
    "restaurant_pos": "restaurant",
    "takeaway_pos": "takeaway",
    "retail_pos": "retail_pos",
}


def q4(value: Decimal | int | float | None) -> Decimal:
    return Decimal(value or 0).quantize(FOURPLACES, rounding=ROUND_HALF_UP)


def expected_business_type(source_module: str) -> str:
    try:
        return MODULE_BUSINESS_TYPE[source_module]
    except KeyError as exc:
        raise ValueError(f"ไม่รองรับโมดูลต้นทาง {source_module}") from exc


def reconciliation(shipped: Decimal, received: Decimal, rejected: Decimal, returned: Decimal) -> dict[str, Decimal]:
    shipped_q, received_q, rejected_q, returned_q = map(q4, (shipped, received, rejected, returned))
    if min(shipped_q, received_q, rejected_q, returned_q) < 0:
        raise ValueError("จำนวนกระจายสินค้าต้องไม่ติดลบ")
    if received_q + rejected_q > shipped_q:
        raise ValueError("ยอดรับรวมยอดปฏิเสธมากกว่ายอดส่ง")
    if returned_q > received_q:
        raise ValueError("ยอดคืนมากกว่ายอดที่รับ")
    return {
        "shipped_qty": shipped_q,
        "received_qty": received_q,
        "rejected_qty": rejected_q,
        "returned_qty": returned_q,
        "in_transit_qty": q4(shipped_q - received_q - rejected_q),
        "net_received_qty": q4(received_q - returned_q),
    }


def _fingerprint(payload: dict[str, object]) -> str:
    normalized = {key: str(value) if isinstance(value, (date, Decimal, uuid.UUID)) else value for key, value in payload.items()}
    return hashlib.sha256(json.dumps(normalized, sort_keys=True, ensure_ascii=True, separators=(",", ":")).encode()).hexdigest()


class DistributionService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.transfer = TransferService(db)

    async def create_demand(
        self,
        company_id: uuid.UUID,
        actor_id: uuid.UUID,
        data: DistributionDemandCreateRequest,
    ) -> dict:
        payload_hash = _fingerprint(data.model_dump())
        existing = await self.db.scalar(
            select(CompanyDistributionDemand).where(
                CompanyDistributionDemand.company_id == company_id,
                CompanyDistributionDemand.idempotency_key == data.idempotency_key,
            )
        )
        if existing:
            self._assert_replay(existing.payload_hash, payload_hash)
            return {**await self._demand_dict(existing), "replayed": True}

        await self._distribution_context(
            company_id, data.source_module, data.brand_id, data.branch_id, data.product_id
        )
        demand = CompanyDistributionDemand(
            company_id=company_id,
            source_module=data.source_module,
            brand_id=data.brand_id,
            branch_id=data.branch_id,
            product_id=data.product_id,
            needed_on=data.needed_on,
            requested_qty=q4(data.requested_qty),
            unit_code=data.unit_code.strip(),
            status="submitted",
            source_type=data.source_type.strip(),
            source_id=data.source_id.strip(),
            idempotency_key=data.idempotency_key,
            payload_hash=payload_hash,
            requested_by=actor_id,
            note=data.note,
        )
        self.db.add(demand)
        await self.db.flush()
        self._audit(company_id, actor_id, "company_distribution.demand.created", str(demand.id), {
            "source_module": data.source_module, "source_id": data.source_id
        })
        await self.db.commit()
        return {**await self._demand_dict(demand), "replayed": False}

    async def plan_shipment(
        self,
        company_id: uuid.UUID,
        actor_id: uuid.UUID,
        data: DistributionShipmentPlanRequest,
    ) -> dict:
        payload_hash = _fingerprint(data.model_dump())
        existing = await self.db.scalar(
            select(CompanyDistributionShipment).where(
                CompanyDistributionShipment.company_id == company_id,
                CompanyDistributionShipment.idempotency_key == data.idempotency_key,
            )
        )
        if existing:
            self._assert_replay(existing.payload_hash, payload_hash)
            return {**await self._shipment_dict(existing), "replayed": True}
        try:
            demand = await self._get_demand(company_id, data.demand_id, lock=True)
            if demand.status in {"fulfilled", "cancelled"}:
                raise HTTPException(status_code=409, detail="Demand นี้ปิดแล้ว")
            planned_qty = q4(data.planned_qty)
            allocated = q4(await self.db.scalar(
                select(func.coalesce(func.sum(CompanyDistributionShipment.planned_qty), 0)).where(
                    CompanyDistributionShipment.company_id == company_id,
                    CompanyDistributionShipment.demand_id == demand.id,
                    CompanyDistributionShipment.status != "cancelled",
                )
            ))
            remaining = q4(demand.requested_qty - allocated)
            if planned_qty > remaining:
                raise HTTPException(status_code=409, detail=f"จำนวนเกิน Demand คงเหลือ {remaining}")
            context = await self._distribution_context(
                company_id, demand.source_module, demand.brand_id, demand.branch_id, demand.product_id
            )
            product: Product = context["product"]
            product_unit = product.unit.code if product.unit else None
            if product_unit and product_unit.lower() != demand.unit_code.lower():
                raise HTTPException(status_code=409, detail=f"หน่วย Demand ต้องเป็น {product_unit}")
            transfer = await self.transfer.create_to(
                company_id,
                actor_id,
                CreateTORequest(
                    from_branch_id=context["brand"].central_branch_id,
                    to_branch_id=demand.branch_id,
                    from_location_id=context["brand"].central_ready_location_id,
                    to_location_id=context["brand_branch"].store_location_id,
                    expected_date=demand.needed_on,
                    note=f"WP6 {demand.source_module} · {demand.source_type}:{demand.source_id}",
                    items=[TOItemCreate(product_id=demand.product_id, qty_requested=planned_qty)],
                ),
                commit=False,
            )
            transfer = await self.transfer.submit_to(transfer.id, company_id, actor_id, commit=False)
            transfer = await self.transfer.approve_to(
                transfer.id,
                company_id,
                actor_id,
                ApproveTORequest(items=[TOItemApprove(item_id=transfer.items[0].id, qty_approved=planned_qty)]),
                commit=False,
            )
            shipment_number = await self._generate_shipment_number(company_id)
            shipment = CompanyDistributionShipment(
                company_id=company_id,
                demand_id=demand.id,
                transfer_order_id=transfer.id,
                source_module=demand.source_module,
                brand_id=demand.brand_id,
                branch_id=demand.branch_id,
                product_id=demand.product_id,
                from_location_id=context["brand"].central_ready_location_id,
                to_location_id=context["brand_branch"].store_location_id,
                shipment_number=shipment_number,
                status="planned",
                planned_qty=planned_qty,
                unit_code=demand.unit_code,
                idempotency_key=data.idempotency_key,
                payload_hash=payload_hash,
                planned_by=actor_id,
                note=data.note,
            )
            self.db.add(shipment)
            await self.db.flush()
            self._event(shipment, actor_id, "planned", planned_qty, f"planned:{data.idempotency_key}", payload_hash, transfer.id, data.note)
            demand.status = "allocated" if planned_qty == remaining else "partially_allocated"
            self._audit(company_id, actor_id, "company_distribution.shipment.planned", str(shipment.id), {
                "shipment_number": shipment_number, "transfer_order_id": str(transfer.id)
            })
            await self.db.commit()
        except Exception:
            await self.db.rollback()
            raise
        return {**await self._shipment_dict(shipment), "replayed": False}

    async def dispatch(
        self, company_id: uuid.UUID, actor_id: uuid.UUID, shipment_id: uuid.UUID, data: DistributionActionRequest
    ) -> dict:
        payload_hash = _fingerprint({"shipment_id": shipment_id, **data.model_dump()})
        replay = await self._event_replay(company_id, f"dispatched:{data.idempotency_key}", payload_hash)
        if replay:
            return {**await self._shipment_dict(replay.shipment), "replayed": True}
        try:
            shipment = await self._get_shipment(company_id, shipment_id, lock=True)
            if shipment.status != "planned":
                raise HTTPException(status_code=409, detail="ส่งสินค้าได้เฉพาะรายการที่วางแผนแล้ว")
            transfer = await self.transfer.ship_to(
                shipment.transfer_order_id, company_id, actor_id, ShipTORequest(note=data.note), commit=False
            )
            item = transfer.items[0]
            shipment.status = "in_transit"
            shipment.shipped_qty = q4(item.qty_sent)
            shipment.unit_cost = q4(item.unit_cost)
            shipment.dispatched_at = datetime.now(timezone.utc)
            self._event(shipment, actor_id, "dispatched", shipment.shipped_qty, f"dispatched:{data.idempotency_key}", payload_hash, transfer.id, data.note)
            self._audit(company_id, actor_id, "company_distribution.shipment.dispatched", str(shipment.id))
            await self.db.commit()
        except Exception:
            await self.db.rollback()
            raise
        return {**await self._shipment_dict(shipment), "replayed": False}

    async def receive(
        self, company_id: uuid.UUID, actor_id: uuid.UUID, shipment_id: uuid.UUID, data: DistributionReceiveRequest
    ) -> dict:
        payload_hash = _fingerprint({"shipment_id": shipment_id, **data.model_dump()})
        replay = await self._event_replay(company_id, f"received:{data.idempotency_key}", payload_hash)
        if replay:
            return {**await self._shipment_dict(replay.shipment), "replayed": True}
        try:
            shipment = await self._get_shipment(company_id, shipment_id, lock=True)
            if shipment.status not in {"in_transit", "partially_received"}:
                raise HTTPException(status_code=409, detail="รับสินค้าได้เฉพาะรายการระหว่างทาง")
            target = q4(data.cumulative_received_qty)
            current = q4(shipment.received_qty)
            if target < current or target > q4(shipment.shipped_qty):
                raise HTTPException(status_code=400, detail="ยอดรับสะสมไม่ถูกต้อง")
            delta = q4(target - current)
            transfer = await self.transfer.get_to(shipment.transfer_order_id, company_id)
            if data.finalize and target < q4(shipment.shipped_qty) and not (data.note or "").strip():
                raise HTTPException(status_code=400, detail="ต้องระบุเหตุผลเมื่อปิดรับไม่ครบ")
            transfer = await self.transfer.receive_to(
                transfer.id,
                company_id,
                actor_id,
                ReceiveTORequest(
                    items=[TOItemReceive(item_id=transfer.items[0].id, qty_received=target)],
                    note=data.note,
                    finalize=data.finalize,
                ),
                commit=False,
            )
            shipment.received_qty = target
            if transfer.status == "completed":
                shipment.rejected_qty = q4(shipment.shipped_qty - target)
                shipment.status = "rejected" if shipment.rejected_qty > 0 else "received"
                shipment.settled_at = datetime.now(timezone.utc)
            else:
                shipment.status = "partially_received"
            event_type = "rejected" if shipment.status == "rejected" else "received"
            event_qty = shipment.rejected_qty if event_type == "rejected" else delta
            self._event(
                shipment, actor_id, event_type, event_qty, f"received:{data.idempotency_key}", payload_hash,
                transfer.id, data.note, {"received_delta": str(delta), "cumulative_received_qty": str(target)}
            )
            await self._refresh_demand_status(shipment.demand_id, company_id)
            self._audit(company_id, actor_id, f"company_distribution.shipment.{event_type}", str(shipment.id))
            await self.db.commit()
        except Exception:
            await self.db.rollback()
            raise
        return {**await self._shipment_dict(shipment), "replayed": False}

    async def reject(
        self, company_id: uuid.UUID, actor_id: uuid.UUID, shipment_id: uuid.UUID, data: DistributionRejectRequest
    ) -> dict:
        payload_hash = _fingerprint({"shipment_id": shipment_id, **data.model_dump()})
        replay = await self._event_replay(company_id, f"rejected:{data.idempotency_key}", payload_hash)
        if replay:
            return {**await self._shipment_dict(replay.shipment), "replayed": True}
        try:
            shipment = await self._get_shipment(company_id, shipment_id, lock=True)
            if shipment.status not in {"in_transit", "partially_received"}:
                raise HTTPException(status_code=409, detail="ปฏิเสธได้เฉพาะรายการระหว่างทางที่ยังไม่ปิดรับ")
            transfer = await self.transfer.get_to(shipment.transfer_order_id, company_id)
            target = q4(shipment.received_qty)
            transfer = await self.transfer.receive_to(
                transfer.id,
                company_id,
                actor_id,
                ReceiveTORequest(
                    items=[TOItemReceive(item_id=transfer.items[0].id, qty_received=target)],
                    note=data.reason,
                    finalize=True,
                ),
                commit=False,
            )
            shipment.rejected_qty = q4(shipment.shipped_qty - target)
            shipment.status = "rejected"
            shipment.settled_at = datetime.now(timezone.utc)
            self._event(shipment, actor_id, "rejected", shipment.rejected_qty, f"rejected:{data.idempotency_key}", payload_hash, transfer.id, data.reason)
            await self._refresh_demand_status(shipment.demand_id, company_id)
            self._audit(company_id, actor_id, "company_distribution.shipment.rejected", str(shipment.id), {"reason": data.reason})
            await self.db.commit()
        except Exception:
            await self.db.rollback()
            raise
        return {**await self._shipment_dict(shipment), "replayed": False}

    async def return_goods(
        self, company_id: uuid.UUID, actor_id: uuid.UUID, shipment_id: uuid.UUID, data: DistributionReturnRequest
    ) -> dict:
        payload_hash = _fingerprint({"shipment_id": shipment_id, **data.model_dump()})
        replay = await self._event_replay(company_id, f"returned:{data.idempotency_key}", payload_hash)
        if replay:
            return {**await self._shipment_dict(replay.shipment), "replayed": True}
        try:
            shipment = await self._get_shipment(company_id, shipment_id, lock=True)
            qty = q4(data.qty)
            available_to_return = q4(shipment.received_qty - shipment.returned_qty)
            if shipment.status not in {"received", "rejected", "partially_returned"} or qty > available_to_return:
                raise HTTPException(status_code=409, detail=f"คืนสินค้าได้ไม่เกิน {available_to_return}")
            original = await self.transfer.get_to(shipment.transfer_order_id, company_id)
            reverse = await self.transfer.create_to(
                company_id,
                actor_id,
                CreateTORequest(
                    from_branch_id=original.to_branch_id,
                    to_branch_id=original.from_branch_id,
                    from_location_id=shipment.to_location_id,
                    to_location_id=shipment.from_location_id,
                    expected_date=datetime.now(BANGKOK).date(),
                    note=f"WP6 คืนจาก {shipment.shipment_number}: {data.reason}",
                    items=[TOItemCreate(product_id=shipment.product_id, qty_requested=qty)],
                ),
                commit=False,
            )
            reverse = await self.transfer.submit_to(reverse.id, company_id, actor_id, commit=False)
            reverse = await self.transfer.approve_to(
                reverse.id, company_id, actor_id,
                ApproveTORequest(items=[TOItemApprove(item_id=reverse.items[0].id, qty_approved=qty)]),
                commit=False,
            )
            reverse = await self.transfer.ship_to(reverse.id, company_id, actor_id, ShipTORequest(note=data.reason), commit=False)
            reverse = await self.transfer.receive_to(
                reverse.id, company_id, actor_id,
                ReceiveTORequest(items=[TOItemReceive(item_id=reverse.items[0].id, qty_received=qty)], note=data.reason, finalize=True),
                commit=False,
            )
            shipment.returned_qty = q4(shipment.returned_qty + qty)
            shipment.status = "returned" if shipment.returned_qty == q4(shipment.received_qty) else "partially_returned"
            self._event(
                shipment, actor_id, "returned", qty, f"returned:{data.idempotency_key}", payload_hash,
                reverse.id, data.reason, {"return_transfer_number": reverse.to_number}
            )
            await self._refresh_demand_status(shipment.demand_id, company_id)
            self._audit(company_id, actor_id, "company_distribution.shipment.returned", str(shipment.id), {
                "qty": str(qty), "return_transfer_order_id": str(reverse.id)
            })
            await self.db.commit()
        except Exception:
            await self.db.rollback()
            raise
        return {**await self._shipment_dict(shipment), "replayed": False}

    async def cancel(
        self, company_id: uuid.UUID, actor_id: uuid.UUID, shipment_id: uuid.UUID, data: DistributionRejectRequest
    ) -> dict:
        payload_hash = _fingerprint({"shipment_id": shipment_id, **data.model_dump()})
        replay = await self._event_replay(company_id, f"cancelled:{data.idempotency_key}", payload_hash)
        if replay:
            return {**await self._shipment_dict(replay.shipment), "replayed": True}
        try:
            shipment = await self._get_shipment(company_id, shipment_id, lock=True)
            if shipment.status != "planned":
                raise HTTPException(status_code=409, detail="ยกเลิกได้ก่อนส่งสินค้าเท่านั้น")
            await self.transfer.cancel_to(
                shipment.transfer_order_id, company_id, actor_id, data.reason, commit=False
            )
            shipment.status = "cancelled"
            self._event(shipment, actor_id, "cancelled", Decimal("0"), f"cancelled:{data.idempotency_key}", payload_hash, shipment.transfer_order_id, data.reason)
            await self._refresh_demand_status(shipment.demand_id, company_id)
            self._audit(company_id, actor_id, "company_distribution.shipment.cancelled", str(shipment.id), {"reason": data.reason})
            await self.db.commit()
        except Exception:
            await self.db.rollback()
            raise
        return {**await self._shipment_dict(shipment), "replayed": False}

    async def dashboard(self, company_id: uuid.UUID) -> dict:
        demands = list((await self.db.scalars(
            select(CompanyDistributionDemand)
            .where(CompanyDistributionDemand.company_id == company_id)
            .options(
                selectinload(CompanyDistributionDemand.brand),
                selectinload(CompanyDistributionDemand.branch),
                selectinload(CompanyDistributionDemand.product),
                selectinload(CompanyDistributionDemand.shipments),
            )
            .order_by(CompanyDistributionDemand.needed_on.asc(), CompanyDistributionDemand.created_at.desc())
            .limit(200)
        )).unique().all())
        shipments = list((await self.db.scalars(
            select(CompanyDistributionShipment)
            .where(CompanyDistributionShipment.company_id == company_id)
            .options(
                selectinload(CompanyDistributionShipment.brand),
                selectinload(CompanyDistributionShipment.branch),
                selectinload(CompanyDistributionShipment.product),
                selectinload(CompanyDistributionShipment.transfer_order).selectinload(TransferOrder.items),
                selectinload(CompanyDistributionShipment.events),
            )
            .order_by(CompanyDistributionShipment.created_at.desc())
            .limit(200)
        )).unique().all())
        return {
            "demands": [await self._demand_dict(row) for row in demands],
            "shipments": [await self._shipment_dict(row) for row in shipments],
            "setup_options": await self._setup_options(company_id),
        }

    async def report(self, company_id: uuid.UUID, date_from: date, date_to: date) -> dict:
        if date_to < date_from or (date_to - date_from).days > 92:
            raise HTTPException(status_code=400, detail="ช่วงรายงานต้องไม่เกิน 93 วัน")
        start = datetime.combine(date_from, time.min, BANGKOK).astimezone(timezone.utc)
        end = datetime.combine(date_to, time.max, BANGKOK).astimezone(timezone.utc)
        rows = list((await self.db.scalars(
            select(CompanyDistributionShipment)
            .join(
                CompanyDistributionEvent,
                CompanyDistributionEvent.shipment_id == CompanyDistributionShipment.id,
            )
            .where(
                CompanyDistributionShipment.company_id == company_id,
                CompanyDistributionEvent.created_at >= start,
                CompanyDistributionEvent.created_at <= end,
            )
            .options(
                selectinload(CompanyDistributionShipment.brand),
                selectinload(CompanyDistributionShipment.branch),
                selectinload(CompanyDistributionShipment.product),
                selectinload(CompanyDistributionShipment.transfer_order).selectinload(TransferOrder.items),
                selectinload(CompanyDistributionShipment.events),
            )
            .order_by(CompanyDistributionShipment.created_at.desc())
            .distinct()
        )).unique().all())
        groups: dict[tuple[str, uuid.UUID, uuid.UUID], dict] = {}
        totals = {key: Decimal("0") for key in ("planned_qty", "shipped_qty", "received_qty", "rejected_qty", "returned_qty", "in_transit_qty", "net_received_qty")}
        for row in rows:
            rec = reconciliation(row.shipped_qty, row.received_qty, row.rejected_qty, row.returned_qty)
            key = (row.source_module, row.brand_id, row.branch_id)
            group = groups.setdefault(key, {
                "source_module": row.source_module, "brand_id": row.brand_id, "brand_name": row.brand.name,
                "branch_id": row.branch_id, "branch_name": row.branch.name, "shipment_count": 0,
                **{name: Decimal("0") for name in totals},
            })
            group["shipment_count"] += 1
            group["planned_qty"] = q4(group["planned_qty"] + row.planned_qty)
            totals["planned_qty"] = q4(totals["planned_qty"] + row.planned_qty)
            for name, value in rec.items():
                group[name] = q4(group[name] + value)
                totals[name] = q4(totals[name] + value)
        return {
            "date_from": date_from,
            "date_to": date_to,
            "totals": totals,
            "by_workspace": sorted(groups.values(), key=lambda row: (row["source_module"], row["brand_name"], row["branch_name"])),
            "shipments": [await self._shipment_dict(row) for row in rows],
        }

    async def _distribution_context(
        self, company_id: uuid.UUID, source_module: str, brand_id: uuid.UUID, branch_id: uuid.UUID, product_id: uuid.UUID
    ) -> dict:
        try:
            business_type = expected_business_type(source_module)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        brand = await self.db.scalar(select(Brand).where(
            Brand.id == brand_id, Brand.company_id == company_id, Brand.is_active.is_(True)
        ))
        if brand is None or brand.business_type != business_type:
            raise HTTPException(status_code=409, detail="โมดูลต้นทางไม่ตรงกับประเภทแบรนด์")
        brand_branch = await self.db.scalar(select(BrandBranch).where(
            BrandBranch.company_id == company_id,
            BrandBranch.brand_id == brand_id,
            BrandBranch.branch_id == branch_id,
            BrandBranch.is_active.is_(True),
        ))
        if brand_branch is None or brand_branch.store_location_id is None:
            raise HTTPException(status_code=409, detail="สาขายังไม่มีคลังรับสินค้าของแบรนด์")
        if brand.central_branch_id is None or brand.central_ready_location_id is None:
            raise HTTPException(status_code=409, detail="แบรนด์ยังไม่ได้ตั้งคลัง READY ส่วนกลาง")
        product = await self.db.scalar(
            select(Product)
            .where(Product.id == product_id, Product.company_id == company_id, Product.deleted_at.is_(None))
            .options(selectinload(Product.unit))
        )
        if product is None or product.brand_id != brand_id or product.inventory_role != "central_ready":
            raise HTTPException(status_code=409, detail="สินค้าต้องเป็น READY ของแบรนด์เดียวกับ Demand")
        location_ids = [brand.central_ready_location_id, brand_branch.store_location_id]
        locations = list((await self.db.scalars(select(StockLocation).where(
            StockLocation.company_id == company_id,
            StockLocation.id.in_(location_ids),
            StockLocation.deleted_at.is_(None),
            StockLocation.is_active.is_(True),
        ))).all())
        if len(locations) != 2:
            raise HTTPException(status_code=409, detail="คลังต้นทางหรือปลายทางไม่พร้อมใช้งาน")
        return {"brand": brand, "brand_branch": brand_branch, "product": product}

    async def _setup_options(self, company_id: uuid.UUID) -> dict:
        brands = list((await self.db.scalars(select(Brand).where(
            Brand.company_id == company_id, Brand.is_active.is_(True), Brand.central_ready_location_id.is_not(None)
        ).order_by(Brand.name))).all())
        mappings = list((await self.db.scalars(
            select(BrandBranch).where(
                BrandBranch.company_id == company_id, BrandBranch.is_active.is_(True), BrandBranch.store_location_id.is_not(None)
            ).options(selectinload(BrandBranch.branch))
        )).all())
        products = list((await self.db.scalars(
            select(Product).where(
                Product.company_id == company_id,
                Product.brand_id.in_([row.id for row in brands] or [uuid.uuid4()]),
                Product.inventory_role == "central_ready",
                Product.deleted_at.is_(None),
                Product.is_active.is_(True),
            ).options(selectinload(Product.unit)).order_by(Product.name)
        )).all())
        balances = list((await self.db.scalars(select(StockBalance).where(
            StockBalance.company_id == company_id,
            StockBalance.location_id.in_([row.central_ready_location_id for row in brands] or [uuid.uuid4()]),
            StockBalance.product_id.in_([row.id for row in products] or [uuid.uuid4()]),
        ))).all())
        balance_by_key = {(row.location_id, row.product_id): row for row in balances}
        brand_by_id = {row.id: row for row in brands}
        return {
            "brands": [{"id": row.id, "name": row.name, "business_type": row.business_type, "source_module": next(key for key, value in MODULE_BUSINESS_TYPE.items() if value == row.business_type)} for row in brands],
            "brand_branches": [{
                "brand_id": row.brand_id, "branch_id": row.branch_id, "branch_name": row.branch.name,
                "store_location_id": row.store_location_id,
            } for row in mappings if row.brand_id in brand_by_id],
            "products": [{
                "id": row.id, "brand_id": row.brand_id, "name": row.name, "sku": row.sku,
                "unit_code": row.unit.code if row.unit else None,
                "available_qty": q4(balance_by_key.get((brand_by_id[row.brand_id].central_ready_location_id, row.id)).qty_available)
                if balance_by_key.get((brand_by_id[row.brand_id].central_ready_location_id, row.id)) else Decimal("0"),
            } for row in products],
        }

    async def _get_demand(self, company_id: uuid.UUID, demand_id: uuid.UUID, *, lock: bool = False) -> CompanyDistributionDemand:
        statement = select(CompanyDistributionDemand).where(
            CompanyDistributionDemand.id == demand_id, CompanyDistributionDemand.company_id == company_id
        ).options(
            selectinload(CompanyDistributionDemand.brand), selectinload(CompanyDistributionDemand.branch),
            selectinload(CompanyDistributionDemand.product), selectinload(CompanyDistributionDemand.shipments),
        )
        if lock:
            statement = statement.with_for_update()
        row = await self.db.scalar(statement)
        if row is None:
            raise HTTPException(status_code=404, detail="ไม่พบ Demand")
        return row

    async def _get_shipment(self, company_id: uuid.UUID, shipment_id: uuid.UUID, *, lock: bool = False) -> CompanyDistributionShipment:
        statement = select(CompanyDistributionShipment).where(
            CompanyDistributionShipment.id == shipment_id, CompanyDistributionShipment.company_id == company_id
        ).options(
            selectinload(CompanyDistributionShipment.brand), selectinload(CompanyDistributionShipment.branch),
            selectinload(CompanyDistributionShipment.product),
            selectinload(CompanyDistributionShipment.transfer_order).selectinload(TransferOrder.items),
            selectinload(CompanyDistributionShipment.events),
        )
        if lock:
            statement = statement.with_for_update()
        row = await self.db.scalar(statement)
        if row is None:
            raise HTTPException(status_code=404, detail="ไม่พบรายการกระจายสินค้า")
        return row

    async def _event_replay(self, company_id: uuid.UUID, key: str, payload_hash: str) -> CompanyDistributionEvent | None:
        row = await self.db.scalar(
            select(CompanyDistributionEvent)
            .where(CompanyDistributionEvent.company_id == company_id, CompanyDistributionEvent.idempotency_key == key)
            .options(selectinload(CompanyDistributionEvent.shipment).selectinload(CompanyDistributionShipment.brand),
                     selectinload(CompanyDistributionEvent.shipment).selectinload(CompanyDistributionShipment.branch),
                     selectinload(CompanyDistributionEvent.shipment).selectinload(CompanyDistributionShipment.product),
                     selectinload(CompanyDistributionEvent.shipment).selectinload(CompanyDistributionShipment.transfer_order).selectinload(TransferOrder.items),
                     selectinload(CompanyDistributionEvent.shipment).selectinload(CompanyDistributionShipment.events))
        )
        if row:
            self._assert_replay(row.payload_hash, payload_hash)
        return row

    async def _refresh_demand_status(self, demand_id: uuid.UUID, company_id: uuid.UUID) -> None:
        demand = await self._get_demand(company_id, demand_id, lock=True)
        shipments = [row for row in demand.shipments if row.status != "cancelled"]
        planned = q4(sum((q4(row.planned_qty) for row in shipments), Decimal("0")))
        net_received = q4(sum((q4(row.received_qty) - q4(row.returned_qty) for row in shipments), Decimal("0")))
        if net_received >= q4(demand.requested_qty):
            demand.status = "fulfilled"
        elif planned >= q4(demand.requested_qty):
            demand.status = "allocated"
        elif planned > 0:
            demand.status = "partially_allocated"
        else:
            demand.status = "submitted"

    async def _generate_shipment_number(self, company_id: uuid.UUID) -> str:
        target = datetime.now(BANGKOK).date()
        prefix = f"DS{target:%Y%m%d}-"
        lock_key = hash(f"{company_id}:{target}:DISTRIBUTION") % (2**31)
        await self.db.execute(text(f"SELECT pg_advisory_xact_lock({lock_key})"))
        count = await self.db.scalar(select(func.count(CompanyDistributionShipment.id)).where(
            CompanyDistributionShipment.company_id == company_id,
            CompanyDistributionShipment.shipment_number.like(f"{prefix}%"),
        )) or 0
        return f"{prefix}{int(count) + 1:04d}"

    async def _demand_dict(self, row: CompanyDistributionDemand) -> dict:
        if "brand" not in row.__dict__:
            row = await self._get_demand(row.company_id, row.id)
        active = [item for item in (row.shipments if "shipments" in row.__dict__ else []) if item.status != "cancelled"]
        allocated = q4(sum((q4(item.planned_qty) for item in active), Decimal("0")))
        net_received = q4(sum((q4(item.received_qty) - q4(item.returned_qty) for item in active), Decimal("0")))
        return {
            "id": row.id, "source_module": row.source_module, "brand_id": row.brand_id,
            "brand_name": row.brand.name, "branch_id": row.branch_id, "branch_name": row.branch.name,
            "product_id": row.product_id, "product_name": row.product.name, "needed_on": row.needed_on,
            "requested_qty": q4(row.requested_qty), "allocated_qty": allocated, "net_received_qty": net_received,
            "unit_code": row.unit_code, "status": row.status, "source_type": row.source_type,
            "source_id": row.source_id, "note": row.note,
        }

    async def _shipment_dict(self, row: CompanyDistributionShipment) -> dict:
        if "brand" not in row.__dict__:
            row = await self._get_shipment(row.company_id, row.id)
        rec = reconciliation(row.shipped_qty, row.received_qty, row.rejected_qty, row.returned_qty)
        return {
            "id": row.id, "shipment_number": row.shipment_number, "demand_id": row.demand_id,
            "transfer_order_id": row.transfer_order_id, "transfer_number": row.transfer_order.to_number,
            "source_module": row.source_module, "brand_id": row.brand_id, "brand_name": row.brand.name,
            "branch_id": row.branch_id, "branch_name": row.branch.name, "product_id": row.product_id,
            "product_name": row.product.name, "status": row.status, "planned_qty": q4(row.planned_qty),
            **rec, "unit_code": row.unit_code, "unit_cost": q4(row.unit_cost),
            "dispatched_at": row.dispatched_at, "settled_at": row.settled_at, "note": row.note,
            "events": [{
                "id": event.id, "event_type": event.event_type, "qty": q4(event.qty),
                "unit_code": event.unit_code, "transfer_order_id": event.transfer_order_id,
                "note": event.note, "created_at": event.created_at,
            } for event in (row.events if "events" in row.__dict__ else [])],
        }

    @staticmethod
    def _assert_replay(actual: str, expected: str) -> None:
        if actual != expected:
            raise HTTPException(status_code=409, detail="idempotency key นี้ถูกใช้กับข้อมูลอื่นแล้ว")

    def _event(
        self, shipment: CompanyDistributionShipment, actor_id: uuid.UUID, event_type: str,
        qty: Decimal, key: str, payload_hash: str, transfer_order_id: uuid.UUID | None,
        note: str | None, metadata: dict | None = None,
    ) -> None:
        self.db.add(CompanyDistributionEvent(
            company_id=shipment.company_id, shipment_id=shipment.id, transfer_order_id=transfer_order_id,
            source_module=shipment.source_module, event_type=event_type, qty=q4(qty), unit_code=shipment.unit_code,
            idempotency_key=key, payload_hash=payload_hash, metadata_json=metadata or {}, actor_id=actor_id, note=note,
        ))

    def _audit(self, company_id: uuid.UUID, actor_id: uuid.UUID, action: str, resource_id: str, value: dict | None = None) -> None:
        self.db.add(AuditLog(
            company_id=company_id, user_id=actor_id, action=action, resource="CompanyDistribution",
            resource_id=resource_id, new_value=value,
        ))
