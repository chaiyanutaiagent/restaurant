from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
import uuid
from zoneinfo import ZoneInfo

from fastapi import HTTPException, status
from sqlalchemy import case, distinct, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.audit import AuditLog
from app.models.branch import Branch
from app.models.product import Product, ProductVariant
from app.models.stock import StockBalance, StockLocation
from app.models.transfer import TransferOrder, TransferOrderItem
from app.models.user import User
from app.schemas.transfer import (
    ApproveTORequest,
    BranchStockSummary,
    CreateTORequest,
    MultiBranchStockResponse,
    ReceiveTORequest,
    ShipTORequest,
)
from app.services.stock_service import StockService

TWOPLACES = Decimal("0.01")
FOURPLACES = Decimal("0.0001")
BANGKOK = ZoneInfo("Asia/Bangkok")


def q4(value: Decimal | int | float | None) -> Decimal:
    return Decimal(value or 0).quantize(FOURPLACES, rounding=ROUND_HALF_UP)


class TransferService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.stock_service = StockService(db)

    async def create_to(
        self,
        company_id: uuid.UUID,
        user_id: uuid.UUID,
        data: CreateTORequest,
        *,
        commit: bool = True,
    ) -> TransferOrder:
        if data.from_location_id == data.to_location_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Source and destination locations must be different")
        if not data.items:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="At least one item is required")

        from_branch = await self._get_branch(company_id, data.from_branch_id)
        to_branch = await self._get_branch(company_id, data.to_branch_id)
        from_location = await self.stock_service._get_location(data.from_location_id, company_id)
        to_location = await self.stock_service._get_location(data.to_location_id, company_id)
        if from_location.branch_id != from_branch.id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Source location does not belong to source branch")
        if to_location.branch_id != to_branch.id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Destination location does not belong to destination branch")

        prepared_items = await self._prepare_items(company_id, data.items)
        to_number = await self._generate_number(company_id, data.expected_date or datetime.now(BANGKOK).date())
        transfer_order = TransferOrder(
            company_id=company_id,
            to_number=to_number,
            status="draft",
            from_branch_id=from_branch.id,
            to_branch_id=to_branch.id,
            from_location_id=from_location.id,
            to_location_id=to_location.id,
            requested_by=user_id,
            request_date=datetime.now(BANGKOK).date(),
            expected_date=data.expected_date,
            note=data.note,
        )
        self.db.add(transfer_order)
        await self.db.flush()
        self.db.add_all(
            [
                TransferOrderItem(
                    to_id=transfer_order.id,
                    company_id=company_id,
                    product_id=item["product_id"],
                    variant_id=item["variant_id"],
                    product_name=item["product_name"],
                    sku=item["sku"],
                    unit_code=item["unit_code"],
                    qty_requested=item["qty_requested"],
                )
                for item in prepared_items
            ]
        )
        self._audit(company_id, user_id, "inventory.transfer.create", str(transfer_order.id), {"to_number": to_number})
        if commit:
            await self.db.commit()
        else:
            await self.db.flush()
        return await self.get_to(transfer_order.id, company_id)

    async def submit_to(
        self,
        to_id: uuid.UUID,
        company_id: uuid.UUID,
        user_id: uuid.UUID,
        *,
        commit: bool = True,
    ) -> TransferOrder:
        transfer_order = await self._get_to_entity(to_id, company_id)
        if transfer_order.status != "draft":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Only draft transfer orders can be submitted")

        for item in transfer_order.items:
            balance = await self.stock_service._get_or_create_balance(
                company_id=company_id,
                branch_id=transfer_order.from_branch_id,
                location_id=transfer_order.from_location_id,
                product_id=item.product_id,
                variant_id=item.variant_id,
            )
            if Decimal(balance.qty_available or 0) < Decimal(item.qty_requested):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Insufficient stock for {item.product_name}",
                )

        transfer_order.status = "pending_approval"
        self._audit(company_id, user_id, "inventory.transfer.submit", str(transfer_order.id))
        if commit:
            await self.db.commit()
        else:
            await self.db.flush()
        return await self.get_to(transfer_order.id, company_id)

    async def approve_to(
        self,
        to_id: uuid.UUID,
        company_id: uuid.UUID,
        approver_id: uuid.UUID,
        data: ApproveTORequest,
        *,
        commit: bool = True,
    ) -> TransferOrder:
        transfer_order = await self._get_to_entity(to_id, company_id)
        if transfer_order.status != "pending_approval":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Only pending transfer orders can be approved")
        if transfer_order.requested_by == approver_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "maker_checker_conflict",
                    "message": "Transfer requester and approver must be different users",
                },
            )

        approve_map = {item.item_id: item for item in data.items}
        if set(approve_map.keys()) != {item.id for item in transfer_order.items}:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Approval items must match transfer order items")

        for item in transfer_order.items:
            approved_qty = q4(approve_map[item.id].qty_approved)
            if approved_qty <= 0:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Approved quantity must be positive")
            if approved_qty > Decimal(item.qty_requested):
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Approved quantity cannot exceed requested quantity")
            balance = await self.stock_service._get_or_create_balance(
                company_id=company_id,
                branch_id=transfer_order.from_branch_id,
                location_id=transfer_order.from_location_id,
                product_id=item.product_id,
                variant_id=item.variant_id,
            )
            if Decimal(balance.qty_available or 0) < approved_qty:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Insufficient stock for {item.product_name}")
            balance.qty_reserved = q4(Decimal(balance.qty_reserved or 0) + approved_qty)
            item.qty_approved = approved_qty

        transfer_order.status = "approved"
        transfer_order.approved_by = approver_id
        transfer_order.approved_at = datetime.now(timezone.utc)
        if data.note:
            transfer_order.note = "\n".join(filter(None, [transfer_order.note, data.note]))
        self._audit(company_id, approver_id, "inventory.transfer.approve", str(transfer_order.id))
        if commit:
            await self.db.commit()
        else:
            await self.db.flush()
        return await self.get_to(transfer_order.id, company_id)

    async def ship_to(
        self,
        to_id: uuid.UUID,
        company_id: uuid.UUID,
        user_id: uuid.UUID,
        data: ShipTORequest,
        *,
        commit: bool = True,
    ) -> TransferOrder:
        try:
            transfer_order = await self._get_to_entity(to_id, company_id, lock=True)
            if transfer_order.status != "approved":
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Only approved transfer orders can be shipped once",
                )

            movement_ids: list[str] = []
            movement_note = data.note or transfer_order.note
            for item in sorted(
                transfer_order.items,
                key=lambda row: (str(row.product_id), str(row.variant_id or "")),
            ):
                qty = q4(item.qty_approved)
                if qty <= 0:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Missing approved quantity for {item.product_name}",
                    )
                balance = await self.stock_service._get_or_create_balance(
                    company_id=company_id,
                    branch_id=transfer_order.from_branch_id,
                    location_id=transfer_order.from_location_id,
                    product_id=item.product_id,
                    variant_id=item.variant_id,
                )
                on_hand = q4(balance.qty_on_hand)
                reserved = q4(balance.qty_reserved)
                if on_hand < qty:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Insufficient stock for {item.product_name}",
                    )
                if reserved < qty:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail=f"Reserved stock is incomplete for {item.product_name}",
                    )
                unit_cost = q4(balance.cost_per_unit)
                movement = await self.stock_service._record_movement(
                    balance=balance,
                    movement_type="transfer_out",
                    qty_delta=-qty,
                    user_id=user_id,
                    cost_per_unit=unit_cost,
                    reference_type="transfer_order",
                    reference_id=str(transfer_order.id),
                    note=movement_note,
                )
                balance.qty_reserved = q4(reserved - qty)
                item.qty_sent = qty
                item.qty_received = Decimal("0")
                item.qty_discrepancy = Decimal("0")
                item.unit_cost = unit_cost
                movement_ids.append(str(movement.id))

            transfer_order.status = "in_transit"
            transfer_order.shipped_at = datetime.now(timezone.utc)
            transfer_order.has_discrepancy = False
            transfer_order.discrepancy_note = None
            transfer_order.destination_posted_at_ship = False
            if data.note:
                transfer_order.note = "\n".join(filter(None, [transfer_order.note, data.note]))
            self._audit(
                company_id,
                user_id,
                "inventory.transfer.ship",
                str(transfer_order.id),
                {"movement_ids": movement_ids},
            )
            if commit:
                await self.db.commit()
            else:
                await self.db.flush()
        except Exception:
            if commit:
                await self.db.rollback()
            raise
        return await self.get_to(transfer_order.id, company_id)

    async def receive_to(
        self,
        to_id: uuid.UUID,
        company_id: uuid.UUID,
        user_id: uuid.UUID,
        data: ReceiveTORequest,
        *,
        commit: bool = True,
    ) -> TransferOrder:
        try:
            transfer_order = await self._get_to_entity(to_id, company_id, lock=True)
            if transfer_order.status not in {"in_transit", "partially_received"}:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Only an active in-transit transfer can be received",
                )

            receive_map = {item.item_id: item for item in data.items}
            if len(receive_map) != len(data.items):
                raise HTTPException(status_code=400, detail="Receive items must not contain duplicates")
            if set(receive_map.keys()) != {item.id for item in transfer_order.items}:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Receive items must match transfer order items")

            targets: dict[uuid.UUID, Decimal] = {}
            has_increase = False
            for item in transfer_order.items:
                target = q4(receive_map[item.id].qty_received)
                current = q4(item.qty_received)
                sent = q4(item.qty_sent)
                if target < current or target > sent:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=(
                            f"Invalid cumulative received quantity for {item.product_name}: "
                            f"current {current}, sent {sent}"
                        ),
                    )
                targets[item.id] = target
                has_increase = has_increase or target > current

            all_received = all(
                targets[item.id] == q4(item.qty_sent)
                for item in transfer_order.items
            )
            if not has_increase and not (data.finalize and not all_received):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="No new quantity was received",
                )
            if data.finalize and not all_received and not (data.note or "").strip():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="A discrepancy note is required when final received quantity is short",
                )

            movement_ids: list[str] = []
            movement_note = data.note or transfer_order.note
            legacy_destination_posted = transfer_order.destination_posted_at_ship
            for item in sorted(
                transfer_order.items,
                key=lambda row: (str(row.product_id), str(row.variant_id or "")),
            ):
                target = targets[item.id]
                current = q4(item.qty_received)
                delta = q4(target - current)
                legacy_correction = (
                    q4(q4(item.qty_sent) - target)
                    if legacy_destination_posted
                    else Decimal("0")
                )
                if delta > 0 or legacy_correction > 0:
                    balance = await self.stock_service._get_or_create_balance(
                        company_id=company_id,
                        branch_id=transfer_order.to_branch_id,
                        location_id=transfer_order.to_location_id,
                        product_id=item.product_id,
                        variant_id=item.variant_id,
                    )
                    if legacy_destination_posted:
                        if q4(item.unit_cost) == 0:
                            item.unit_cost = q4(balance.cost_per_unit)
                        if legacy_correction > 0:
                            movement = await self.stock_service._record_movement(
                                balance=balance,
                                movement_type="transfer_out",
                                qty_delta=-legacy_correction,
                                user_id=user_id,
                                cost_per_unit=q4(item.unit_cost),
                                reference_type="transfer_order_legacy_reconcile",
                                reference_id=str(transfer_order.id),
                                note=movement_note,
                            )
                            movement_ids.append(str(movement.id))
                    elif delta > 0:
                        movement = await self.stock_service._record_movement(
                            balance=balance,
                            movement_type="transfer_in",
                            qty_delta=delta,
                            user_id=user_id,
                            cost_per_unit=q4(item.unit_cost),
                            reference_type="transfer_order",
                            reference_id=str(transfer_order.id),
                            note=movement_note,
                        )
                        movement_ids.append(str(movement.id))
                item.qty_received = target
                item.qty_discrepancy = Decimal("0")

            transfer_order.destination_posted_at_ship = False

            now = datetime.now(timezone.utc)
            should_complete = all_received or data.finalize
            discrepancies: list[str] = []
            if should_complete:
                for item in transfer_order.items:
                    discrepancy = q4(q4(item.qty_sent) - q4(item.qty_received))
                    item.qty_discrepancy = discrepancy
                    if discrepancy > 0:
                        discrepancies.append(
                            f"{item.product_name}: ส่ง {q4(item.qty_sent)} รับ {q4(item.qty_received)} ขาด {discrepancy}"
                        )
                transfer_order.status = "completed"
                transfer_order.completed_at = now
                transfer_order.has_discrepancy = bool(discrepancies)
                transfer_order.discrepancy_note = "\n".join(discrepancies) or None
            else:
                transfer_order.status = "partially_received"
                transfer_order.completed_at = None
                transfer_order.has_discrepancy = False
                transfer_order.discrepancy_note = None
            transfer_order.received_by = user_id
            transfer_order.last_received_at = now
            if data.note:
                transfer_order.note = "\n".join(filter(None, [transfer_order.note, data.note]))
            self._audit(
                company_id,
                user_id,
                "inventory.transfer.receive",
                str(transfer_order.id),
                {
                    "status": transfer_order.status,
                    "finalize": data.finalize,
                    "movement_ids": movement_ids,
                    "has_discrepancy": transfer_order.has_discrepancy,
                    "legacy_destination_reconciled": legacy_destination_posted,
                },
            )
            if commit:
                await self.db.commit()
            else:
                await self.db.flush()
        except Exception:
            if commit:
                await self.db.rollback()
            raise
        return await self.get_to(transfer_order.id, company_id)

    async def cancel_to(
        self,
        to_id: uuid.UUID,
        company_id: uuid.UUID,
        user_id: uuid.UUID,
        reason: str,
        *,
        commit: bool = True,
    ) -> TransferOrder:
        transfer_order = await self._get_to_entity(to_id, company_id)
        if transfer_order.status not in {"draft", "pending_approval", "approved"}:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Transfer order cannot be cancelled")

        if transfer_order.status == "approved":
            for item in transfer_order.items:
                approved_qty = Decimal(item.qty_approved or 0)
                if approved_qty <= 0:
                    continue
                balance = await self.stock_service._get_or_create_balance(
                    company_id=company_id,
                    branch_id=transfer_order.from_branch_id,
                    location_id=transfer_order.from_location_id,
                    product_id=item.product_id,
                    variant_id=item.variant_id,
                )
                balance.qty_reserved = q4(max(Decimal("0"), Decimal(balance.qty_reserved or 0) - approved_qty))

        transfer_order.status = "cancelled"
        transfer_order.cancelled_at = datetime.now(timezone.utc)
        transfer_order.cancel_reason = reason
        self._audit(company_id, user_id, "inventory.transfer.cancel", str(transfer_order.id), {"reason": reason})
        if commit:
            await self.db.commit()
        else:
            await self.db.flush()
        return await self.get_to(transfer_order.id, company_id)

    async def get_to(self, to_id: uuid.UUID, company_id: uuid.UUID) -> TransferOrder:
        transfer_order = await self._get_to_entity(to_id, company_id)
        self._apply_names(transfer_order)
        return transfer_order

    async def list_tos(
        self,
        company_id: uuid.UUID,
        from_branch_id: uuid.UUID | None = None,
        to_branch_id: uuid.UUID | None = None,
        status_value: str | None = None,
        page: int = 1,
        limit: int = 20,
    ) -> tuple[list[TransferOrder], int]:
        filters = [TransferOrder.company_id == company_id]
        if from_branch_id is not None:
            filters.append(TransferOrder.from_branch_id == from_branch_id)
        if to_branch_id is not None:
            filters.append(TransferOrder.to_branch_id == to_branch_id)
        if status_value:
            filters.append(TransferOrder.status == status_value)

        total = await self.db.scalar(select(func.count(TransferOrder.id)).where(*filters)) or 0
        rows = await self.db.scalars(
            select(TransferOrder)
            .where(*filters)
            .options(
                selectinload(TransferOrder.items),
                selectinload(TransferOrder.from_branch),
                selectinload(TransferOrder.to_branch),
                selectinload(TransferOrder.from_location),
                selectinload(TransferOrder.to_location),
                selectinload(TransferOrder.requester),
            )
            .order_by(TransferOrder.request_date.desc(), TransferOrder.created_at.desc())
            .offset((page - 1) * limit)
            .limit(limit)
        )
        orders = rows.unique().all()
        for order in orders:
            self._apply_names(order)
        return orders, int(total)

    async def get_multi_branch_stock(
        self, company_id: uuid.UUID
    ) -> MultiBranchStockResponse:
        location_counts = (
            select(
                StockLocation.branch_id.label("branch_id"),
                func.count(distinct(StockLocation.id)).label("location_count"),
            )
            .where(StockLocation.company_id == company_id, StockLocation.deleted_at.is_(None))
            .group_by(StockLocation.branch_id)
            .subquery()
        )
        balance_summary = (
            select(
                StockBalance.branch_id.label("branch_id"),
                func.count(
                    distinct(case((StockBalance.qty_on_hand > 0, StockBalance.product_id)))
                ).label("product_count"),
                func.coalesce(
                    func.sum(StockBalance.qty_on_hand * StockBalance.cost_per_unit), 0
                ).label("total_value"),
                func.count(
                    distinct(
                        case(
                            (
                                (Product.min_stock_qty > 0)
                                & (StockBalance.qty_on_hand <= Product.min_stock_qty),
                                StockBalance.id,
                            )
                        )
                    )
                ).label("low_stock_count"),
                func.count(
                    distinct(case((StockBalance.qty_on_hand == 0, StockBalance.id)))
                ).label("zero_stock_count"),
            )
            .select_from(StockBalance)
            .join(Product, Product.id == StockBalance.product_id)
            .where(StockBalance.company_id == company_id)
            .group_by(StockBalance.branch_id)
            .subquery()
        )
        statement = (
            select(
                Branch.id,
                Branch.name,
                func.coalesce(location_counts.c.location_count, 0),
                func.coalesce(balance_summary.c.product_count, 0),
                func.coalesce(balance_summary.c.total_value, 0),
                func.coalesce(balance_summary.c.low_stock_count, 0),
                func.coalesce(balance_summary.c.zero_stock_count, 0),
            )
            .select_from(Branch)
            .join(location_counts, location_counts.c.branch_id == Branch.id, isouter=True)
            .join(balance_summary, balance_summary.c.branch_id == Branch.id, isouter=True)
            .where(Branch.company_id == company_id, Branch.deleted_at.is_(None))
            .order_by(Branch.sort_order.asc(), Branch.name.asc())
        )
        rows = await self.db.execute(statement)
        branches: list[BranchStockSummary] = []
        grand_total_value = Decimal("0")
        grand_low_stock_count = 0
        for branch_id, branch_name, location_count, product_count, total_value, low_stock_count, zero_stock_count in rows.all():
            total_value_decimal = Decimal(total_value or 0).quantize(TWOPLACES, rounding=ROUND_HALF_UP)
            branches.append(
                BranchStockSummary(
                    branch_id=str(branch_id),
                    branch_name=branch_name,
                    location_count=int(location_count or 0),
                    product_count=int(product_count or 0),
                    total_value=total_value_decimal,
                    low_stock_count=int(low_stock_count or 0),
                    zero_stock_count=int(zero_stock_count or 0),
                )
            )
            grand_total_value += total_value_decimal
            grand_low_stock_count += int(low_stock_count or 0)
        return MultiBranchStockResponse(
            branches=branches,
            grand_total_value=grand_total_value.quantize(TWOPLACES, rounding=ROUND_HALF_UP),
            grand_low_stock_count=grand_low_stock_count,
        )

    async def _get_branch(self, company_id: uuid.UUID, branch_id: uuid.UUID) -> Branch:
        branch = await self.db.scalar(
            select(Branch).where(Branch.id == branch_id, Branch.company_id == company_id, Branch.deleted_at.is_(None))
        )
        if branch is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Branch not found")
        return branch

    async def _prepare_items(self, company_id: uuid.UUID, items) -> list[dict[str, object]]:
        prepared: list[dict[str, object]] = []
        for item in items:
            if item.qty_requested <= 0:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Requested quantity must be positive")
            product = await self.db.scalar(
                select(Product)
                .where(Product.id == item.product_id, Product.company_id == company_id, Product.deleted_at.is_(None))
                .options(selectinload(Product.unit))
            )
            if product is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
            variant = None
            if item.variant_id is not None:
                variant = await self.db.scalar(
                    select(ProductVariant).where(
                        ProductVariant.id == item.variant_id,
                        ProductVariant.company_id == company_id,
                        ProductVariant.product_id == product.id,
                        ProductVariant.deleted_at.is_(None),
                    )
                )
                if variant is None:
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Variant not found")
            prepared.append(
                {
                    "product_id": product.id,
                    "variant_id": variant.id if variant else None,
                    "product_name": product.name if variant is None else f"{product.name} - {variant.name}",
                    "sku": variant.sku if variant else product.sku,
                    "unit_code": product.unit.code if product.unit else None,
                    "qty_requested": q4(item.qty_requested),
                }
            )
        return prepared

    async def _generate_number(self, company_id: uuid.UUID, target_date: date) -> str:
        day_prefix = f"TO{target_date:%Y%m%d}-"
        # ``to_number`` is globally unique, so its sequence and advisory lock
        # must also be global for the day. A Company-scoped counter can issue
        # the same number concurrently to two tenants.
        lock_key = hash(target_date.strftime("%Y%m%d") + "TRANSFER") % (2**31)
        await self.db.execute(text(f"SELECT pg_advisory_xact_lock({lock_key})"))
        count = await self.db.scalar(
            select(func.count(TransferOrder.id)).where(
                TransferOrder.to_number.like(f"{day_prefix}%"),
            )
        ) or 0
        return f"{day_prefix}{int(count) + 1:04d}"

    async def _get_to_entity(
        self,
        to_id: uuid.UUID,
        company_id: uuid.UUID,
        *,
        lock: bool = False,
    ) -> TransferOrder:
        statement = (
            select(TransferOrder)
            .where(TransferOrder.id == to_id, TransferOrder.company_id == company_id)
            .options(
                selectinload(TransferOrder.items),
                selectinload(TransferOrder.from_branch),
                selectinload(TransferOrder.to_branch),
                selectinload(TransferOrder.from_location),
                selectinload(TransferOrder.to_location),
                selectinload(TransferOrder.requester),
                selectinload(TransferOrder.approver),
                selectinload(TransferOrder.receiver),
            )
        )
        if lock:
            statement = statement.with_for_update()
        transfer_order = await self.db.scalar(statement)
        if transfer_order is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transfer order not found")
        return transfer_order

    def _apply_names(self, transfer_order: TransferOrder) -> None:
        transfer_order.from_branch_name = transfer_order.from_branch.name
        transfer_order.to_branch_name = transfer_order.to_branch.name
        transfer_order.from_location_name = transfer_order.from_location.name
        transfer_order.to_location_name = transfer_order.to_location.name
        transfer_order.requested_by_name = transfer_order.requester.display_name or transfer_order.requester.username
        transfer_order.item_count = len(transfer_order.items)

    def _audit(
        self,
        company_id: uuid.UUID,
        user_id: uuid.UUID,
        action: str,
        resource_id: str,
        new_value: dict | None = None,
    ) -> None:
        self.db.add(
            AuditLog(
                company_id=company_id,
                user_id=user_id,
                action=action,
                resource="TransferOrder",
                resource_id=resource_id,
                new_value=new_value,
            )
        )
