from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
import logging
import uuid
from zoneinfo import ZoneInfo

from fastapi import HTTPException, status
from sqlalchemy import and_, func, or_, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.audit import AuditLog
from app.models.branch import Branch
from app.models.company import Company
from app.models.pos import CashierShift, Payment, SaleOrder, SaleOrderItem
from app.models.product import Product, ProductVariant
from app.models.restaurant import BrandBranch
from app.models.stock import StockBalance, StockLocation
from app.models.user import User
from app.schemas.pos import (
    CloseShiftRequest,
    CreateSaleRequest,
    OpenShiftRequest,
    PartialRefundRequest,
    PaymentCreateRequest,
    SyncSalesRequest,
    VoidRequest,
)
from app.services.accounting_service import AccountingService
from app.services.crm_service import CRMService
from app.services.notification_service import NotificationService
from app.services.stock_service import StockService
from app.utils.webhook_dispatcher import trigger_event
from app.schemas.crm import EarnPointsRequest

TWOPLACES = Decimal("0.01")
FOURPLACES = Decimal("0.0001")
BANGKOK = ZoneInfo("Asia/Bangkok")
logger = logging.getLogger(__name__)


def q2(value: Decimal) -> Decimal:
    return Decimal(value).quantize(TWOPLACES, rounding=ROUND_HALF_UP)


def q4(value: Decimal) -> Decimal:
    return Decimal(value).quantize(FOURPLACES, rounding=ROUND_HALF_UP)


class SaleService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.stock_service = StockService(db)

    async def open_shift(
        self,
        company_id: uuid.UUID,
        branch_id: uuid.UUID,
        user_id: uuid.UUID,
        data: OpenShiftRequest,
    ) -> CashierShift:
        existing = await self.get_open_shift(company_id, user_id, branch_id)
        if existing is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Shift already open")

        location = await self._get_location(company_id, data.location_id)
        if location.branch_id != branch_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Location not in current branch")

        now_local = datetime.now(BANGKOK)
        today_start = now_local.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)
        today_end = now_local.replace(hour=23, minute=59, second=59, microsecond=999999).astimezone(timezone.utc)
        count = await self.db.scalar(
            select(func.count(CashierShift.id)).where(
                CashierShift.company_id == company_id,
                CashierShift.branch_id == branch_id,
                CashierShift.opened_at >= today_start,
                CashierShift.opened_at <= today_end,
            )
        ) or 0
        shift = CashierShift(
            company_id=company_id,
            branch_id=branch_id,
            location_id=data.location_id,
            user_id=user_id,
            shift_number=f"S{now_local:%Y%m%d}-{int(count) + 1:03d}",
            opening_cash=q2(data.opening_cash),
        )
        self.db.add(shift)
        await self.db.commit()
        await self.db.refresh(shift)
        return shift

    async def get_open_shift(
        self,
        company_id: uuid.UUID,
        user_id: uuid.UUID,
        branch_id: uuid.UUID,
    ) -> CashierShift | None:
        return await self.db.scalar(
            select(CashierShift).where(
                CashierShift.company_id == company_id,
                CashierShift.user_id == user_id,
                CashierShift.branch_id == branch_id,
                CashierShift.status == "open",
            )
        )

    async def close_shift(
        self,
        shift_id: uuid.UUID,
        company_id: uuid.UUID,
        user_id: uuid.UUID,
        data: CloseShiftRequest,
    ) -> CashierShift:
        shift = await self.db.scalar(
            select(CashierShift).where(
                CashierShift.id == shift_id,
                CashierShift.company_id == company_id,
                CashierShift.user_id == user_id,
            )
        )
        if shift is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shift not found")
        if shift.status != "open":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Shift already closed")

        cash_paid = await self.db.scalar(
            select(func.coalesce(func.sum(Payment.amount), 0))
            .join(SaleOrder, SaleOrder.id == Payment.order_id)
            .where(
                SaleOrder.shift_id == shift.id,
                SaleOrder.status.in_(("completed", "partially_refunded", "refunded")),
                Payment.payment_method == "cash",
            )
        ) or Decimal("0")
        cash_change = await self.db.scalar(
            select(func.coalesce(func.sum(SaleOrder.change_amount), 0)).where(
                SaleOrder.shift_id == shift.id,
                SaleOrder.status.in_(("completed", "partially_refunded", "refunded")),
            )
        ) or Decimal("0")
        expected_cash = q2(Decimal(shift.opening_cash or 0) + Decimal(cash_paid) - Decimal(cash_change))
        closing_cash = q2(data.closing_cash)
        shift.expected_cash = expected_cash
        shift.closing_cash = closing_cash
        shift.cash_difference = q2(closing_cash - expected_cash)
        shift.note = data.note
        shift.status = "closed"
        shift.closed_at = datetime.now(timezone.utc)
        await self.db.commit()
        await self.db.refresh(shift)
        return shift

    async def list_shifts(
        self,
        company_id: uuid.UUID,
        branch_id: uuid.UUID | None,
        page: int = 1,
        limit: int = 20,
    ) -> tuple[list[CashierShift], int]:
        filters = [CashierShift.company_id == company_id]
        if branch_id is not None:
            filters.append(CashierShift.branch_id == branch_id)
        total = await self.db.scalar(select(func.count(CashierShift.id)).where(*filters)) or 0
        rows = await self.db.scalars(
            select(CashierShift)
            .where(*filters)
            .order_by(CashierShift.opened_at.desc())
            .offset((page - 1) * limit)
            .limit(limit)
        )
        return rows.all(), int(total)

    async def get_existing_sale_by_client_order_id(
        self,
        company_id: uuid.UUID,
        branch_id: uuid.UUID,
        client_order_id: str | None,
    ) -> SaleOrder | None:
        if not client_order_id:
            return None
        order = await self.db.scalar(
            select(SaleOrder)
            .where(
                SaleOrder.company_id == company_id,
                SaleOrder.branch_id == branch_id,
                SaleOrder.client_order_id == client_order_id,
            )
            .options(selectinload(SaleOrder.items), selectinload(SaleOrder.payments))
        )
        return order

    async def create_sale(
        self,
        company_id: uuid.UUID,
        branch_id: uuid.UUID,
        user_id: uuid.UUID,
        data: CreateSaleRequest,
        brand_id: uuid.UUID | None = None,
        recipe_inventory_location_id: uuid.UUID | None = None,
    ) -> SaleOrder:
        if not data.items:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="At least one cart item is required")

        shift = await self._get_shift_for_sale(company_id, branch_id, user_id, data.shift_id)
        location = await self._get_location(company_id, data.location_id)
        if location.branch_id != branch_id or shift.location_id != data.location_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Shift and location mismatch")
        if recipe_inventory_location_id is not None and recipe_inventory_location_id != data.location_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Store stock location mismatch")

        stock_needs: dict[tuple[uuid.UUID, uuid.UUID | None], Decimal] = {}
        item_rows: list[dict[str, object]] = []
        subtotal = Decimal("0")
        vat_total = Decimal("0")
        excluded_vat_total = Decimal("0")

        for item in data.items:
            if item.qty <= 0:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Quantity must be positive")
            product, variant = await self._get_product_snapshot(company_id, item.product_id, item.variant_id)
            key = (item.product_id, item.variant_id)
            stock_needs[key] = stock_needs.get(key, Decimal("0")) + Decimal(item.qty)

            effective_price = self._apply_discount(
                base_price=Decimal(item.original_price),
                discount_amount=Decimal(item.discount_amount),
                discount_type=item.discount_type,
            )
            effective_price = q4(effective_price)
            line_subtotal = q4(effective_price * Decimal(item.qty))
            line_vat = self._calc_vat(line_subtotal, item.vat_type, Decimal(item.vat_rate))
            if item.vat_type == "excluded":
                excluded_vat_total += line_vat
            vat_total += line_vat
            subtotal += line_subtotal
            item_rows.append(
                {
                    "product": product,
                    "variant": variant,
                    "qty": q4(Decimal(item.qty)),
                    "unit_price": effective_price,
                    "original_price": q4(Decimal(item.original_price)),
                    "discount_amount": q4(Decimal(item.discount_amount)),
                    "discount_type": item.discount_type,
                    "vat_type": item.vat_type,
                    "vat_rate": q2(Decimal(item.vat_rate)),
                    "vat_amount": line_vat,
                    "subtotal": line_subtotal,
                }
            )

        await self._ensure_stock_available(company_id, branch_id, data.location_id, stock_needs)

        order_discount = q2(
            self._apply_discount(
                base_price=q2(subtotal),
                discount_amount=Decimal(data.discount_amount),
                discount_type=data.discount_type,
            )
        )
        base_subtotal = q2(subtotal)
        actual_order_discount = q2(base_subtotal - order_discount)
        total_amount = q2(base_subtotal - actual_order_discount + q2(excluded_vat_total))
        payment_rows = self._prepare_payments(data, total_amount)
        paid_amount = q2(sum((Decimal(item.amount) for item in payment_rows), Decimal("0")))
        if paid_amount < total_amount:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Paid amount is insufficient")
        change_amount = q2(max(Decimal("0"), paid_amount - total_amount))

        now_local = datetime.now(BANGKOK)
        order_number = await self._generate_order_number(company_id, now_local.strftime("%Y%m%d"))

        order_values = {
            "id": uuid.uuid4(),
            "company_id": company_id,
            "branch_id": branch_id,
            "location_id": data.location_id,
            "shift_id": shift.id,
            "user_id": user_id,
            "order_number": order_number,
            "customer_name": data.customer_name,
            "customer_phone": data.customer_phone,
            "customer_tax_id": data.customer_tax_id,
            "subtotal": base_subtotal,
            "discount_amount": actual_order_discount,
            "discount_type": data.discount_type,
            "vat_amount": q2(vat_total),
            "vat_rate": Decimal("7.00"),
            "total_amount": total_amount,
            "paid_amount": paid_amount,
            "change_amount": change_amount,
            "is_offline": data.is_offline,
            "client_order_id": data.client_order_id,
            "synced_at": datetime.now(timezone.utc) if not data.is_offline else None,
            "note": data.note,
        }
        if data.client_order_id:
            inserted_id = (
                await self.db.execute(
                    insert(SaleOrder)
                    .values(**order_values)
                    .on_conflict_do_nothing(constraint="uq_sale_orders_client_order_id")
                    .returning(SaleOrder.id)
                )
            ).scalar_one_or_none()
            if inserted_id is None:
                await self.db.rollback()
                existing = await self.get_existing_sale_by_client_order_id(company_id, branch_id, data.client_order_id)
                if existing is None:
                    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Duplicate client_order_id")
                if brand_id is not None and recipe_inventory_location_id is not None and existing.recipe_stock_posted_at is None:
                    from app.services.store_inventory_service import StoreInventoryService

                    await StoreInventoryService(self.db).post_sale(
                        order=existing,
                        company_id=company_id,
                        brand_id=brand_id,
                        branch_id=branch_id,
                        location_id=recipe_inventory_location_id,
                        user_id=user_id,
                        items=[
                            (row["product"], Decimal(row["qty"]))
                            for row in item_rows
                            if isinstance(row["product"], Product) and row["product"].product_type == "menu_item"
                        ],
                    )
                    await self.db.commit()
                    return await self.get_sale(existing.id, company_id)
                return existing
            order_id = inserted_id
        else:
            order = SaleOrder(**order_values)
            self.db.add(order)
            await self.db.flush()
            order_id = order.id

        for row in item_rows:
            product = row["product"]
            variant = row["variant"]
            assert isinstance(product, Product)
            assert variant is None or isinstance(variant, ProductVariant)
            self.db.add(
                SaleOrderItem(
                    order_id=order_id,
                    company_id=company_id,
                    product_id=product.id,
                    variant_id=variant.id if variant else None,
                    product_name=product.name,
                    variant_name=variant.name if variant else None,
                    sku=variant.sku if variant else product.sku,
                    unit_code=product.unit.code if product.unit else None,
                    qty=row["qty"],
                    unit_price=row["unit_price"],
                    original_price=row["original_price"],
                    discount_amount=row["discount_amount"],
                    discount_type=row["discount_type"],
                    vat_type=row["vat_type"],
                    vat_rate=row["vat_rate"],
                    vat_amount=row["vat_amount"],
                    subtotal=row["subtotal"],
                )
            )

        for payment in payment_rows:
            self.db.add(
                Payment(
                    order_id=order_id,
                    company_id=company_id,
                    payment_method=payment.payment_method,
                    amount=q2(Decimal(payment.amount)),
                    reference_no=payment.reference_no,
                    note=data.note,
                )
            )

        for row in item_rows:
            product = row["product"]
            variant = row["variant"]
            assert isinstance(product, Product)
            if product.product_type in ("menu_item", "raw_material"):
                continue
            balance = await self.stock_service._get_or_create_balance(
                company_id=company_id,
                branch_id=branch_id,
                location_id=data.location_id,
                product_id=product.id,
                variant_id=variant.id if variant else None,
            )
            await self.stock_service._record_movement(
                balance=balance,
                movement_type="sale",
                qty_delta=-Decimal(row["qty"]),
                user_id=user_id,
                cost_per_unit=Decimal(balance.cost_per_unit or 0),
                reference_type="SaleOrder",
                reference_id=str(order_id),
                note=data.note,
            )

        if brand_id is not None and recipe_inventory_location_id is not None:
            from app.services.store_inventory_service import StoreInventoryService

            sale_order = await self.db.get(SaleOrder, order_id)
            if sale_order is None:
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Sale order was not created")
            await StoreInventoryService(self.db).post_sale(
                order=sale_order,
                company_id=company_id,
                brand_id=brand_id,
                branch_id=branch_id,
                location_id=recipe_inventory_location_id,
                user_id=user_id,
                items=[
                    (row["product"], Decimal(row["qty"]))
                    for row in item_rows
                    if isinstance(row["product"], Product) and row["product"].product_type == "menu_item"
                ],
            )

        shift.total_sales = q2(Decimal(shift.total_sales or 0) + total_amount)
        shift.total_orders = int(shift.total_orders or 0) + 1
        self.db.add(
            AuditLog(
                company_id=company_id,
                branch_id=branch_id,
                user_id=user_id,
                action="pos.sale.create",
                resource="SaleOrder",
                resource_id=str(order_id),
                new_value={"order_number": order_values["order_number"], "total_amount": str(total_amount)},
            )
        )
        try:
            await trigger_event(
                self.db,
                company_id,
                "sale.created",
                {
                    "order_number": order_values["order_number"],
                    "total_amount": str(total_amount),
                    "branch_id": str(order_values["branch_id"]),
                    "items_count": len(item_rows),
                },
            )
        except Exception:
            pass
        try:
            notif_svc = NotificationService(self.db)
            await notif_svc.notify_event(
                company_id,
                "sale.created",
                context={
                    "order_number": order_values["order_number"],
                    "total_amount": f"{total_amount:,.2f}",
                    "branch_name": str(order_values["branch_id"]),
                },
                reference_type="SaleOrder",
                reference_id=str(order_id),
            )
        except Exception:
            pass
        await self.db.commit()
        order = await self.get_sale(order_id, company_id)
        if data.customer_id:
            try:
                crm_svc = CRMService(self.db)
                await crm_svc.earn_points(
                    company_id=company_id,
                    user_id=user_id,
                    data=EarnPointsRequest(
                        customer_id=data.customer_id,
                        sale_order_id=str(order.id),
                        spend_amount=order.total_amount,
                    ),
                )
                await self.db.commit()
            except Exception as e:
                logger.error(f"Points earn failed: {e}")
                await self.db.rollback()
        try:
            accounting_svc = AccountingService(self.db)
            await accounting_svc.post_sale(order, company_id, user_id)
            await self.db.commit()
        except Exception as e:
            logger.error(f"Accounting post failed for {order.order_number}: {e}")
            await self.db.rollback()
        return await self.get_sale(order_id, company_id)

    async def _generate_order_number(self, company_id: uuid.UUID, date_str: str) -> str:
        lock_key = hash(str(company_id) + date_str + "SALE") % (2**31)
        await self.db.execute(text(f"SELECT pg_advisory_xact_lock({lock_key})"))
        count = (
            await self.db.scalar(
                select(func.count(SaleOrder.id)).where(
                    SaleOrder.company_id == company_id,
                    SaleOrder.order_number.like(f"SO{date_str}-%"),
                )
            )
        ) or 0
        return f"SO{date_str}-{int(count) + 1:04d}"

    async def void_sale(
        self,
        order_id: uuid.UUID,
        company_id: uuid.UUID,
        user_id: uuid.UUID,
        data: VoidRequest,
    ) -> SaleOrder:
        order = await self.get_sale(order_id, company_id)
        if order.status != "completed":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Order cannot be voided")
        shift = await self.get_open_shift(company_id, user_id, order.branch_id)
        if shift is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Active shift required to void sale")

        recipe_return_items: list[tuple[Product, Decimal]] = []
        for item in order.items:
            product = await self.db.get(Product, item.product_id)
            if product is not None and product.product_type in ("menu_item", "raw_material"):
                if product.product_type == "menu_item":
                    recipe_return_items.append((product, Decimal(item.qty)))
                continue
            balance = await self.stock_service._get_or_create_balance(
                company_id=company_id,
                branch_id=order.branch_id,
                location_id=order.location_id,
                product_id=item.product_id,
                variant_id=item.variant_id,
            )
            await self.stock_service._record_movement(
                balance=balance,
                movement_type="sale_return",
                qty_delta=Decimal(item.qty),
                user_id=user_id,
                cost_per_unit=Decimal(balance.cost_per_unit or 0),
                reference_type="SaleOrder",
                reference_id=str(order.id),
                note=data.void_reason,
            )

        if order.recipe_stock_posted_at is not None:
            brand_branch = await self._get_store_brand_context(order)
            if brand_branch is None:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Store stock mapping is missing")
            from app.services.store_inventory_service import StoreInventoryService

            await StoreInventoryService(self.db).reverse_items(
                order=order,
                company_id=company_id,
                brand_id=brand_branch.brand_id,
                branch_id=order.branch_id,
                location_id=order.location_id,
                user_id=user_id,
                items=recipe_return_items,
                reference_type="pos_sale_recipe_void",
                note=data.void_reason,
                mark_fully_reversed=True,
            )

        order.status = "voided"
        order.voided_at = datetime.now(timezone.utc)
        order.voided_by = user_id
        order.void_reason = data.void_reason
        order.shift.total_voids = int(order.shift.total_voids or 0) + 1
        order.shift.total_sales = q2(max(Decimal("0"), Decimal(order.shift.total_sales or 0) - Decimal(order.total_amount)))
        self.db.add(
            AuditLog(
                company_id=company_id,
                branch_id=order.branch_id,
                user_id=user_id,
                action="pos.sale.void",
                resource="SaleOrder",
                resource_id=str(order.id),
                new_value={"void_reason": data.void_reason},
            )
        )
        try:
            crm_svc = CRMService(self.db)
            await crm_svc.void_earn(company_id, user_id, str(order.id))
        except Exception as e:
            logger.error(f"Points void failed: {e}")
        await self.db.commit()
        return await self.get_sale(order.id, company_id)

    async def refund_sale(
        self,
        order_id: uuid.UUID,
        company_id: uuid.UUID,
        user_id: uuid.UUID,
        refund_reason: str,
    ) -> SaleOrder:
        order = await self.get_sale(order_id, company_id)
        if order.status not in {"completed", "partially_refunded"}:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Order cannot be refunded")
        active_shift = await self.get_open_shift(company_id, user_id, order.branch_id)
        if active_shift is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Active shift required to refund sale")
        refundable_items = [
            (item, q4(Decimal(item.qty) - Decimal(item.refunded_qty or 0)))
            for item in order.items
            if q4(Decimal(item.qty) - Decimal(item.refunded_qty or 0)) > 0
        ]
        if not refundable_items:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Order has no refundable items left")
        refund_total = await self._apply_refund(
            order=order,
            company_id=company_id,
            user_id=user_id,
            active_shift=active_shift,
            refund_reason=refund_reason,
            refund_rows=refundable_items,
            audit_action="pos.sale.refund",
        )
        if q2(Decimal(order.refund_amount or 0)) >= q2(Decimal(order.total_amount or 0)):
            try:
                crm_svc = CRMService(self.db)
                await crm_svc.void_earn(company_id, user_id, str(order.id))
            except Exception as e:
                logger.error(f"Points refund failed: {e}")
        await self.db.commit()
        logger.info("Full refund processed for %s amount=%s", order.order_number, refund_total)
        return await self.get_sale(order.id, company_id)

    async def partial_refund_sale(
        self,
        order_id: uuid.UUID,
        company_id: uuid.UUID,
        user_id: uuid.UUID,
        payload: PartialRefundRequest,
    ) -> SaleOrder:
        order = await self.get_sale(order_id, company_id)
        if order.status not in {"completed", "partially_refunded"}:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Order cannot be partially refunded")
        active_shift = await self.get_open_shift(company_id, user_id, order.branch_id)
        if active_shift is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Active shift required to refund sale")
        if not payload.items:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="At least one refund item is required")

        order_items = {item.id: item for item in order.items}
        refund_rows: list[tuple[SaleOrderItem, Decimal]] = []
        for entry in payload.items:
            item = order_items.get(entry.order_item_id)
            if item is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sale order item not found")
            qty = q4(Decimal(entry.qty))
            if qty <= 0:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Refund quantity must be positive")
            refundable_qty = q4(Decimal(item.qty) - Decimal(item.refunded_qty or 0))
            if qty > refundable_qty:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Refund quantity exceeds available balance")
            refund_rows.append((item, qty))

        await self._apply_refund(
            order=order,
            company_id=company_id,
            user_id=user_id,
            active_shift=active_shift,
            refund_reason=payload.refund_reason,
            refund_rows=refund_rows,
            audit_action="pos.sale.partial_refund",
        )
        await self.db.commit()
        return await self.get_sale(order.id, company_id)

    async def get_sale(self, order_id: uuid.UUID, company_id: uuid.UUID) -> SaleOrder:
        order = await self.db.scalar(
            select(SaleOrder)
            .where(SaleOrder.id == order_id, SaleOrder.company_id == company_id)
            .options(
                selectinload(SaleOrder.items),
                selectinload(SaleOrder.payments),
                selectinload(SaleOrder.shift),
            )
        )
        if order is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sale order not found")
        return order

    async def list_sales(
        self,
        company_id: uuid.UUID,
        shift_id: uuid.UUID | None = None,
        branch_id: uuid.UUID | None = None,
        status_value: str | None = None,
        page: int = 1,
        limit: int = 20,
    ) -> tuple[list[SaleOrder], int]:
        filters = [SaleOrder.company_id == company_id]
        if shift_id is not None:
            filters.append(SaleOrder.shift_id == shift_id)
        if branch_id is not None:
            filters.append(SaleOrder.branch_id == branch_id)
        if status_value is not None:
            filters.append(SaleOrder.status == status_value)

        total = await self.db.scalar(select(func.count(SaleOrder.id)).where(*filters)) or 0
        rows = await self.db.scalars(
            select(SaleOrder)
            .where(*filters)
            .options(selectinload(SaleOrder.items), selectinload(SaleOrder.payments))
            .order_by(SaleOrder.created_at.desc())
            .offset((page - 1) * limit)
            .limit(limit)
        )
        return rows.all(), int(total)

    async def sync_offline_sales(
        self,
        company_id: uuid.UUID,
        branch_id: uuid.UUID,
        user_id: uuid.UUID,
        orders: list[CreateSaleRequest],
    ) -> list[SaleOrder]:
        created: list[SaleOrder] = []
        for order in orders:
            existing = await self.get_existing_sale_by_client_order_id(company_id, branch_id, order.client_order_id)
            if existing is not None:
                created.append(existing)
                continue
            created.append(await self.create_sale(company_id, branch_id, user_id, order))
        return created

    async def get_receipt_data(self, order_id: uuid.UUID, company_id: uuid.UUID) -> dict[str, str]:
        order = await self.get_sale(order_id, company_id)
        company = await self.db.get(Company, company_id)
        branch = await self.db.get(Branch, order.branch_id)
        cashier = await self.db.get(User, order.user_id)
        return {
            "company_name": company.name if company else "Restaurant POS",
            "branch_name": branch.name if branch else "-",
            "cashier_name": cashier.display_name or cashier.username if cashier else "-",
        }

    def _prepare_payments(self, data: CreateSaleRequest, total_amount: Decimal) -> list[PaymentCreateRequest]:
        if data.payments:
            rows = [item for item in data.payments if Decimal(item.amount) > 0]
            if not rows:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="At least one payment entry is required")
            return rows

        paid_amount = q2(Decimal(data.paid_amount))
        if data.payment_method != "cash" and paid_amount <= 0:
            paid_amount = q2(total_amount)
        return [
            PaymentCreateRequest(
                payment_method=data.payment_method,
                amount=paid_amount,
                reference_no=data.payment_reference,
            )
        ]

    async def _apply_refund(
        self,
        order: SaleOrder,
        company_id: uuid.UUID,
        user_id: uuid.UUID,
        active_shift: CashierShift,
        refund_reason: str,
        refund_rows: list[tuple[SaleOrderItem, Decimal]],
        audit_action: str,
    ) -> Decimal:
        if not refund_reason.strip():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Refund reason is required")

        subtotal_refund = Decimal("0")
        excluded_vat_refund = Decimal("0")

        for item, qty in refund_rows:
            line_ratio = Decimal("0") if Decimal(item.qty) <= 0 else q4(qty / Decimal(item.qty))
            line_subtotal = q4(Decimal(item.subtotal) * line_ratio)
            subtotal_refund += line_subtotal
            if item.vat_type == "excluded":
                excluded_vat_refund += q2(Decimal(item.vat_amount) * line_ratio)

        order_subtotal = q4(Decimal(order.subtotal or 0))
        discount_share = Decimal("0")
        if order_subtotal > 0 and subtotal_refund > 0:
            discount_share = q2(Decimal(order.discount_amount or 0) * (subtotal_refund / order_subtotal))
        refund_total = q2(q2(subtotal_refund) - discount_share + excluded_vat_refund)
        remaining_refundable = q2(Decimal(order.total_amount or 0) - Decimal(order.refund_amount or 0))
        if refund_total <= 0:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Refund amount must be greater than zero")
        if refund_total > remaining_refundable:
            refund_total = remaining_refundable

        recipe_return_items: list[tuple[Product, Decimal]] = []
        for item, qty in refund_rows:
            product = await self.db.get(Product, item.product_id)
            if product is not None and product.product_type in ("menu_item", "raw_material"):
                if product.product_type == "menu_item":
                    recipe_return_items.append((product, qty))
                continue
            balance = await self.stock_service._get_or_create_balance(
                company_id=company_id,
                branch_id=order.branch_id,
                location_id=order.location_id,
                product_id=item.product_id,
                variant_id=item.variant_id,
            )
            await self.stock_service._record_movement(
                balance=balance,
                movement_type="sale_return",
                qty_delta=qty,
                user_id=user_id,
                cost_per_unit=Decimal(balance.cost_per_unit or 0),
                reference_type="SaleOrder",
                reference_id=str(order.id),
                note=refund_reason,
            )

        if order.recipe_stock_posted_at is not None and recipe_return_items:
            brand_branch = await self._get_store_brand_context(order)
            if brand_branch is None:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Store stock mapping is missing")
            from app.services.store_inventory_service import StoreInventoryService

            await StoreInventoryService(self.db).reverse_items(
                order=order,
                company_id=company_id,
                brand_id=brand_branch.brand_id,
                branch_id=order.branch_id,
                location_id=order.location_id,
                user_id=user_id,
                items=recipe_return_items,
                reference_type="pos_sale_recipe_refund",
                note=refund_reason,
            )

        refundable_allocations = self._allocate_refund_payments(order, refund_total)
        for item, qty in refund_rows:
            line_refund = self._calculate_item_refund_amount(order, item, qty)
            item.refunded_qty = q4(Decimal(item.refunded_qty or 0) + qty)
            item.refunded_amount = q2(Decimal(item.refunded_amount or 0) + line_refund)

        order.refund_amount = q2(Decimal(order.refund_amount or 0) + refund_total)
        order.refunded_at = datetime.now(timezone.utc)
        order.status = "refunded" if q2(Decimal(order.refund_amount or 0)) >= q2(Decimal(order.total_amount or 0)) else "partially_refunded"
        note_line = f"REFUND {datetime.now(BANGKOK).strftime('%d/%m/%Y %H:%M')} {refund_total:,.2f}: {refund_reason.strip()}"
        order.note = f"{order.note}\n{note_line}".strip() if order.note else note_line
        active_shift.total_sales = q2(max(Decimal("0"), Decimal(active_shift.total_sales or 0) - refund_total))

        for payment_method, amount, reference_no in refundable_allocations:
            self.db.add(
                Payment(
                    order_id=order.id,
                    company_id=company_id,
                    payment_method=payment_method,
                    amount=-amount,
                    reference_no=reference_no,
                    note=refund_reason.strip(),
                )
            )

        self.db.add(
            AuditLog(
                company_id=company_id,
                branch_id=order.branch_id,
                user_id=user_id,
                action=audit_action,
                resource="SaleOrder",
                resource_id=str(order.id),
                new_value={
                    "refund_reason": refund_reason.strip(),
                    "refund_amount": str(refund_total),
                    "items": [
                        {
                            "order_item_id": str(item.id),
                            "product_name": item.product_name,
                            "qty": str(qty),
                        }
                        for item, qty in refund_rows
                    ],
                },
            )
        )
        return refund_total

    def _calculate_item_refund_amount(self, order: SaleOrder, item: SaleOrderItem, qty: Decimal) -> Decimal:
        ratio = Decimal("0") if Decimal(item.qty) <= 0 else q4(qty / Decimal(item.qty))
        line_subtotal = q4(Decimal(item.subtotal) * ratio)
        order_discount_share = Decimal("0")
        if Decimal(order.subtotal or 0) > 0 and line_subtotal > 0:
            order_discount_share = q2(Decimal(order.discount_amount or 0) * (line_subtotal / Decimal(order.subtotal or 0)))
        excluded_vat = q2(Decimal(item.vat_amount) * ratio) if item.vat_type == "excluded" else Decimal("0")
        return q2(q2(line_subtotal) - order_discount_share + excluded_vat)

    def _allocate_refund_payments(self, order: SaleOrder, refund_total: Decimal) -> list[tuple[str, Decimal, str | None]]:
        positive_payments = [payment for payment in order.payments if Decimal(payment.amount) > 0]
        if not positive_payments:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Original payment data not found")

        total_paid = q2(sum((Decimal(payment.amount) for payment in positive_payments), Decimal("0")))
        remaining = q2(refund_total)
        rows: list[tuple[str, Decimal, str | None]] = []
        for index, payment in enumerate(positive_payments):
            if index == len(positive_payments) - 1:
                amount = remaining
            else:
                amount = q2(refund_total * (Decimal(payment.amount) / total_paid))
                remaining = q2(remaining - amount)
            if amount > 0:
                rows.append((payment.payment_method, amount, payment.reference_no))
        return rows

    async def _get_shift_for_sale(
        self,
        company_id: uuid.UUID,
        branch_id: uuid.UUID,
        user_id: uuid.UUID,
        shift_id: uuid.UUID,
    ) -> CashierShift:
        shift = await self.db.scalar(
            select(CashierShift).where(
                CashierShift.id == shift_id,
                CashierShift.company_id == company_id,
                CashierShift.branch_id == branch_id,
                CashierShift.user_id == user_id,
            )
        )
        if shift is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shift not found")
        if shift.status != "open":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Shift is not open")
        return shift

    async def _get_location(self, company_id: uuid.UUID, location_id: uuid.UUID) -> StockLocation:
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

    async def _get_product_snapshot(
        self,
        company_id: uuid.UUID,
        product_id: uuid.UUID,
        variant_id: uuid.UUID | None,
    ) -> tuple[Product, ProductVariant | None]:
        product = await self.db.scalar(
            select(Product)
            .where(
                Product.id == product_id,
                Product.company_id == company_id,
                Product.deleted_at.is_(None),
                Product.is_active.is_(True),
            )
            .options(selectinload(Product.unit))
        )
        if product is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
        variant = None
        if variant_id is not None:
            variant = await self.db.scalar(
                select(ProductVariant).where(
                    ProductVariant.id == variant_id,
                    ProductVariant.product_id == product_id,
                    ProductVariant.company_id == company_id,
                    ProductVariant.deleted_at.is_(None),
                    ProductVariant.is_active.is_(True),
                )
            )
            if variant is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Variant not found")
        return product, variant

    async def _ensure_stock_available(
        self,
        company_id: uuid.UUID,
        branch_id: uuid.UUID,
        location_id: uuid.UUID,
        stock_needs: dict[tuple[uuid.UUID, uuid.UUID | None], Decimal],
    ) -> None:
        for (product_id, variant_id), needed in stock_needs.items():
            # skip stock check for menu_item and raw_material — tracked via recipes
            product_type_row = await self.db.scalar(
                select(Product.product_type).where(Product.id == product_id)
            )
            if product_type_row in ("menu_item", "raw_material"):
                continue

            balance = await self.db.scalar(
                select(StockBalance).where(
                    StockBalance.company_id == company_id,
                    StockBalance.branch_id == branch_id,
                    StockBalance.location_id == location_id,
                    StockBalance.product_id == product_id,
                    StockBalance.variant_id.is_(None) if variant_id is None else StockBalance.variant_id == variant_id,
                )
            )
            available = Decimal(balance.qty_available if balance is not None else 0)
            if available < needed:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Insufficient stock for one or more items",
                )

    async def _get_store_brand_context(self, order: SaleOrder) -> BrandBranch | None:
        return await self.db.scalar(
            select(BrandBranch).where(
                BrandBranch.company_id == order.company_id,
                BrandBranch.branch_id == order.branch_id,
                BrandBranch.store_location_id == order.location_id,
            ).limit(1)
        )

    def _apply_discount(self, base_price: Decimal, discount_amount: Decimal, discount_type: str) -> Decimal:
        if discount_type == "percent":
            discounted = base_price - (base_price * discount_amount / Decimal("100"))
        else:
            discounted = base_price - discount_amount
        return max(Decimal("0"), discounted)

    def _calc_vat(self, subtotal: Decimal, vat_type: str, vat_rate: Decimal) -> Decimal:
        if vat_type == "excluded":
            return q4(subtotal * vat_rate / Decimal("100"))
        if vat_type == "included":
            return q4(subtotal * vat_rate / (Decimal("100") + vat_rate))
        return Decimal("0.0000")
