from __future__ import annotations

from datetime import date
from decimal import Decimal

from pydantic import ConfigDict

from app.schemas import BaseSchema
from app.schemas.pos import SaleOrderRead, ShiftRead


class DailySalesSummary(BaseSchema):
    date: date
    date_thai: str
    total_orders: int
    total_amount: Decimal
    total_vat: Decimal
    total_discount: Decimal
    avg_order_value: Decimal
    by_payment_method: dict[str, Decimal]


class SalesRangeSummary(BaseSchema):
    date_from: date
    date_to: date
    days: list[DailySalesSummary]
    grand_total_orders: int
    grand_total_amount: Decimal
    grand_total_vat: Decimal
    grand_total_discount: Decimal
    by_payment_method: dict[str, Decimal]


class TopProductItem(BaseSchema):
    product_id: str
    product_name: str
    sku: str
    total_qty: Decimal
    total_amount: Decimal
    order_count: int


class TopProductsReport(BaseSchema):
    date_from: date
    date_to: date
    items: list[TopProductItem]


class HourlySales(BaseSchema):
    hour: int
    total_orders: int
    total_amount: Decimal


class ShiftSummary(BaseSchema):
    shift: ShiftRead
    sales: list[SaleOrderRead]
    voided: list[SaleOrderRead]
    daily_summary: DailySalesSummary
    by_payment_method: dict[str, Decimal]
    cashier_name: str
    branch_name: str
    location_name: str


class DashboardStats(BaseSchema):
    today_orders: int
    today_sales: Decimal
    today_vat: Decimal
    today_avg_order: Decimal
    open_shifts_count: int
    low_stock_count: int
    total_products: int
    compared_yesterday_pct: Decimal | None = None

    model_config = ConfigDict(from_attributes=True)
