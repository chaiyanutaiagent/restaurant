from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.dependencies import DeviceTokenData, TokenData
from app.models.product import Product
from app.models.restaurant import (
    BrandBranch,
    DiningOrder,
    DiningOrderItem,
    DiningSession,
    KitchenCancellationEvent,
    KitchenTicket,
    RestaurantCancellation,
    RestaurantCancellationAudit,
    RestaurantCancellationWaste,
)
from app.models.settings import BranchSettings
from app.models.stock import StockBalance
from app.schemas.restaurant import (
    KitchenCancellationAckRequest,
    OrderItemCreate,
    PlaceOrderRequest,
    RestaurantCancellationReopenRequest,
    RestaurantCancellationRequest,
)
from app.services.approval_service import ApprovalService, has_permission
from app.services.dining_service import DiningService
from app.services.pricing_service import canonical_hash
from app.services.stock_service import StockService
from app.services.store_inventory_service import StoreInventoryService


CANCELLATION_POLICY_VERSION = "restaurant-cancellation-v1"
REASON_LABELS = {
    "customer_changed_mind": "ลูกค้าเปลี่ยนใจ",
    "wrong_item": "สั่งผิดรายการ",
    "duplicate_order": "ออเดอร์ซ้ำ",
    "out_of_stock": "วัตถุดิบหมด",
    "quality_failed": "คุณภาพไม่ผ่าน",
    "kitchen_error": "ครัวทำผิด",
    "other": "อื่น ๆ",
}
STAGE_PRIORITY = {"pending": 1, "cooking": 2, "done": 3}


def cancellation_error(status_code: int, code: str, message: str, **details: Any) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"code": code, "message": message, **details},
    )


class RestaurantCancellationService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    @staticmethod
    def _validate_device(current: TokenData, device: DeviceTokenData | None) -> None:
        if device is None:
            return
        if (
            device.company_id != current.company_id
            or device.branch_id != current.branch_id
            or (current.brand_id is not None and device.brand_id != current.brand_id)
        ):
            raise cancellation_error(
                status.HTTP_403_FORBIDDEN,
                "device_scope_mismatch",
                "Paired device does not match the active Company/Brand/Branch context",
            )

    async def _brand_branch(self, current: TokenData) -> BrandBranch:
        if current.branch_id is None:
            raise cancellation_error(status.HTTP_409_CONFLICT, "branch_required", "Select a branch before cancellation")
        if current.brand_id is None:
            raise cancellation_error(status.HTTP_409_CONFLICT, "brand_required", "Select a Brand before cancellation")
        statement = select(BrandBranch).where(
            BrandBranch.company_id == current.company_id,
            BrandBranch.branch_id == current.branch_id,
            BrandBranch.is_active.is_(True),
        )
        statement = statement.where(BrandBranch.brand_id == current.brand_id)
        brand_branch = await self.db.scalar(statement)
        if brand_branch is None:
            raise cancellation_error(
                status.HTTP_409_CONFLICT,
                "brand_branch_required",
                "Restaurant branch is not mapped to an active Brand",
            )
        return brand_branch

    async def _existing(
        self,
        current: TokenData,
        idempotency_key: str,
        request_hash: str,
    ) -> RestaurantCancellation | None:
        if current.branch_id is None:
            return None
        row = await self.db.scalar(
            select(RestaurantCancellation)
            .options(
                selectinload(RestaurantCancellation.waste_lines),
                selectinload(RestaurantCancellation.kds_events).selectinload(KitchenCancellationEvent.ticket),
            )
            .where(
                RestaurantCancellation.company_id == current.company_id,
                RestaurantCancellation.branch_id == current.branch_id,
                RestaurantCancellation.requester_id == current.user_id,
                RestaurantCancellation.idempotency_key == idempotency_key,
            )
        )
        if row is not None and current.brand_id is not None and row.brand_id != current.brand_id:
            raise cancellation_error(
                status.HTTP_409_CONFLICT,
                "idempotency_scope_conflict",
                "Cancellation idempotency key already belongs to another Brand context",
            )
        if row is not None and row.request_hash != request_hash:
            raise cancellation_error(
                status.HTTP_409_CONFLICT,
                "duplicate_request",
                "Cancellation idempotency key was replayed with a different payload",
            )
        return row

    async def _load_target(
        self,
        current: TokenData,
        payload: RestaurantCancellationRequest,
        *,
        lock: bool,
    ) -> tuple[DiningOrder, list[DiningOrderItem], DiningSession, dict[uuid.UUID, KitchenTicket]]:
        if current.branch_id is None:
            raise cancellation_error(status.HTTP_409_CONFLICT, "branch_required", "Select a branch before cancellation")

        if payload.target_type == "item":
            item_statement = select(DiningOrderItem).where(DiningOrderItem.id == payload.target_id)
            item = await self.db.scalar(item_statement)
            if item is None:
                raise cancellation_error(status.HTTP_404_NOT_FOUND, "target_not_found", "Cancellation item was not found")
            order_statement = select(DiningOrder).where(DiningOrder.id == item.order_id)
            if lock:
                order_statement = order_statement.with_for_update()
            order = await self.db.scalar(order_statement)
            if lock:
                item = await self.db.scalar(
                    select(DiningOrderItem).where(DiningOrderItem.id == payload.target_id).with_for_update()
                )
                if item is None:
                    raise cancellation_error(status.HTTP_404_NOT_FOUND, "target_not_found", "Cancellation item was not found")
            items = [item]
        else:
            order_statement = select(DiningOrder).where(DiningOrder.id == payload.target_id)
            if lock:
                order_statement = order_statement.with_for_update()
            order = await self.db.scalar(order_statement)
            if order is None:
                raise cancellation_error(status.HTTP_404_NOT_FOUND, "target_not_found", "Cancellation order was not found")
            item_statement = select(DiningOrderItem).where(DiningOrderItem.order_id == order.id)
            if lock:
                item_statement = item_statement.with_for_update()
            items = list((await self.db.scalars(item_statement)).all())

        if (
            order is None
            or order.company_id != current.company_id
            or order.branch_id != current.branch_id
        ):
            raise cancellation_error(status.HTTP_404_NOT_FOUND, "target_not_found", "Cancellation target was not found in this branch")
        if order.row_version != payload.expected_order_version:
            raise cancellation_error(
                status.HTTP_409_CONFLICT,
                "stale_cancellation",
                "Order changed on another device; refresh before cancelling",
                current_order_version=order.row_version,
            )
        if payload.target_type == "item" and items[0].row_version != payload.expected_item_version:
            raise cancellation_error(
                status.HTTP_409_CONFLICT,
                "stale_cancellation",
                "Item changed on another device; refresh before cancelling",
                current_item_version=items[0].row_version,
            )

        session_statement = select(DiningSession).where(DiningSession.id == order.session_id)
        if lock:
            session_statement = session_statement.with_for_update()
        session = await self.db.scalar(session_statement)
        if session is None or session.company_id != current.company_id or session.branch_id != current.branch_id:
            raise cancellation_error(status.HTTP_404_NOT_FOUND, "session_not_found", "Restaurant session was not found")
        if session.status == "closed" or session.sale_order_id is not None:
            raise cancellation_error(
                status.HTTP_409_CONFLICT,
                "refund_required",
                "This session has been checked out; use the refund/credit-note flow instead",
            )

        active_items = [item for item in items if item.status != "cancelled"]
        if not active_items:
            raise cancellation_error(status.HTTP_409_CONFLICT, "already_cancelled", "Cancellation target is already cancelled")
        if any(item.status == "served" for item in active_items):
            raise cancellation_error(
                status.HTTP_409_CONFLICT,
                "served_requires_comp_or_refund",
                "Served items cannot be cancelled; use comp/refund instead",
            )
        unsupported = sorted({item.status for item in active_items if item.status not in STAGE_PRIORITY})
        if unsupported:
            raise cancellation_error(
                status.HTTP_409_CONFLICT,
                "unsupported_kitchen_state",
                "Cancellation policy does not support the current kitchen state",
                states=unsupported,
            )

        ticket_statement = select(KitchenTicket).where(
            KitchenTicket.order_item_id.in_([item.id for item in active_items])
        )
        if lock:
            ticket_statement = ticket_statement.with_for_update()
        tickets = list((await self.db.scalars(ticket_statement)).all())
        ticket_by_item = {ticket.order_item_id: ticket for ticket in tickets}
        missing_ticket_ids = [str(item.id) for item in active_items if item.id not in ticket_by_item]
        if missing_ticket_ids:
            raise cancellation_error(
                status.HTTP_409_CONFLICT,
                "kds_contract_missing",
                "Cancellation cannot continue because a KDS ticket is missing",
                order_item_ids=missing_ticket_ids,
            )
        return order, active_items, session, ticket_by_item

    @staticmethod
    def _stage(items: list[DiningOrderItem]) -> str:
        return max((item.status for item in items), key=lambda value: STAGE_PRIORITY[value])

    @staticmethod
    def _bill_impact(items: list[DiningOrderItem]) -> dict[str, Any]:
        amount = sum(
            (
                Decimal(item.line_total)
                if Decimal(item.line_total or 0) != 0
                else Decimal(item.unit_price) * Decimal(item.qty)
                for item in items
            ),
            Decimal("0"),
        )
        return {
            "currency": "THB",
            "amount_removed": str(amount.quantize(Decimal("0.01"))),
            "sale_return_created": False,
            "payment_refund_created": False,
            "tax_document_created": False,
        }

    @staticmethod
    def _before_state(
        order: DiningOrder,
        items: list[DiningOrderItem],
        tickets: dict[uuid.UUID, KitchenTicket],
    ) -> dict[str, Any]:
        return {
            "order_id": str(order.id),
            "order_number": order.order_number,
            "order_status": order.status,
            "order_version": order.row_version,
            "items": [
                {
                    "id": str(item.id),
                    "product_id": str(item.product_id),
                    "product_name": item.product_name,
                    "qty": item.qty,
                    "unit_price": str(item.unit_price),
                    "line_total": str(item.line_total),
                    "special_request": item.special_request,
                    "status": item.status,
                    "row_version": item.row_version,
                    "ticket_id": str(tickets[item.id].id),
                    "ticket_status": tickets[item.id].status,
                    "ticket_version": tickets[item.id].row_version,
                    "station": tickets[item.id].station,
                }
                for item in items
            ],
        }

    async def _waste_plan(
        self,
        *,
        current: TokenData,
        brand_branch: BrandBranch,
        items: list[DiningOrderItem],
        lock: bool,
    ) -> tuple[list[dict[str, Any]], list[str]]:
        blockers: list[str] = []
        if brand_branch.store_location_id is None:
            return [], ["ยังไม่ได้กำหนดคลัง STORE-STOCK ของสาขา"]

        menu_items: list[tuple[Product, Decimal]] = []
        for item in items:
            product = await self.db.scalar(
                select(Product)
                .options(selectinload(Product.unit))
                .where(Product.id == item.product_id)
            )
            if product is None or product.company_id != current.company_id:
                blockers.append(f"ไม่พบ Product ของ {item.product_name}")
                continue
            menu_items.append((product, Decimal(item.qty)))
        if blockers:
            return [], blockers

        try:
            usage, warnings = await StoreInventoryService(self.db)._expand_items(
                company_id=current.company_id,
                brand_id=brand_branch.brand_id,
                branch_id=brand_branch.branch_id,
                items=menu_items,
            )
        except (ValueError, TypeError) as exc:
            return [], [str(exc)]
        blockers.extend(warnings)
        if not usage and not blockers:
            blockers.append("ไม่พบรายการวัตถุดิบสำหรับบันทึก Waste")

        lines: list[dict[str, Any]] = []
        for product, quantity in usage.values():
            statement = select(StockBalance).where(
                StockBalance.company_id == current.company_id,
                StockBalance.branch_id == brand_branch.branch_id,
                StockBalance.location_id == brand_branch.store_location_id,
                StockBalance.product_id == product.id,
                StockBalance.variant_id.is_(None),
            )
            if lock:
                statement = statement.with_for_update()
            balance = await self.db.scalar(statement)
            if balance is None:
                blockers.append(f"{product.name} ยังไม่มียอดใน STORE-STOCK")
                continue
            on_hand = Decimal(balance.qty_on_hand or 0)
            if on_hand < quantity:
                blockers.append(f"{product.name} ไม่พอสำหรับ Waste (มี {on_hand}, ต้องใช้ {quantity})")
            lines.append(
                {
                    "product": product,
                    "balance": balance,
                    "quantity": quantity,
                    "unit": product.unit.code if product.unit else None,
                    "qty_before": on_hand,
                    "qty_after": on_hand - quantity,
                }
            )
        return lines, list(dict.fromkeys(blockers))

    async def preview(
        self,
        *,
        current: TokenData,
        payload: RestaurantCancellationRequest,
        device: DeviceTokenData | None,
    ) -> dict[str, Any]:
        self._validate_device(current, device)
        brand_branch = await self._brand_branch(current)
        order, items, _session, tickets = await self._load_target(current, payload, lock=False)
        stage = self._stage(items)
        approval_required = stage in {"cooking", "done"}
        waste_disposition = "full" if approval_required else "none"
        waste_lines: list[dict[str, Any]] = []
        blockers: list[str] = []
        if approval_required:
            waste_lines, blockers = await self._waste_plan(
                current=current,
                brand_branch=brand_branch,
                items=items,
                lock=False,
            )
        return {
            "policy_version": CANCELLATION_POLICY_VERSION,
            "target_type": payload.target_type,
            "target_id": str(payload.target_id),
            "order_id": str(order.id),
            "stage_before": stage,
            "approval_required": approval_required,
            "approval_action": "fb.order.cancel_after_kitchen" if approval_required else None,
            "waste_disposition": waste_disposition,
            "waste_ready": not blockers,
            "blockers": blockers,
            "bill_impact": self._bill_impact(items),
            "affected_items": [
                {
                    "id": str(item.id),
                    "product_name": item.product_name,
                    "qty": item.qty,
                    "status": item.status,
                    "station": tickets[item.id].station,
                }
                for item in items
            ],
            "waste_lines": [
                {
                    "product_id": str(line["product"].id),
                    "product_name": line["product"].name,
                    "quantity": str(line["quantity"]),
                    "unit": line["unit"],
                }
                for line in waste_lines
            ],
        }

    async def execute(
        self,
        *,
        current: TokenData,
        payload: RestaurantCancellationRequest,
        device: DeviceTokenData | None,
    ) -> dict[str, Any]:
        self._validate_device(current, device)
        request_payload = payload.approval_payload()
        request_hash = canonical_hash(request_payload)
        existing = await self._existing(current, payload.idempotency_key, request_hash)
        if existing is not None:
            return await self.serialize(existing)

        brand_branch = await self._brand_branch(current)
        order, items, session, tickets = await self._load_target(current, payload, lock=True)
        existing = await self._existing(current, payload.idempotency_key, request_hash)
        if existing is not None:
            return await self.serialize(existing)

        stage = self._stage(items)
        approval_required = stage in {"cooking", "done"}
        if approval_required:
            if not (
                has_permission(current.permissions, "fb.order.cancel.request")
                or has_permission(current.permissions, "fb.order.cancel.approve")
            ):
                raise cancellation_error(
                    status.HTTP_403_FORBIDDEN,
                    "permission_denied",
                    "Permission required: fb.order.cancel.request",
                )
            approval = await ApprovalService(self.db).authorize_operation(
                current=current,
                action="fb.order.cancel_after_kitchen",
                request_payload=request_payload,
                approval_token=payload.approval_token,
                reason=payload.reason_note or REASON_LABELS[payload.reason_code],
                resource_type="RestaurantCancellation",
                resource_id=str(payload.target_id),
                allow_direct=False,
            )
        else:
            if not has_permission(current.permissions, "fb.order.cancel"):
                raise cancellation_error(
                    status.HTTP_403_FORBIDDEN,
                    "permission_denied",
                    "Permission required: fb.order.cancel",
                )
            approval = None

        waste_lines: list[dict[str, Any]] = []
        if approval_required:
            waste_lines, blockers = await self._waste_plan(
                current=current,
                brand_branch=brand_branch,
                items=items,
                lock=True,
            )
            if blockers:
                raise cancellation_error(
                    status.HTTP_409_CONFLICT,
                    "waste_contract_missing",
                    "Cancellation stopped because Waste/Stock contract is incomplete",
                    blockers=blockers,
                )

        before_state = self._before_state(order, items, tickets)
        policy_snapshot = {
            "version": CANCELLATION_POLICY_VERSION,
            "stage_before": stage,
            "approval_required": approval_required,
            "approval_action": "fb.order.cancel_after_kitchen" if approval_required else None,
            "maker_checker": approval_required,
            "waste_disposition": "full" if approval_required else "none",
            "served_policy": "fail_closed_comp_or_refund",
        }
        cancellation = RestaurantCancellation(
            company_id=current.company_id,
            brand_id=brand_branch.brand_id,
            branch_id=brand_branch.branch_id,
            session_id=session.id,
            order_id=order.id,
            order_item_id=items[0].id if payload.target_type == "item" else None,
            target_type=payload.target_type,
            stage_before=stage,
            requester_id=current.user_id,
            approver_id=approval.approver_id if approval else None,
            origin_device_id=device.device_id if device else None,
            origin_device_code=device.device_code if device else None,
            station_key=current.station_key,
            reason_code=payload.reason_code,
            reason_note=payload.reason_note,
            before_state=before_state,
            approval_policy_snapshot=policy_snapshot,
            bill_impact=self._bill_impact(items),
            waste_disposition="full" if approval_required else "none",
            waste_status="posted" if approval_required else "not_required",
            stock_location_id=brand_branch.store_location_id if approval_required else None,
            approval_grant_id=approval.grant_id if approval else None,
            approval_mode=approval.mode if approval else "not_required",
            idempotency_key=payload.idempotency_key,
            request_hash=request_hash,
        )
        self.db.add(cancellation)
        await self.db.flush()

        stock_service = StockService(self.db)
        for line in waste_lines:
            movement = await stock_service._record_movement(
                balance=line["balance"],
                movement_type="waste",
                qty_delta=-line["quantity"],
                user_id=current.user_id,
                cost_per_unit=Decimal(line["balance"].cost_per_unit or line["product"].cost_price or 0),
                reference_type="restaurant_cancellation",
                reference_id=str(cancellation.id),
                note=f"[{payload.reason_code}] Waste from restaurant cancellation",
                allow_negative=False,
            )
            self.db.add(
                RestaurantCancellationWaste(
                    cancellation_id=cancellation.id,
                    company_id=current.company_id,
                    branch_id=brand_branch.branch_id,
                    location_id=brand_branch.store_location_id,
                    product_id=line["product"].id,
                    quantity=line["quantity"],
                    unit=line["unit"],
                    stock_movement_id=movement.id,
                )
            )

        for item in items:
            ticket = tickets[item.id]
            ticket_status_before = ticket.status
            item.status = "cancelled"
            item.row_version += 1
            ticket.status = "cancelled"
            ticket.row_version += 1
            self.db.add(
                KitchenCancellationEvent(
                    cancellation_id=cancellation.id,
                    ticket_id=ticket.id,
                    company_id=current.company_id,
                    brand_id=brand_branch.brand_id,
                    branch_id=brand_branch.branch_id,
                    station=ticket.station,
                    reason_code=payload.reason_code,
                    reason_note=payload.reason_note,
                    ticket_status_before=ticket_status_before,
                )
            )

        remaining = await self.db.scalar(
            select(DiningOrderItem.id).where(
                DiningOrderItem.order_id == order.id,
                DiningOrderItem.status != "cancelled",
                DiningOrderItem.id.not_in([item.id for item in items]),
            ).limit(1)
        )
        if remaining is None:
            order.status = "cancelled"
        order.row_version += 1

        self.db.add(
            RestaurantCancellationAudit(
                cancellation_id=cancellation.id,
                company_id=current.company_id,
                branch_id=brand_branch.branch_id,
                actor_user_id=current.user_id,
                approver_id=approval.approver_id if approval else None,
                device_id=device.device_id if device else None,
                station_key=current.station_key,
                action="cancel",
                from_state=before_state,
                to_state={
                    "order_status": order.status,
                    "order_version": order.row_version,
                    "item_status": "cancelled",
                    "kds_status": "cancelled",
                    "kds_ack": "pending_ack",
                },
                idempotency_key=payload.idempotency_key,
                request_hash=request_hash,
                metadata_json={
                    "reason_code": payload.reason_code,
                    "reason_note": payload.reason_note,
                    "policy": policy_snapshot,
                    "approval": approval.as_audit_value() if approval else None,
                    "bill_impact": cancellation.bill_impact,
                },
            )
        )
        await self.db.commit()
        return await self.serialize(cancellation)

    async def serialize(self, cancellation: RestaurantCancellation) -> dict[str, Any]:
        loaded = await self.db.scalar(
            select(RestaurantCancellation)
            .options(
                selectinload(RestaurantCancellation.waste_lines),
                selectinload(RestaurantCancellation.kds_events).selectinload(KitchenCancellationEvent.ticket),
            )
            .where(RestaurantCancellation.id == cancellation.id)
        )
        row = loaded or cancellation
        return {
            "id": str(row.id),
            "company_id": str(row.company_id),
            "brand_id": str(row.brand_id),
            "branch_id": str(row.branch_id),
            "session_id": str(row.session_id),
            "order_id": str(row.order_id),
            "order_item_id": str(row.order_item_id) if row.order_item_id else None,
            "target_type": row.target_type,
            "stage_before": row.stage_before,
            "requester_id": str(row.requester_id),
            "approver_id": str(row.approver_id) if row.approver_id else None,
            "reason_code": row.reason_code,
            "reason_note": row.reason_note,
            "bill_impact": row.bill_impact,
            "waste_disposition": row.waste_disposition,
            "waste_status": row.waste_status,
            "approval_policy_snapshot": row.approval_policy_snapshot,
            "approval_mode": row.approval_mode,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "waste_lines": [
                {
                    "id": str(line.id),
                    "product_id": str(line.product_id),
                    "quantity": str(line.quantity),
                    "unit": line.unit,
                    "stock_movement_id": str(line.stock_movement_id),
                }
                for line in row.waste_lines
            ],
            "kds_events": [self.serialize_kds_event(event) for event in row.kds_events],
        }

    @staticmethod
    def serialize_kds_event(event: KitchenCancellationEvent) -> dict[str, Any]:
        ticket = event.ticket
        return {
            "id": str(event.id),
            "cancellation_id": str(event.cancellation_id),
            "ticket_id": str(event.ticket_id),
            "brand_id": str(event.brand_id),
            "product_name": ticket.product_name if ticket else None,
            "qty": ticket.qty if ticket else None,
            "queue_number": ticket.queue_number if ticket else None,
            "table_name": ticket.table_name if ticket else None,
            "station": event.station,
            "reason_code": event.reason_code,
            "reason_note": event.reason_note,
            "ticket_status_before": event.ticket_status_before,
            "status": event.status,
            "row_version": event.row_version,
            "acknowledged_at": event.acknowledged_at.isoformat() if event.acknowledged_at else None,
            "created_at": event.created_at.isoformat() if event.created_at else None,
        }

    async def list_kds_events(
        self,
        *,
        company_id: uuid.UUID,
        brand_id: uuid.UUID,
        branch_id: uuid.UUID,
        station: str | None,
        include_acknowledged: bool = False,
    ) -> list[dict[str, Any]]:
        statement = (
            select(KitchenCancellationEvent)
            .options(selectinload(KitchenCancellationEvent.ticket))
            .where(
                KitchenCancellationEvent.company_id == company_id,
                KitchenCancellationEvent.brand_id == brand_id,
                KitchenCancellationEvent.branch_id == branch_id,
            )
        )
        if station is not None:
            statement = statement.where(KitchenCancellationEvent.station == station)
        if not include_acknowledged:
            statement = statement.where(KitchenCancellationEvent.status == "pending_ack")
        rows = list((await self.db.scalars(statement.order_by(KitchenCancellationEvent.created_at.asc()))).all())
        return [self.serialize_kds_event(row) for row in rows]

    async def acknowledge_kds_event(
        self,
        *,
        event_id: uuid.UUID,
        company_id: uuid.UUID,
        brand_id: uuid.UUID,
        branch_id: uuid.UUID,
        station: str | None,
        actor_user_id: uuid.UUID | None,
        device_id: uuid.UUID | None,
        payload: KitchenCancellationAckRequest,
    ) -> dict[str, Any]:
        request_hash = canonical_hash(
            {
                "event_id": str(event_id),
                "expected_version": payload.expected_version,
                "idempotency_key": payload.idempotency_key,
            }
        )
        existing_audit = await self.db.scalar(
            select(RestaurantCancellationAudit).where(
                RestaurantCancellationAudit.company_id == company_id,
                RestaurantCancellationAudit.branch_id == branch_id,
                RestaurantCancellationAudit.action == "kds_ack",
                RestaurantCancellationAudit.idempotency_key == payload.idempotency_key,
            )
        )
        if existing_audit is not None:
            if existing_audit.request_hash != request_hash or existing_audit.metadata_json.get("event_id") != str(event_id):
                raise cancellation_error(status.HTTP_409_CONFLICT, "duplicate_request", "KDS acknowledgment key was replayed with different data")
            event = await self.db.scalar(
                select(KitchenCancellationEvent)
                .options(selectinload(KitchenCancellationEvent.ticket))
                .where(
                    KitchenCancellationEvent.id == event_id,
                    KitchenCancellationEvent.company_id == company_id,
                    KitchenCancellationEvent.brand_id == brand_id,
                    KitchenCancellationEvent.branch_id == branch_id,
                )
            )
            if event is None or (station is not None and event.station != station):
                raise cancellation_error(status.HTTP_404_NOT_FOUND, "event_not_found", "KDS cancellation event was not found")
            return self.serialize_kds_event(event)

        event = await self.db.scalar(
            select(KitchenCancellationEvent)
            .options(selectinload(KitchenCancellationEvent.ticket))
            .where(
                KitchenCancellationEvent.id == event_id,
                KitchenCancellationEvent.company_id == company_id,
                KitchenCancellationEvent.brand_id == brand_id,
                KitchenCancellationEvent.branch_id == branch_id,
            )
            .with_for_update()
        )
        if event is None or (station is not None and event.station != station):
            raise cancellation_error(status.HTTP_404_NOT_FOUND, "event_not_found", "KDS cancellation event was not found")
        if event.row_version != payload.expected_version:
            raise cancellation_error(
                status.HTTP_409_CONFLICT,
                "stale_kds_event",
                "Cancellation acknowledgment changed on another device",
                current_version=event.row_version,
            )
        if event.status != "pending_ack":
            raise cancellation_error(status.HTTP_409_CONFLICT, "already_acknowledged", "Cancellation was already acknowledged")

        before = {"status": event.status, "row_version": event.row_version}
        event.status = "acknowledged"
        event.row_version += 1
        event.acknowledged_by = actor_user_id
        event.acknowledged_device_id = device_id
        event.acknowledged_at = datetime.now(timezone.utc)
        self.db.add(
            RestaurantCancellationAudit(
                cancellation_id=event.cancellation_id,
                company_id=company_id,
                branch_id=branch_id,
                actor_user_id=actor_user_id,
                device_id=device_id,
                station_key=station,
                action="kds_ack",
                from_state=before,
                to_state={"status": event.status, "row_version": event.row_version},
                idempotency_key=payload.idempotency_key,
                request_hash=request_hash,
                metadata_json={"event_id": str(event.id), "ticket_id": str(event.ticket_id)},
            )
        )
        await self.db.commit()
        return self.serialize_kds_event(event)

    async def reopen(
        self,
        *,
        cancellation_id: uuid.UUID,
        current: TokenData,
        payload: RestaurantCancellationReopenRequest,
        device: DeviceTokenData | None,
    ) -> dict[str, Any]:
        self._validate_device(current, device)
        if current.branch_id is None:
            raise cancellation_error(status.HTTP_409_CONFLICT, "branch_required", "Select a branch before reopening")
        request_payload = payload.approval_payload(cancellation_id)
        request_hash = canonical_hash(request_payload)
        cancellation = await self.db.scalar(
            select(RestaurantCancellation).where(
                RestaurantCancellation.id == cancellation_id,
                RestaurantCancellation.company_id == current.company_id,
                RestaurantCancellation.branch_id == current.branch_id,
            )
        )
        if cancellation is None:
            raise cancellation_error(status.HTTP_404_NOT_FOUND, "cancellation_not_found", "Cancellation record was not found")
        brand_branch = await self._brand_branch(current)
        if cancellation.brand_id != brand_branch.brand_id:
            raise cancellation_error(status.HTTP_403_FORBIDDEN, "brand_scope_mismatch", "Cancellation belongs to another Brand")
        existing_audit = await self.db.scalar(
            select(RestaurantCancellationAudit).where(
                RestaurantCancellationAudit.company_id == current.company_id,
                RestaurantCancellationAudit.branch_id == current.branch_id,
                RestaurantCancellationAudit.action == "reopen",
                RestaurantCancellationAudit.idempotency_key == payload.idempotency_key,
            )
        )
        if existing_audit is not None:
            if existing_audit.request_hash != request_hash or existing_audit.cancellation_id != cancellation_id:
                raise cancellation_error(status.HTTP_409_CONFLICT, "duplicate_request", "Reopen idempotency key was replayed with different data")
            return {
                "cancellation_id": str(cancellation_id),
                "new_order_id": existing_audit.metadata_json.get("new_order_id"),
                "idempotent_replay": True,
            }

        session = await self.db.scalar(
            select(DiningSession).where(DiningSession.id == cancellation.session_id).with_for_update()
        )
        if session is None or session.status == "closed" or session.sale_order_id is not None:
            raise cancellation_error(status.HTTP_409_CONFLICT, "session_not_reopenable", "Session is closed or already checked out")
        if not (
            has_permission(current.permissions, "fb.order.cancel.reopen.request")
            or has_permission(current.permissions, "fb.order.cancel.reopen")
        ):
            raise cancellation_error(status.HTTP_403_FORBIDDEN, "permission_denied", "Permission required: fb.order.cancel.reopen.request")
        approval = await ApprovalService(self.db).authorize_operation(
            current=current,
            action="fb.order.cancel.reopen",
            request_payload=request_payload,
            approval_token=payload.approval_token,
            reason=payload.reason,
            resource_type="RestaurantCancellation",
            resource_id=str(cancellation.id),
            allow_direct=False,
        )

        source_items = cancellation.before_state.get("items") or []
        if not source_items:
            raise cancellation_error(status.HTTP_409_CONFLICT, "reopen_contract_missing", "Cancellation snapshot has no items to reopen")
        order_payload = PlaceOrderRequest(
            items=[
                OrderItemCreate(
                    product_id=uuid.UUID(str(item["product_id"])),
                    qty=int(item["qty"]),
                    special_request=item.get("special_request"),
                )
                for item in source_items
            ],
            note=f"Reopened from cancellation {cancellation.id}: {payload.reason}",
            idempotency_key=(f"reopen-{cancellation.id}-{payload.idempotency_key}")[:100],
        )
        branch_settings = await self.db.scalar(
            select(BranchSettings).where(BranchSettings.branch_id == session.branch_id)
        )
        new_order = await DiningService(self.db).place_order(
            current.company_id,
            session.branch_id,
            session,
            order_payload,
            source="reopen",
            settings=branch_settings,
            commit=False,
        )
        self.db.add(
            RestaurantCancellationAudit(
                cancellation_id=cancellation.id,
                company_id=current.company_id,
                branch_id=current.branch_id,
                actor_user_id=current.user_id,
                approver_id=approval.approver_id,
                device_id=device.device_id if device else None,
                station_key=current.station_key,
                action="reopen",
                from_state={"cancellation_id": str(cancellation.id), "state": "cancelled"},
                to_state={"new_order_id": str(new_order.id), "state": "pending"},
                idempotency_key=payload.idempotency_key,
                request_hash=request_hash,
                metadata_json={
                    "new_order_id": str(new_order.id),
                    "approval": approval.as_audit_value(),
                    "waste_reversed": False,
                    "pricing_recalculated": True,
                },
            )
        )
        await self.db.commit()
        return {
            "cancellation_id": str(cancellation.id),
            "new_order_id": str(new_order.id),
            "idempotent_replay": False,
        }
