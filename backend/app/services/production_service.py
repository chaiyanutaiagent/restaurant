from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
import uuid

from fastapi import HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.business_context import RESTAURANT
from app.models.audit import AuditLog
from app.models.product import Product
from app.models.restaurant import (
    Brand,
    ProductionBatch,
    ProductionBatchLine,
    Recipe,
    RecipeIngredient,
)
from app.models.stock import StockBalance, StockLocation
from app.schemas.restaurant import (
    ProductionBatchCompleteRequest,
    ProductionBatchCreate,
    ProductionBatchLineCreate,
    ProductionBatchLineRead,
    ProductionBatchRead,
)
from app.services.stock_service import StockService
from app.services.recipe_service import convert_quantity


ACTIVE_BATCH_STATUSES = {"draft", "planned", "in_progress"}


def calculate_production_required(
    requested_qty: Decimal,
    ready_available: Decimal,
    in_production_qty: Decimal,
) -> Decimal:
    return max(requested_qty - ready_available - in_production_qty, Decimal("0"))


class ProductionService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def _brand_config(
        self,
        company_id: uuid.UUID,
        brand_id: uuid.UUID,
        *,
        lock: bool = False,
    ) -> tuple[Brand, StockLocation, StockLocation]:
        statement = select(Brand).where(
            Brand.id == brand_id,
            Brand.company_id == company_id,
            Brand.business_type == RESTAURANT,
            Brand.is_active.is_(True),
        )
        if lock:
            statement = statement.with_for_update()
        brand = await self.db.scalar(statement)
        if brand is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ไม่พบแบรนด์")
        if (
            brand.central_branch_id is None
            or brand.central_location_id is None
            or brand.central_ready_location_id is None
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="กรุณาตั้งค่าสาขาครัวกลาง คลัง RAW และคลัง READY ก่อนสร้าง Batch",
            )
        if brand.central_location_id == brand.central_ready_location_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="คลัง RAW และ READY ต้องเป็นคนละคลัง",
            )
        locations = list(
            (
                await self.db.scalars(
                    select(StockLocation).where(
                        StockLocation.id.in_(
                            [brand.central_location_id, brand.central_ready_location_id]
                        ),
                        StockLocation.company_id == company_id,
                        StockLocation.branch_id == brand.central_branch_id,
                        StockLocation.deleted_at.is_(None),
                        StockLocation.is_active.is_(True),
                    )
                )
            ).all()
        )
        locations_by_id = {location.id: location for location in locations}
        raw_location = locations_by_id.get(brand.central_location_id)
        ready_location = locations_by_id.get(brand.central_ready_location_id)
        if raw_location is None or ready_location is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="คลัง RAW หรือ READY ไม่ถูกต้องหรือถูกปิดใช้งาน",
            )
        return brand, raw_location, ready_location

    @staticmethod
    def _batch_number(planned_date: date) -> str:
        suffix = uuid.uuid4().hex[:6].upper()
        return f"PB-{planned_date:%y%m%d}-{suffix}"

    async def _load_batch(
        self,
        company_id: uuid.UUID,
        brand_id: uuid.UUID,
        batch_id: uuid.UUID,
        *,
        lock: bool = False,
    ) -> ProductionBatch:
        statement = (
            select(ProductionBatch)
            .options(
                selectinload(ProductionBatch.raw_location),
                selectinload(ProductionBatch.ready_location),
                selectinload(ProductionBatch.lines).selectinload(ProductionBatchLine.product),
                selectinload(ProductionBatch.lines).selectinload(ProductionBatchLine.source_location),
                selectinload(ProductionBatch.lines).selectinload(ProductionBatchLine.destination_location),
            )
            .where(
                ProductionBatch.id == batch_id,
                ProductionBatch.company_id == company_id,
                ProductionBatch.brand_id == brand_id,
            )
        )
        if lock:
            statement = statement.with_for_update()
        batch = await self.db.scalar(statement)
        if batch is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ไม่พบ Production Batch")
        return batch

    @staticmethod
    def serialize(batch: ProductionBatch) -> ProductionBatchRead:
        return ProductionBatchRead(
            id=batch.id,
            company_id=batch.company_id,
            brand_id=batch.brand_id,
            batch_number=batch.batch_number,
            planned_date=batch.planned_date,
            status=batch.status,
            raw_location_id=batch.raw_location_id,
            raw_location_name=batch.raw_location.name,
            ready_location_id=batch.ready_location_id,
            ready_location_name=batch.ready_location.name,
            planned_by=batch.planned_by,
            started_by=batch.started_by,
            completed_by=batch.completed_by,
            planned_at=batch.planned_at,
            started_at=batch.started_at,
            completed_at=batch.completed_at,
            note=batch.note,
            lines=[
                ProductionBatchLineRead(
                    id=line.id,
                    line_type=line.line_type,
                    product_id=line.product_id,
                    product_name=line.product.name,
                    product_sku=line.product.sku,
                    source_location_id=line.source_location_id,
                    source_location_name=(
                        line.source_location.name if line.source_location else None
                    ),
                    destination_location_id=line.destination_location_id,
                    destination_location_name=(
                        line.destination_location.name if line.destination_location else None
                    ),
                    planned_qty=line.planned_qty,
                    actual_qty=line.actual_qty,
                    unit_code=line.unit_code,
                    cost_per_unit=line.cost_per_unit,
                    sort_order=line.sort_order,
                )
                for line in batch.lines
            ],
        )

    async def list_batches(
        self,
        company_id: uuid.UUID,
        brand_id: uuid.UUID,
        *,
        date_from: date | None = None,
        date_to: date | None = None,
        status_filter: str | None = None,
    ) -> list[ProductionBatchRead]:
        filters = [
            ProductionBatch.company_id == company_id,
            ProductionBatch.brand_id == brand_id,
        ]
        if date_from is not None:
            filters.append(ProductionBatch.planned_date >= date_from)
        if date_to is not None:
            filters.append(ProductionBatch.planned_date <= date_to)
        if status_filter is not None:
            valid_statuses = {"draft", "planned", "in_progress", "completed", "cancelled"}
            if status_filter not in valid_statuses:
                raise HTTPException(status_code=400, detail="สถานะ Production Batch ไม่ถูกต้อง")
            filters.append(ProductionBatch.status == status_filter)
        rows = list(
            (
                await self.db.scalars(
                    select(ProductionBatch)
                    .options(
                        selectinload(ProductionBatch.raw_location),
                        selectinload(ProductionBatch.ready_location),
                        selectinload(ProductionBatch.lines).selectinload(ProductionBatchLine.product),
                        selectinload(ProductionBatch.lines).selectinload(ProductionBatchLine.source_location),
                        selectinload(ProductionBatch.lines).selectinload(ProductionBatchLine.destination_location),
                    )
                    .where(*filters)
                    .order_by(
                        ProductionBatch.planned_date.desc(),
                        ProductionBatch.created_at.desc(),
                    )
                )
            ).all()
        )
        return [self.serialize(row) for row in rows]

    async def create_batch(
        self,
        company_id: uuid.UUID,
        brand_id: uuid.UUID,
        actor_id: uuid.UUID,
        payload: ProductionBatchCreate,
    ) -> ProductionBatchRead:
        if not payload.outputs:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Production Batch ต้องมีผลผลิตอย่างน้อย 1 รายการ",
            )
        input_items = payload.inputs or await self._derive_inputs(
            company_id,
            brand_id,
            payload.outputs,
        )
        if not input_items:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="ไม่พบวัตถุดิบจากสูตรผลิต",
            )
        all_lines = [("input", item) for item in input_items] + [
            ("output", item) for item in payload.outputs
        ]
        keys = [(line_type, item.product_id) for line_type, item in all_lines]
        if len(keys) != len(set(keys)):
            raise HTTPException(status_code=400, detail="มีสินค้าซ้ำใน Production Batch")
        if any(Decimal(str(item.planned_qty)) <= 0 for _, item in all_lines):
            raise HTTPException(status_code=400, detail="จำนวนที่วางแผนต้องมากกว่า 0")

        brand, raw_location, ready_location = await self._brand_config(
            company_id,
            brand_id,
            lock=True,
        )
        product_ids = list(dict.fromkeys(item.product_id for _, item in all_lines))
        products = list(
            (
                await self.db.scalars(
                    select(Product)
                    .options(selectinload(Product.unit))
                    .where(
                        Product.id.in_(product_ids),
                        Product.company_id == company_id,
                        Product.deleted_at.is_(None),
                        Product.is_active.is_(True),
                    )
                    .with_for_update()
                )
            ).all()
        )
        products_by_id = {product.id: product for product in products}
        if len(products_by_id) != len(product_ids):
            raise HTTPException(status_code=400, detail="พบสินค้าที่ไม่อยู่ในบริษัทหรือถูกปิดใช้งาน")
        for product in products:
            if product.brand_id not in {None, brand.id}:
                raise HTTPException(status_code=400, detail=f"สินค้า {product.name} เป็นของแบรนด์อื่น")

        batch = ProductionBatch(
            company_id=company_id,
            brand_id=brand.id,
            batch_number=self._batch_number(payload.planned_date),
            planned_date=payload.planned_date,
            status="planned",
            raw_location_id=raw_location.id,
            ready_location_id=ready_location.id,
            planned_by=actor_id,
            planned_at=datetime.now(timezone.utc),
            note=(payload.note or "").strip() or None,
        )
        self.db.add(batch)
        await self.db.flush()

        for sort_order, (line_type, item) in enumerate(all_lines):
            product = products_by_id[item.product_id]
            if line_type == "input":
                if product.inventory_role == "central_raw":
                    source_location_id = raw_location.id
                elif product.inventory_role == "central_ready":
                    source_location_id = ready_location.id
                else:
                    raise HTTPException(
                        status_code=400,
                        detail=f"วัตถุดิบ {product.name} ต้องเป็น CENTRAL-RAW หรือ CENTRAL-READY",
                    )
                destination_location_id = None
                default_cost = Decimal(str(product.cost_price or 0))
            else:
                if product.inventory_role != "central_ready":
                    raise HTTPException(
                        status_code=400,
                        detail=f"ผลผลิต {product.name} ต้องเป็น CENTRAL-READY",
                    )
                source_location_id = None
                destination_location_id = ready_location.id
                default_cost = Decimal("0")
            unit_code = (item.unit_code or (product.unit.code if product.unit else "unit")).strip()
            if not unit_code:
                raise HTTPException(status_code=400, detail=f"สินค้า {product.name} ไม่มีหน่วย")
            self.db.add(
                ProductionBatchLine(
                    batch_id=batch.id,
                    line_type=line_type,
                    product_id=product.id,
                    source_location_id=source_location_id,
                    destination_location_id=destination_location_id,
                    planned_qty=Decimal(str(item.planned_qty)),
                    actual_qty=None,
                    unit_code=unit_code,
                    cost_per_unit=(
                        Decimal(str(item.cost_per_unit))
                        if item.cost_per_unit is not None
                        else default_cost
                    ),
                    sort_order=sort_order,
                )
            )
        self.db.add(
            AuditLog(
                company_id=company_id,
                branch_id=brand.central_branch_id,
                user_id=actor_id,
                action="production_batch.created",
                resource="ProductionBatch",
                resource_id=str(batch.id),
                new_value={
                    "brand_id": str(brand.id),
                    "batch_number": batch.batch_number,
                    "input_count": len(input_items),
                    "output_count": len(payload.outputs),
                },
            )
        )
        await self.db.commit()
        saved = await self._load_batch(company_id, brand.id, batch.id)
        return self.serialize(saved)

    async def _derive_inputs(
        self,
        company_id: uuid.UUID,
        brand_id: uuid.UUID,
        outputs: list[ProductionBatchLineCreate],
    ) -> list[ProductionBatchLineCreate]:
        grouped: dict[tuple[uuid.UUID, str], Decimal] = {}
        products: dict[uuid.UUID, Product] = {}
        for output in outputs:
            recipe = await self.db.scalar(
                select(Recipe)
                .options(
                    selectinload(Recipe.ingredients)
                    .selectinload(RecipeIngredient.ingredient)
                    .selectinload(Product.unit)
                )
                .where(
                    Recipe.company_id == company_id,
                    Recipe.brand_id == brand_id,
                    Recipe.product_id == output.product_id,
                    Recipe.recipe_type == "production_recipe",
                    Recipe.is_active.is_(True),
                )
                .order_by(
                    Recipe.version_no.desc(),
                    Recipe.effective_from.desc().nullslast(),
                    Recipe.created_at.desc(),
                )
                .limit(1)
            )
            if recipe is None:
                raise HTTPException(
                    status_code=400,
                    detail=f"ผลผลิต {output.product_id} ยังไม่มีสูตรผลิตที่เปิดใช้งาน",
                )
            loss_rate = min(
                max(Decimal(str(recipe.loss_percent or 0)), Decimal("0")),
                Decimal("100"),
            )
            effective_yield = Decimal(str(recipe.yield_qty or 1)) * (
                Decimal("1") - (loss_rate / Decimal("100"))
            )
            if effective_yield <= 0:
                raise HTTPException(status_code=400, detail=f"สูตร {recipe.name} มี yield ไม่ถูกต้อง")
            multiplier = Decimal(str(output.planned_qty)) / effective_yield
            for ingredient in recipe.ingredients:
                product = ingredient.ingredient
                unit_code = product.unit.code if product.unit else ingredient.unit
                qty = convert_quantity(
                    Decimal(str(ingredient.quantity)) * multiplier,
                    ingredient.unit,
                    unit_code,
                )
                key = (ingredient.ingredient_id, unit_code)
                grouped[key] = grouped.get(key, Decimal("0")) + qty
                products[ingredient.ingredient_id] = product
        return [
            ProductionBatchLineCreate(
                product_id=product_id,
                planned_qty=qty.quantize(Decimal("0.0001")),
                unit_code=unit_code,
                cost_per_unit=products[product_id].cost_price,
            )
            for (product_id, unit_code), qty in grouped.items()
            if qty > 0
        ]

    async def start_batch(
        self,
        company_id: uuid.UUID,
        brand_id: uuid.UUID,
        batch_id: uuid.UUID,
        actor_id: uuid.UUID,
    ) -> ProductionBatchRead:
        batch = await self._load_batch(company_id, brand_id, batch_id, lock=True)
        if batch.status not in {"draft", "planned"}:
            raise HTTPException(status_code=409, detail="เริ่มผลิตได้เฉพาะ Batch ที่วางแผนไว้")
        batch.status = "in_progress"
        batch.started_by = actor_id
        batch.started_at = datetime.now(timezone.utc)
        self.db.add(
            AuditLog(
                company_id=company_id,
                branch_id=batch.raw_location.branch_id,
                user_id=actor_id,
                action="production_batch.started",
                resource="ProductionBatch",
                resource_id=str(batch.id),
                new_value={"status": batch.status},
            )
        )
        await self.db.commit()
        saved = await self._load_batch(company_id, brand_id, batch.id)
        return self.serialize(saved)

    async def cancel_batch(
        self,
        company_id: uuid.UUID,
        brand_id: uuid.UUID,
        batch_id: uuid.UUID,
        actor_id: uuid.UUID,
        reason: str,
    ) -> ProductionBatchRead:
        batch = await self._load_batch(company_id, brand_id, batch_id, lock=True)
        if batch.status not in ACTIVE_BATCH_STATUSES:
            raise HTTPException(status_code=409, detail="ยกเลิก Batch สถานะนี้ไม่ได้")
        reason_value = reason.strip()
        if not reason_value:
            raise HTTPException(status_code=400, detail="กรุณาระบุเหตุผลยกเลิก")
        old_status = batch.status
        batch.status = "cancelled"
        batch.note = "\n".join(part for part in [batch.note, f"ยกเลิก: {reason_value}"] if part)
        self.db.add(
            AuditLog(
                company_id=company_id,
                branch_id=batch.raw_location.branch_id,
                user_id=actor_id,
                action="production_batch.cancelled",
                resource="ProductionBatch",
                resource_id=str(batch.id),
                old_value={"status": old_status},
                new_value={"status": batch.status, "reason": reason_value},
            )
        )
        await self.db.commit()
        saved = await self._load_batch(company_id, brand_id, batch.id)
        return self.serialize(saved)

    async def complete_batch(
        self,
        company_id: uuid.UUID,
        brand_id: uuid.UUID,
        batch_id: uuid.UUID,
        actor_id: uuid.UUID,
        payload: ProductionBatchCompleteRequest,
    ) -> ProductionBatchRead:
        try:
            batch = await self._load_batch(company_id, brand_id, batch_id, lock=True)
            if batch.status != "in_progress":
                raise HTTPException(
                    status_code=409,
                    detail="ยืนยันผลิตเสร็จได้เฉพาะ Batch ที่กำลังผลิต และทำได้ครั้งเดียว",
                )
            _, current_raw_location, current_ready_location = await self._brand_config(
                company_id,
                brand_id,
                lock=True,
            )
            if (
                batch.raw_location_id != current_raw_location.id
                or batch.ready_location_id != current_ready_location.id
            ):
                raise HTTPException(
                    status_code=409,
                    detail="การตั้งค่าคลัง RAW/READY เปลี่ยนหลังสร้าง Batch กรุณายกเลิกและสร้างใหม่",
                )
            lines = list(batch.lines)
            overrides: dict[uuid.UUID, Decimal] = {}
            valid_line_ids = {line.id for line in lines}
            for item in payload.lines:
                if item.line_id not in valid_line_ids:
                    raise HTTPException(status_code=400, detail="พบบรรทัด actual ที่ไม่อยู่ใน Batch")
                if item.line_id in overrides:
                    raise HTTPException(status_code=400, detail="มีบรรทัด actual ซ้ำ")
                actual_qty = Decimal(str(item.actual_qty))
                if actual_qty < 0:
                    raise HTTPException(status_code=400, detail="จำนวนผลิตจริงต้องไม่ติดลบ")
                overrides[item.line_id] = actual_qty

            actual_by_line = {
                line.id: overrides.get(line.id, Decimal(str(line.planned_qty)))
                for line in lines
            }
            input_lines = [line for line in lines if line.line_type == "input"]
            output_lines = [line for line in lines if line.line_type == "output"]
            if not any(actual_by_line[line.id] > 0 for line in input_lines):
                raise HTTPException(status_code=400, detail="ต้องมีวัตถุดิบใช้จริงอย่างน้อย 1 รายการ")
            if not any(actual_by_line[line.id] > 0 for line in output_lines):
                raise HTTPException(status_code=400, detail="ต้องมีผลผลิตจริงอย่างน้อย 1 รายการ")

            product_ids = list(dict.fromkeys(line.product_id for line in lines))
            locked_products = list(
                (
                    await self.db.scalars(
                        select(Product)
                        .where(Product.id.in_(product_ids), Product.company_id == company_id)
                        .order_by(Product.id)
                        .with_for_update()
                    )
                ).all()
            )
            if len(locked_products) != len(product_ids):
                raise HTTPException(status_code=400, detail="พบสินค้าใน Batch ที่ไม่อยู่ในบริษัท")

            conditions = []
            for line in lines:
                location_id = line.source_location_id or line.destination_location_id
                if location_id is not None:
                    conditions.append(
                        (StockBalance.location_id == location_id)
                        & (StockBalance.product_id == line.product_id)
                        & StockBalance.variant_id.is_(None)
                    )
            balances = list(
                (
                    await self.db.scalars(
                        select(StockBalance)
                        .where(
                            StockBalance.company_id == company_id,
                            or_(*conditions),
                        )
                        .order_by(StockBalance.location_id, StockBalance.product_id)
                        .with_for_update()
                    )
                ).all()
            )
            balances_by_key = {
                (balance.location_id, balance.product_id): balance for balance in balances
            }

            for line in input_lines:
                qty = actual_by_line[line.id]
                if qty <= 0:
                    continue
                balance = balances_by_key.get((line.source_location_id, line.product_id))
                if balance is None:
                    raise HTTPException(
                        status_code=400,
                        detail=f"ไม่พบ stock วัตถุดิบ {line.product.name} ในคลังที่กำหนด",
                    )
                available = Decimal(str(balance.qty_on_hand or 0)) - Decimal(
                    str(balance.qty_reserved or 0)
                )
                if available < qty:
                    raise HTTPException(
                        status_code=400,
                        detail=(
                            f"วัตถุดิบ {line.product.name} ไม่พอ: "
                            f"ต้องใช้ {qty} แต่ใช้ได้ {available}"
                        ),
                    )

            stock_service = StockService(self.db)
            movements = []
            total_input_cost = Decimal("0")
            movement_note = (payload.note or batch.note or f"ผลิต {batch.batch_number}").strip()
            for line in sorted(input_lines, key=lambda item: (str(item.source_location_id), str(item.product_id))):
                qty = actual_by_line[line.id]
                line.actual_qty = qty
                if qty <= 0:
                    continue
                balance = balances_by_key[(line.source_location_id, line.product_id)]
                issue_cost = Decimal(str(balance.cost_per_unit or line.cost_per_unit or 0))
                line.cost_per_unit = issue_cost
                total_input_cost += qty * issue_cost
                movements.append(
                    await stock_service._record_movement(
                        balance=balance,
                        movement_type="issue",
                        qty_delta=-qty,
                        user_id=actor_id,
                        cost_per_unit=issue_cost,
                        reference_type="central_production_batch",
                        reference_id=str(batch.id),
                        note=movement_note,
                    )
                )

            total_output_qty = sum(
                (actual_by_line[line.id] for line in output_lines),
                start=Decimal("0"),
            )
            derived_output_cost = (
                (total_input_cost / total_output_qty).quantize(Decimal("0.0001"))
                if total_output_qty > 0
                else Decimal("0")
            )
            for line in sorted(
                output_lines,
                key=lambda item: (str(item.destination_location_id), str(item.product_id)),
            ):
                qty = actual_by_line[line.id]
                line.actual_qty = qty
                if qty <= 0:
                    continue
                key = (line.destination_location_id, line.product_id)
                balance = balances_by_key.get(key)
                if balance is None:
                    balance = StockBalance(
                        company_id=company_id,
                        branch_id=batch.ready_location.branch_id,
                        location_id=line.destination_location_id,
                        product_id=line.product_id,
                        variant_id=None,
                        qty_on_hand=Decimal("0"),
                        qty_reserved=Decimal("0"),
                        cost_per_unit=Decimal("0"),
                    )
                    self.db.add(balance)
                    await self.db.flush()
                    balances_by_key[key] = balance
                output_cost = (
                    Decimal(str(line.cost_per_unit))
                    if Decimal(str(line.cost_per_unit or 0)) > 0
                    else derived_output_cost
                )
                line.cost_per_unit = output_cost
                movements.append(
                    await stock_service._record_movement(
                        balance=balance,
                        movement_type="receive",
                        qty_delta=qty,
                        user_id=actor_id,
                        cost_per_unit=output_cost,
                        reference_type="central_production_batch",
                        reference_id=str(batch.id),
                        note=movement_note,
                    )
                )

            batch.status = "completed"
            batch.completed_by = actor_id
            batch.completed_at = datetime.now(timezone.utc)
            if payload.note and payload.note.strip():
                batch.note = payload.note.strip()
            self.db.add(
                AuditLog(
                    company_id=company_id,
                    branch_id=batch.raw_location.branch_id,
                    user_id=actor_id,
                    action="production_batch.completed",
                    resource="ProductionBatch",
                    resource_id=str(batch.id),
                    old_value={"status": "in_progress"},
                    new_value={
                        "status": batch.status,
                        "movement_ids": [str(movement.id) for movement in movements],
                        "input_cost": str(total_input_cost),
                    },
                )
            )
            await self.db.commit()
        except Exception:
            await self.db.rollback()
            raise
        saved = await self._load_batch(company_id, brand_id, batch_id)
        return self.serialize(saved)
