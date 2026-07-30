from __future__ import annotations

from datetime import date, datetime, time, timezone
from decimal import Decimal, ROUND_HALF_UP
import logging
import uuid
from zoneinfo import ZoneInfo

from fastapi import HTTPException, status
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.audit import AuditLog
from app.models.product import Product, ProductVariant, Unit
from app.models.stock import StockBalance, StockMovement
from app.models.stock_count import StockCountItem, StockCountSession
from app.schemas.stock_count import (
    BatchUpdateCountRequest,
    CompleteSessionRequest,
    CreateCountSessionRequest,
    UpdateCountItemRequest,
    VarianceReport,
    VarianceReportItem,
)
from app.services.accounting_service import AccountingService
from app.services.stock_service import StockService
from app.utils.thai_date import format_thai_date

TWOPLACES = Decimal("0.01")
FOURPLACES = Decimal("0.0001")
BANGKOK = ZoneInfo("Asia/Bangkok")
logger = logging.getLogger(__name__)


def q2(value: Decimal | int | float | None) -> Decimal:
    return Decimal(value or 0).quantize(TWOPLACES, rounding=ROUND_HALF_UP)


def q4(value: Decimal | int | float | None) -> Decimal:
    return Decimal(value or 0).quantize(FOURPLACES, rounding=ROUND_HALF_UP)


class StockCountService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.stock_service = StockService(db)

    async def create_session(
        self, company_id: uuid.UUID, user_id: uuid.UUID, data: CreateCountSessionRequest
    ) -> StockCountSession:
        branch = await self.stock_service._get_branch(data.branch_id, company_id)
        location = await self.stock_service._get_location(data.location_id, company_id)
        if location.branch_id != branch.id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Location does not belong to branch")

        existing = await self.db.scalar(
            select(StockCountSession.id).where(
                StockCountSession.company_id == company_id,
                StockCountSession.location_id == location.id,
                StockCountSession.status == "in_progress",
            )
        )
        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Stock count session already in progress at this location",
            )

        session_date = data.count_date or datetime.now(BANGKOK).date()
        session_number = await self._generate_session_number(company_id, session_date)
        session = StockCountSession(
            company_id=company_id,
            branch_id=branch.id,
            location_id=location.id,
            session_number=session_number,
            status="draft",
            count_date=session_date,
            created_by=user_id,
            note=data.note,
        )
        self.db.add(session)
        await self.db.flush()

        statement = (
            select(
                StockBalance,
                Product.name,
                Product.sku,
                ProductVariant.name,
                ProductVariant.sku,
                Unit.code,
            )
            .join(Product, Product.id == StockBalance.product_id)
            .outerjoin(ProductVariant, ProductVariant.id == StockBalance.variant_id)
            .outerjoin(Unit, Unit.id == Product.unit_id)
            .where(
                StockBalance.location_id == location.id,
                StockBalance.company_id == company_id,
                Product.deleted_at.is_(None),
            )
            .order_by(Product.name.asc(), ProductVariant.name.asc())
        )
        if data.product_ids:
            statement = statement.where(StockBalance.product_id.in_(data.product_ids))
        else:
            statement = statement.where(StockBalance.qty_on_hand > 0)

        rows = (await self.db.execute(statement)).all()
        items: list[StockCountItem] = []
        for balance, product_name, product_sku, variant_name, variant_sku, unit_code in rows:
            items.append(
                StockCountItem(
                    session_id=session.id,
                    company_id=company_id,
                    product_id=balance.product_id,
                    variant_id=balance.variant_id,
                    product_name=product_name if not variant_name else f"{product_name} - {variant_name}",
                    sku=variant_sku or product_sku,
                    unit_code=unit_code,
                    expected_qty=q4(balance.qty_on_hand),
                    cost_per_unit=q4(balance.cost_per_unit),
                )
            )
        if items:
            self.db.add_all(items)
        session.total_items = len(items)

        self._audit(
            company_id=company_id,
            branch_id=session.branch_id,
            user_id=user_id,
            action="inventory.stock_count.create",
            resource_id=str(session.id),
            new_value={"session_number": session.session_number, "total_items": len(items)},
        )
        await self.db.commit()
        return await self.get_session(session.id, company_id)

    async def start_session(self, session_id: uuid.UUID, company_id: uuid.UUID, user_id: uuid.UUID) -> StockCountSession:
        session = await self._get_session_entity(session_id, company_id, load_items=True)
        if session.status != "draft":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Only draft sessions can be started")
        session.status = "in_progress"
        session.started_at = datetime.now(timezone.utc)
        self._audit(company_id, session.branch_id, user_id, "inventory.stock_count.start", str(session.id))
        await self.db.commit()
        return await self.get_session(session.id, company_id)

    async def update_count_item(
        self,
        session_id: uuid.UUID,
        item_id: uuid.UUID,
        company_id: uuid.UUID,
        user_id: uuid.UUID,
        data: UpdateCountItemRequest,
    ) -> StockCountItem:
        session = await self._get_session_entity(session_id, company_id, load_items=False)
        if session.status != "in_progress":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Session is not in progress")

        item = await self.db.scalar(
            select(StockCountItem).where(
                StockCountItem.id == item_id,
                StockCountItem.session_id == session.id,
                StockCountItem.company_id == company_id,
            )
        )
        if item is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Count item not found")

        self._apply_item_count(item, user_id, data.actual_qty, data.note)
        await self.db.commit()
        await self.db.refresh(item)
        return item

    async def batch_update_items(
        self,
        session_id: uuid.UUID,
        company_id: uuid.UUID,
        user_id: uuid.UUID,
        data: BatchUpdateCountRequest,
    ) -> list[StockCountItem]:
        session = await self._get_session_entity(session_id, company_id, load_items=True)
        if session.status != "in_progress":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Session is not in progress")

        item_map = {item.id: item for item in session.items}
        updated_items: list[StockCountItem] = []
        for payload in data.items:
            item = item_map.get(payload.item_id)
            if item is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Count item not found")
            self._apply_item_count(item, user_id, payload.actual_qty, payload.note)
            updated_items.append(item)

        await self.db.commit()
        return updated_items

    async def complete_session(
        self,
        session_id: uuid.UUID,
        company_id: uuid.UUID,
        user_id: uuid.UUID,
        data: CompleteSessionRequest,
    ) -> StockCountSession:
        session = await self._get_session_entity(session_id, company_id, load_items=True)
        if session.status != "in_progress":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Session is not in progress")

        for item in session.items:
            if item.actual_qty is None:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"สินค้า {item.product_name} ยังไม่ได้นับ")

        matched = 0
        over = 0
        short = 0
        total_variance_value = Decimal("0")
        for item in session.items:
            variance_qty = q4(item.variance_qty)
            variance_value = q2(item.variance_value)
            total_variance_value += abs(variance_value)
            if variance_qty == 0:
                matched += 1
            elif variance_qty > 0:
                over += 1
            else:
                short += 1

        if data.apply_adjustments:
            for item in session.items:
                variance_qty = q4(item.variance_qty)
                if variance_qty == 0:
                    continue
                balance = await self.stock_service._get_or_create_balance(
                    company_id=company_id,
                    branch_id=session.branch_id,
                    location_id=session.location_id,
                    product_id=item.product_id,
                    variant_id=item.variant_id,
                )
                await self.stock_service._record_movement(
                    balance=balance,
                    movement_type="adjust",
                    qty_delta=variance_qty,
                    user_id=user_id,
                    note=f"Stock count adjustment: SC {session.session_number}",
                    reference_type="StockCountSession",
                    reference_id=str(session.id),
                )
                movement_record = await self.db.scalar(
                    select(StockMovement)
                    .where(
                        StockMovement.reference_type == "StockCountSession",
                        StockMovement.reference_id == str(session.id),
                        StockMovement.product_id == item.product_id,
                        StockMovement.variant_id == item.variant_id,
                        StockMovement.movement_type == "adjust",
                    )
                    .order_by(StockMovement.created_at.desc())
                )
                try:
                    accounting_svc = AccountingService(self.db)
                    if movement_record is not None:
                        await accounting_svc.post_stock_adjustment(movement_record, company_id, user_id)
                except Exception as e:
                    logger.error(f"Accounting post failed for movement: {e}")
                item.is_adjusted = True

        session.items_matched = matched
        session.items_over = over
        session.items_short = short
        session.total_variance_value = q2(total_variance_value)
        session.status = "completed"
        session.completed_at = datetime.now(timezone.utc)
        session.completed_by = user_id
        if data.note:
            session.note = "\n".join(filter(None, [session.note, data.note]))

        self._audit(
            company_id=company_id,
            branch_id=session.branch_id,
            user_id=user_id,
            action="inventory.stock_count.complete",
            resource_id=str(session.id),
            new_value={"adjusted": data.apply_adjustments, "variances": over + short},
        )
        await self.db.commit()
        return await self.get_session(session.id, company_id)

    async def cancel_session(self, session_id: uuid.UUID, company_id: uuid.UUID, user_id: uuid.UUID) -> StockCountSession:
        session = await self._get_session_entity(session_id, company_id, load_items=True)
        if session.status == "completed":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Cannot cancel completed session")
        if session.status == "cancelled":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Session already cancelled")
        if session.status not in {"draft", "in_progress"}:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Session cannot be cancelled")

        session.status = "cancelled"
        session.cancelled_at = datetime.now(timezone.utc)
        self._audit(company_id, session.branch_id, user_id, "inventory.stock_count.cancel", str(session.id))
        await self.db.commit()
        return await self.get_session(session.id, company_id)

    async def get_session(self, session_id: uuid.UUID, company_id: uuid.UUID) -> StockCountSession:
        return await self._get_session_entity(session_id, company_id, load_items=True)

    async def list_sessions(
        self,
        company_id: uuid.UUID,
        branch_id: uuid.UUID | None = None,
        location_id: uuid.UUID | None = None,
        status: str | None = None,
        page: int = 1,
        limit: int = 20,
        location_ids: tuple[uuid.UUID, ...] | None = None,
    ) -> tuple[list[StockCountSession], int]:
        filters = [StockCountSession.company_id == company_id]
        if branch_id is not None:
            filters.append(StockCountSession.branch_id == branch_id)
        if location_id is not None:
            filters.append(StockCountSession.location_id == location_id)
        if location_ids is not None:
            filters.append(StockCountSession.location_id.in_(location_ids))
        if status:
            filters.append(StockCountSession.status == status)

        total = await self.db.scalar(select(func.count(StockCountSession.id)).where(*filters)) or 0
        rows = await self.db.scalars(
            select(StockCountSession)
            .where(*filters)
            .order_by(StockCountSession.count_date.desc(), StockCountSession.created_at.desc())
            .offset((page - 1) * limit)
            .limit(limit)
        )
        return rows.all(), int(total)

    async def get_variance_report(self, session_id: uuid.UUID, company_id: uuid.UUID) -> VarianceReport:
        session = await self.db.scalar(
            select(StockCountSession)
            .where(StockCountSession.id == session_id, StockCountSession.company_id == company_id)
            .options(
                selectinload(StockCountSession.items),
                selectinload(StockCountSession.branch),
                selectinload(StockCountSession.location),
                selectinload(StockCountSession.completer),
            )
        )
        if session is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Stock count session not found")
        if session.status != "completed":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Variance report available only for completed sessions")

        variances: list[VarianceReportItem] = []
        matched_items: list[VarianceReportItem] = []
        for item in session.items:
            actual_qty = q4(item.actual_qty)
            variance_qty = q4(item.variance_qty)
            variance_value = q2(item.variance_value)
            if item.expected_qty and Decimal(item.expected_qty) != 0:
                variance_pct = q2(abs(variance_qty / Decimal(item.expected_qty) * Decimal("100")))
            else:
                variance_pct = q2(Decimal("100") if actual_qty > 0 else Decimal("0"))
            row = VarianceReportItem(
                product_name=item.product_name,
                sku=item.sku,
                unit_code=item.unit_code,
                expected_qty=q4(item.expected_qty),
                actual_qty=actual_qty,
                variance_qty=variance_qty,
                variance_value=variance_value,
                variance_pct=variance_pct,
            )
            if variance_qty == 0:
                matched_items.append(row)
            else:
                variances.append(row)

        variances.sort(key=lambda row: abs(row.variance_value), reverse=True)
        matched_items.sort(key=lambda row: row.product_name.lower())
        completed_by_name = "-"
        if session.completer is not None:
            completed_by_name = session.completer.display_name or session.completer.username

        report = VarianceReport(
            session_number=session.session_number,
            location_name=session.location.name,
            branch_name=session.branch.name,
            count_date=session.count_date.isoformat(),
            count_date_thai=format_thai_date(datetime.combine(session.count_date, time.min), "long"),
            completed_by_name=completed_by_name,
            items_matched=session.items_matched,
            items_over=session.items_over,
            items_short=session.items_short,
            total_variance_value=q2(session.total_variance_value),
            variances=variances,
            matched_items=matched_items,
        )
        report.__dict__["adjustment_note"] = "ปรับสต็อกแล้ว" if any(item.is_adjusted for item in session.items) else "ยังไม่ได้ปรับสต็อก"
        return report

    async def get_count_sheet_data(self, session_id: uuid.UUID, company_id: uuid.UUID) -> dict:
        session = await self.db.scalar(
            select(StockCountSession)
            .where(StockCountSession.id == session_id, StockCountSession.company_id == company_id)
            .options(
                selectinload(StockCountSession.items),
                selectinload(StockCountSession.branch),
                selectinload(StockCountSession.location),
                selectinload(StockCountSession.company),
            )
        )
        if session is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Stock count session not found")
        return {
            "session": session,
            "items": sorted(session.items, key=lambda item: item.product_name.lower()),
            "branch_name": session.branch.name,
            "location_name": session.location.name,
            "company_name": session.company.name,
        }

    async def _get_session_entity(self, session_id: uuid.UUID, company_id: uuid.UUID, load_items: bool) -> StockCountSession:
        statement = select(StockCountSession).where(
            StockCountSession.id == session_id,
            StockCountSession.company_id == company_id,
        )
        if load_items:
            statement = statement.options(
                selectinload(StockCountSession.items),
                selectinload(StockCountSession.branch),
                selectinload(StockCountSession.location),
                selectinload(StockCountSession.completer),
                selectinload(StockCountSession.company),
            )
        session = await self.db.scalar(statement)
        if session is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Stock count session not found")
        return session

    async def _generate_session_number(self, company_id: uuid.UUID, session_date: date) -> str:
        prefix = f"SC{session_date.strftime('%Y%m%d')}"
        lock_key = hash(str(company_id) + session_date.strftime("%Y%m%d") + "STOCK_COUNT") % (2**31)
        await self.db.execute(text(f"SELECT pg_advisory_xact_lock({lock_key})"))
        count = await self.db.scalar(
            select(func.count(StockCountSession.id)).where(
                StockCountSession.company_id == company_id,
                StockCountSession.session_number.like(f"{prefix}-%"),
            )
        ) or 0
        return f"{prefix}-{int(count) + 1:04d}"

    def _apply_item_count(self, item: StockCountItem, user_id: uuid.UUID, actual_qty: Decimal, note: str | None) -> None:
        normalized_actual = q4(actual_qty)
        variance_qty = q4(normalized_actual - Decimal(item.expected_qty or 0))
        item.actual_qty = normalized_actual
        item.variance_qty = variance_qty
        item.variance_value = q2(variance_qty * Decimal(item.cost_per_unit or 0))
        item.counted_at = datetime.now(timezone.utc)
        item.counted_by = user_id
        item.note = note

    def _audit(
        self,
        company_id: uuid.UUID,
        branch_id: uuid.UUID,
        user_id: uuid.UUID,
        action: str,
        resource_id: str,
        new_value: dict | None = None,
    ) -> None:
        self.db.add(
            AuditLog(
                company_id=company_id,
                branch_id=branch_id,
                user_id=user_id,
                action=action,
                resource="StockCountSession",
                resource_id=resource_id,
                new_value=new_value,
            )
        )
