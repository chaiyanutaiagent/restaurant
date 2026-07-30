from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
import logging
import uuid
from zoneinfo import ZoneInfo

from fastapi import HTTPException, status
from sqlalchemy import func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.audit import AuditLog
from app.models.branch import Branch
from app.models.company import Company
from app.models.product import Product, ProductVariant, Unit
from app.models.purchase import (
    GoodsReceipt,
    GoodsReceiptItem,
    PurchaseOrder,
    PurchaseOrderItem,
    Supplier,
)
from app.models.user import User
from app.schemas.purchase import (
    ApprovePORequest,
    CreateGRRequest,
    CreatePORequest,
    GoodsReceiptRead,
    GRItemCreate,
    POItemCreate,
    PurchaseOrderRead,
    SupplierCreate,
    SupplierUpdate,
    UpdatePORequest,
)
from app.schemas.stock import ReceiveItem, ReceiveStockRequest
from app.services.accounting_service import AccountingService
from app.services.stock_service import StockService

TWOPLACES = Decimal("0.01")
FOURPLACES = Decimal("0.0001")
BANGKOK = ZoneInfo("Asia/Bangkok")
logger = logging.getLogger(__name__)


def q2(value: Decimal | int | float | None) -> Decimal:
    return Decimal(value or 0).quantize(TWOPLACES, rounding=ROUND_HALF_UP)


def q4(value: Decimal | int | float | None) -> Decimal:
    return Decimal(value or 0).quantize(FOURPLACES, rounding=ROUND_HALF_UP)


class PurchaseService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.stock_service = StockService(db)

    async def list_suppliers(
        self,
        company_id: uuid.UUID,
        search: str | None = None,
        is_active: bool | None = None,
        page: int = 1,
        limit: int = 20,
    ) -> tuple[list[Supplier], int]:
        filters = [Supplier.company_id == company_id, Supplier.deleted_at.is_(None)]
        if search:
            term = f"%{search.strip()}%"
            filters.append(or_(Supplier.code.ilike(term), Supplier.name.ilike(term), Supplier.tax_id.ilike(term)))
        if is_active is not None:
            filters.append(Supplier.is_active.is_(is_active))

        total = await self.db.scalar(select(func.count(Supplier.id)).where(*filters)) or 0
        rows = await self.db.scalars(
            select(Supplier)
            .where(*filters)
            .order_by(Supplier.code.asc())
            .offset((page - 1) * limit)
            .limit(limit)
        )
        return rows.all(), int(total)

    async def get_supplier(self, supplier_id: uuid.UUID, company_id: uuid.UUID) -> Supplier:
        supplier = await self.db.scalar(
            select(Supplier).where(
                Supplier.id == supplier_id,
                Supplier.company_id == company_id,
                Supplier.deleted_at.is_(None),
            )
        )
        if supplier is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Supplier not found")
        return supplier

    async def create_supplier(self, company_id: uuid.UUID, data: SupplierCreate) -> Supplier:
        await self._ensure_supplier_code_unique(company_id, data.code)
        supplier = Supplier(company_id=company_id, **data.model_dump())
        self.db.add(supplier)
        await self.db.commit()
        await self.db.refresh(supplier)
        return supplier

    async def update_supplier(
        self, supplier_id: uuid.UUID, company_id: uuid.UUID, data: SupplierUpdate
    ) -> Supplier:
        supplier = await self.get_supplier(supplier_id, company_id)
        updates = data.model_dump(exclude_unset=True)
        if "code" in updates and updates["code"] != supplier.code:
            await self._ensure_supplier_code_unique(company_id, str(updates["code"]), exclude_id=supplier_id)
        for field, value in updates.items():
            setattr(supplier, field, value)
        await self.db.commit()
        await self.db.refresh(supplier)
        return supplier

    async def delete_supplier(self, supplier_id: uuid.UUID, company_id: uuid.UUID) -> None:
        supplier = await self.get_supplier(supplier_id, company_id)
        has_active_po = await self.db.scalar(
            select(PurchaseOrder.id).where(
                PurchaseOrder.supplier_id == supplier_id,
                PurchaseOrder.company_id == company_id,
                PurchaseOrder.deleted_at.is_(None),
                PurchaseOrder.status != "cancelled",
            )
        )
        if has_active_po is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Supplier has active purchase orders",
            )
        supplier.deleted_at = datetime.now(timezone.utc)
        await self.db.commit()

    async def _calc_po_totals(
        self,
        items: list[POItemCreate],
        vat_type: str,
        vat_rate: Decimal,
        wht_rate: Decimal,
        order_discount: Decimal = Decimal("0"),
    ) -> dict[str, Decimal]:
        subtotal = Decimal("0")
        item_discount_total = Decimal("0")
        vat_total = Decimal("0")
        excluded_vat_total = Decimal("0")

        for item in items:
            line_subtotal = q4((Decimal(item.qty_ordered) * Decimal(item.unit_cost)) - Decimal(item.discount_amount))
            if line_subtotal < 0:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Line subtotal cannot be negative")
            line_vat = self._calc_vat(line_subtotal, item.vat_type or vat_type, Decimal(item.vat_rate or vat_rate))
            subtotal += line_subtotal
            item_discount_total += Decimal(item.discount_amount)
            vat_total += line_vat
            if (item.vat_type or vat_type) == "excluded":
                excluded_vat_total += line_vat

        order_discount = q2(order_discount)
        subtotal_q2 = q2(subtotal)
        subtotal_after_discount = q2(subtotal_q2 - order_discount)
        wht_amount = q2((subtotal_after_discount * Decimal(wht_rate or 0)) / Decimal("100"))
        total_amount = q2(subtotal_after_discount + q2(excluded_vat_total) - wht_amount)
        return {
            "subtotal": subtotal_q2,
            "discount_amount": q2(item_discount_total + order_discount),
            "vat_amount": q2(vat_total),
            "wht_amount": wht_amount,
            "total_amount": total_amount,
            "remaining_amount": total_amount,
        }

    async def create_po(
        self,
        company_id: uuid.UUID,
        user_id: uuid.UUID,
        data: CreatePORequest,
    ) -> PurchaseOrder:
        if not data.items:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="At least one item is required")

        branch = await self._get_branch(company_id, data.branch_id)
        supplier = await self.get_supplier(data.supplier_id, company_id)
        prepared_items = await self._prepare_po_items(company_id, data.items, data.vat_type)
        order_date = data.order_date or datetime.now(BANGKOK).date()
        po_number = await self._generate_number("PO", company_id, PurchaseOrder, PurchaseOrder.po_number, order_date)
        totals = await self._calc_po_totals(data.items, data.vat_type, Decimal("7.00"), Decimal(supplier.wht_rate or 0))

        po = PurchaseOrder(
            company_id=company_id,
            branch_id=branch.id,
            supplier_id=supplier.id,
            created_by=user_id,
            po_number=po_number,
            status="draft",
            order_date=order_date,
            expected_date=data.expected_date,
            subtotal=totals["subtotal"],
            discount_amount=totals["discount_amount"],
            vat_amount=totals["vat_amount"],
            wht_amount=totals["wht_amount"],
            total_amount=totals["total_amount"],
            paid_amount=Decimal("0"),
            remaining_amount=totals["remaining_amount"],
            vat_type=data.vat_type,
            vat_rate=Decimal("7.00"),
            wht_rate=Decimal(supplier.wht_rate or 0),
            note=data.note,
            internal_note=data.internal_note,
        )
        self.db.add(po)
        await self.db.flush()
        self.db.add_all(
            [
                PurchaseOrderItem(
                    po_id=po.id,
                    company_id=company_id,
                    product_id=item["product_id"],
                    variant_id=item["variant_id"],
                    product_name=item["product_name"],
                    sku=item["sku"],
                    unit_code=item["unit_code"],
                    qty_ordered=item["qty_ordered"],
                    qty_received=Decimal("0"),
                    unit_cost=item["unit_cost"],
                    discount_amount=item["discount_amount"],
                    vat_type=item["vat_type"],
                    vat_rate=item["vat_rate"],
                    vat_amount=item["vat_amount"],
                    subtotal=item["subtotal"],
                )
                for item in prepared_items
            ]
        )
        self._audit(
            company_id=company_id,
            branch_id=branch.id,
            user_id=user_id,
            action="purchase.po.create",
            resource="PurchaseOrder",
            resource_id=str(po.id),
            new_value={"po_number": po.po_number, "supplier_id": str(supplier.id)},
        )
        await self.db.commit()
        return await self.get_po(po.id, company_id)

    async def update_po(
        self, po_id: uuid.UUID, company_id: uuid.UUID, data: UpdatePORequest
    ) -> PurchaseOrder:
        po = await self._get_po_entity(po_id, company_id)
        if po.status != "draft":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Only draft purchase orders can be updated")

        po.expected_date = data.expected_date
        po.note = data.note
        po.internal_note = data.internal_note

        if data.items is not None:
            if not data.items:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="At least one item is required")
            prepared_items = await self._prepare_po_items(company_id, data.items, po.vat_type)
            totals = await self._calc_po_totals(data.items, po.vat_type, Decimal(po.vat_rate or 7), Decimal(po.wht_rate or 0))
            for item in list(po.items):
                await self.db.delete(item)
            await self.db.flush()
            self.db.add_all(
                [
                    PurchaseOrderItem(
                        po_id=po.id,
                        company_id=company_id,
                        product_id=item["product_id"],
                        variant_id=item["variant_id"],
                        product_name=item["product_name"],
                        sku=item["sku"],
                        unit_code=item["unit_code"],
                        qty_ordered=item["qty_ordered"],
                        qty_received=Decimal("0"),
                        unit_cost=item["unit_cost"],
                        discount_amount=item["discount_amount"],
                        vat_type=item["vat_type"],
                        vat_rate=item["vat_rate"],
                        vat_amount=item["vat_amount"],
                        subtotal=item["subtotal"],
                    )
                    for item in prepared_items
                ]
            )
            po.subtotal = totals["subtotal"]
            po.discount_amount = totals["discount_amount"]
            po.vat_amount = totals["vat_amount"]
            po.wht_amount = totals["wht_amount"]
            po.total_amount = totals["total_amount"]
            po.remaining_amount = q2(Decimal(po.total_amount) - Decimal(po.paid_amount or 0))

        await self.db.commit()
        return await self.get_po(po.id, company_id)

    async def submit_for_approval(
        self, po_id: uuid.UUID, company_id: uuid.UUID, user_id: uuid.UUID
    ) -> PurchaseOrder:
        po = await self._get_po_entity(po_id, company_id)
        if po.status != "draft":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Only draft purchase orders can be submitted")
        po.status = "pending_approval"
        self._audit(
            company_id=company_id,
            branch_id=po.branch_id,
            user_id=user_id,
            action="purchase.po.submit",
            resource="PurchaseOrder",
            resource_id=str(po.id),
        )
        await self.db.commit()
        return await self.get_po(po.id, company_id)

    async def approve_po(
        self,
        po_id: uuid.UUID,
        company_id: uuid.UUID,
        approver_id: uuid.UUID,
        data: ApprovePORequest,
    ) -> PurchaseOrder:
        po = await self._get_po_entity(po_id, company_id)
        if po.status != "pending_approval":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Only pending purchase orders can be approved")
        po.status = "approved"
        po.approved_by = approver_id
        po.approved_at = datetime.now(timezone.utc)
        if data.note:
            po.internal_note = "\n".join(filter(None, [po.internal_note, data.note]))
        self._audit(
            company_id=company_id,
            branch_id=po.branch_id,
            user_id=approver_id,
            action="purchase.po.approve",
            resource="PurchaseOrder",
            resource_id=str(po.id),
        )
        await self.db.commit()
        return await self.get_po(po.id, company_id)

    async def cancel_po(
        self,
        po_id: uuid.UUID,
        company_id: uuid.UUID,
        user_id: uuid.UUID,
        reason: str,
    ) -> PurchaseOrder:
        po = await self._get_po_entity(po_id, company_id)
        if po.status not in {"draft", "pending_approval", "approved"}:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Purchase order cannot be cancelled")
        has_receipts = await self.db.scalar(select(GoodsReceipt.id).where(GoodsReceipt.po_id == po.id))
        if has_receipts is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Purchase order already has goods receipts")
        po.status = "cancelled"
        po.cancelled_at = datetime.now(timezone.utc)
        po.cancel_reason = reason
        self._audit(
            company_id=company_id,
            branch_id=po.branch_id,
            user_id=user_id,
            action="purchase.po.cancel",
            resource="PurchaseOrder",
            resource_id=str(po.id),
            new_value={"reason": reason},
        )
        await self.db.commit()
        return await self.get_po(po.id, company_id)

    async def get_po(self, po_id: uuid.UUID, company_id: uuid.UUID) -> PurchaseOrder:
        po = await self.db.scalar(
            select(PurchaseOrder)
            .where(
                PurchaseOrder.id == po_id,
                PurchaseOrder.company_id == company_id,
                PurchaseOrder.deleted_at.is_(None),
            )
            .options(
                selectinload(PurchaseOrder.supplier),
                selectinload(PurchaseOrder.items),
                selectinload(PurchaseOrder.receipts).selectinload(GoodsReceipt.items),
            )
        )
        if po is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Purchase order not found")
        return po

    async def list_pos(
        self,
        company_id: uuid.UUID,
        branch_id: uuid.UUID | None = None,
        supplier_id: uuid.UUID | None = None,
        status_value: str | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        page: int = 1,
        limit: int = 20,
    ) -> tuple[list[PurchaseOrder], int]:
        filters = [PurchaseOrder.company_id == company_id, PurchaseOrder.deleted_at.is_(None)]
        if branch_id is not None:
            filters.append(PurchaseOrder.branch_id == branch_id)
        if supplier_id is not None:
            filters.append(PurchaseOrder.supplier_id == supplier_id)
        if status_value:
            filters.append(PurchaseOrder.status == status_value)
        if date_from is not None:
            filters.append(PurchaseOrder.order_date >= date_from)
        if date_to is not None:
            filters.append(PurchaseOrder.order_date <= date_to)

        total = await self.db.scalar(select(func.count(PurchaseOrder.id)).where(*filters)) or 0
        rows = await self.db.scalars(
            select(PurchaseOrder)
            .where(*filters)
            .options(selectinload(PurchaseOrder.supplier), selectinload(PurchaseOrder.items))
            .order_by(PurchaseOrder.order_date.desc(), PurchaseOrder.created_at.desc())
            .offset((page - 1) * limit)
            .limit(limit)
        )
        return rows.unique().all(), int(total)

    async def receive_goods(
        self,
        company_id: uuid.UUID,
        branch_id: uuid.UUID | None,
        user_id: uuid.UUID,
        data: CreateGRRequest,
    ) -> GoodsReceipt:
        if not data.items:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="At least one receipt item is required")

        po = await self.get_po(data.po_id, company_id)
        if po.status not in {"approved", "partially_received"}:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Purchase order cannot receive goods in current status")
        if branch_id is not None and po.branch_id != branch_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Branch mismatch")

        location = await self.stock_service._get_location(data.location_id, company_id)
        if location.branch_id != po.branch_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Location must belong to the purchase order branch")

        po_items = {item.id: item for item in po.items}
        stock_items: list[ReceiveItem] = []
        receipt_items_data: list[GRItemCreate] = []

        for item in data.items:
            po_item = po_items.get(item.po_item_id)
            if po_item is None:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Receipt item does not belong to this purchase order")
            remaining_qty = Decimal(po_item.qty_ordered) - Decimal(po_item.qty_received)
            if item.qty_received <= 0:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Received quantity must be positive")
            if Decimal(item.qty_received) > remaining_qty:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot receive more than remaining quantity")
            receipt_items_data.append(item)
            stock_items.append(
                ReceiveItem(
                    product_id=item.product_id,
                    variant_id=item.variant_id,
                    qty=item.qty_received,
                    cost_per_unit=item.unit_cost,
                )
            )

        received_date = data.received_date or datetime.now(BANGKOK).date()
        gr_number = await self._generate_number("GR", company_id, GoodsReceipt, GoodsReceipt.gr_number, received_date)
        receipt = GoodsReceipt(
            company_id=company_id,
            branch_id=po.branch_id,
            po_id=po.id,
            location_id=location.id,
            received_by=user_id,
            gr_number=gr_number,
            received_date=received_date,
            note=data.note,
        )
        self.db.add(receipt)
        await self.db.flush()

        for item in receipt_items_data:
            po_item = po_items[item.po_item_id]
            po_item.qty_received = q4(Decimal(po_item.qty_received) + Decimal(item.qty_received))
            self.db.add(
                GoodsReceiptItem(
                    gr_id=receipt.id,
                    po_item_id=po_item.id,
                    product_id=item.product_id,
                    variant_id=item.variant_id,
                    qty_received=q4(item.qty_received),
                    unit_cost=q4(item.unit_cost),
                    note=item.note,
                )
            )

        for stock_item in stock_items:
            await self.stock_service._ensure_product_variant(company_id, stock_item.product_id, stock_item.variant_id)
            balance = await self.stock_service._get_or_create_balance(
                company_id=company_id,
                branch_id=po.branch_id,
                location_id=location.id,
                product_id=stock_item.product_id,
                variant_id=stock_item.variant_id,
            )
            await self.stock_service._record_movement(
                balance=balance,
                movement_type="receive",
                qty_delta=stock_item.qty,
                user_id=user_id,
                cost_per_unit=stock_item.cost_per_unit,
                reference_type="PurchaseOrder",
                reference_id=str(po.id),
                note=f"GR: {gr_number}",
            )

        all_received = all(Decimal(item.qty_received) >= Decimal(item.qty_ordered) for item in po.items)
        po.status = "fully_received" if all_received else "partially_received"
        self._audit(
            company_id=company_id,
            branch_id=po.branch_id,
            user_id=user_id,
            action="purchase.goods_receipt.create",
            resource="GoodsReceipt",
            resource_id=str(receipt.id),
            new_value={"gr_number": gr_number, "po_id": str(po.id)},
        )
        await self.db.commit()
        if po.status == "fully_received":
            try:
                accounting_svc = AccountingService(self.db)
                refreshed_po = await self.get_po(po.id, company_id)
                await accounting_svc.post_purchase(refreshed_po, company_id, user_id)
                await self.db.commit()
            except Exception as e:
                logger.error(f"Accounting post failed for {po.po_number}: {e}")
                await self.db.rollback()
        return await self.get_gr(receipt.id, company_id)

    async def list_gr_by_po(
        self, po_id: uuid.UUID, company_id: uuid.UUID
    ) -> list[GoodsReceipt]:
        rows = await self.db.scalars(
            select(GoodsReceipt)
            .where(GoodsReceipt.po_id == po_id, GoodsReceipt.company_id == company_id)
            .options(selectinload(GoodsReceipt.items).selectinload(GoodsReceiptItem.po_item))
            .order_by(GoodsReceipt.received_date.desc(), GoodsReceipt.created_at.desc())
        )
        return rows.unique().all()

    async def list_receipts(
        self,
        company_id: uuid.UUID,
        po_id: uuid.UUID | None = None,
        branch_id: uuid.UUID | None = None,
    ) -> list[GoodsReceipt]:
        if po_id is None and branch_id is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="po_id or branch_id is required")
        filters = [GoodsReceipt.company_id == company_id]
        if po_id is not None:
            filters.append(GoodsReceipt.po_id == po_id)
        if branch_id is not None:
            filters.append(GoodsReceipt.branch_id == branch_id)
        rows = await self.db.scalars(
            select(GoodsReceipt)
            .where(*filters)
            .options(selectinload(GoodsReceipt.items).selectinload(GoodsReceiptItem.po_item))
            .order_by(GoodsReceipt.received_date.desc(), GoodsReceipt.created_at.desc())
        )
        return rows.unique().all()

    async def get_gr(self, gr_id: uuid.UUID, company_id: uuid.UUID) -> GoodsReceipt:
        receipt = await self.db.scalar(
            select(GoodsReceipt)
            .where(GoodsReceipt.id == gr_id, GoodsReceipt.company_id == company_id)
            .options(
                selectinload(GoodsReceipt.items).selectinload(GoodsReceiptItem.po_item),
                selectinload(GoodsReceipt.purchase_order).selectinload(PurchaseOrder.supplier),
                selectinload(GoodsReceipt.location),
                selectinload(GoodsReceipt.receiver),
            )
        )
        if receipt is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Goods receipt not found")
        return receipt

    async def _ensure_supplier_code_unique(
        self,
        company_id: uuid.UUID,
        code: str,
        exclude_id: uuid.UUID | None = None,
    ) -> None:
        statement = select(Supplier.id).where(
            Supplier.company_id == company_id,
            Supplier.code == code,
            Supplier.deleted_at.is_(None),
        )
        if exclude_id is not None:
            statement = statement.where(Supplier.id != exclude_id)
        existing = await self.db.scalar(statement)
        if existing is not None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Supplier code already exists")

    async def _get_branch(self, company_id: uuid.UUID, branch_id: uuid.UUID) -> Branch:
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

    async def _get_po_entity(self, po_id: uuid.UUID, company_id: uuid.UUID) -> PurchaseOrder:
        po = await self.db.scalar(
            select(PurchaseOrder)
            .where(
                PurchaseOrder.id == po_id,
                PurchaseOrder.company_id == company_id,
                PurchaseOrder.deleted_at.is_(None),
            )
            .options(
                selectinload(PurchaseOrder.items),
                selectinload(PurchaseOrder.supplier),
            )
        )
        if po is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Purchase order not found")
        return po

    async def _prepare_po_items(
        self,
        company_id: uuid.UUID,
        items: list[POItemCreate],
        default_vat_type: str,
    ) -> list[dict[str, object]]:
        prepared: list[dict[str, object]] = []
        for item in items:
            product = await self.db.scalar(
                select(Product)
                .where(
                    Product.id == item.product_id,
                    Product.company_id == company_id,
                    Product.deleted_at.is_(None),
                )
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
            subtotal = q4((Decimal(item.qty_ordered) * Decimal(item.unit_cost)) - Decimal(item.discount_amount))
            vat_type = item.vat_type or default_vat_type
            vat_rate = Decimal(item.vat_rate or product.vat_rate or 7)
            prepared.append(
                {
                    "product_id": product.id,
                    "variant_id": variant.id if variant else None,
                    "product_name": product.name if variant is None else f"{product.name} - {variant.name}",
                    "sku": variant.sku if variant else product.sku,
                    "unit_code": product.unit.code if product.unit else None,
                    "qty_ordered": q4(item.qty_ordered),
                    "unit_cost": q4(item.unit_cost),
                    "discount_amount": q4(item.discount_amount),
                    "vat_type": vat_type,
                    "vat_rate": q2(vat_rate),
                    "vat_amount": self._calc_vat(subtotal, vat_type, vat_rate),
                    "subtotal": subtotal,
                }
            )
        return prepared

    def _calc_vat(self, subtotal: Decimal, vat_type: str, vat_rate: Decimal) -> Decimal:
        vat_rate = Decimal(vat_rate or 0)
        if vat_type == "included":
            return q4((Decimal(subtotal) * vat_rate) / (Decimal("100") + vat_rate))
        if vat_type == "excluded":
            return q4((Decimal(subtotal) * vat_rate) / Decimal("100"))
        return Decimal("0.0000")

    async def _generate_number(
        self,
        prefix: str,
        company_id: uuid.UUID,
        model,
        field,
        target_date: date,
    ) -> str:
        day_prefix = f"{prefix}{target_date:%Y%m%d}-"
        lock_key = hash(str(company_id) + target_date.strftime("%Y%m%d") + f"PURCHASE_{prefix}") % (2**31)
        await self.db.execute(text(f"SELECT pg_advisory_xact_lock({lock_key})"))
        count = await self.db.scalar(
            select(func.count(model.id)).where(
                model.company_id == company_id,
                field.like(f"{day_prefix}%"),
            )
        ) or 0
        return f"{day_prefix}{int(count) + 1:04d}"

    def _audit(
        self,
        company_id: uuid.UUID,
        branch_id: uuid.UUID | None,
        user_id: uuid.UUID | None,
        action: str,
        resource: str,
        resource_id: str,
        new_value: dict | None = None,
    ) -> None:
        self.db.add(
            AuditLog(
                company_id=company_id,
                branch_id=branch_id,
                user_id=user_id,
                action=action,
                resource=resource,
                resource_id=resource_id,
                new_value=new_value,
            )
        )
