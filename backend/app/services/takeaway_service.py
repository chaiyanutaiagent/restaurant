from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
import base64
import hashlib
import hmac
import secrets
from typing import Iterable
import uuid

from fastapi import HTTPException, status
from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import TokenData
from app.config import settings
from app.models.takeaway import (
    TakeawayBranchCatalogItem,
    TakeawayCatalogItem,
    TakeawayCategory,
    TakeawayCentralOrder,
    TakeawayCentralOrderItem,
    TakeawayCentralOrderRound,
    TakeawayCreditAccount,
    TakeawayCreditEntry,
    TakeawayKitchenTicket,
    TakeawayOperationalOutbox,
    TakeawayOrderingToken,
    TakeawayOrder,
    TakeawayOrderItem,
    TakeawayPayment,
    TakeawayPickupToken,
    TakeawayProductionBatch,
    TakeawayProductionLine,
    TakeawayReceipt,
    TakeawayReferenceProjection,
    TakeawayShift,
    TakeawayStockBalance,
    TakeawayStockLocation,
    TakeawayStockMovement,
    TakeawayTransfer,
    TakeawayTransferItem,
)
from app.schemas.takeaway import (
    TakeawayCatalogItemCreate,
    TakeawayCategoryCreate,
    TakeawayCentralOrderCreate,
    TakeawayReceiptPrintCreate,
    TakeawayCreditEntryCreate,
    TakeawayCreditLimitUpdate,
    TakeawayErpEventAcknowledge,
    TakeawayOrderPaymentCapture,
    TakeawayOrderingLinkCreate,
    TakeawayProductionBatchCreate,
    TakeawayProductionComplete,
    TakeawaySaleCreate,
    TakeawayPublicOrderCreate,
    TakeawayShiftClose,
    TakeawayShiftOpen,
    TakeawayStoreCentralOrderCreate,
    TakeawayStockMovementCreate,
    TakeawayTransferCreate,
    TakeawayTransferStatusUpdate,
)


MONEY = Decimal("0.01")
QUANTITY = Decimal("0.0001")


def money(value: Decimal | int | str) -> Decimal:
    return Decimal(value).quantize(MONEY, rounding=ROUND_HALF_UP)


def assert_takeaway_scope(
    current: TokenData,
    *,
    brand_id: uuid.UUID | None = None,
    branch_id: uuid.UUID | None = None,
    require_branch: bool = False,
) -> None:
    if current.business_type not in {None, "takeaway"}:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Takeaway resource not found")
    if current.target_database not in {None, "takeaway"}:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Takeaway resource not found")
    if current.brand_id is not None and brand_id is not None and current.brand_id != brand_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Takeaway resource not found")
    if current.branch_id is not None and branch_id is not None and current.branch_id != branch_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Takeaway resource not found")
    if require_branch and current.branch_id is None and "*" not in current.permissions:
        if not {"branch", "brand", "company"}.intersection(current.scope_types):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Branch context required")


class TakeawayService:
    def __init__(self, db: AsyncSession, current: TokenData):
        self.db = db
        self.current = current

    @staticmethod
    def _public_pickup_token(order_id: uuid.UUID) -> str:
        digest = hmac.new(
            settings.secret_key.encode(),
            f"takeaway-public-pickup:{order_id}".encode(),
            hashlib.sha256,
        ).digest()
        return base64.urlsafe_b64encode(digest).decode().rstrip("=")

    async def _reference(
        self,
        aggregate_type: str,
        aggregate_id: uuid.UUID,
    ) -> TakeawayReferenceProjection:
        row = await self.db.scalar(
            select(TakeawayReferenceProjection).where(
                TakeawayReferenceProjection.aggregate_type == aggregate_type,
                TakeawayReferenceProjection.aggregate_id == aggregate_id,
                TakeawayReferenceProjection.company_id == self.current.company_id,
            )
        )
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"{aggregate_type} reference is not synchronized to Takeaway",
            )
        if row.payload.get("is_active") is False:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"{aggregate_type} is inactive")
        if aggregate_type == "brand" and row.payload.get("business_type") != "takeaway":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Takeaway Brand not found")
        return row

    async def _validate_context(
        self,
        *,
        brand_id: uuid.UUID,
        branch_id: uuid.UUID | None = None,
    ) -> None:
        assert_takeaway_scope(self.current, brand_id=brand_id, branch_id=branch_id)
        await self._reference("brand", brand_id)
        if branch_id is not None:
            await self._reference("branch", branch_id)
            link = await self.db.scalar(
                select(TakeawayReferenceProjection.id).where(
                    TakeawayReferenceProjection.aggregate_type == "brand_branch",
                    TakeawayReferenceProjection.company_id == self.current.company_id,
                    TakeawayReferenceProjection.payload["brand_id"].astext == str(brand_id),
                    TakeawayReferenceProjection.payload["branch_id"].astext == str(branch_id),
                    TakeawayReferenceProjection.payload["is_active"].astext == "true",
                )
            )
            if link is None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Branch is not assigned to this Takeaway Brand",
                )

    def _outbox(
        self,
        *,
        event_type: str,
        aggregate_type: str,
        aggregate_id: uuid.UUID,
        idempotency_key: str,
        payload: dict[str, object],
        brand_id: uuid.UUID | None = None,
        branch_id: uuid.UUID | None = None,
    ) -> None:
        self.db.add(
            TakeawayOperationalOutbox(
                company_id=self.current.company_id,
                brand_id=brand_id,
                branch_id=branch_id,
                event_type=event_type,
                aggregate_type=aggregate_type,
                aggregate_id=aggregate_id,
                idempotency_key=idempotency_key,
                payload=payload,
            )
        )

    async def create_category(self, data: TakeawayCategoryCreate) -> TakeawayCategory:
        await self._validate_context(brand_id=data.brand_id)
        category = TakeawayCategory(
            company_id=self.current.company_id,
            brand_id=data.brand_id,
            code=data.code.lower(),
            name=data.name,
            sort_order=data.sort_order,
        )
        self.db.add(category)
        await self.db.commit()
        await self.db.refresh(category)
        return category

    async def list_categories(self, brand_id: uuid.UUID) -> list[TakeawayCategory]:
        await self._validate_context(brand_id=brand_id)
        return list(
            await self.db.scalars(
                select(TakeawayCategory)
                .where(
                    TakeawayCategory.company_id == self.current.company_id,
                    TakeawayCategory.brand_id == brand_id,
                    TakeawayCategory.is_active.is_(True),
                )
                .order_by(TakeawayCategory.sort_order, TakeawayCategory.name)
            )
        )

    async def create_catalog_item(self, data: TakeawayCatalogItemCreate) -> TakeawayCatalogItem:
        await self._validate_context(brand_id=data.brand_id)
        if data.category_id is not None:
            category = await self.db.scalar(
                select(TakeawayCategory.id).where(
                    TakeawayCategory.id == data.category_id,
                    TakeawayCategory.company_id == self.current.company_id,
                    TakeawayCategory.brand_id == data.brand_id,
                    TakeawayCategory.is_active.is_(True),
                )
            )
            if category is None:
                raise HTTPException(status_code=404, detail="Takeaway category not found")
        item = TakeawayCatalogItem(
            company_id=self.current.company_id,
            **data.model_dump(),
        )
        self.db.add(item)
        await self.db.commit()
        await self.db.refresh(item)
        return item

    async def list_catalog(
        self,
        brand_id: uuid.UUID,
        branch_id: uuid.UUID | None = None,
    ) -> list[tuple[TakeawayCatalogItem, Decimal | None, bool]]:
        await self._validate_context(brand_id=brand_id, branch_id=branch_id)
        statement = (
            select(
                TakeawayCatalogItem,
                TakeawayBranchCatalogItem.price_override,
                func.coalesce(TakeawayBranchCatalogItem.is_available, True),
            )
            .outerjoin(
                TakeawayBranchCatalogItem,
                (TakeawayBranchCatalogItem.catalog_item_id == TakeawayCatalogItem.id)
                & (TakeawayBranchCatalogItem.branch_id == branch_id),
            )
            .where(
                TakeawayCatalogItem.company_id == self.current.company_id,
                TakeawayCatalogItem.brand_id == brand_id,
                TakeawayCatalogItem.is_active.is_(True),
            )
            .order_by(TakeawayCatalogItem.name)
        )
        return [(row[0], row[1], bool(row[2])) for row in (await self.db.execute(statement)).all()]

    async def set_branch_availability(
        self,
        *,
        brand_id: uuid.UUID,
        branch_id: uuid.UUID,
        item_id: uuid.UUID,
        price_override: Decimal | None,
        is_available: bool,
    ) -> TakeawayBranchCatalogItem:
        await self._validate_context(brand_id=brand_id, branch_id=branch_id)
        item = await self.db.scalar(
            select(TakeawayCatalogItem).where(
                TakeawayCatalogItem.id == item_id,
                TakeawayCatalogItem.company_id == self.current.company_id,
                TakeawayCatalogItem.brand_id == brand_id,
            )
        )
        if item is None:
            raise HTTPException(status_code=404, detail="Takeaway catalog item not found")
        row_id = (
            await self.db.execute(
                insert(TakeawayBranchCatalogItem)
                .values(
                    id=uuid.uuid4(),
                    company_id=self.current.company_id,
                    brand_id=brand_id,
                    branch_id=branch_id,
                    catalog_item_id=item_id,
                    price_override=price_override,
                    is_available=is_available,
                )
                .on_conflict_do_update(
                    constraint="uq_takeaway_branch_catalog_item",
                    set_={"price_override": price_override, "is_available": is_available},
                )
                .returning(TakeawayBranchCatalogItem.id)
            )
        ).scalar_one()
        await self.db.commit()
        return await self.db.get(TakeawayBranchCatalogItem, row_id)  # type: ignore[return-value]

    async def open_shift(self, data: TakeawayShiftOpen) -> TakeawayShift:
        if self.current.branch_id is None or self.current.brand_id is None:
            raise HTTPException(status_code=400, detail="Takeaway Branch context required")
        await self._validate_context(brand_id=self.current.brand_id, branch_id=self.current.branch_id)
        existing = await self.db.scalar(
            select(TakeawayShift).where(
                TakeawayShift.company_id == self.current.company_id,
                TakeawayShift.branch_id == self.current.branch_id,
                TakeawayShift.status == "open",
            )
        )
        if existing is not None:
            return existing
        round_no = int(
            await self.db.scalar(
                select(func.coalesce(func.max(TakeawayShift.round_no), 0)).where(
                    TakeawayShift.branch_id == self.current.branch_id,
                    TakeawayShift.business_date == data.business_date,
                )
            )
            or 0
        ) + 1
        shift = TakeawayShift(
            company_id=self.current.company_id,
            brand_id=self.current.brand_id,
            branch_id=self.current.branch_id,
            business_date=data.business_date,
            round_no=round_no,
            opened_by=self.current.user_id,
            opening_cash=money(data.opening_cash),
        )
        self.db.add(shift)
        await self.db.commit()
        await self.db.refresh(shift)
        return shift

    async def close_shift(self, shift_id: uuid.UUID, data: TakeawayShiftClose) -> TakeawayShift:
        shift = await self.db.scalar(
            select(TakeawayShift)
            .where(
                TakeawayShift.id == shift_id,
                TakeawayShift.company_id == self.current.company_id,
                TakeawayShift.status == "open",
            )
            .with_for_update()
        )
        if shift is None:
            raise HTTPException(status_code=404, detail="Open Takeaway shift not found")
        assert_takeaway_scope(self.current, brand_id=shift.brand_id, branch_id=shift.branch_id)
        cash_sales = await self.db.scalar(
            select(func.coalesce(func.sum(TakeawayPayment.amount), 0))
            .join(TakeawayOrder, TakeawayOrder.id == TakeawayPayment.order_id)
            .where(
                TakeawayOrder.shift_id == shift.id,
                TakeawayOrder.status == "paid",
                TakeawayPayment.method == "cash",
                TakeawayPayment.status == "captured",
            )
        )
        shift.expected_cash = money(shift.opening_cash + Decimal(cash_sales or 0))
        shift.counted_cash = money(data.counted_cash)
        shift.close_note = data.note
        shift.closed_by = self.current.user_id
        shift.closed_at = datetime.now(timezone.utc)
        shift.status = "closed"
        self._outbox(
            event_type="takeaway.shift.closed.v1",
            aggregate_type="shift",
            aggregate_id=shift.id,
            idempotency_key=f"shift:{shift.id}:closed",
            payload={
                "business_date": str(shift.business_date),
                "round_no": shift.round_no,
                "expected_cash": str(shift.expected_cash),
                "counted_cash": str(shift.counted_cash),
            },
            brand_id=shift.brand_id,
            branch_id=shift.branch_id,
        )
        await self.db.commit()
        await self.db.refresh(shift)
        return shift

    async def shift_summary(self, shift_id: uuid.UUID) -> dict[str, object]:
        shift = await self.db.scalar(
            select(TakeawayShift).where(
                TakeawayShift.id == shift_id,
                TakeawayShift.company_id == self.current.company_id,
            )
        )
        if shift is None:
            raise HTTPException(status_code=404, detail="Takeaway shift not found")
        assert_takeaway_scope(self.current, brand_id=shift.brand_id, branch_id=shift.branch_id)

        order_rows = (
            await self.db.execute(
                select(
                    TakeawayOrder.status,
                    func.count(TakeawayOrder.id),
                    func.coalesce(func.sum(TakeawayOrder.total_amount), 0),
                    func.coalesce(func.sum(TakeawayOrder.tax_amount), 0),
                    func.coalesce(func.sum(TakeawayOrder.discount_amount), 0),
                )
                .where(TakeawayOrder.shift_id == shift.id)
                .group_by(TakeawayOrder.status)
            )
        ).all()
        payment_rows = (
            await self.db.execute(
                select(
                    TakeawayPayment.method,
                    TakeawayPayment.status,
                    func.coalesce(func.sum(TakeawayPayment.amount), 0),
                )
                .join(TakeawayOrder, TakeawayOrder.id == TakeawayPayment.order_id)
                .where(TakeawayOrder.shift_id == shift.id)
                .group_by(TakeawayPayment.method, TakeawayPayment.status)
            )
        ).all()
        by_status = {
            str(row[0]): {
                "order_count": int(row[1]),
                "amount": str(money(row[2])),
                "tax_amount": str(money(row[3])),
                "discount_amount": str(money(row[4])),
            }
            for row in order_rows
        }
        payment_totals: dict[str, str] = {}
        refunded_payments: dict[str, str] = {}
        for method, payment_status, total in payment_rows:
            target = payment_totals if payment_status == "captured" else refunded_payments
            target[str(method)] = str(money(total))
        cash_sales = Decimal(payment_totals.get("cash", "0"))
        expected_cash = money(shift.opening_cash + cash_sales)
        counted_cash = money(shift.counted_cash) if shift.counted_cash is not None else None
        return {
            "shift": shift,
            "paid": by_status.get("paid", {"order_count": 0, "amount": "0.00", "tax_amount": "0.00", "discount_amount": "0.00"}),
            "refunded": by_status.get("refunded", {"order_count": 0, "amount": "0.00", "tax_amount": "0.00", "discount_amount": "0.00"}),
            "payment_totals": payment_totals,
            "refunded_payments": refunded_payments,
            "expected_cash": str(expected_cash),
            "counted_cash": str(counted_cash) if counted_cash is not None else None,
            "cash_variance": str(money(counted_cash - expected_cash)) if counted_cash is not None else None,
        }

    async def _apply_stock(
        self,
        *,
        location_id: uuid.UUID,
        item_id: uuid.UUID,
        lot_code: str,
        quantity_delta: Decimal,
        unit_cost: Decimal,
        movement_type: str,
        idempotency_key: str,
        brand_id: uuid.UUID | None = None,
        branch_id: uuid.UUID | None = None,
        order_id: uuid.UUID | None = None,
        production_batch_id: uuid.UUID | None = None,
        transfer_id: uuid.UUID | None = None,
        note: str | None = None,
    ) -> TakeawayStockBalance:
        existing_movement = await self.db.scalar(
            select(TakeawayStockMovement).where(
                TakeawayStockMovement.idempotency_key == idempotency_key
            )
        )
        if existing_movement is not None:
            balance = await self.db.scalar(
                select(TakeawayStockBalance).where(
                    TakeawayStockBalance.company_id == self.current.company_id,
                    TakeawayStockBalance.location_id == location_id,
                    TakeawayStockBalance.item_id == item_id,
                    TakeawayStockBalance.lot_code == lot_code,
                )
            )
            if balance is None:
                raise RuntimeError("Idempotent stock movement has no balance")
            return balance
        balance = await self.db.scalar(
            select(TakeawayStockBalance)
            .where(
                TakeawayStockBalance.company_id == self.current.company_id,
                TakeawayStockBalance.location_id == location_id,
                TakeawayStockBalance.item_id == item_id,
                TakeawayStockBalance.lot_code == lot_code,
            )
            .with_for_update()
        )
        delta = Decimal(quantity_delta).quantize(QUANTITY)
        if balance is None:
            if delta < 0:
                raise HTTPException(status_code=409, detail="Insufficient Takeaway stock")
            balance = TakeawayStockBalance(
                company_id=self.current.company_id,
                location_id=location_id,
                item_id=item_id,
                lot_code=lot_code,
                on_hand_qty=Decimal("0"),
                reserved_qty=Decimal("0"),
                average_cost=Decimal("0"),
            )
            self.db.add(balance)
            await self.db.flush()
        previous_qty = Decimal(balance.on_hand_qty)
        resulting_qty = previous_qty + delta
        if resulting_qty < 0:
            raise HTTPException(status_code=409, detail="Insufficient Takeaway stock")
        if delta > 0 and unit_cost >= 0:
            previous_value = previous_qty * Decimal(balance.average_cost)
            added_value = delta * Decimal(unit_cost)
            balance.average_cost = (
                (previous_value + added_value) / resulting_qty
                if resulting_qty > 0
                else Decimal("0")
            ).quantize(QUANTITY)
        balance.on_hand_qty = resulting_qty
        self.db.add(
            TakeawayStockMovement(
                company_id=self.current.company_id,
                location_id=location_id,
                item_id=item_id,
                lot_code=lot_code,
                brand_id=brand_id,
                branch_id=branch_id,
                order_id=order_id,
                production_batch_id=production_batch_id,
                transfer_id=transfer_id,
                movement_type=movement_type,
                quantity_delta=delta,
                unit_cost=unit_cost,
                idempotency_key=idempotency_key,
                note=note,
            )
        )
        return balance

    async def create_stock_movement(self, data: TakeawayStockMovementCreate) -> TakeawayStockBalance:
        if data.brand_id is not None:
            await self._validate_context(brand_id=data.brand_id, branch_id=data.branch_id)
        balance = await self._apply_stock(**data.model_dump())
        self._outbox(
            event_type="takeaway.stock.moved.v1",
            aggregate_type="stock_balance",
            aggregate_id=balance.id,
            idempotency_key=f"outbox:{data.idempotency_key}",
            payload={
                "location_id": str(data.location_id),
                "item_id": str(data.item_id),
                "quantity_delta": str(data.quantity_delta),
                "movement_type": data.movement_type,
            },
            brand_id=data.brand_id,
            branch_id=data.branch_id,
        )
        await self.db.commit()
        await self.db.refresh(balance)
        return balance

    async def list_stock(
        self,
        *,
        location_id: uuid.UUID | None = None,
    ) -> list[TakeawayStockBalance]:
        statement = select(TakeawayStockBalance).where(
            TakeawayStockBalance.company_id == self.current.company_id
        )
        if self.current.branch_id is not None:
            statement = statement.join(
                TakeawayStockLocation,
                TakeawayStockLocation.id == TakeawayStockBalance.location_id,
            ).where(TakeawayStockLocation.branch_id == self.current.branch_id)
        if location_id is not None:
            statement = statement.where(TakeawayStockBalance.location_id == location_id)
        return list(await self.db.scalars(statement.order_by(TakeawayStockBalance.item_id)))

    async def list_stock_movements(
        self,
        *,
        location_id: uuid.UUID | None = None,
        limit: int = 200,
    ) -> list[TakeawayStockMovement]:
        statement = select(TakeawayStockMovement).where(
            TakeawayStockMovement.company_id == self.current.company_id
        )
        if self.current.brand_id is not None:
            statement = statement.where(
                (TakeawayStockMovement.brand_id == self.current.brand_id)
                | (TakeawayStockMovement.brand_id.is_(None))
            )
        if self.current.branch_id is not None:
            statement = statement.where(TakeawayStockMovement.branch_id == self.current.branch_id)
        if location_id is not None:
            statement = statement.where(TakeawayStockMovement.location_id == location_id)
        return list(
            await self.db.scalars(
                statement.order_by(TakeawayStockMovement.occurred_at.desc()).limit(limit)
            )
        )

    async def list_stock_locations(self) -> list[TakeawayStockLocation]:
        statement = select(TakeawayStockLocation).where(
            TakeawayStockLocation.company_id == self.current.company_id,
            TakeawayStockLocation.is_active.is_(True),
        )
        if self.current.branch_id is not None:
            statement = statement.where(TakeawayStockLocation.branch_id == self.current.branch_id)
        return list(await self.db.scalars(statement.order_by(TakeawayStockLocation.name)))

    async def create_ordering_link(
        self,
        data: TakeawayOrderingLinkCreate,
    ) -> tuple[TakeawayOrderingToken, str]:
        if self.current.brand_id is None or self.current.branch_id is None:
            raise HTTPException(status_code=400, detail="Takeaway Branch context required")
        await self._validate_context(
            brand_id=self.current.brand_id,
            branch_id=self.current.branch_id,
        )
        raw_token = secrets.token_urlsafe(32)
        row = TakeawayOrderingToken(
            company_id=self.current.company_id,
            brand_id=self.current.brand_id,
            branch_id=self.current.branch_id,
            token_hash=hashlib.sha256(raw_token.encode()).hexdigest(),
            expires_at=datetime.now(timezone.utc) + timedelta(hours=data.expires_in_hours),
            created_by=self.current.user_id,
        )
        self.db.add(row)
        await self.db.commit()
        await self.db.refresh(row)
        return row, raw_token

    async def create_public_order(
        self,
        data: TakeawayPublicOrderCreate,
    ) -> tuple[TakeawayOrder, str | None, bool]:
        if self.current.brand_id is None or self.current.branch_id is None:
            raise HTTPException(status_code=404, detail="Takeaway ordering link not found")
        brand_id = self.current.brand_id
        branch_id = self.current.branch_id
        await self._validate_context(brand_id=brand_id, branch_id=branch_id)
        existing = await self.db.scalar(
            select(TakeawayOrder).where(
                TakeawayOrder.branch_id == branch_id,
                TakeawayOrder.idempotency_key == data.idempotency_key,
            )
        )
        if existing is not None:
            pickup_token = (
                self._public_pickup_token(existing.id)
                if (existing.source_metadata or {}).get("public_order") is True
                else None
            )
            return existing, pickup_token, True
        shift = await self.db.scalar(
            select(TakeawayShift).where(
                TakeawayShift.company_id == self.current.company_id,
                TakeawayShift.brand_id == brand_id,
                TakeawayShift.branch_id == branch_id,
                TakeawayShift.status == "open",
            )
        )
        if shift is None:
            raise HTTPException(status_code=409, detail="Store is not accepting Takeaway orders")
        item_ids = [line.catalog_item_id for line in data.items]
        catalog = {
            item.id: item
            for item in await self.db.scalars(
                select(TakeawayCatalogItem).where(
                    TakeawayCatalogItem.id.in_(item_ids),
                    TakeawayCatalogItem.company_id == self.current.company_id,
                    TakeawayCatalogItem.brand_id == brand_id,
                    TakeawayCatalogItem.is_active.is_(True),
                )
            )
        }
        if len(catalog) != len(set(item_ids)):
            raise HTTPException(status_code=404, detail="One or more Takeaway items were not found")
        availability = {
            row.catalog_item_id: row
            for row in await self.db.scalars(
                select(TakeawayBranchCatalogItem).where(
                    TakeawayBranchCatalogItem.branch_id == branch_id,
                    TakeawayBranchCatalogItem.catalog_item_id.in_(item_ids),
                )
            )
        }
        if any(not availability[item_id].is_available for item_id in availability):
            raise HTTPException(status_code=409, detail="One or more Takeaway items are unavailable")
        prepared: list[tuple[object, TakeawayCatalogItem, Decimal, Decimal, Decimal]] = []
        subtotal = Decimal("0")
        for line in data.items:
            item = catalog[line.catalog_item_id]
            override = availability.get(item.id)
            unit_price = money(override.price_override if override and override.price_override is not None else item.price)
            line_subtotal = money(unit_price * line.quantity)
            line_tax = money(line_subtotal * Decimal(item.tax_rate) / Decimal("100"))
            subtotal += line_subtotal
            prepared.append((line, item, unit_price, line_subtotal, line_tax))
        subtotal = money(subtotal)
        tax = money(sum((entry[4] for entry in prepared), Decimal("0")))
        total = money(subtotal + tax)

        await self.db.execute(
            text("SELECT pg_advisory_xact_lock(hashtext(:key))"),
            {"key": f"takeaway-queue:{branch_id}:{shift.business_date}"},
        )
        queue_number = int(
            await self.db.scalar(
                select(func.coalesce(func.max(TakeawayOrder.queue_number), 0)).where(
                    TakeawayOrder.branch_id == branch_id,
                    TakeawayOrder.business_date == shift.business_date,
                )
            )
            or 0
        ) + 1
        branch_key = str(branch_id).replace("-", "")[:6].upper()
        order = TakeawayOrder(
            company_id=self.current.company_id,
            brand_id=brand_id,
            branch_id=branch_id,
            shift_id=shift.id,
            order_number=f"TW-{shift.business_date:%Y%m%d}-{branch_key}-{queue_number:04d}",
            business_date=shift.business_date,
            queue_number=queue_number,
            channel="qr",
            status="draft",
            fulfillment_status="awaiting_payment",
            subtotal=subtotal,
            discount_amount=Decimal("0"),
            tax_amount=tax,
            total_amount=total,
            customer_name=data.customer_name,
            customer_phone=data.customer_phone,
            note=data.note,
            idempotency_key=data.idempotency_key,
            source_metadata={
                "public_order": True,
                "stock_item_ids": [str(item.id) for _, item, _, _, _ in prepared if item.track_stock],
            },
        )
        self.db.add(order)
        await self.db.flush()
        for line, item, unit_price, line_subtotal, line_tax in prepared:
            self.db.add(
                TakeawayOrderItem(
                    order_id=order.id,
                    catalog_item_id=item.id,
                    sku=item.sku,
                    name=item.name,
                    quantity=line.quantity,
                    unit_price=unit_price,
                    discount_amount=Decimal("0"),
                    tax_amount=line_tax,
                    line_total=line_subtotal + line_tax,
                    kitchen_station=item.kitchen_station,
                    note=line.note,
                )
            )
        pickup_token = self._public_pickup_token(order.id)
        self.db.add(
            TakeawayPickupToken(
                order_id=order.id,
                token_hash=hashlib.sha256(pickup_token.encode()).hexdigest(),
                expires_at=datetime.combine(shift.business_date, time(23, 59, 59), tzinfo=timezone.utc),
            )
        )
        await self.db.commit()
        await self.db.refresh(order)
        return order, pickup_token, False

    async def capture_order_payment(
        self,
        order_id: uuid.UUID,
        data: TakeawayOrderPaymentCapture,
    ) -> tuple[TakeawayOrder, bool]:
        order = await self.db.scalar(
            select(TakeawayOrder)
            .where(
                TakeawayOrder.id == order_id,
                TakeawayOrder.company_id == self.current.company_id,
            )
            .with_for_update()
        )
        if order is None:
            raise HTTPException(status_code=404, detail="Takeaway order not found")
        assert_takeaway_scope(self.current, brand_id=order.brand_id, branch_id=order.branch_id)
        existing_payment = await self.db.scalar(
            select(TakeawayPayment).where(
                TakeawayPayment.order_id == order.id,
                TakeawayPayment.idempotency_key == data.payment.idempotency_key,
            )
        )
        if existing_payment is not None:
            return order, True
        if order.status != "draft" or order.fulfillment_status != "awaiting_payment":
            raise HTTPException(status_code=409, detail="Takeaway order is not awaiting payment")
        if money(data.payment.amount) != money(order.total_amount):
            raise HTTPException(status_code=422, detail="Payment amount must equal Takeaway order total")

        order_items = list(
            await self.db.scalars(
                select(TakeawayOrderItem).where(TakeawayOrderItem.order_id == order.id)
            )
        )
        store_location_id = await self.db.scalar(
            select(TakeawayStockLocation.id)
            .where(
                TakeawayStockLocation.company_id == self.current.company_id,
                TakeawayStockLocation.branch_id == order.branch_id,
                TakeawayStockLocation.location_type == "store",
                TakeawayStockLocation.is_active.is_(True),
            )
            .order_by(TakeawayStockLocation.created_at, TakeawayStockLocation.id)
            .limit(1)
        )
        sale_location_id = store_location_id or order.branch_id
        raw_stock_item_ids = (order.source_metadata or {}).get("stock_item_ids", [])
        stock_item_ids = (
            {str(value) for value in raw_stock_item_ids}
            if isinstance(raw_stock_item_ids, list)
            else set()
        )
        receipt_lines: list[dict[str, object]] = []
        for item in order_items:
            self.db.add(
                TakeawayKitchenTicket(
                    company_id=order.company_id,
                    brand_id=order.brand_id,
                    branch_id=order.branch_id,
                    order_id=order.id,
                    order_item_id=item.id,
                    queue_number=order.queue_number or 0,
                    station=item.kitchen_station or "default",
                    item_name=item.name,
                    quantity=item.quantity,
                )
            )
            if item.catalog_item_id is not None and str(item.catalog_item_id) in stock_item_ids:
                await self._apply_stock(
                    location_id=sale_location_id,
                    item_id=item.catalog_item_id,
                    lot_code="",
                    quantity_delta=-item.quantity,
                    unit_cost=Decimal("0"),
                    movement_type="sale",
                    idempotency_key=f"sale:{order.id}:{item.id}",
                    brand_id=order.brand_id,
                    branch_id=order.branch_id,
                    order_id=order.id,
                )
            receipt_lines.append(
                {"sku": item.sku, "name": item.name, "quantity": str(item.quantity), "line_total": str(item.line_total)}
            )
        self.db.add(
            TakeawayPayment(
                order_id=order.id,
                method=data.payment.method,
                amount=money(order.total_amount),
                reference=data.payment.reference,
                idempotency_key=data.payment.idempotency_key,
            )
        )
        if data.payment.method == "credit":
            await self._apply_credit(
                brand_id=order.brand_id,
                branch_id=order.branch_id,
                entry_type="charge",
                amount=money(order.total_amount),
                reference_type="takeaway_order",
                reference_id=order.id,
                idempotency_key=f"credit:{data.payment.idempotency_key}",
            )
        receipt_number = order.order_number.replace("TW-", "TR-", 1)
        self.db.add(
            TakeawayReceipt(
                order_id=order.id,
                company_id=order.company_id,
                branch_id=order.branch_id,
                receipt_number=receipt_number,
                payload={
                    "order_number": order.order_number,
                    "queue_number": order.queue_number,
                    "items": receipt_lines,
                    "subtotal": str(order.subtotal),
                    "discount_amount": str(order.discount_amount),
                    "tax_amount": str(order.tax_amount),
                    "total_amount": str(order.total_amount),
                    "payment_method": data.payment.method,
                },
            )
        )
        order.status = "paid"
        order.fulfillment_status = "queued"
        order.paid_at = datetime.now(timezone.utc)
        self._outbox(
            event_type="takeaway.sale.paid.v1",
            aggregate_type="order",
            aggregate_id=order.id,
            idempotency_key=f"sale:{order.id}:captured",
            payload={
                "order_number": order.order_number,
                "business_date": str(order.business_date),
                "queue_number": order.queue_number,
                "total_amount": str(order.total_amount),
                "payment_method": data.payment.method,
            },
            brand_id=order.brand_id,
            branch_id=order.branch_id,
        )
        await self.db.commit()
        await self.db.refresh(order)
        return order, False

    async def create_sale(self, data: TakeawaySaleCreate) -> tuple[TakeawayOrder, str | None, bool]:
        await self._validate_context(brand_id=data.brand_id, branch_id=data.branch_id)
        existing = await self.db.scalar(
            select(TakeawayOrder).where(
                TakeawayOrder.branch_id == data.branch_id,
                TakeawayOrder.idempotency_key == data.idempotency_key,
            )
        )
        if existing is not None:
            return existing, None, True
        shift = await self.db.scalar(
            select(TakeawayShift).where(
                TakeawayShift.id == data.shift_id,
                TakeawayShift.company_id == self.current.company_id,
                TakeawayShift.brand_id == data.brand_id,
                TakeawayShift.branch_id == data.branch_id,
                TakeawayShift.status == "open",
            )
        )
        if shift is None:
            raise HTTPException(status_code=409, detail="An open Takeaway shift is required")
        item_ids = [line.catalog_item_id for line in data.items]
        catalog = {
            item.id: item
            for item in await self.db.scalars(
                select(TakeawayCatalogItem).where(
                    TakeawayCatalogItem.id.in_(item_ids),
                    TakeawayCatalogItem.company_id == self.current.company_id,
                    TakeawayCatalogItem.brand_id == data.brand_id,
                    TakeawayCatalogItem.is_active.is_(True),
                )
            )
        }
        if len(catalog) != len(set(item_ids)):
            raise HTTPException(status_code=404, detail="One or more Takeaway items were not found")
        availability = {
            row.catalog_item_id: row
            for row in await self.db.scalars(
                select(TakeawayBranchCatalogItem).where(
                    TakeawayBranchCatalogItem.branch_id == data.branch_id,
                    TakeawayBranchCatalogItem.catalog_item_id.in_(item_ids),
                )
            )
        }
        if any(not availability[item_id].is_available for item_id in availability):
            raise HTTPException(status_code=409, detail="One or more Takeaway items are unavailable")
        subtotal = Decimal("0")
        prepared: list[tuple[object, TakeawayCatalogItem, Decimal, Decimal, Decimal]] = []
        for line in data.items:
            item = catalog[line.catalog_item_id]
            override = availability.get(item.id)
            unit_price = money(override.price_override if override and override.price_override is not None else item.price)
            line_subtotal = money(unit_price * line.quantity)
            line_tax = money(line_subtotal * Decimal(item.tax_rate) / Decimal("100"))
            subtotal += line_subtotal
            prepared.append((line, item, unit_price, line_subtotal, line_tax))
        subtotal = money(subtotal)
        discount = money(data.discount_amount)
        if discount > subtotal:
            raise HTTPException(status_code=422, detail="Discount cannot exceed subtotal")
        tax = money(sum((entry[4] for entry in prepared), Decimal("0")))
        total = money(subtotal - discount + tax)
        if money(data.payment.amount) != total:
            raise HTTPException(status_code=422, detail="Payment amount must equal Takeaway order total")

        await self.db.execute(
            text("SELECT pg_advisory_xact_lock(hashtext(:key))"),
            {"key": f"takeaway-queue:{data.branch_id}:{shift.business_date}"},
        )
        queue_number = int(
            await self.db.scalar(
                select(func.coalesce(func.max(TakeawayOrder.queue_number), 0)).where(
                    TakeawayOrder.branch_id == data.branch_id,
                    TakeawayOrder.business_date == shift.business_date,
                )
            )
            or 0
        ) + 1
        branch_key = str(data.branch_id).replace("-", "")[:6].upper()
        order_number = f"TW-{shift.business_date:%Y%m%d}-{branch_key}-{queue_number:04d}"
        order = TakeawayOrder(
            company_id=self.current.company_id,
            brand_id=data.brand_id,
            branch_id=data.branch_id,
            shift_id=shift.id,
            order_number=order_number,
            business_date=shift.business_date,
            queue_number=queue_number,
            channel=data.channel,
            status="paid",
            fulfillment_status="queued",
            subtotal=subtotal,
            discount_amount=discount,
            tax_amount=tax,
            total_amount=total,
            customer_name=data.customer_name,
            customer_phone=data.customer_phone,
            note=data.note,
            idempotency_key=data.idempotency_key,
            offline_device_id=data.offline_device_id,
            offline_sequence=data.offline_sequence,
            paid_at=datetime.now(timezone.utc),
        )
        self.db.add(order)
        await self.db.flush()
        store_location_id = await self.db.scalar(
            select(TakeawayStockLocation.id)
            .where(
                TakeawayStockLocation.company_id == self.current.company_id,
                TakeawayStockLocation.branch_id == data.branch_id,
                TakeawayStockLocation.location_type == "store",
                TakeawayStockLocation.is_active.is_(True),
            )
            .order_by(TakeawayStockLocation.created_at, TakeawayStockLocation.id)
            .limit(1)
        )
        # Existing pre-Phase-6 fixtures use the branch id as a virtual store
        # location. Keep that fallback while preferring the explicit location
        # created by setup/import for all new tenants.
        sale_location_id = store_location_id or data.branch_id
        receipt_lines: list[dict[str, object]] = []
        for line, item, unit_price, line_subtotal, line_tax in prepared:
            order_item = TakeawayOrderItem(
                order_id=order.id,
                catalog_item_id=item.id,
                sku=item.sku,
                name=item.name,
                quantity=line.quantity,
                unit_price=unit_price,
                discount_amount=Decimal("0"),
                tax_amount=line_tax,
                line_total=line_subtotal + line_tax,
                kitchen_station=item.kitchen_station,
                note=line.note,
            )
            self.db.add(order_item)
            await self.db.flush()
            self.db.add(
                TakeawayKitchenTicket(
                    company_id=self.current.company_id,
                    brand_id=data.brand_id,
                    branch_id=data.branch_id,
                    order_id=order.id,
                    order_item_id=order_item.id,
                    queue_number=queue_number,
                    station=item.kitchen_station or "default",
                    item_name=item.name,
                    quantity=line.quantity,
                )
            )
            if item.track_stock:
                await self._apply_stock(
                    location_id=sale_location_id,
                    item_id=item.id,
                    lot_code="",
                    quantity_delta=-line.quantity,
                    unit_cost=Decimal("0"),
                    movement_type="sale",
                    idempotency_key=f"sale:{order.id}:{order_item.id}",
                    brand_id=data.brand_id,
                    branch_id=data.branch_id,
                    order_id=order.id,
                )
            receipt_lines.append(
                {"sku": item.sku, "name": item.name, "quantity": str(line.quantity), "line_total": str(line_subtotal + line_tax)}
            )
        payment = TakeawayPayment(
            order_id=order.id,
            method=data.payment.method,
            amount=total,
            reference=data.payment.reference,
            idempotency_key=data.payment.idempotency_key,
        )
        self.db.add(payment)
        if data.payment.method == "credit":
            await self._apply_credit(
                brand_id=data.brand_id,
                branch_id=data.branch_id,
                entry_type="charge",
                amount=total,
                reference_type="takeaway_order",
                reference_id=order.id,
                idempotency_key=f"credit:{data.payment.idempotency_key}",
            )
        receipt_number = f"TR-{shift.business_date:%Y%m%d}-{branch_key}-{queue_number:04d}"
        self.db.add(
            TakeawayReceipt(
                order_id=order.id,
                company_id=self.current.company_id,
                branch_id=data.branch_id,
                receipt_number=receipt_number,
                payload={
                    "order_number": order_number,
                    "queue_number": queue_number,
                    "items": receipt_lines,
                    "subtotal": str(subtotal),
                    "discount_amount": str(discount),
                    "tax_amount": str(tax),
                    "total_amount": str(total),
                    "payment_method": data.payment.method,
                },
            )
        )
        pickup_token = secrets.token_urlsafe(24)
        self.db.add(
            TakeawayPickupToken(
                order_id=order.id,
                token_hash=hashlib.sha256(pickup_token.encode()).hexdigest(),
                expires_at=datetime.combine(
                    shift.business_date,
                    time(23, 59, 59),
                    tzinfo=timezone.utc,
                ),
            )
        )
        self._outbox(
            event_type="takeaway.sale.paid.v1",
            aggregate_type="order",
            aggregate_id=order.id,
            idempotency_key=f"sale:{data.idempotency_key}",
            payload={
                "order_number": order_number,
                "business_date": str(shift.business_date),
                "queue_number": queue_number,
                "total_amount": str(total),
                "payment_method": data.payment.method,
            },
            brand_id=data.brand_id,
            branch_id=data.branch_id,
        )
        await self.db.commit()
        await self.db.refresh(order)
        return order, pickup_token, False

    async def list_orders(
        self,
        *,
        branch_id: uuid.UUID | None = None,
        fulfillment_status: str | None = None,
        limit: int = 100,
    ) -> list[TakeawayOrder]:
        statement = select(TakeawayOrder).where(TakeawayOrder.company_id == self.current.company_id)
        if self.current.brand_id is not None:
            statement = statement.where(TakeawayOrder.brand_id == self.current.brand_id)
        if self.current.branch_id is not None:
            branch_id = self.current.branch_id
        if branch_id is not None:
            statement = statement.where(TakeawayOrder.branch_id == branch_id)
        if fulfillment_status is not None:
            statement = statement.where(TakeawayOrder.fulfillment_status == fulfillment_status)
        return list(await self.db.scalars(statement.order_by(TakeawayOrder.created_at.desc()).limit(limit)))

    async def get_receipt(self, order_id: uuid.UUID) -> TakeawayReceipt:
        row = await self.db.scalar(
            select(TakeawayReceipt)
            .join(TakeawayOrder, TakeawayOrder.id == TakeawayReceipt.order_id)
            .where(
                TakeawayReceipt.order_id == order_id,
                TakeawayReceipt.company_id == self.current.company_id,
            )
        )
        if row is None:
            raise HTTPException(status_code=404, detail="Takeaway receipt not found")
        order = await self.db.get(TakeawayOrder, order_id)
        if order is None:
            raise HTTPException(status_code=404, detail="Takeaway order not found")
        assert_takeaway_scope(self.current, brand_id=order.brand_id, branch_id=order.branch_id)
        return row

    async def mark_receipt_printed(
        self,
        order_id: uuid.UUID,
        data: TakeawayReceiptPrintCreate,
    ) -> tuple[TakeawayReceipt, bool]:
        outbox_key = f"receipt-print:{order_id}:{data.idempotency_key}"
        existing = await self.db.scalar(
            select(TakeawayOperationalOutbox.id).where(
                TakeawayOperationalOutbox.idempotency_key == outbox_key
            )
        )
        if existing is not None:
            return await self.get_receipt(order_id), True
        receipt = await self.db.scalar(
            select(TakeawayReceipt)
            .where(
                TakeawayReceipt.order_id == order_id,
                TakeawayReceipt.company_id == self.current.company_id,
            )
            .with_for_update()
        )
        if receipt is None:
            raise HTTPException(status_code=404, detail="Takeaway receipt not found")
        order = await self.db.get(TakeawayOrder, order_id)
        if order is None:
            raise HTTPException(status_code=404, detail="Takeaway order not found")
        assert_takeaway_scope(self.current, brand_id=order.brand_id, branch_id=order.branch_id)
        receipt.print_count += 1
        receipt.last_printed_at = datetime.now(timezone.utc)
        receipt.last_printed_copy = data.copy_type
        self._outbox(
            event_type="takeaway.receipt.printed.v1",
            aggregate_type="receipt",
            aggregate_id=receipt.id,
            idempotency_key=outbox_key,
            payload={
                "order_id": str(order.id),
                "receipt_number": receipt.receipt_number,
                "copy_type": data.copy_type,
                "print_count": receipt.print_count,
            },
            brand_id=order.brand_id,
            branch_id=order.branch_id,
        )
        await self.db.commit()
        await self.db.refresh(receipt)
        return receipt, False

    async def update_kitchen_ticket(self, ticket_id: uuid.UUID, next_status: str) -> TakeawayKitchenTicket:
        ticket = await self.db.scalar(
            select(TakeawayKitchenTicket)
            .where(
                TakeawayKitchenTicket.id == ticket_id,
                TakeawayKitchenTicket.company_id == self.current.company_id,
            )
            .with_for_update()
        )
        if ticket is None:
            raise HTTPException(status_code=404, detail="Takeaway kitchen ticket not found")
        assert_takeaway_scope(self.current, brand_id=ticket.brand_id, branch_id=ticket.branch_id)
        transitions = {"queued": "preparing", "preparing": "ready"}
        if transitions.get(ticket.status) != next_status:
            raise HTTPException(status_code=409, detail="Invalid Takeaway kitchen status transition")
        ticket.status = next_status
        if next_status == "ready":
            ticket.ready_at = datetime.now(timezone.utc)
            remaining = await self.db.scalar(
                select(func.count()).select_from(TakeawayKitchenTicket).where(
                    TakeawayKitchenTicket.order_id == ticket.order_id,
                    TakeawayKitchenTicket.id != ticket.id,
                    TakeawayKitchenTicket.status != "ready",
                )
            )
            if int(remaining or 0) == 0:
                order = await self.db.get(TakeawayOrder, ticket.order_id)
                if order is not None:
                    order.fulfillment_status = "ready"
                    self._outbox(
                        event_type="takeaway.order.ready.v1",
                        aggregate_type="order",
                        aggregate_id=order.id,
                        idempotency_key=f"order:{order.id}:ready",
                        payload={"order_number": order.order_number, "queue_number": order.queue_number},
                        brand_id=order.brand_id,
                        branch_id=order.branch_id,
                    )
        await self.db.commit()
        await self.db.refresh(ticket)
        return ticket

    async def mark_picked_up(self, order_id: uuid.UUID) -> TakeawayOrder:
        order = await self.db.scalar(
            select(TakeawayOrder)
            .where(TakeawayOrder.id == order_id, TakeawayOrder.company_id == self.current.company_id)
            .with_for_update()
        )
        if order is None:
            raise HTTPException(status_code=404, detail="Takeaway order not found")
        assert_takeaway_scope(self.current, brand_id=order.brand_id, branch_id=order.branch_id)
        if order.fulfillment_status != "ready":
            raise HTTPException(status_code=409, detail="Only a ready Takeaway order can be picked up")
        order.fulfillment_status = "picked_up"
        order.picked_up_at = datetime.now(timezone.utc)
        self._outbox(
            event_type="takeaway.order.picked_up.v1",
            aggregate_type="order",
            aggregate_id=order.id,
            idempotency_key=f"order:{order.id}:picked-up",
            payload={"order_number": order.order_number, "queue_number": order.queue_number},
            brand_id=order.brand_id,
            branch_id=order.branch_id,
        )
        await self.db.commit()
        await self.db.refresh(order)
        return order

    async def refund_order(self, order_id: uuid.UUID, idempotency_key: str, reason: str) -> TakeawayOrder:
        order = await self.db.scalar(
            select(TakeawayOrder)
            .where(TakeawayOrder.id == order_id, TakeawayOrder.company_id == self.current.company_id)
            .with_for_update()
        )
        if order is None:
            raise HTTPException(status_code=404, detail="Takeaway order not found")
        assert_takeaway_scope(self.current, brand_id=order.brand_id, branch_id=order.branch_id)
        if order.status == "refunded":
            return order
        if order.status != "paid":
            raise HTTPException(status_code=409, detail="Only a paid Takeaway order can be refunded")
        sale_movements = list(
            await self.db.scalars(
                select(TakeawayStockMovement).where(
                    TakeawayStockMovement.order_id == order.id,
                    TakeawayStockMovement.company_id == self.current.company_id,
                    TakeawayStockMovement.movement_type == "sale",
                )
            )
        )
        for movement in sale_movements:
            await self._apply_stock(
                location_id=movement.location_id,
                item_id=movement.item_id,
                lot_code=movement.lot_code,
                quantity_delta=-movement.quantity_delta,
                unit_cost=movement.unit_cost,
                movement_type="refund",
                idempotency_key=f"refund:{idempotency_key}:{movement.id}",
                brand_id=order.brand_id,
                branch_id=order.branch_id,
                order_id=order.id,
            )
        payments = list(await self.db.scalars(select(TakeawayPayment).where(TakeawayPayment.order_id == order.id)))
        for payment in payments:
            payment.status = "refunded"
            if payment.method == "credit":
                await self._apply_credit(
                    brand_id=order.brand_id,
                    branch_id=order.branch_id,
                    entry_type="payment",
                    amount=payment.amount,
                    reference_type="takeaway_refund",
                    reference_id=order.id,
                    idempotency_key=f"credit-refund:{idempotency_key}:{payment.id}",
                )
        order.status = "refunded"
        order.fulfillment_status = "cancelled"
        self._outbox(
            event_type="takeaway.sale.refunded.v1",
            aggregate_type="order",
            aggregate_id=order.id,
            idempotency_key=f"refund:{idempotency_key}",
            payload={"order_number": order.order_number, "amount": str(order.total_amount), "reason": reason},
            brand_id=order.brand_id,
            branch_id=order.branch_id,
        )
        await self.db.commit()
        await self.db.refresh(order)
        return order

    async def create_central_round(self, brand_id: uuid.UUID, business_date: date, round_no: int) -> TakeawayCentralOrderRound:
        await self._validate_context(brand_id=brand_id)
        await self.db.execute(
            text("SELECT pg_advisory_xact_lock(hashtext(:key))"),
            {"key": f"takeaway-central-round:{brand_id}:{business_date}:{round_no}"},
        )
        existing = await self.db.scalar(
            select(TakeawayCentralOrderRound).where(
                TakeawayCentralOrderRound.company_id == self.current.company_id,
                TakeawayCentralOrderRound.brand_id == brand_id,
                TakeawayCentralOrderRound.business_date == business_date,
                TakeawayCentralOrderRound.round_no == round_no,
            )
        )
        if existing is not None:
            return existing
        row = TakeawayCentralOrderRound(
            company_id=self.current.company_id,
            brand_id=brand_id,
            business_date=business_date,
            round_no=round_no,
        )
        self.db.add(row)
        await self.db.commit()
        await self.db.refresh(row)
        return row

    async def create_central_order(self, data: TakeawayCentralOrderCreate) -> TakeawayCentralOrder:
        await self._validate_context(brand_id=data.brand_id, branch_id=data.branch_id)
        await self.db.execute(
            text("SELECT pg_advisory_xact_lock(hashtext(:key))"),
            {"key": f"takeaway-central-order-idempotency:{data.branch_id}:{data.idempotency_key}"},
        )
        existing = await self.db.scalar(
            select(TakeawayCentralOrder).where(
                TakeawayCentralOrder.branch_id == data.branch_id,
                TakeawayCentralOrder.idempotency_key == data.idempotency_key,
            )
        )
        if existing is not None:
            return existing
        round_row = await self.db.scalar(
            select(TakeawayCentralOrderRound).where(
                TakeawayCentralOrderRound.id == data.round_id,
                TakeawayCentralOrderRound.company_id == self.current.company_id,
                TakeawayCentralOrderRound.brand_id == data.brand_id,
                TakeawayCentralOrderRound.status == "open",
            )
        )
        if round_row is None:
            raise HTTPException(status_code=409, detail="Open Takeaway central-order round not found")
        await self.db.execute(
            text("SELECT pg_advisory_xact_lock(hashtext(:key))"),
            {"key": f"takeaway-central-order:{data.branch_id}:{data.round_id}"},
        )
        count = int(
            await self.db.scalar(
                select(func.count()).select_from(TakeawayCentralOrder).where(
                    TakeawayCentralOrder.branch_id == data.branch_id,
                    TakeawayCentralOrder.round_id == data.round_id,
                )
            )
            or 0
        ) + 1
        order = TakeawayCentralOrder(
            company_id=self.current.company_id,
            brand_id=data.brand_id,
            branch_id=data.branch_id,
            round_id=data.round_id,
            order_number=f"CO-{round_row.business_date:%Y%m%d}-{str(data.branch_id)[:6]}-{count:03d}",
            order_type=data.order_type,
            requested_delivery_date=data.requested_delivery_date,
            submitted_by=self.current.user_id,
            idempotency_key=data.idempotency_key,
            note=data.note,
        )
        self.db.add(order)
        await self.db.flush()
        for line in data.items:
            self.db.add(TakeawayCentralOrderItem(central_order_id=order.id, **line.model_dump()))
        self._outbox(
            event_type="takeaway.central_order.submitted.v1",
            aggregate_type="central_order",
            aggregate_id=order.id,
            idempotency_key=f"central-order:{order.id}:submitted",
            payload={"order_number": order.order_number, "order_type": order.order_type},
            brand_id=order.brand_id,
            branch_id=order.branch_id,
        )
        await self.db.commit()
        await self.db.refresh(order)
        return order

    async def create_store_central_order(
        self,
        data: TakeawayStoreCentralOrderCreate,
    ) -> TakeawayCentralOrder:
        if self.current.brand_id is None or self.current.branch_id is None:
            raise HTTPException(status_code=400, detail="Takeaway Branch context required")
        round_row = await self.create_central_round(
            self.current.brand_id,
            data.business_date,
            data.round_no,
        )
        if round_row.status != "open":
            raise HTTPException(status_code=409, detail="Takeaway central-order round is closed")
        return await self.create_central_order(
            TakeawayCentralOrderCreate(
                brand_id=self.current.brand_id,
                branch_id=self.current.branch_id,
                round_id=round_row.id,
                **data.model_dump(exclude={"business_date", "round_no"}),
            )
        )

    async def receive_store_central_order(self, order_id: uuid.UUID) -> TakeawayCentralOrder:
        row = await self.db.scalar(
            select(TakeawayCentralOrder)
            .where(
                TakeawayCentralOrder.id == order_id,
                TakeawayCentralOrder.company_id == self.current.company_id,
            )
            .with_for_update()
        )
        if row is None:
            raise HTTPException(status_code=404, detail="Takeaway central order not found")
        assert_takeaway_scope(
            self.current,
            brand_id=row.brand_id,
            branch_id=row.branch_id,
            require_branch=True,
        )
        if row.status == "received":
            return row
        if row.status != "shipped":
            raise HTTPException(status_code=409, detail="Only a shipped Takeaway central order can be received")
        location_id = await self.db.scalar(
            select(TakeawayStockLocation.id)
            .where(
                TakeawayStockLocation.company_id == self.current.company_id,
                TakeawayStockLocation.branch_id == row.branch_id,
                TakeawayStockLocation.location_type == "store",
                TakeawayStockLocation.is_active.is_(True),
            )
            .order_by(TakeawayStockLocation.created_at, TakeawayStockLocation.id)
            .limit(1)
        )
        items = list(
            await self.db.scalars(
                select(TakeawayCentralOrderItem).where(
                    TakeawayCentralOrderItem.central_order_id == row.id
                )
            )
        )
        for item in items:
            if item.catalog_item_id is None:
                continue
            await self._apply_stock(
                location_id=location_id or row.branch_id,
                item_id=item.catalog_item_id,
                lot_code="",
                quantity_delta=item.quantity,
                unit_cost=Decimal("0"),
                movement_type="central_order_receive",
                idempotency_key=f"central-order:{row.id}:{item.id}:receive",
                brand_id=row.brand_id,
                branch_id=row.branch_id,
                note=f"รับสินค้า {row.order_number}",
            )
        row.status = "received"
        self._outbox(
            event_type="takeaway.central_order.received.v1",
            aggregate_type="central_order",
            aggregate_id=row.id,
            idempotency_key=f"central-order:{row.id}:received",
            payload={"order_number": row.order_number, "status": "received"},
            brand_id=row.brand_id,
            branch_id=row.branch_id,
        )
        await self.db.commit()
        await self.db.refresh(row)
        return row

    async def update_central_order_status(self, order_id: uuid.UUID, next_status: str) -> TakeawayCentralOrder:
        row = await self.db.scalar(
            select(TakeawayCentralOrder)
            .where(
                TakeawayCentralOrder.id == order_id,
                TakeawayCentralOrder.company_id == self.current.company_id,
            )
            .with_for_update()
        )
        if row is None:
            raise HTTPException(status_code=404, detail="Takeaway central order not found")
        assert_takeaway_scope(self.current, brand_id=row.brand_id)
        transitions = {
            "submitted": {"approved", "rejected"},
            "approved": {"in_production"},
            "in_production": {"packed"},
            "packed": {"shipped"},
        }
        if next_status not in transitions.get(row.status, set()):
            raise HTTPException(status_code=409, detail="Invalid Takeaway central-order transition")
        row.status = next_status
        self._outbox(
            event_type=f"takeaway.central_order.{next_status}.v1",
            aggregate_type="central_order",
            aggregate_id=row.id,
            idempotency_key=f"central-order:{row.id}:{next_status}",
            payload={"order_number": row.order_number, "status": next_status},
            brand_id=row.brand_id,
            branch_id=row.branch_id,
        )
        await self.db.commit()
        await self.db.refresh(row)
        return row

    async def create_production_batch(self, data: TakeawayProductionBatchCreate) -> TakeawayProductionBatch:
        await self._validate_context(brand_id=data.brand_id)
        sequence = int(
            await self.db.scalar(
                select(func.count()).select_from(TakeawayProductionBatch).where(
                    TakeawayProductionBatch.company_id == self.current.company_id
                )
            )
            or 0
        ) + 1
        batch = TakeawayProductionBatch(
            company_id=self.current.company_id,
            brand_id=data.brand_id,
            location_id=data.location_id,
            batch_number=f"PB-{datetime.now(timezone.utc):%Y%m%d}-{sequence:04d}",
            planned_at=(
                datetime.combine(data.planned_at, time.min, tzinfo=timezone.utc)
                if data.planned_at
                else datetime.now(timezone.utc)
            ),
            created_by=self.current.user_id,
        )
        self.db.add(batch)
        await self.db.flush()
        for line in data.lines:
            self.db.add(TakeawayProductionLine(batch_id=batch.id, **line.model_dump()))
        await self.db.commit()
        await self.db.refresh(batch)
        return batch

    async def complete_production_batch(
        self,
        batch_id: uuid.UUID,
        data: TakeawayProductionComplete,
    ) -> TakeawayProductionBatch:
        batch = await self.db.scalar(
            select(TakeawayProductionBatch)
            .where(
                TakeawayProductionBatch.id == batch_id,
                TakeawayProductionBatch.company_id == self.current.company_id,
            )
            .with_for_update()
        )
        if batch is None:
            raise HTTPException(status_code=404, detail="Takeaway production batch not found")
        assert_takeaway_scope(self.current, brand_id=batch.brand_id)
        if batch.status == "completed":
            return batch
        if batch.status not in {"planned", "in_progress"}:
            raise HTTPException(status_code=409, detail="Takeaway production batch cannot be completed")
        lines = {
            line.id: line
            for line in await self.db.scalars(
                select(TakeawayProductionLine).where(TakeawayProductionLine.batch_id == batch.id)
            )
        }
        if set(lines) != {line.line_id for line in data.lines}:
            raise HTTPException(status_code=422, detail="Actual production lines must match the batch")
        for actual in data.lines:
            line = lines[actual.line_id]
            line.actual_qty = actual.actual_qty
            await self._apply_stock(
                location_id=batch.location_id,
                item_id=line.item_id,
                lot_code="",
                quantity_delta=(-actual.actual_qty if line.line_type == "input" else actual.actual_qty),
                unit_cost=Decimal("0"),
                movement_type="production_consume" if line.line_type == "input" else "production_output",
                idempotency_key=f"production:{data.idempotency_key}:{line.id}",
                brand_id=batch.brand_id,
                production_batch_id=batch.id,
            )
        batch.status = "completed"
        batch.completed_at = datetime.now(timezone.utc)
        self._outbox(
            event_type="takeaway.production.completed.v1",
            aggregate_type="production_batch",
            aggregate_id=batch.id,
            idempotency_key=f"production:{data.idempotency_key}:completed",
            payload={"batch_number": batch.batch_number, "location_id": str(batch.location_id)},
            brand_id=batch.brand_id,
        )
        await self.db.commit()
        await self.db.refresh(batch)
        return batch

    async def create_transfer(self, data: TakeawayTransferCreate) -> TakeawayTransfer:
        if data.brand_id is not None:
            await self._validate_context(brand_id=data.brand_id)
        sequence = int(
            await self.db.scalar(
                select(func.count()).select_from(TakeawayTransfer).where(
                    TakeawayTransfer.company_id == self.current.company_id
                )
            )
            or 0
        ) + 1
        row = TakeawayTransfer(
            company_id=self.current.company_id,
            brand_id=data.brand_id,
            transfer_number=f"TT-{datetime.now(timezone.utc):%Y%m%d}-{sequence:04d}",
            from_location_id=data.from_location_id,
            to_location_id=data.to_location_id,
            requested_by=self.current.user_id,
        )
        self.db.add(row)
        await self.db.flush()
        for line in data.items:
            self.db.add(TakeawayTransferItem(transfer_id=row.id, **line.model_dump()))
        await self.db.commit()
        await self.db.refresh(row)
        return row

    async def update_transfer(
        self,
        transfer_id: uuid.UUID,
        data: TakeawayTransferStatusUpdate,
    ) -> TakeawayTransfer:
        row = await self.db.scalar(
            select(TakeawayTransfer)
            .where(
                TakeawayTransfer.id == transfer_id,
                TakeawayTransfer.company_id == self.current.company_id,
            )
            .with_for_update()
        )
        if row is None:
            raise HTTPException(status_code=404, detail="Takeaway transfer not found")
        if row.brand_id is not None:
            assert_takeaway_scope(self.current, brand_id=row.brand_id)
        transitions = {"draft": {"shipped", "cancelled"}, "shipped": {"received"}}
        if data.status not in transitions.get(row.status, set()):
            raise HTTPException(status_code=409, detail="Invalid Takeaway transfer transition")
        items = list(await self.db.scalars(select(TakeawayTransferItem).where(TakeawayTransferItem.transfer_id == row.id)))
        if data.status == "shipped":
            for item in items:
                item.shipped_qty = item.requested_qty
                await self._apply_stock(
                    location_id=row.from_location_id,
                    item_id=item.item_id,
                    lot_code="",
                    quantity_delta=-item.requested_qty,
                    unit_cost=Decimal("0"),
                    movement_type="transfer_out",
                    idempotency_key=f"transfer:{data.idempotency_key}:{item.id}:out",
                    brand_id=row.brand_id,
                    transfer_id=row.id,
                )
            row.shipped_at = datetime.now(timezone.utc)
        elif data.status == "received":
            for item in items:
                received_qty = item.shipped_qty or item.requested_qty
                item.received_qty = received_qty
                await self._apply_stock(
                    location_id=row.to_location_id,
                    item_id=item.item_id,
                    lot_code="",
                    quantity_delta=received_qty,
                    unit_cost=Decimal("0"),
                    movement_type="transfer_in",
                    idempotency_key=f"transfer:{data.idempotency_key}:{item.id}:in",
                    brand_id=row.brand_id,
                    transfer_id=row.id,
                )
            row.received_at = datetime.now(timezone.utc)
        row.status = data.status
        self._outbox(
            event_type=f"takeaway.transfer.{data.status}.v1",
            aggregate_type="transfer",
            aggregate_id=row.id,
            idempotency_key=f"transfer:{data.idempotency_key}:{data.status}",
            payload={"transfer_number": row.transfer_number, "status": data.status},
            brand_id=row.brand_id,
        )
        await self.db.commit()
        await self.db.refresh(row)
        return row

    async def set_credit_limit(self, data: TakeawayCreditLimitUpdate) -> TakeawayCreditAccount:
        await self._validate_context(brand_id=data.brand_id, branch_id=data.branch_id)
        row_id = (
            await self.db.execute(
                insert(TakeawayCreditAccount)
                .values(
                    id=uuid.uuid4(),
                    company_id=self.current.company_id,
                    brand_id=data.brand_id,
                    branch_id=data.branch_id,
                    credit_limit=data.credit_limit,
                    balance=Decimal("0"),
                )
                .on_conflict_do_update(
                    constraint="uq_takeaway_credit_account",
                    set_={"credit_limit": data.credit_limit},
                )
                .returning(TakeawayCreditAccount.id)
            )
        ).scalar_one()
        await self.db.commit()
        return await self.db.get(TakeawayCreditAccount, row_id)  # type: ignore[return-value]

    async def _apply_credit(
        self,
        *,
        brand_id: uuid.UUID,
        branch_id: uuid.UUID,
        entry_type: str,
        amount: Decimal,
        reference_type: str,
        reference_id: uuid.UUID,
        idempotency_key: str,
    ) -> TakeawayCreditAccount:
        existing = await self.db.scalar(
            select(TakeawayCreditEntry).where(TakeawayCreditEntry.idempotency_key == idempotency_key)
        )
        account = await self.db.scalar(
            select(TakeawayCreditAccount)
            .where(
                TakeawayCreditAccount.company_id == self.current.company_id,
                TakeawayCreditAccount.brand_id == brand_id,
                TakeawayCreditAccount.branch_id == branch_id,
                TakeawayCreditAccount.status == "active",
            )
            .with_for_update()
        )
        if account is None:
            raise HTTPException(status_code=409, detail="Takeaway credit account is not active")
        if existing is not None:
            return account
        delta = amount if entry_type in {"charge", "adjustment"} else -amount
        next_balance = Decimal(account.balance) + delta
        if next_balance < 0 or next_balance > Decimal(account.credit_limit):
            raise HTTPException(status_code=409, detail="Takeaway credit limit would be exceeded")
        account.balance = money(next_balance)
        self.db.add(
            TakeawayCreditEntry(
                account_id=account.id,
                entry_type=entry_type,
                amount=money(amount),
                reference_type=reference_type,
                reference_id=reference_id,
                idempotency_key=idempotency_key,
            )
        )
        return account

    async def create_credit_entry(self, account_id: uuid.UUID, data: TakeawayCreditEntryCreate) -> TakeawayCreditAccount:
        account = await self.db.scalar(
            select(TakeawayCreditAccount).where(
                TakeawayCreditAccount.id == account_id,
                TakeawayCreditAccount.company_id == self.current.company_id,
            )
        )
        if account is None:
            raise HTTPException(status_code=404, detail="Takeaway credit account not found")
        assert_takeaway_scope(self.current, brand_id=account.brand_id, branch_id=account.branch_id)
        result = await self._apply_credit(
            brand_id=account.brand_id,
            branch_id=account.branch_id,
            **data.model_dump(),
        )
        self._outbox(
            event_type="takeaway.credit.changed.v1",
            aggregate_type="credit_account",
            aggregate_id=result.id,
            idempotency_key=f"credit-outbox:{data.idempotency_key}",
            payload={"entry_type": data.entry_type, "amount": str(data.amount), "balance": str(result.balance)},
            brand_id=result.brand_id,
            branch_id=result.branch_id,
        )
        await self.db.commit()
        await self.db.refresh(result)
        return result

    async def sales_summary(
        self,
        *,
        date_from: date,
        date_to: date,
        brand_id: uuid.UUID | None = None,
        branch_id: uuid.UUID | None = None,
    ) -> dict[str, object]:
        if brand_id is not None:
            assert_takeaway_scope(self.current, brand_id=brand_id, branch_id=branch_id)
        statement = select(
            func.count(TakeawayOrder.id),
            func.coalesce(func.sum(TakeawayOrder.total_amount), 0),
            func.coalesce(func.sum(TakeawayOrder.tax_amount), 0),
            func.coalesce(func.sum(TakeawayOrder.discount_amount), 0),
        ).where(
            TakeawayOrder.company_id == self.current.company_id,
            TakeawayOrder.business_date >= date_from,
            TakeawayOrder.business_date <= date_to,
            TakeawayOrder.status == "paid",
        )
        if self.current.brand_id is not None:
            brand_id = self.current.brand_id
        if self.current.branch_id is not None:
            branch_id = self.current.branch_id
        if brand_id is not None:
            statement = statement.where(TakeawayOrder.brand_id == brand_id)
        if branch_id is not None:
            statement = statement.where(TakeawayOrder.branch_id == branch_id)
        row = (await self.db.execute(statement)).one()
        return {
            "date_from": str(date_from),
            "date_to": str(date_to),
            "order_count": int(row[0]),
            "gross_sales": str(money(row[1])),
            "tax_amount": str(money(row[2])),
            "discount_amount": str(money(row[3])),
        }

    async def list_shifts(self, *, limit: int = 100) -> list[TakeawayShift]:
        statement = select(TakeawayShift).where(
            TakeawayShift.company_id == self.current.company_id
        )
        if self.current.brand_id is not None:
            statement = statement.where(TakeawayShift.brand_id == self.current.brand_id)
        if self.current.branch_id is not None:
            statement = statement.where(TakeawayShift.branch_id == self.current.branch_id)
        return list(await self.db.scalars(statement.order_by(TakeawayShift.opened_at.desc()).limit(limit)))

    async def list_kitchen_tickets(
        self,
        *,
        branch_id: uuid.UUID | None = None,
        ticket_status: str | None = None,
        station: str | None = None,
        limit: int = 200,
    ) -> list[TakeawayKitchenTicket]:
        effective_branch = self.current.branch_id or branch_id
        statement = select(TakeawayKitchenTicket).where(
            TakeawayKitchenTicket.company_id == self.current.company_id
        )
        if self.current.brand_id is not None:
            statement = statement.where(TakeawayKitchenTicket.brand_id == self.current.brand_id)
        if effective_branch is not None:
            statement = statement.where(TakeawayKitchenTicket.branch_id == effective_branch)
        if ticket_status is not None:
            statement = statement.where(TakeawayKitchenTicket.status == ticket_status)
        if station is not None:
            statement = statement.where(TakeawayKitchenTicket.station == station)
        return list(
            await self.db.scalars(
                statement.order_by(TakeawayKitchenTicket.queue_number, TakeawayKitchenTicket.created_at).limit(limit)
            )
        )

    async def list_central_orders(
        self,
        *,
        brand_id: uuid.UUID | None = None,
        branch_id: uuid.UUID | None = None,
        limit: int = 200,
    ) -> list[dict[str, object]]:
        statement = select(TakeawayCentralOrder).where(
            TakeawayCentralOrder.company_id == self.current.company_id
        )
        effective_brand = self.current.brand_id or brand_id
        effective_branch = self.current.branch_id or branch_id
        if effective_brand is not None:
            statement = statement.where(TakeawayCentralOrder.brand_id == effective_brand)
        if effective_branch is not None:
            statement = statement.where(TakeawayCentralOrder.branch_id == effective_branch)
        orders = list(
            await self.db.scalars(
                statement.order_by(TakeawayCentralOrder.created_at.desc()).limit(limit)
            )
        )
        if not orders:
            return []
        item_rows = list(
            await self.db.scalars(
                select(TakeawayCentralOrderItem)
                .where(TakeawayCentralOrderItem.central_order_id.in_([row.id for row in orders]))
                .order_by(TakeawayCentralOrderItem.created_at, TakeawayCentralOrderItem.id)
            )
        )
        items_by_order: dict[uuid.UUID, list[TakeawayCentralOrderItem]] = {}
        for item in item_rows:
            items_by_order.setdefault(item.central_order_id, []).append(item)
        return [
            {
                "id": row.id,
                "company_id": row.company_id,
                "brand_id": row.brand_id,
                "branch_id": row.branch_id,
                "round_id": row.round_id,
                "order_number": row.order_number,
                "order_type": row.order_type,
                "status": row.status,
                "requested_delivery_date": row.requested_delivery_date,
                "submitted_by": row.submitted_by,
                "note": row.note,
                "created_at": row.created_at,
                "updated_at": row.updated_at,
                "items": items_by_order.get(row.id, []),
            }
            for row in orders
        ]

    async def list_production_batches(
        self, *, brand_id: uuid.UUID | None = None, limit: int = 200
    ) -> list[TakeawayProductionBatch]:
        statement = select(TakeawayProductionBatch).where(
            TakeawayProductionBatch.company_id == self.current.company_id
        )
        effective_brand = self.current.brand_id or brand_id
        if effective_brand is not None:
            statement = statement.where(TakeawayProductionBatch.brand_id == effective_brand)
        return list(await self.db.scalars(statement.order_by(TakeawayProductionBatch.created_at.desc()).limit(limit)))

    async def list_transfers(
        self, *, brand_id: uuid.UUID | None = None, limit: int = 200
    ) -> list[TakeawayTransfer]:
        statement = select(TakeawayTransfer).where(
            TakeawayTransfer.company_id == self.current.company_id
        )
        effective_brand = self.current.brand_id or brand_id
        if effective_brand is not None:
            statement = statement.where(TakeawayTransfer.brand_id == effective_brand)
        return list(await self.db.scalars(statement.order_by(TakeawayTransfer.created_at.desc()).limit(limit)))

    async def list_credit_accounts(
        self,
        *,
        brand_id: uuid.UUID | None = None,
        branch_id: uuid.UUID | None = None,
    ) -> list[TakeawayCreditAccount]:
        statement = select(TakeawayCreditAccount).where(
            TakeawayCreditAccount.company_id == self.current.company_id
        )
        effective_brand = self.current.brand_id or brand_id
        effective_branch = self.current.branch_id or branch_id
        if effective_brand is not None:
            statement = statement.where(TakeawayCreditAccount.brand_id == effective_brand)
        if effective_branch is not None:
            statement = statement.where(TakeawayCreditAccount.branch_id == effective_branch)
        return list(await self.db.scalars(statement.order_by(TakeawayCreditAccount.updated_at.desc())))

    async def list_erp_events(
        self, *, event_status: str = "pending", limit: int = 200
    ) -> list[TakeawayOperationalOutbox]:
        statement = select(TakeawayOperationalOutbox).where(
            TakeawayOperationalOutbox.company_id == self.current.company_id,
            TakeawayOperationalOutbox.status == event_status,
        )
        if self.current.brand_id is not None:
            statement = statement.where(
                (TakeawayOperationalOutbox.brand_id == self.current.brand_id)
                | (TakeawayOperationalOutbox.brand_id.is_(None))
            )
        return list(
            await self.db.scalars(
                statement.order_by(TakeawayOperationalOutbox.created_at).limit(limit)
            )
        )

    async def acknowledge_erp_event(
        self,
        event_id: uuid.UUID,
        data: TakeawayErpEventAcknowledge,
    ) -> tuple[TakeawayOperationalOutbox, bool]:
        row = await self.db.scalar(
            select(TakeawayOperationalOutbox)
            .where(
                TakeawayOperationalOutbox.id == event_id,
                TakeawayOperationalOutbox.company_id == self.current.company_id,
            )
            .with_for_update()
        )
        if row is None:
            raise HTTPException(status_code=404, detail="Takeaway ERP event not found")
        if self.current.brand_id is not None and row.brand_id not in {None, self.current.brand_id}:
            raise HTTPException(status_code=404, detail="Takeaway ERP event not found")
        if row.status == "processed":
            return row, True
        row.payload = {
            **row.payload,
            "erp_ack": {
                "erp_reference": data.erp_reference,
                "idempotency_key": data.idempotency_key,
            },
        }
        row.status = "processed"
        row.attempts += 1
        row.processed_at = datetime.now(timezone.utc)
        await self.db.commit()
        await self.db.refresh(row)
        return row, False

    async def erp_reconciliation(self) -> dict[str, object]:
        rows = list(
            (
                await self.db.execute(
                    select(
                        TakeawayOperationalOutbox.status,
                        func.count(TakeawayOperationalOutbox.id),
                    )
                    .where(TakeawayOperationalOutbox.company_id == self.current.company_id)
                    .group_by(TakeawayOperationalOutbox.status)
                )
            ).all()
        )
        counts = {str(status_value): int(count) for status_value, count in rows}
        return {
            "contract": "foodchainservice.takeaway-erp-event.v1",
            "pending": counts.get("pending", 0),
            "processed": counts.get("processed", 0),
            "failed": counts.get("failed", 0),
            "is_reconciled": counts.get("pending", 0) == 0 and counts.get("failed", 0) == 0,
        }
