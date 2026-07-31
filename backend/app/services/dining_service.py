from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
import json
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.pos import CashierShift, SaleOrder
from app.models.product import Product, Category
from app.models.restaurant import (
    DiningOrder, DiningOrderItem, DiningSession, DiningTable, KitchenTicket,
)
from app.models.settings import BranchSettings
from app.models.branch import Branch
from app.models.stock import StockLocation
from app.services.notification_service import NotificationService
from app.schemas.pos import CartItem, CreateSaleRequest, PaymentCreateRequest
from app.schemas.restaurant import (
    DiningOrderItemRead, DiningOrderRead, KitchenTicketRead,
    PlaceOrderRequest, PublicMenuProduct, PublicMenuResponse, PublicOrderHistory,
    PublicOrderStatus, SessionCheckoutRequest, SessionCheckoutResult,
    SessionOpen, SessionRead, TableRead, WapOrderItemRead, WapOrderRead,
    WapPaidOrderRequest,
)


class DiningService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    def _validate_ticket_transition(self, current_status: str, new_status: str) -> None:
        allowed: dict[str, set[str]] = {
            "pending": {"cooking", "cancelled"},
            "cooking": {"done", "cancelled"},
            "done": {"served"},
            "served": set(),
            "cancelled": set(),
        }
        if new_status == current_status:
            return
        if new_status not in allowed.get(current_status, set()):
            raise ValueError(f"ไม่สามารถเปลี่ยนสถานะจาก {current_status} เป็น {new_status} ได้")

    @staticmethod
    def _merge_local_print_state(session: DiningSession, payload: WapPaidOrderRequest) -> bool:
        changed = False
        if payload.local_customer_slip_printed_at and session.customer_slip_printed_at is None:
            session.customer_slip_printed_at = payload.local_customer_slip_printed_at
            changed = True
        if payload.local_kitchen_slip_printed_at and session.kitchen_slip_printed_at is None:
            session.kitchen_slip_printed_at = payload.local_kitchen_slip_printed_at
            session.kitchen_sent_at = payload.local_kitchen_slip_printed_at
            changed = True
        return changed

    # ── Tables ────────────────────────────────────────────────────────────────

    async def list_tables(self, company_id: uuid.UUID, branch_id: uuid.UUID) -> list[TableRead]:
        settings = await self.db.scalar(
            select(BranchSettings).where(BranchSettings.branch_id == branch_id)
        )
        qr_enabled = bool(settings and settings.fb_table_qr_enabled)
        rows = (await self.db.scalars(
            select(DiningTable)
            .where(DiningTable.company_id == company_id, DiningTable.branch_id == branch_id, DiningTable.is_active.is_(True))
            .order_by(DiningTable.sort_order, DiningTable.zone, DiningTable.name)
        )).all()

        result: list[TableRead] = []
        for t in rows:
            active_session = await self.db.scalar(
                select(DiningSession)
                .options(selectinload(DiningSession.orders).selectinload(DiningOrder.items))
                .where(DiningSession.table_id == t.id, DiningSession.status.in_(["open", "bill_requested"]))
                .limit(1)
            )
            active_items: list[DiningOrderItem] = []
            qr_pending_count = 0
            if active_session:
                for order in active_session.orders:
                    if order.status == "cancelled":
                        continue
                    for item in order.items:
                        if item.status == "cancelled":
                            continue
                        active_items.append(item)
                        if order.source == "qr_self" and item.status == "pending":
                            qr_pending_count += item.qty
            result.append(TableRead(
                id=t.id, branch_id=t.branch_id, name=t.name, zone=t.zone,
                capacity=t.capacity,
                session_qr_token=active_session.qr_token if active_session and qr_enabled else None,
                table_type=t.table_type, status=t.status,
                sort_order=t.sort_order, is_active=t.is_active,
                active_session_id=active_session.id if active_session else None,
                queue_number=active_session.queue_number if active_session else None,
                pending_count=sum(item.qty for item in active_items if item.status == "pending"),
                cooking_count=sum(item.qty for item in active_items if item.status == "cooking"),
                ready_count=sum(item.qty for item in active_items if item.status == "done"),
                served_count=sum(item.qty for item in active_items if item.status == "served"),
                qr_pending_count=qr_pending_count,
            ))
        return result

    async def get_session_by_token(self, qr_token: uuid.UUID) -> DiningSession | None:
        return await self.db.scalar(
            select(DiningSession)
            .join(BranchSettings, BranchSettings.branch_id == DiningSession.branch_id)
            .options(selectinload(DiningSession.orders).selectinload(DiningOrder.items))
            .where(
                DiningSession.qr_token == qr_token,
                DiningSession.status.in_(["open", "bill_requested"]),
                BranchSettings.fb_table_qr_enabled.is_(True),
            )
        )

    async def create_table(
        self,
        company_id: uuid.UUID,
        branch_id: uuid.UUID,
        name: str,
        capacity: int = 4,
        table_type: str = "dine_in",
        sort_order: int = 0,
        zone: str = "โซนทั่วไป",
    ) -> DiningTable:
        normalized_zone = " ".join(zone.split()) or "โซนทั่วไป"
        table = DiningTable(
            company_id=company_id,
            branch_id=branch_id,
            name=name,
            zone=normalized_zone,
            capacity=capacity,
            table_type=table_type,
            sort_order=sort_order,
        )
        self.db.add(table)
        await self.db.commit()
        await self.db.refresh(table)
        return table

    async def update_table(self, table: DiningTable, **kwargs) -> DiningTable:
        for key, val in kwargs.items():
            if val is not None and hasattr(table, key):
                setattr(table, key, val)
        await self.db.commit()
        await self.db.refresh(table)
        return table

    # ── Sessions ──────────────────────────────────────────────────────────────

    async def _next_queue_number(self, branch_id: uuid.UUID, reset: str = "daily") -> tuple[int, str]:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        filter_date = today if reset == "daily" else None
        q = select(func.max(DiningSession.queue_number)).where(
            DiningSession.branch_id == branch_id,
            DiningSession.queue_number.isnot(None),
        )
        if filter_date:
            q = q.where(DiningSession.queue_date == filter_date)
        last = await self.db.scalar(q)
        return (last or 0) + 1, today

    async def open_session(
        self,
        company_id: uuid.UUID,
        branch_id: uuid.UUID,
        payload: SessionOpen,
        opened_by: uuid.UUID | None = None,
        settings: BranchSettings | None = None,
    ) -> DiningSession:
        queue_num: int | None = None
        queue_date: str | None = None

        table: DiningTable | None = None
        if payload.table_id:
            table = await self.db.get(DiningTable, payload.table_id)
            if not table or not table.is_active or table.company_id != company_id or table.branch_id != branch_id:
                raise ValueError("ไม่พบโต๊ะในสาขานี้")
            active_session = await self.db.scalar(
                select(DiningSession.id).where(
                    DiningSession.table_id == payload.table_id,
                    DiningSession.status.in_(["open", "bill_requested"]),
                )
            )
            if active_session:
                raise ValueError("โต๊ะนี้มี session เปิดอยู่แล้ว")

        if settings and settings.fb_queue_enabled:
            reset = settings.fb_queue_reset if settings else "daily"
            queue_num, queue_date = await self._next_queue_number(branch_id, reset)

        session = DiningSession(
            company_id=company_id,
            branch_id=branch_id,
            table_id=payload.table_id,
            opened_by=opened_by,
            queue_number=queue_num,
            queue_date=queue_date,
            guest_count=payload.guest_count,
            customer_name=payload.customer_name,
            customer_phone=payload.customer_phone,
        )
        self.db.add(session)

        if table:
            table.status = "occupied"

        await self.db.commit()
        await self.db.refresh(session)
        return session

    async def get_session(self, session_id: uuid.UUID) -> DiningSession | None:
        return await self.db.scalar(
            select(DiningSession)
            .options(selectinload(DiningSession.orders).selectinload(DiningOrder.items))
            .where(DiningSession.id == session_id)
        )

    async def get_open_session_by_table(self, table_id: uuid.UUID) -> DiningSession | None:
        return await self.db.scalar(
            select(DiningSession)
            .options(selectinload(DiningSession.orders).selectinload(DiningOrder.items))
            .where(DiningSession.table_id == table_id, DiningSession.status == "open")
        )

    async def request_bill(self, session: DiningSession) -> DiningSession:
        session.status = "bill_requested"
        if session.table_id:
            table = await self.db.get(DiningTable, session.table_id)
            if table:
                table.status = "bill_requested"
        await self.db.commit()
        await self.db.refresh(session)
        return session

    async def close_session(self, session: DiningSession, sale_order_id: uuid.UUID | None = None) -> DiningSession:
        session.status = "closed"
        session.closed_at = datetime.now(timezone.utc)
        if sale_order_id:
            session.sale_order_id = sale_order_id
        if session.table_id:
            table = await self.db.get(DiningTable, session.table_id)
            if table:
                table.status = "available"
        await self.db.commit()
        await self.db.refresh(session)
        return session

    # ── Orders ────────────────────────────────────────────────────────────────

    async def _get_product(self, product_id: uuid.UUID) -> Product | None:
        return await self.db.get(Product, product_id)

    async def _get_orderable_product(
        self,
        company_id: uuid.UUID,
        product_id: uuid.UUID,
    ) -> Product | None:
        return await self.db.scalar(
            select(Product).where(
                Product.id == product_id,
                Product.company_id == company_id,
                Product.product_type == "menu_item",
                Product.is_active.is_(True),
                Product.is_for_sale.is_(True),
                Product.deleted_at.is_(None),
            )
        )

    async def _resolve_station(self, product: Product, settings: BranchSettings | None) -> str | None:
        stations = settings.fb_kitchen_stations if settings and settings.fb_kitchen_stations else []
        if not stations:
            return None
        # ลอง match ชื่อ category กับ station
        if product.category_id:
            cat = await self.db.get(Category, product.category_id)
            if cat:
                cat_name = cat.name.lower()
                for station in stations:
                    if any(kw in cat_name for kw in station.lower().split()):
                        return station
        return stations[0] if stations else None

    async def place_order(
        self,
        company_id: uuid.UUID,
        branch_id: uuid.UUID,
        session: DiningSession,
        payload: PlaceOrderRequest,
        source: str = "qr_self",
        settings: BranchSettings | None = None,
        create_tickets: bool = True,
    ) -> DiningOrder:
        from app.models.branch import Branch as BranchModel
        branch = await self.db.get(BranchModel, branch_id)
        table = await self.db.get(DiningTable, session.table_id) if session.table_id else None
        products_by_id: dict[uuid.UUID, Product] = {}
        for item_data in payload.items:
            product = await self._get_orderable_product(company_id, item_data.product_id)
            if not product:
                raise ValueError("มีเมนูที่ไม่พร้อมขาย กรุณาโหลดเมนูใหม่แล้วลองอีกครั้ง")
            products_by_id[item_data.product_id] = product

        ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        order_number = f"DO-{ts[-8:]}-{str(session.id)[:4].upper()}"

        order = DiningOrder(
            company_id=company_id, branch_id=branch_id,
            session_id=session.id, order_number=order_number,
            source=source, note=payload.note,
        )
        self.db.add(order)
        await self.db.flush()

        for item_data in payload.items:
            product = products_by_id[item_data.product_id]
            station = await self._resolve_station(product, settings)
            item = DiningOrderItem(
                order_id=order.id,
                product_id=product.id,
                product_name=product.name,
                qty=item_data.qty,
                unit_price=product.selling_price,
                special_request=item_data.special_request,
                station=station,
            )
            self.db.add(item)
            await self.db.flush()

            if create_tickets:
                ticket = KitchenTicket(
                    company_id=company_id,
                    branch_id=branch_id,
                    session_id=session.id,
                    order_item_id=item.id,
                    product_name=product.name,
                    qty=item_data.qty,
                    special_request=item_data.special_request,
                    station=station,
                    queue_number=session.queue_number,
                    table_name=table.name if table else None,
                )
                self.db.add(ticket)

        await self.db.commit()
        await self.db.refresh(order)
        return order

    def _queue_display(self, settings: BranchSettings | None, queue_number: int | None) -> str | None:
        if queue_number is None:
            return None
        return f"{settings.fb_queue_prefix or ''}{str(queue_number).zfill(3)}" if settings else str(queue_number).zfill(3)

    async def _create_missing_kitchen_tickets(
        self,
        session: DiningSession,
        settings: BranchSettings | None = None,
    ) -> None:
        table = await self.db.get(DiningTable, session.table_id) if session.table_id else None
        full_session = await self.get_session(session.id)
        if not full_session:
            raise ValueError("Session not found")

        for order in full_session.orders:
            if order.status == "cancelled":
                continue
            for item in order.items:
                if item.status == "cancelled":
                    continue
                existing = await self.db.scalar(
                    select(KitchenTicket.id).where(KitchenTicket.order_item_id == item.id)
                )
                if existing:
                    continue
                product = await self._get_product(item.product_id)
                station = await self._resolve_station(product, settings) if product else None
                self.db.add(KitchenTicket(
                    company_id=session.company_id,
                    branch_id=session.branch_id,
                    session_id=session.id,
                    order_item_id=item.id,
                    product_name=item.product_name,
                    qty=item.qty,
                    special_request=item.special_request,
                    station=station or item.station,
                    queue_number=session.queue_number,
                    table_name=table.name if table else None,
                ))

    async def get_wap_order(self, session_id: uuid.UUID, company_id: uuid.UUID) -> WapOrderRead:
        session = await self.get_session(session_id)
        if not session or session.company_id != company_id:
            raise ValueError("ไม่พบออเดอร์")
        settings = await self.db.scalar(select(BranchSettings).where(BranchSettings.branch_id == session.branch_id))
        active_orders = [order for order in session.orders if order.status != "cancelled"]
        if not active_orders or not session.sale_order_id:
            raise ValueError("ไม่พบออเดอร์")

        sale_order = await self.db.scalar(
            select(SaleOrder)
            .options(selectinload(SaleOrder.payments))
            .where(SaleOrder.id == session.sale_order_id, SaleOrder.company_id == company_id)
        )
        if not sale_order:
            raise ValueError("ไม่พบใบขาย")

        items = [
            item
            for order in active_orders
            for item in order.items
            if item.status != "cancelled"
        ]
        payment_method = sale_order.payments[0].payment_method if sale_order.payments else "cash"
        return WapOrderRead(
            session_id=session.id,
            order_id=active_orders[0].id,
            sale_order_id=sale_order.id,
            sale_order_number=sale_order.order_number,
            opened_by=session.opened_by,
            cashier_user_id=sale_order.user_id,
            queue_number=session.queue_number,
            queue_display=self._queue_display(settings, session.queue_number),
            status=session.status,
            customer_name=session.customer_name,
            customer_phone=session.customer_phone,
            subtotal=sale_order.subtotal,
            total_amount=sale_order.total_amount,
            paid_amount=sale_order.paid_amount,
            change_amount=sale_order.change_amount,
            payment_method=payment_method,
            customer_slip_printed_at=session.customer_slip_printed_at.isoformat() if session.customer_slip_printed_at else None,
            kitchen_slip_printed_at=session.kitchen_slip_printed_at.isoformat() if session.kitchen_slip_printed_at else None,
            kitchen_sent_at=session.kitchen_sent_at.isoformat() if session.kitchen_sent_at else None,
            recipe_stock_status=sale_order.recipe_stock_status,
            recipe_stock_warnings=self._decode_recipe_stock_warnings(sale_order.recipe_stock_warnings),
            created_at=session.opened_at.isoformat() if session.opened_at else None,
            client_order_id=sale_order.client_order_id,
            items=[
                WapOrderItemRead(
                    product_id=item.product_id,
                    product_name=item.product_name,
                    qty=item.qty,
                    unit_price=item.unit_price,
                    special_request=item.special_request,
                )
                for item in items
            ],
        )

    async def get_wap_order_by_client_order_id(
        self,
        company_id: uuid.UUID,
        branch_id: uuid.UUID,
        client_order_id: str | None,
    ) -> WapOrderRead | None:
        if not client_order_id:
            return None
        sale_order_id = await self.db.scalar(
            select(SaleOrder.id).where(
                SaleOrder.company_id == company_id,
                SaleOrder.branch_id == branch_id,
                SaleOrder.client_order_id == client_order_id,
            )
        )
        if sale_order_id is None:
            return None
        session_id = await self.db.scalar(
            select(DiningSession.id).where(
                DiningSession.company_id == company_id,
                DiningSession.branch_id == branch_id,
                DiningSession.sale_order_id == sale_order_id,
            )
        )
        if session_id is None:
            return None
        return await self.get_wap_order(session_id, company_id)

    async def create_wap_paid_order(
        self,
        company_id: uuid.UUID,
        branch_id: uuid.UUID,
        user_id: uuid.UUID,
        payload: WapPaidOrderRequest,
        brand_id: uuid.UUID | None = None,
        required_location_id: uuid.UUID | None = None,
    ) -> WapOrderRead:
        if not payload.items:
            raise ValueError("กรุณาเลือกรายการสินค้า")

        existing_order = await self.get_wap_order_by_client_order_id(
            company_id,
            branch_id,
            payload.client_order_id,
        )
        if existing_order is not None:
            existing_session = await self.db.get(DiningSession, existing_order.session_id)
            if existing_session and self._merge_local_print_state(existing_session, payload):
                await self.db.commit()
                return await self.get_wap_order(existing_session.id, company_id)
            return existing_order

        payment_rows = [
            PaymentCreateRequest(
                payment_method=item.payment_method,
                amount=item.amount,
                reference_no=item.reference_no,
            )
            for item in payload.payments
        ]
        sale_items: list[CartItem] = []
        expected_total = Decimal("0")
        for item in payload.items:
            product = await self.db.get(Product, item.product_id)
            if not product:
                raise ValueError("พบสินค้าที่ไม่มีอยู่ในระบบ กรุณาเชื่อมต่อเพื่อโหลดเมนูใหม่")
            expected_total += Decimal(product.selling_price) * Decimal(item.qty)
            sale_items.append(CartItem(
                product_id=item.product_id,
                variant_id=None,
                qty=Decimal(item.qty),
                unit_price=product.selling_price,
                original_price=product.selling_price,
                discount_amount=Decimal("0"),
                discount_type="amount",
                vat_type=product.vat_type,
                vat_rate=Decimal(str(product.vat_rate)),
            ))
        paid_total = (
            sum((Decimal(item.amount) for item in payload.payments), Decimal("0"))
            if payload.payments
            else Decimal(payload.paid_amount)
        )
        if paid_total < expected_total:
            raise ValueError("ราคาเมนูบนเซิร์ฟเวอร์เปลี่ยนหลังขายออฟไลน์ กรุณาให้ผู้ดูแลตรวจสอบยอด")

        resolved_shift_id, resolved_location_id = await self._resolve_shift_and_location(
            company_id,
            branch_id,
            user_id,
            payload.shift_id,
            payload.location_id,
            required_location_id,
            strict_shift=payload.is_offline,
        )
        settings = await self.db.scalar(select(BranchSettings).where(BranchSettings.branch_id == branch_id))
        session = await self.open_session(
            company_id=company_id,
            branch_id=branch_id,
            payload=SessionOpen(
                table_id=None,
                guest_count=1,
                customer_name=payload.customer_name,
                customer_phone=payload.customer_phone,
            ),
            opened_by=user_id,
            settings=settings,
        )
        if session.queue_number is None:
            queue_num, queue_date = await self._next_queue_number(
                branch_id,
                settings.fb_queue_reset if settings else "daily",
            )
            session.queue_number = queue_num
            session.queue_date = queue_date
            await self.db.commit()
            await self.db.refresh(session)
        order = await self.place_order(
            company_id=company_id,
            branch_id=branch_id,
            session=session,
            payload=PlaceOrderRequest(items=payload.items, note=payload.note),
            source="staff_wap",
            settings=settings,
            create_tickets=False,
        )

        from app.services.sale_service import SaleService

        sale_svc = SaleService(self.db)
        sale_order = await sale_svc.create_sale(
            company_id=company_id,
            branch_id=branch_id,
            user_id=user_id,
            data=CreateSaleRequest(
                shift_id=resolved_shift_id,
                location_id=resolved_location_id,
                items=sale_items,
                discount_amount=Decimal("0"),
                discount_type="amount",
                payment_method=payload.payment_method,
                payments=payment_rows,
                paid_amount=payload.paid_amount,
                customer_name=payload.customer_name,
                customer_phone=payload.customer_phone,
                customer_tax_id=payload.customer_tax_id,
                note=" | ".join(filter(None, [
                    "WAP Quick Service",
                    f"คิว {self._queue_display(settings, session.queue_number) or '-'}",
                    f"ขายจากเครื่องเมื่อ {payload.local_created_at.isoformat()}" if payload.local_created_at else None,
                    payload.note,
                ])),
                is_offline=payload.is_offline,
                client_order_id=payload.client_order_id,
            ),
            brand_id=brand_id,
            recipe_inventory_location_id=required_location_id,
        )
        session.sale_order_id = sale_order.id
        self._merge_local_print_state(session, payload)
        await self.db.commit()
        return await self.get_wap_order(session.id, company_id)

    async def mark_customer_slip_printed(self, session_id: uuid.UUID, company_id: uuid.UUID) -> WapOrderRead:
        session = await self.get_session(session_id)
        if not session or session.company_id != company_id or not session.sale_order_id:
            raise ValueError("ไม่พบออเดอร์")
        if not session.customer_slip_printed_at:
            session.customer_slip_printed_at = datetime.now(timezone.utc)
            await self.db.commit()
        return await self.get_wap_order(session.id, company_id)

    async def mark_kitchen_slip_printed(self, session_id: uuid.UUID, company_id: uuid.UUID) -> WapOrderRead:
        session = await self.get_session(session_id)
        if not session or session.company_id != company_id or not session.sale_order_id:
            raise ValueError("ไม่พบออเดอร์")
        if not session.customer_slip_printed_at:
            raise ValueError("กรุณาพิมพ์สลิปลูกค้าก่อนส่งออเดอร์เข้าครัว")
        settings = await self.db.scalar(select(BranchSettings).where(BranchSettings.branch_id == session.branch_id))
        await self._create_missing_kitchen_tickets(session, settings)
        now = datetime.now(timezone.utc)
        if not session.kitchen_slip_printed_at:
            session.kitchen_slip_printed_at = now
        if not session.kitchen_sent_at:
            session.kitchen_sent_at = now
        await self.db.commit()
        return await self.get_wap_order(session.id, company_id)

    # ── Kitchen ───────────────────────────────────────────────────────────────

    async def list_kitchen_tickets(
        self,
        branch_id: uuid.UUID,
        station: str | None = None,
        status: str | None = None,
    ) -> list[KitchenTicket]:
        q = select(KitchenTicket).where(KitchenTicket.branch_id == branch_id)
        if station:
            q = q.where(KitchenTicket.station == station)
        if status:
            q = q.where(KitchenTicket.status == status)
        else:
            q = q.where(KitchenTicket.status.in_(["pending", "cooking", "done"]))
        q = q.order_by(KitchenTicket.created_at)
        return list((await self.db.scalars(q)).all())

    async def update_ticket_status(self, ticket: KitchenTicket, new_status: str) -> KitchenTicket:
        self._validate_ticket_transition(ticket.status, new_status)
        ticket.status = new_status
        if new_status == "done":
            ticket.done_at = datetime.now(timezone.utc)
        await self.db.commit()
        await self.db.refresh(ticket)

        # sync order item status
        item = await self.db.get(DiningOrderItem, ticket.order_item_id)
        if item:
            item.status = new_status
            await self.db.commit()

        # ส่ง Line Notify เมื่อ done — ตรวจว่าทุก ticket ใน session เสร็จหมดแล้ว
        if new_status == "done":
            await self._notify_pickup_if_ready(ticket)

        return ticket

    async def update_order_item_status(self, item: DiningOrderItem, new_status: str) -> DiningOrderItem:
        ticket = await self.db.scalar(
            select(KitchenTicket).where(KitchenTicket.order_item_id == item.id)
        )
        if ticket:
            await self.update_ticket_status(ticket, new_status)
            await self.db.refresh(item)
            return item

        self._validate_ticket_transition(item.status, new_status)
        item.status = new_status
        await self.db.commit()
        await self.db.refresh(item)
        return item

    async def cancel_order_item(self, item: DiningOrderItem, reason: str) -> DiningOrderItem:
        if item.status == "served":
            raise ValueError("รายการนี้เสิร์ฟแล้ว ไม่สามารถยกเลิกได้")
        if item.status == "cancelled":
            return item

        clean_reason = reason.strip()
        item.status = "cancelled"
        item.special_request = f"{item.special_request or ''}\nยกเลิก: {clean_reason}".strip()

        ticket = await self.db.scalar(
            select(KitchenTicket).where(KitchenTicket.order_item_id == item.id)
        )
        if ticket:
            ticket.status = "cancelled"

        order = await self.db.get(DiningOrder, item.order_id)
        if order:
            items = (await self.db.scalars(
                select(DiningOrderItem).where(DiningOrderItem.order_id == order.id)
            )).all()
            if all(row.status == "cancelled" for row in items):
                order.status = "cancelled"
                order.note = f"{order.note or ''}\nยกเลิก: {clean_reason}".strip()

        await self.db.commit()
        await self.db.refresh(item)
        return item

    async def cancel_order(self, order: DiningOrder, reason: str) -> DiningOrder:
        if order.status == "cancelled":
            return order

        items = (await self.db.scalars(
            select(DiningOrderItem).where(DiningOrderItem.order_id == order.id)
        )).all()
        if any(item.status == "served" for item in items):
            raise ValueError("มีรายการที่เสิร์ฟแล้ว ไม่สามารถยกเลิกทั้งออเดอร์ได้")

        clean_reason = reason.strip()
        order.status = "cancelled"
        order.note = f"{order.note or ''}\nยกเลิก: {clean_reason}".strip()
        for item in items:
            item.status = "cancelled"
            item.special_request = f"{item.special_request or ''}\nยกเลิก: {clean_reason}".strip()

        tickets = (await self.db.scalars(
            select(KitchenTicket).where(KitchenTicket.order_item_id.in_([item.id for item in items]))
        )).all() if items else []
        for ticket in tickets:
            ticket.status = "cancelled"

        await self.db.commit()
        await self.db.refresh(order)
        return order

    async def _notify_pickup_if_ready(self, done_ticket: KitchenTicket) -> None:
        """ส่ง Line Notify เมื่อทุกรายการใน session พร้อมหมดแล้ว"""
        # ตรวจว่ายังมี ticket ที่ยัง pending/cooking ใน session เดียวกันไหม
        remaining = await self.db.scalar(
            select(func.count(KitchenTicket.id)).where(
                KitchenTicket.session_id == done_ticket.session_id,
                KitchenTicket.status.in_(["pending", "cooking"]),
            )
        )
        if remaining and remaining > 0:
            return  # ยังมีรายการที่ยังทำอยู่

        # ดึง settings ของสาขา
        settings = await self.db.scalar(
            select(BranchSettings).where(BranchSettings.branch_id == done_ticket.branch_id)
        )
        if not settings or not settings.fb_line_notify_token:
            return

        # สร้างข้อความ
        session = await self.db.get(DiningSession, done_ticket.session_id)
        if not session:
            return

        prefix = settings.fb_queue_prefix or ""
        if session.queue_number:
            queue_str = f"{prefix}{str(session.queue_number).zfill(3)}"
            message = f"\n🍽️ ออเดอร์พร้อมแล้ว!\nคิว {queue_str} — มารับได้เลยครับ 🔔"
        else:
            table = await self.db.get(DiningTable, session.table_id) if session.table_id else None
            table_name = table.name if table else "ของคุณ"
            message = f"\n🍽️ ออเดอร์พร้อมแล้ว!\nโต๊ะ {table_name} — พร้อมเสิร์ฟครับ 🔔"

        # ดึง company_id จาก branch
        branch = await self.db.get(Branch, done_ticket.branch_id)
        if not branch:
            return

        try:
            notif_svc = NotificationService(self.db)
            await notif_svc.send_line_notify(
                token=settings.fb_line_notify_token,
                message=message,
                company_id=branch.company_id,
                event_type="fb_order_ready",
                reference_type="dining_session",
                reference_id=str(session.id),
            )
        except Exception:
            pass  # notification ไม่ควร block การทำงานหลัก

    async def get_ready_pickup_queues(self, branch_id: uuid.UUID) -> list[dict[str, object]]:
        """คิว Quick Service ที่อาหารพร้อมทุกรายการแล้ว (สำหรับหน้าจอ Pickup Display)"""
        done_sessions = await self.db.scalars(
            select(KitchenTicket.session_id)
            .where(KitchenTicket.branch_id == branch_id, KitchenTicket.status == "done")
            .distinct()
        )
        done_set = set(done_sessions.all())
        if not done_set:
            return []

        pending_sessions = await self.db.scalars(
            select(KitchenTicket.session_id)
            .where(KitchenTicket.branch_id == branch_id, KitchenTicket.status.in_(["pending", "cooking"]))
            .distinct()
        )
        still_cooking = set(pending_sessions.all())
        fully_done = done_set - still_cooking

        if not fully_done:
            return []

        sessions = list((await self.db.scalars(
            select(DiningSession)
            .where(
                DiningSession.id.in_(fully_done),
                DiningSession.queue_number.isnot(None),
                DiningSession.table_id.is_(None),
                DiningSession.status == "open",
            )
            .order_by(DiningSession.queue_number)
        )).all())

        result: list[dict[str, object]] = []
        for session in sessions:
            stats = await self.db.execute(
                select(func.count(KitchenTicket.id), func.coalesce(func.sum(KitchenTicket.qty), 0), func.max(KitchenTicket.done_at))
                .where(KitchenTicket.session_id == session.id, KitchenTicket.status == "done")
            )
            ticket_count, item_count, ready_at = stats.one()
            result.append({
                "session_id": str(session.id),
                "queue_number": session.queue_number,
                "customer_name": session.customer_name,
                "ticket_count": int(ticket_count or 0),
                "item_count": int(item_count or 0),
                "ready_at": ready_at.isoformat() if ready_at else None,
            })
        return result

    async def get_ready_queue_numbers(self, branch_id: uuid.UUID) -> list[int]:
        """Backward-compatible list of ready Quick Service queue numbers."""
        queues = await self.get_ready_pickup_queues(branch_id)
        return [int(item["queue_number"]) for item in queues if item.get("queue_number") is not None]

    async def mark_pickup_session_served(
        self,
        session_id: uuid.UUID,
        company_id: uuid.UUID,
        branch_id: uuid.UUID,
    ) -> dict[str, object]:
        session = await self.db.get(DiningSession, session_id)
        if (
            not session
            or session.company_id != company_id
            or session.branch_id != branch_id
            or session.table_id is not None
            or session.queue_number is None
        ):
            raise ValueError("ไม่พบคิวรับสินค้า")

        tickets = list((await self.db.scalars(
            select(KitchenTicket)
            .where(
                KitchenTicket.session_id == session.id,
                KitchenTicket.branch_id == branch_id,
                KitchenTicket.status == "done",
            )
        )).all())
        if not tickets:
            raise ValueError("คิวนี้ยังไม่พร้อมรับ หรือรับสินค้าแล้ว")

        order_item_ids = [ticket.order_item_id for ticket in tickets if ticket.order_item_id]
        for ticket in tickets:
            ticket.status = "served"

        if order_item_ids:
            items = list((await self.db.scalars(
                select(DiningOrderItem).where(DiningOrderItem.id.in_(order_item_ids))
            )).all())
            for item in items:
                item.status = "served"

        session.status = "closed"
        session.closed_at = datetime.now(timezone.utc)
        await self.db.commit()
        return {
            "session_id": str(session.id),
            "queue_number": session.queue_number,
            "served_count": len(tickets),
            "status": session.status,
        }

    # ── Public Menu (QR) ──────────────────────────────────────────────────────

    async def get_public_menu(self, qr_token: uuid.UUID) -> PublicMenuResponse | None:
        active_session = await self.get_session_by_token(qr_token)
        if not active_session:
            return None

        table: DiningTable | None = None
        if active_session.table_id:
            table = await self.db.get(DiningTable, active_session.table_id)
            if not table or not table.is_active:
                return None

        branch = await self.db.get(Branch, active_session.branch_id)
        if not branch:
            return None

        settings = await self.db.scalar(
            select(BranchSettings).where(BranchSettings.branch_id == active_session.branch_id)
        )
        if not settings or not settings.fb_table_qr_enabled:
            return None

        products_rows = (await self.db.scalars(
            select(Product)
            .where(
                Product.company_id == active_session.company_id,
                Product.product_type == "menu_item",
                Product.is_active.is_(True),
                Product.is_for_sale.is_(True),
            )
            .order_by(Product.name)
        )).all()

        categories_raw = (await self.db.scalars(
            select(Category).where(Category.company_id == active_session.company_id, Category.is_active.is_(True))
        )).all()

        cat_map = {c.id: c.name for c in categories_raw}
        categories = [{"id": str(c.id), "name": c.name} for c in categories_raw]

        products = [
            PublicMenuProduct(
                id=p.id,
                name=p.name,
                description=p.description,
                selling_price=p.selling_price,
                category_id=p.category_id,
                category_name=cat_map.get(p.category_id) if p.category_id else None,
                image_url=p.image_url,
                is_available=True,
            )
            for p in products_rows
        ]

        return PublicMenuResponse(
            session_id=active_session.id,
            queue_number=active_session.queue_number,
            table_name=table.name if table else None,
            source_type="dine_in" if table else "quick_service",
            branch_name=branch.name,
            fb_service_mode=settings.fb_service_mode,
            categories=categories,
            products=products,
            session_status=active_session.status,
            opened_at=active_session.opened_at.isoformat(),
            bill_at_table_enabled=bool(table and settings.fb_bill_at_table),
        )

    async def _resolve_shift_and_location(
        self,
        company_id: uuid.UUID,
        branch_id: uuid.UUID,
        user_id: uuid.UUID,
        shift_id: uuid.UUID | None,
        location_id: uuid.UUID | None,
        required_location_id: uuid.UUID | None = None,
        strict_shift: bool = False,
    ) -> tuple[uuid.UUID, uuid.UUID]:
        """หา shift และ location อัตโนมัติถ้าไม่ได้ระบุ"""
        if required_location_id is not None and location_id is not None and location_id != required_location_id:
            raise ValueError("ต้องใช้คลัง STORE-STOCK ที่ตั้งค่าไว้สำหรับสาขานี้")
        if required_location_id is not None:
            required_location = await self.db.scalar(
                select(StockLocation).where(
                    StockLocation.id == required_location_id,
                    StockLocation.company_id == company_id,
                    StockLocation.branch_id == branch_id,
                    StockLocation.is_active.is_(True),
                    StockLocation.deleted_at.is_(None),
                )
            )
            if required_location is None:
                raise ValueError("ไม่พบคลัง STORE-STOCK ที่เปิดใช้งานสำหรับสาขานี้")
        # 1. ลอง shift ของ user นี้ก่อน
        resolved_shift: CashierShift | None = None
        if shift_id:
            resolved_shift = await self.db.scalar(
                select(CashierShift).where(
                    CashierShift.id == shift_id,
                    CashierShift.company_id == company_id,
                    CashierShift.branch_id == branch_id,
                    CashierShift.user_id == user_id,
                    CashierShift.status == "open",
                )
            )
            if strict_shift and not resolved_shift:
                raise ValueError("กะที่บันทึกไว้ตอนขายออฟไลน์ถูกปิดหรือไม่ตรงกับพนักงาน กรุณาให้ผู้ดูแลตรวจสอบ")

        # 2. ถ้าไม่มี → หา open shift ของ user นี้
        if not resolved_shift:
            resolved_shift = await self.db.scalar(
                select(CashierShift).where(
                    CashierShift.company_id == company_id,
                    CashierShift.branch_id == branch_id,
                    CashierShift.user_id == user_id,
                    CashierShift.status == "open",
                )
            )

        if resolved_shift and required_location_id is not None and resolved_shift.location_id != required_location_id:
            raise ValueError("กะที่เปิดอยู่ไม่ได้ผูกกับคลัง STORE-STOCK กรุณาปิดกะเดิมแล้วเปิดใหม่")

        # 3. ถ้ายังไม่มีเลย → auto-create F&B shift ของ user ปัจจุบัน
        if not resolved_shift:
            # ตรวจ user นี้มี open shift อยู่แล้วไหม (ก่อน create เพื่อหลีกเลี่ยง unique constraint)
            existing_user_shift = await self.db.scalar(
                select(CashierShift).where(
                    CashierShift.company_id == company_id,
                    CashierShift.branch_id == branch_id,
                    CashierShift.user_id == user_id,
                    CashierShift.status == "open",
                )
            )
            if existing_user_shift:
                resolved_shift = existing_user_shift
            else:
                # หา location แรกของสาขา
                first_location = (
                    await self.db.get(StockLocation, required_location_id)
                    if required_location_id is not None
                    else await self.db.scalar(
                        select(StockLocation).where(
                            StockLocation.company_id == company_id,
                            StockLocation.branch_id == branch_id,
                            StockLocation.is_active.is_(True),
                            StockLocation.deleted_at.is_(None),
                        ).order_by(StockLocation.created_at).limit(1)
                    )
                )
                if not first_location:
                    raise ValueError("ไม่พบ Stock Location สำหรับสาขานี้ กรุณาสร้าง Location ก่อน")

                resolved_shift = CashierShift(
                    company_id=company_id,
                    branch_id=branch_id,
                    user_id=user_id,
                    location_id=first_location.id,
                    opening_cash=Decimal("0"),
                    shift_number=f"FB{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
                )
                self.db.add(resolved_shift)
                await self.db.flush()

        resolved_location_id = required_location_id or location_id or resolved_shift.location_id
        return resolved_shift.id, resolved_location_id

    @staticmethod
    def _decode_recipe_stock_warnings(raw: str | None) -> list[str]:
        if not raw:
            return []
        try:
            value = json.loads(raw)
            return [str(item) for item in value] if isinstance(value, list) else [str(value)]
        except (TypeError, ValueError):
            return [raw]

    async def checkout_session(
        self,
        session: DiningSession,
        company_id: uuid.UUID,
        branch_id: uuid.UUID,
        user_id: uuid.UUID,
        payload: SessionCheckoutRequest,
    ) -> SessionCheckoutResult:
        from app.services.sale_service import SaleService

        # resolve shift + location (auto-detect ถ้าไม่ได้ระบุ)
        resolved_shift_id, resolved_location_id = await self._resolve_shift_and_location(
            company_id, branch_id, user_id,
            payload.shift_id, payload.location_id,
        )

        # รวบรวม order items ทั้งหมดจาก session
        await self.db.refresh(session)
        full_session = await self.get_session(session.id)
        if not full_session:
            raise ValueError("Session not found")

        all_items: list[DiningOrderItem] = []
        for order in full_session.orders:
            if order.status != "cancelled":
                all_items.extend([item for item in order.items if item.status != "cancelled"])

        if not all_items:
            raise ValueError("ไม่มีรายการอาหารในออเดอร์นี้")

        # สร้าง CartItems พร้อม vat info จาก Product
        cart_items: list[CartItem] = []
        for item in all_items:
            product = await self.db.get(Product, item.product_id)
            vat_type = product.vat_type if product else "included"
            vat_rate = Decimal(str(product.vat_rate)) if product else Decimal("7")
            cart_items.append(CartItem(
                product_id=item.product_id,
                variant_id=None,
                qty=Decimal(item.qty),
                unit_price=item.unit_price,
                original_price=item.unit_price,
                discount_amount=Decimal("0"),
                discount_type="amount",
                vat_type=vat_type,
                vat_rate=vat_rate,
            ))

        # สร้าง payment rows
        payment_rows: list[PaymentCreateRequest] = []
        if payload.payments:
            for p in payload.payments:
                payment_rows.append(PaymentCreateRequest(
                    payment_method=p.get("payment_method", payload.payment_method),
                    amount=Decimal(str(p.get("amount", 0))),
                    reference_no=p.get("reference_no"),
                ))
        else:
            payment_rows.append(PaymentCreateRequest(
                payment_method=payload.payment_method,
                amount=payload.paid_amount,
                reference_no=None,
            ))

        # customer info — fallback จาก session
        customer_name = payload.customer_name or session.customer_name
        customer_phone = payload.customer_phone or session.customer_phone

        note_parts = ["F&B"]
        source_type = "quick_service" if session.table_id is None else "dine_in"
        note_parts.append("Quick Service" if source_type == "quick_service" else "Dine-in")
        if session.queue_number:
            note_parts.append(f"คิว {str(session.queue_number).zfill(3)}")
        table = await self.db.get(DiningTable, session.table_id) if session.table_id else None
        if table:
            note_parts.append(f"โต๊ะ {table.name}")
        if payload.note:
            note_parts.append(payload.note)

        create_request = CreateSaleRequest(
            shift_id=resolved_shift_id,
            location_id=resolved_location_id,
            items=cart_items,
            discount_amount=payload.discount_amount,
            discount_type="amount",
            payment_method=payload.payment_method,
            payments=payment_rows,
            paid_amount=payload.paid_amount,
            customer_name=customer_name,
            customer_phone=customer_phone,
            customer_tax_id=payload.customer_tax_id,
            customer_id=payload.customer_id,
            note=" | ".join(note_parts) if note_parts else None,
        )

        sale_svc = SaleService(self.db)
        sale_order = await sale_svc.create_sale(company_id, branch_id, user_id, create_request)

        # ปิด session
        await self.close_session(session, sale_order_id=sale_order.id)

        return SessionCheckoutResult(
            sale_order_id=sale_order.id,
            order_number=sale_order.order_number,
            total_amount=sale_order.total_amount,
            paid_amount=sale_order.paid_amount,
            change_amount=sale_order.change_amount,
            session_id=session.id,
            table_name=table.name if table else None,
            queue_number=session.queue_number,
            source_type=source_type,
            customer_name=customer_name,
            customer_phone=customer_phone,
            payment_method=payload.payment_method,
            note=sale_order.note,
        )

    async def get_public_order_status(self, session_id: uuid.UUID) -> PublicOrderStatus | None:
        session = await self.get_session(session_id)
        if not session:
            return None
        items: list[DiningOrderItemRead] = []
        orders: list[PublicOrderHistory] = []
        total_item_count = 0
        total_amount = Decimal("0")
        for order in sorted(session.orders, key=lambda row: row.created_at):
            order_items: list[DiningOrderItemRead] = []
            subtotal = Decimal("0")
            for item in order.items:
                item_read = DiningOrderItemRead(
                    id=item.id,
                    product_id=item.product_id,
                    product_name=item.product_name,
                    qty=item.qty,
                    unit_price=item.unit_price,
                    special_request=item.special_request,
                    status=item.status,
                )
                items.append(item_read)
                order_items.append(item_read)
                if order.status != "cancelled" and item.status != "cancelled":
                    total_item_count += item.qty
                    line_total = item.unit_price * item.qty
                    subtotal += line_total
                    total_amount += line_total
            orders.append(PublicOrderHistory(
                id=order.id,
                order_number=order.order_number,
                status=order.status,
                note=order.note,
                created_at=order.created_at.isoformat(),
                subtotal=subtotal,
                items=order_items,
            ))
        return PublicOrderStatus(
            session_id=session.id,
            queue_number=session.queue_number,
            session_status=session.status,
            items=items,
            orders=orders,
            total_item_count=total_item_count,
            total_amount=total_amount,
        )
