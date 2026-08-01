from __future__ import annotations

from datetime import date, datetime, time, timezone
from decimal import Decimal
import uuid

from fastapi import HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.branch import Branch
from app.models.pos import CashierShift
from app.models.product import Product, ProductVariant, Unit
from app.models.restaurant import Brand, BrandBranch
from app.models.stock import StockBalance, StockLocation, StockMovement
from app.models.user import User
from app.schemas.stock import (
    AdjustmentRequest,
    ReceiveStockRequest,
    StockSummaryResponse,
    StockLocationCreate,
    StockLocationUpdate,
    TransferRequest,
)
from app.services.notification_service import NotificationService
from app.utils.webhook_dispatcher import trigger_event


MOVEMENT_TYPES = {
    "receive",
    "issue",
    "adjust",
    "transfer_in",
    "transfer_out",
    "sale",
    "sale_return",
    "purchase_return",
    "opening",
    "waste",
}


class StockService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_locations(
        self,
        company_id: uuid.UUID,
        branch_id: uuid.UUID | None = None,
        location_ids: tuple[uuid.UUID, ...] | None = None,
        include_inactive: bool = False,
    ) -> list[StockLocation]:
        statement = (
            select(StockLocation)
            .where(StockLocation.company_id == company_id, StockLocation.deleted_at.is_(None))
            .order_by(StockLocation.branch_id.asc(), StockLocation.code.asc())
        )
        if branch_id:
            statement = statement.where(StockLocation.branch_id == branch_id)
        if location_ids is not None:
            statement = statement.where(StockLocation.id.in_(location_ids))
        if not include_inactive:
            statement = statement.where(StockLocation.is_active.is_(True))
        rows = await self.db.scalars(statement)
        return rows.all()

    async def create_location(
        self, company_id: uuid.UUID, data: StockLocationCreate
    ) -> StockLocation:
        await self._get_branch(data.branch_id, company_id)
        exists = await self.db.scalar(
            select(StockLocation.id).where(
                StockLocation.branch_id == data.branch_id,
                func.lower(StockLocation.code) == data.code.lower(),
                StockLocation.deleted_at.is_(None),
            )
        )
        if exists:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Location code already exists in this branch",
            )
        location = StockLocation(company_id=company_id, **data.model_dump())
        self.db.add(location)
        await self.db.commit()
        await self.db.refresh(location)
        return location

    async def get_location(
        self,
        company_id: uuid.UUID,
        location_id: uuid.UUID,
    ) -> StockLocation:
        location = await self.db.scalar(
            select(StockLocation).where(
                StockLocation.id == location_id,
                StockLocation.company_id == company_id,
                StockLocation.deleted_at.is_(None),
            )
        )
        if location is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ไม่พบคลังสินค้า")
        return location

    async def update_location(
        self,
        company_id: uuid.UUID,
        location_id: uuid.UUID,
        data: StockLocationUpdate,
    ) -> StockLocation:
        location = await self.get_location(company_id, location_id)
        changes = data.model_dump(exclude_unset=True)

        requested_branch_id = changes.pop("branch_id", None)
        if requested_branch_id is not None and requested_branch_id != location.branch_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="ไม่สามารถย้ายคลังไปสาขาอื่นได้ กรุณาสร้างคลังใหม่ในสาขาปลายทาง",
            )

        requested_code = changes.get("code")
        if requested_code is not None and requested_code != location.code:
            exists = await self.db.scalar(
                select(StockLocation.id).where(
                    StockLocation.branch_id == location.branch_id,
                    func.lower(StockLocation.code) == requested_code.lower(),
                    StockLocation.id != location.id,
                    StockLocation.deleted_at.is_(None),
                )
            )
            if exists:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="รหัสคลังนี้มีอยู่แล้วในสาขา",
                )

        if changes.get("is_active") is False and location.is_active:
            await self._ensure_location_can_deactivate(company_id, location.id)

        for field, value in changes.items():
            setattr(location, field, value)
        await self.db.commit()
        await self.db.refresh(location)
        return location

    async def _ensure_location_can_deactivate(
        self,
        company_id: uuid.UUID,
        location_id: uuid.UUID,
    ) -> None:
        brand_reference = await self.db.scalar(
            select(Brand.id).where(
                Brand.company_id == company_id,
                Brand.is_active.is_(True),
                or_(
                    Brand.central_location_id == location_id,
                    Brand.central_ready_location_id == location_id,
                ),
            ).limit(1)
        )
        store_reference = await self.db.scalar(
            select(BrandBranch.id).where(
                BrandBranch.company_id == company_id,
                BrandBranch.is_active.is_(True),
                BrandBranch.store_location_id == location_id,
            ).limit(1)
        )
        if brand_reference or store_reference:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="คลังนี้ยังถูกตั้งเป็น RAW, READY หรือ STORE-STOCK ของแบรนด์",
            )

        nonzero_balance = await self.db.scalar(
            select(StockBalance.id).where(
                StockBalance.company_id == company_id,
                StockBalance.location_id == location_id,
                or_(StockBalance.qty_on_hand != 0, StockBalance.qty_reserved != 0),
            ).limit(1)
        )
        if nonzero_balance:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="คลังนี้ยังมียอดคงเหลือหรือยอดจอง กรุณาย้าย/ปรับยอดให้เป็นศูนย์ก่อน",
            )

        open_shift = await self.db.scalar(
            select(CashierShift.id).where(
                CashierShift.company_id == company_id,
                CashierShift.location_id == location_id,
                CashierShift.status == "open",
            ).limit(1)
        )
        if open_shift:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="คลังนี้ยังมีกะขายที่เปิดอยู่ กรุณาปิดกะก่อน",
            )

    async def _get_or_create_balance(
        self,
        company_id: uuid.UUID,
        branch_id: uuid.UUID,
        location_id: uuid.UUID,
        product_id: uuid.UUID,
        variant_id: uuid.UUID | None,
    ) -> StockBalance:
        statement = (
            select(StockBalance)
            .where(
                StockBalance.company_id == company_id,
                StockBalance.branch_id == branch_id,
                StockBalance.location_id == location_id,
                StockBalance.product_id == product_id,
            )
            .with_for_update()
        )
        if variant_id is None:
            statement = statement.where(StockBalance.variant_id.is_(None))
        else:
            statement = statement.where(StockBalance.variant_id == variant_id)

        balance = await self.db.scalar(statement)
        if balance is not None:
            return balance

        balance = StockBalance(
            company_id=company_id,
            branch_id=branch_id,
            location_id=location_id,
            product_id=product_id,
            variant_id=variant_id,
            qty_on_hand=Decimal("0"),
            qty_reserved=Decimal("0"),
            cost_per_unit=Decimal("0"),
        )
        self.db.add(balance)
        await self.db.flush()
        return balance

    async def _record_movement(
        self,
        balance: StockBalance,
        movement_type: str,
        qty_delta: Decimal,
        user_id: uuid.UUID,
        cost_per_unit: Decimal | None = None,
        reference_type: str | None = None,
        reference_id: str | None = None,
        note: str | None = None,
        allow_negative: bool = False,
        suppress_low_stock_events: bool = False,
    ) -> StockMovement:
        if movement_type not in MOVEMENT_TYPES:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid movement type")

        qty_before = Decimal(balance.qty_on_hand or 0)
        qty_after = qty_before + qty_delta
        if qty_after < 0 and qty_delta < 0 and not allow_negative:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Stock cannot go negative",
            )

        qty_reserved = Decimal(balance.qty_reserved or 0)
        balance.qty_on_hand = qty_after
        effective_cost = Decimal(balance.cost_per_unit or 0)

        if cost_per_unit is not None and qty_delta > 0:
            old_qty = qty_before
            old_cost = Decimal(balance.cost_per_unit or 0)
            new_total_qty = qty_after if qty_after > 0 else qty_delta
            if new_total_qty > 0:
                effective_cost = ((old_qty * old_cost) + (qty_delta * cost_per_unit)) / new_total_qty
                balance.cost_per_unit = effective_cost.quantize(Decimal("0.0001"))
        elif cost_per_unit is not None:
            effective_cost = cost_per_unit

        balance.last_movement_at = datetime.now(timezone.utc)
        movement = StockMovement(
            company_id=balance.company_id,
            branch_id=balance.branch_id,
            location_id=balance.location_id,
            product_id=balance.product_id,
            variant_id=balance.variant_id,
            movement_type=movement_type,
            qty=qty_delta,
            qty_before=qty_before,
            qty_after=qty_after,
            cost_per_unit=Decimal(balance.cost_per_unit or effective_cost or 0),
            reference_type=reference_type,
            reference_id=reference_id,
            note=note,
            user_id=user_id,
        )
        balance.qty_reserved = qty_reserved
        self.db.add(movement)
        await self.db.flush()
        product = await self.db.get(Product, balance.product_id)
        if (
            not suppress_low_stock_events
            and product is not None
            and Decimal(balance.qty_on_hand or 0) <= Decimal(product.min_stock_qty or 0)
            and Decimal(product.min_stock_qty or 0) > 0
        ):
            try:
                await trigger_event(
                    self.db,
                    balance.company_id,
                    "stock.low",
                    {
                        "product_id": str(balance.product_id),
                        "location_id": str(balance.location_id),
                        "qty_on_hand": str(balance.qty_on_hand),
                        "min_stock_qty": str(product.min_stock_qty),
                    },
                )
            except Exception:
                pass
            try:
                notif_svc = NotificationService(self.db)
                await notif_svc.notify_event(
                    balance.company_id,
                    "stock.low",
                    context={
                        "product_name": str(balance.product_id),
                        "sku": str(balance.product_id),
                        "qty_on_hand": str(balance.qty_on_hand),
                        "min_stock_qty": str(product.min_stock_qty),
                    },
                    reference_type="StockBalance",
                    reference_id=str(balance.id),
                )
            except Exception:
                pass
        return movement

    async def adjust(
        self,
        company_id: uuid.UUID,
        user_id: uuid.UUID,
        data: AdjustmentRequest,
    ) -> StockMovement:
        location = await self._get_location(data.location_id, company_id)
        await self._ensure_product_variant(company_id, data.product_id, data.variant_id)
        balance = await self._get_or_create_balance(
            company_id=company_id,
            branch_id=location.branch_id,
            location_id=location.id,
            product_id=data.product_id,
            variant_id=data.variant_id,
        )
        movement = await self._record_movement(
            balance=balance,
            movement_type="adjust",
            qty_delta=data.qty,
            user_id=user_id,
            cost_per_unit=data.cost_per_unit,
            note=data.note,
        )
        await self.db.flush()
        return movement

    async def receive(
        self,
        company_id: uuid.UUID,
        user_id: uuid.UUID,
        data: ReceiveStockRequest,
    ) -> list[StockMovement]:
        if not data.items:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="At least one item is required")

        location = await self._get_location(data.location_id, company_id)
        movement_type = "opening" if (data.reference_type or "").lower() == "opening" else "receive"
        movements: list[StockMovement] = []

        for item in data.items:
            if item.qty <= 0:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Receive quantity must be positive")
            await self._ensure_product_variant(company_id, item.product_id, item.variant_id)
            balance = await self._get_or_create_balance(
                company_id=company_id,
                branch_id=location.branch_id,
                location_id=location.id,
                product_id=item.product_id,
                variant_id=item.variant_id,
            )
            movement = await self._record_movement(
                balance=balance,
                movement_type=movement_type,
                qty_delta=item.qty,
                user_id=user_id,
                cost_per_unit=item.cost_per_unit,
                reference_type=data.reference_type,
                reference_id=data.reference_id,
                note=data.note,
            )
            movements.append(movement)

        await self.db.commit()
        return movements

    async def transfer(
        self,
        company_id: uuid.UUID,
        user_id: uuid.UUID,
        data: TransferRequest,
    ) -> list[StockMovement]:
        if data.from_location_id == data.to_location_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Source and destination locations must be different",
            )
        if not data.items:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="At least one item is required")

        from_location = await self._get_location(data.from_location_id, company_id)
        to_location = await self._get_location(data.to_location_id, company_id)
        movements: list[StockMovement] = []

        for item in data.items:
            if item.qty <= 0:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Transfer quantity must be positive")
            await self._ensure_product_variant(company_id, item.product_id, item.variant_id)

            source_balance = await self._get_or_create_balance(
                company_id=company_id,
                branch_id=from_location.branch_id,
                location_id=from_location.id,
                product_id=item.product_id,
                variant_id=item.variant_id,
            )
            source_cost = Decimal(source_balance.cost_per_unit or 0)
            movement_out = await self._record_movement(
                balance=source_balance,
                movement_type="transfer_out",
                qty_delta=-item.qty,
                user_id=user_id,
                cost_per_unit=source_cost,
                note=data.note,
            )
            destination_balance = await self._get_or_create_balance(
                company_id=company_id,
                branch_id=to_location.branch_id,
                location_id=to_location.id,
                product_id=item.product_id,
                variant_id=item.variant_id,
            )
            movement_in = await self._record_movement(
                balance=destination_balance,
                movement_type="transfer_in",
                qty_delta=item.qty,
                user_id=user_id,
                cost_per_unit=source_cost,
                note=data.note,
            )
            movements.extend([movement_out, movement_in])

        await self.db.commit()
        return movements

    async def produce(
        self,
        company_id: uuid.UUID,
        user_id: uuid.UUID,
        location_id: uuid.UUID,
        inputs: list[dict],
        outputs: list[dict],
        note: str | None = None,
        reference_type: str | None = None,
        reference_id: str | None = None,
    ) -> list[StockMovement]:
        if not inputs and not outputs:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="At least one production item is required")

        location = await self._get_location(location_id, company_id)
        movements: list[StockMovement] = []

        for item in inputs:
            product_id = item["product_id"]
            qty = Decimal(str(item["qty"]))
            if qty <= 0:
                continue
            await self._ensure_product_variant(company_id, product_id, None)
            balance = await self._get_or_create_balance(
                company_id=company_id,
                branch_id=location.branch_id,
                location_id=location.id,
                product_id=product_id,
                variant_id=None,
            )
            movements.append(await self._record_movement(
                balance=balance,
                movement_type="issue",
                qty_delta=-qty,
                user_id=user_id,
                cost_per_unit=Decimal(balance.cost_per_unit or 0),
                reference_type=reference_type,
                reference_id=reference_id,
                note=note,
            ))

        for item in outputs:
            product_id = item["product_id"]
            qty = Decimal(str(item["qty"]))
            if qty <= 0:
                continue
            cost_per_unit = item.get("cost_per_unit")
            await self._ensure_product_variant(company_id, product_id, None)
            balance = await self._get_or_create_balance(
                company_id=company_id,
                branch_id=location.branch_id,
                location_id=location.id,
                product_id=product_id,
                variant_id=None,
            )
            movements.append(await self._record_movement(
                balance=balance,
                movement_type="receive",
                qty_delta=qty,
                user_id=user_id,
                cost_per_unit=Decimal(str(cost_per_unit)) if cost_per_unit is not None else None,
                reference_type=reference_type,
                reference_id=reference_id,
                note=note,
            ))

        await self.db.commit()
        return movements

    async def list_balances(
        self,
        company_id: uuid.UUID,
        branch_id: uuid.UUID | None = None,
        location_id: uuid.UUID | None = None,
        product_id: uuid.UUID | None = None,
        low_stock_only: bool = False,
        location_ids: tuple[uuid.UUID, ...] | None = None,
    ) -> list[StockBalance]:
        statement = (
            select(
                StockBalance,
                Product.name,
                Product.sku,
                Unit.code,
                ProductVariant.name,
                StockLocation.name,
                Product.min_stock_qty,
            )
            .join(Product, Product.id == StockBalance.product_id)
            .join(StockLocation, StockLocation.id == StockBalance.location_id)
            .outerjoin(Unit, Unit.id == Product.unit_id)
            .outerjoin(ProductVariant, ProductVariant.id == StockBalance.variant_id)
            .where(
                StockBalance.company_id == company_id,
                Product.deleted_at.is_(None),
            )
            .order_by(Product.name.asc(), StockLocation.name.asc())
        )
        if branch_id:
            statement = statement.where(StockBalance.branch_id == branch_id)
        if location_id:
            statement = statement.where(StockBalance.location_id == location_id)
        if location_ids is not None:
            statement = statement.where(StockBalance.location_id.in_(location_ids))
        if product_id:
            statement = statement.where(StockBalance.product_id == product_id)
        if low_stock_only:
            statement = statement.where(
                Product.min_stock_qty > 0,
                StockBalance.qty_on_hand <= Product.min_stock_qty,
            )

        rows = await self.db.execute(statement)
        balances: list[StockBalance] = []
        for balance, product_name, product_sku, unit_code, variant_name, location_name, min_stock_qty in rows.all():
            balance.product_name = product_name
            balance.product_sku = product_sku
            balance.unit_code = unit_code
            balance.variant_name = variant_name
            balance.location_name = location_name
            balance.min_stock_qty = min_stock_qty or Decimal("0")
            balances.append(balance)
        return balances

    async def list_movements(
        self,
        company_id: uuid.UUID,
        product_id: uuid.UUID | None = None,
        branch_id: uuid.UUID | None = None,
        movement_type: str | None = None,
        page: int = 1,
        limit: int = 50,
        date_from: date | None = None,
        date_to: date | None = None,
        location_id: uuid.UUID | None = None,
        location_ids: tuple[uuid.UUID, ...] | None = None,
    ) -> tuple[list[StockMovement], int]:
        filters = [StockMovement.company_id == company_id]
        if product_id:
            filters.append(StockMovement.product_id == product_id)
        if branch_id:
            filters.append(StockMovement.branch_id == branch_id)
        if location_id:
            filters.append(StockMovement.location_id == location_id)
        if location_ids is not None:
            filters.append(StockMovement.location_id.in_(location_ids))
        if movement_type:
            filters.append(StockMovement.movement_type == movement_type)
        if date_from:
            filters.append(StockMovement.created_at >= datetime.combine(date_from, time.min, tzinfo=timezone.utc))
        if date_to:
            filters.append(StockMovement.created_at <= datetime.combine(date_to, time.max, tzinfo=timezone.utc))

        total = await self.db.scalar(select(func.count(StockMovement.id)).where(*filters)) or 0
        statement = (
            select(
                StockMovement,
                Product.name,
                Product.sku,
                ProductVariant.name,
                func.coalesce(User.display_name, User.username),
            )
            .join(Product, Product.id == StockMovement.product_id)
            .outerjoin(ProductVariant, ProductVariant.id == StockMovement.variant_id)
            .join(User, User.id == StockMovement.user_id)
            .where(*filters)
            .order_by(StockMovement.created_at.desc())
            .offset((page - 1) * limit)
            .limit(limit)
        )
        rows = await self.db.execute(statement)
        movements: list[StockMovement] = []
        for movement, product_name, product_sku, variant_name, user_name in rows.all():
            movement.product_name = product_name
            movement.product_sku = product_sku
            movement.variant_name = variant_name
            movement.user_name = user_name
            movements.append(movement)
        return movements, int(total)

    async def get_stock_summary(
        self,
        company_id: uuid.UUID,
        branch_id: uuid.UUID | None = None,
        location_ids: tuple[uuid.UUID, ...] | None = None,
    ) -> StockSummaryResponse:
        filters = [StockBalance.company_id == company_id]
        if branch_id:
            filters.append(StockBalance.branch_id == branch_id)
        if location_ids is not None:
            filters.append(StockBalance.location_id.in_(location_ids))

        total_skus = await self.db.scalar(
            select(func.count(StockBalance.id)).join(Product, Product.id == StockBalance.product_id).where(
                *filters, Product.deleted_at.is_(None)
            )
        ) or 0
        total_value = await self.db.scalar(
            select(func.coalesce(func.sum(StockBalance.qty_on_hand * StockBalance.cost_per_unit), 0)).where(*filters)
        ) or Decimal("0")
        low_stock_count = await self.db.scalar(
            select(func.count(StockBalance.id))
            .join(Product, Product.id == StockBalance.product_id)
            .where(
                *filters,
                Product.deleted_at.is_(None),
                Product.min_stock_qty > 0,
                StockBalance.qty_on_hand <= Product.min_stock_qty,
            )
        ) or 0
        zero_stock_count = await self.db.scalar(
            select(func.count(StockBalance.id)).where(*filters, StockBalance.qty_on_hand == 0)
        ) or 0

        return StockSummaryResponse(
            total_skus=int(total_skus),
            total_value=Decimal(total_value),
            low_stock_count=int(low_stock_count),
            zero_stock_count=int(zero_stock_count),
        )

    async def get_product_stock(
        self,
        product_id: uuid.UUID,
        company_id: uuid.UUID,
        branch_id: uuid.UUID | None = None,
        location_ids: tuple[uuid.UUID, ...] | None = None,
    ) -> list[StockBalance]:
        return await self.list_balances(
            company_id=company_id,
            branch_id=branch_id,
            product_id=product_id,
            location_ids=location_ids,
        )

    async def _get_location(self, location_id: uuid.UUID, company_id: uuid.UUID) -> StockLocation:
        location = await self.db.scalar(
            select(StockLocation).where(
                StockLocation.id == location_id,
                StockLocation.company_id == company_id,
                StockLocation.deleted_at.is_(None),
                StockLocation.is_active.is_(True),
            )
        )
        if location is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Location not found")
        return location

    async def _get_branch(self, branch_id: uuid.UUID, company_id: uuid.UUID) -> Branch:
        branch = await self.db.scalar(
            select(Branch).where(
                Branch.id == branch_id,
                Branch.company_id == company_id,
                Branch.deleted_at.is_(None),
            )
        )
        if branch is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Branch not found")
        return branch

    async def _ensure_product_variant(
        self,
        company_id: uuid.UUID,
        product_id: uuid.UUID,
        variant_id: uuid.UUID | None,
    ) -> None:
        product = await self.db.scalar(
            select(Product).where(
                Product.id == product_id,
                Product.company_id == company_id,
                Product.deleted_at.is_(None),
            )
        )
        if product is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
        if variant_id is None:
            return
        variant = await self.db.scalar(
            select(ProductVariant).where(
                ProductVariant.id == variant_id,
                ProductVariant.company_id == company_id,
                ProductVariant.product_id == product_id,
                ProductVariant.deleted_at.is_(None),
            )
        )
        if variant is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Variant not found")
