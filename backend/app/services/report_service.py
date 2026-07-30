from __future__ import annotations

from datetime import date, datetime, time, timedelta
from decimal import Decimal, ROUND_HALF_UP
import uuid
from zoneinfo import ZoneInfo

from fastapi import HTTPException, status
from sqlalchemy import Date, Integer, case, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.branch import Branch
from app.models.pos import CashierShift, Payment, SaleOrder, SaleOrderItem
from app.models.product import Product
from app.models.stock import StockLocation, StockBalance
from app.models.user import User
from app.schemas.pos import SaleOrderRead, ShiftRead
from app.schemas.report import (
    DailySalesSummary,
    DashboardStats,
    HourlySales,
    SalesRangeSummary,
    ShiftSummary,
    TopProductItem,
    TopProductsReport,
)
from app.utils.thai_date import format_thai_date

BKK = ZoneInfo("Asia/Bangkok")
TWOPLACES = Decimal("0.01")


def q2(value: Decimal | int | float | None) -> Decimal:
    return Decimal(value or 0).quantize(TWOPLACES, rounding=ROUND_HALF_UP)


def bkk_day_expr():
    return cast(func.timezone("Asia/Bangkok", SaleOrder.created_at), Date)


def bkk_time_range(target_date: date) -> tuple[datetime, datetime]:
    start_local = datetime.combine(target_date, time.min, tzinfo=BKK)
    end_local = datetime.combine(target_date, time.max, tzinfo=BKK)
    return start_local.astimezone(ZoneInfo("UTC")), end_local.astimezone(ZoneInfo("UTC"))


def payment_total_expr():
    return case(
        (
            Payment.payment_method == "cash",
            func.coalesce(Payment.amount, 0) - func.coalesce(SaleOrder.change_amount, 0),
        ),
        else_=func.coalesce(Payment.amount, 0),
    )


class ReportService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_daily_summary(
        self,
        company_id: uuid.UUID,
        target_date: date,
        branch_id: uuid.UUID | None = None,
    ) -> DailySalesSummary:
        filters = [
            SaleOrder.company_id == company_id,
            bkk_day_expr() == target_date,
            SaleOrder.status != "voided",
        ]
        if branch_id is not None:
            filters.append(SaleOrder.branch_id == branch_id)

        totals = (
            await self.db.execute(
                select(
                    func.count(SaleOrder.id),
                    func.coalesce(func.sum(SaleOrder.total_amount), 0),
                    func.coalesce(func.sum(SaleOrder.vat_amount), 0),
                    func.coalesce(func.sum(SaleOrder.discount_amount), 0),
                ).where(*filters)
            )
        ).one()
        total_orders = int(totals[0] or 0)
        total_amount = q2(totals[1])
        total_vat = q2(totals[2])
        total_discount = q2(totals[3])
        avg_order_value = q2((total_amount / total_orders) if total_orders else 0)

        payment_filters = [
            SaleOrder.company_id == company_id,
            bkk_day_expr() == target_date,
            SaleOrder.status != "voided",
        ]
        if branch_id is not None:
            payment_filters.append(SaleOrder.branch_id == branch_id)
        payment_rows = await self.db.execute(
            select(
                Payment.payment_method,
                func.coalesce(func.sum(payment_total_expr()), 0),
            )
            .join(SaleOrder, SaleOrder.id == Payment.order_id)
            .where(*payment_filters)
            .group_by(Payment.payment_method)
        )
        by_payment_method = {method: q2(amount) for method, amount in payment_rows.all()}

        return DailySalesSummary(
            date=target_date,
            date_thai=format_thai_date(datetime.combine(target_date, time.min), "short"),
            total_orders=total_orders,
            total_amount=total_amount,
            total_vat=total_vat,
            total_discount=total_discount,
            avg_order_value=avg_order_value,
            by_payment_method=by_payment_method,
        )

    async def get_sales_range(
        self,
        company_id: uuid.UUID,
        date_from: date,
        date_to: date,
        branch_id: uuid.UUID | None = None,
    ) -> SalesRangeSummary:
        if date_to < date_from:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="date_to must be on or after date_from")
        if (date_to - date_from).days > 92:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="date range cannot exceed 93 days")

        filters = [
            SaleOrder.company_id == company_id,
            bkk_day_expr() >= date_from,
            bkk_day_expr() <= date_to,
            SaleOrder.status != "voided",
        ]
        if branch_id is not None:
            filters.append(SaleOrder.branch_id == branch_id)

        daily_rows = await self.db.execute(
            select(
                bkk_day_expr().label("day"),
                func.count(SaleOrder.id),
                func.coalesce(func.sum(SaleOrder.total_amount), 0),
                func.coalesce(func.sum(SaleOrder.vat_amount), 0),
                func.coalesce(func.sum(SaleOrder.discount_amount), 0),
            )
            .where(*filters)
            .group_by("day")
            .order_by("day")
        )
        payment_rows = await self.db.execute(
            select(
                Payment.payment_method,
                func.coalesce(func.sum(payment_total_expr()), 0),
            )
            .join(SaleOrder, SaleOrder.id == Payment.order_id)
            .where(*filters)
            .group_by(Payment.payment_method)
        )

        daily_map = {
            row.day: {
                "total_orders": int(row[1] or 0),
                "total_amount": q2(row[2]),
                "total_vat": q2(row[3]),
                "total_discount": q2(row[4]),
            }
            for row in daily_rows
        }
        by_payment_method = {method: q2(amount) for method, amount in payment_rows.all()}

        days: list[DailySalesSummary] = []
        current = date_from
        while current <= date_to:
            metrics = daily_map.get(
                current,
                {
                    "total_orders": 0,
                    "total_amount": q2(0),
                    "total_vat": q2(0),
                    "total_discount": q2(0),
                },
            )
            total_orders = metrics["total_orders"]
            total_amount = metrics["total_amount"]
            days.append(
                DailySalesSummary(
                    date=current,
                    date_thai=format_thai_date(datetime.combine(current, time.min), "short"),
                    total_orders=total_orders,
                    total_amount=total_amount,
                    total_vat=metrics["total_vat"],
                    total_discount=metrics["total_discount"],
                    avg_order_value=q2((total_amount / total_orders) if total_orders else 0),
                    by_payment_method={},
                )
            )
            current += timedelta(days=1)

        return SalesRangeSummary(
            date_from=date_from,
            date_to=date_to,
            days=days,
            grand_total_orders=sum(item.total_orders for item in days),
            grand_total_amount=q2(sum(item.total_amount for item in days)),
            grand_total_vat=q2(sum(item.total_vat for item in days)),
            grand_total_discount=q2(sum(item.total_discount for item in days)),
            by_payment_method=by_payment_method,
        )

    async def get_top_products(
        self,
        company_id: uuid.UUID,
        date_from: date,
        date_to: date,
        branch_id: uuid.UUID | None = None,
        limit: int = 20,
    ) -> TopProductsReport:
        if date_to < date_from:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="date_to must be on or after date_from")

        filters = [
            SaleOrder.company_id == company_id,
            bkk_day_expr() >= date_from,
            bkk_day_expr() <= date_to,
            SaleOrder.status != "voided",
        ]
        if branch_id is not None:
            filters.append(SaleOrder.branch_id == branch_id)

        rows = await self.db.execute(
            select(
                SaleOrderItem.product_id,
                SaleOrderItem.product_name,
                SaleOrderItem.sku,
                func.coalesce(func.sum(SaleOrderItem.qty), 0),
                func.coalesce(func.sum(SaleOrderItem.subtotal), 0),
                func.count(func.distinct(SaleOrderItem.order_id)),
            )
            .join(SaleOrder, SaleOrder.id == SaleOrderItem.order_id)
            .where(*filters)
            .group_by(SaleOrderItem.product_id, SaleOrderItem.product_name, SaleOrderItem.sku)
            .order_by(func.sum(SaleOrderItem.subtotal).desc())
            .limit(limit)
        )
        return TopProductsReport(
            date_from=date_from,
            date_to=date_to,
            items=[
                TopProductItem(
                    product_id=str(product_id),
                    product_name=product_name,
                    sku=sku,
                    total_qty=q2(total_qty),
                    total_amount=q2(total_amount),
                    order_count=int(order_count or 0),
                )
                for product_id, product_name, sku, total_qty, total_amount, order_count in rows.all()
            ],
        )

    async def get_hourly_sales(
        self,
        company_id: uuid.UUID,
        target_date: date,
        branch_id: uuid.UUID | None = None,
    ) -> list[HourlySales]:
        filters = [
            SaleOrder.company_id == company_id,
            bkk_day_expr() == target_date,
            SaleOrder.status != "voided",
        ]
        if branch_id is not None:
            filters.append(SaleOrder.branch_id == branch_id)

        hour_expr = cast(
            func.extract("hour", func.timezone("Asia/Bangkok", SaleOrder.created_at)),
            Integer,
        )
        rows = await self.db.execute(
            select(
                hour_expr.label("hour"),
                func.count(SaleOrder.id),
                func.coalesce(func.sum(SaleOrder.total_amount), 0),
            )
            .where(*filters)
            .group_by(hour_expr)
            .order_by(hour_expr)
        )
        values = {int(hour): (int(total_orders or 0), q2(total_amount)) for hour, total_orders, total_amount in rows.all()}
        return [
            HourlySales(
                hour=hour,
                total_orders=values.get(hour, (0, q2(0)))[0],
                total_amount=values.get(hour, (0, q2(0)))[1],
            )
            for hour in range(24)
        ]

    async def get_shift_summary(
        self,
        shift_id: uuid.UUID,
        company_id: uuid.UUID,
    ) -> ShiftSummary:
        shift = await self.db.scalar(
            select(CashierShift)
            .where(CashierShift.id == shift_id, CashierShift.company_id == company_id)
            .options(
                selectinload(CashierShift.orders).selectinload(SaleOrder.items),
                selectinload(CashierShift.orders).selectinload(SaleOrder.payments),
                selectinload(CashierShift.user),
                selectinload(CashierShift.branch),
                selectinload(CashierShift.location),
            )
        )
        if shift is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shift not found")

        sales = [order for order in shift.orders if order.status != "voided"]
        voided = [order for order in shift.orders if order.status == "voided"]
        by_payment_method: dict[str, Decimal] = {}
        for order in sales:
            for payment in order.payments:
                amount = Decimal(payment.amount or 0)
                if payment.payment_method == "cash":
                    amount -= Decimal(order.change_amount or 0)
                by_payment_method[payment.payment_method] = q2(
                    by_payment_method.get(payment.payment_method, 0) + amount
                )

        target_date = shift.opened_at.astimezone(BKK).date()
        total_orders = len(sales)
        total_amount = q2(sum(Decimal(order.total_amount or 0) for order in sales))
        total_vat = q2(sum(Decimal(order.vat_amount or 0) for order in sales))
        total_discount = q2(sum(Decimal(order.discount_amount or 0) for order in sales))
        daily_summary = DailySalesSummary(
            date=target_date,
            date_thai=format_thai_date(datetime.combine(target_date, time.min), "short"),
            total_orders=total_orders,
            total_amount=total_amount,
            total_vat=total_vat,
            total_discount=total_discount,
            avg_order_value=q2((total_amount / total_orders) if total_orders else 0),
            by_payment_method=by_payment_method,
        )

        return ShiftSummary(
            shift=ShiftRead.model_validate(shift),
            sales=[SaleOrderRead.model_validate(item) for item in sales],
            voided=[SaleOrderRead.model_validate(item) for item in voided],
            daily_summary=daily_summary,
            by_payment_method=by_payment_method,
            cashier_name=shift.user.display_name or shift.user.username,
            branch_name=shift.branch.name,
            location_name=shift.location.name,
        )

    async def get_dashboard_stats(
        self,
        company_id: uuid.UUID,
        branch_id: uuid.UUID | None = None,
    ) -> DashboardStats:
        now_bkk = datetime.now(BKK)
        today = now_bkk.date()
        yesterday = today - timedelta(days=1)
        today_summary = await self.get_daily_summary(company_id, today, branch_id)
        yesterday_summary = await self.get_daily_summary(company_id, yesterday, branch_id)

        open_shift_filters = [CashierShift.company_id == company_id, CashierShift.status == "open"]
        if branch_id is not None:
            open_shift_filters.append(CashierShift.branch_id == branch_id)
        open_shifts_count = await self.db.scalar(select(func.count(CashierShift.id)).where(*open_shift_filters)) or 0

        low_stock_filters = [
            StockBalance.company_id == company_id,
            Product.deleted_at.is_(None),
            Product.is_active.is_(True),
            Product.min_stock_qty > 0,
            StockBalance.qty_on_hand <= Product.min_stock_qty,
        ]
        if branch_id is not None:
            low_stock_filters.append(StockBalance.branch_id == branch_id)
        low_stock_count = await self.db.scalar(
            select(func.count(StockBalance.id)).join(Product, Product.id == StockBalance.product_id).where(*low_stock_filters)
        ) or 0

        product_filters = [Product.company_id == company_id, Product.deleted_at.is_(None), Product.is_active.is_(True)]
        total_products = await self.db.scalar(select(func.count(Product.id)).where(*product_filters)) or 0

        compared = None
        if yesterday_summary.total_amount > 0:
            compared = q2(((today_summary.total_amount - yesterday_summary.total_amount) / yesterday_summary.total_amount) * 100)

        return DashboardStats(
            today_orders=today_summary.total_orders,
            today_sales=today_summary.total_amount,
            today_vat=today_summary.total_vat,
            today_avg_order=today_summary.avg_order_value,
            open_shifts_count=int(open_shifts_count),
            low_stock_count=int(low_stock_count),
            total_products=int(total_products),
            compared_yesterday_pct=compared,
        )
