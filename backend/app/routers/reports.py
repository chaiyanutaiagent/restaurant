from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any
import uuid

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.dependencies import TokenData, require_permission
from app.schemas.report import DashboardStats
from app.services.report_service import ReportService
from app.utils.thai_date import format_thai_date

router = APIRouter(prefix="/api/v1/reports", tags=["reports"])


def ok(data: Any, meta: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"data": data, "meta": {"version": settings.app_version, **(meta or {})}, "error": None}


def bkk_today() -> date:
    from zoneinfo import ZoneInfo

    return datetime.now(ZoneInfo("Asia/Bangkok")).date()


def shift_summary_html(summary) -> str:
    payment_rows = "".join(
        f"<tr><td>{method}</td><td style='text-align:right'>{amount:,.2f}</td></tr>"
        for method, amount in summary.by_payment_method.items()
    )
    order_rows = "".join(
        f"<tr><td>{order.order_number}</td><td>{format_thai_date(order.created_at, 'short')}</td>"
        f"<td style='text-align:right'>{Decimal(order.total_amount):,.2f}</td><td>{order.status}</td></tr>"
        for order in summary.sales + summary.voided
    )
    return f"""
    <html>
      <head>
        <meta charset="utf-8" />
        <style>
          body {{ font-family: sans-serif; padding: 24px; }}
          h1, h2 {{ margin-bottom: 8px; }}
          table {{ width: 100%; border-collapse: collapse; margin-top: 12px; }}
          th, td {{ border: 1px solid #ccc; padding: 8px; font-size: 12px; }}
          .summary {{ display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px; margin-top: 16px; }}
          .box {{ border: 1px solid #ddd; padding: 12px; border-radius: 8px; }}
        </style>
      </head>
      <body>
        <h1>Shift Summary {summary.shift.shift_number}</h1>
        <p>{summary.branch_name} / {summary.location_name}</p>
        <p>Cashier: {summary.cashier_name}</p>
        <div class="summary">
          <div class="box">ยอดขาย: {Decimal(summary.daily_summary.total_amount):,.2f}</div>
          <div class="box">จำนวนบิล: {summary.daily_summary.total_orders}</div>
          <div class="box">ยกเลิก: {len(summary.voided)}</div>
          <div class="box">VAT: {Decimal(summary.daily_summary.total_vat):,.2f}</div>
        </div>
        <h2>Payments</h2>
        <table>
          <thead><tr><th>Method</th><th>Amount</th></tr></thead>
          <tbody>{payment_rows}</tbody>
        </table>
        <h2>Orders</h2>
        <table>
          <thead><tr><th>เลขบิล</th><th>เวลา</th><th>ยอด</th><th>สถานะ</th></tr></thead>
          <tbody>{order_rows}</tbody>
        </table>
      </body>
    </html>
    """


@router.get("/dashboard")
async def get_dashboard(
    branch_id: uuid.UUID | None = Query(default=None),
    current: TokenData = Depends(require_permission("pos.report.view")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    stats = await ReportService(db).get_dashboard_stats(current.company_id, branch_id)
    return ok(DashboardStats.model_validate(stats).model_dump())


@router.get("/sales/daily")
async def get_daily_sales(
    date_value: date | None = Query(default=None, alias="date"),
    branch_id: uuid.UUID | None = Query(default=None),
    current: TokenData = Depends(require_permission("pos.report.view")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    summary = await ReportService(db).get_daily_summary(current.company_id, date_value or bkk_today(), branch_id)
    return ok(summary.model_dump())


@router.get("/sales/range")
async def get_sales_range(
    date_from: date = Query(...),
    date_to: date = Query(...),
    branch_id: uuid.UUID | None = Query(default=None),
    current: TokenData = Depends(require_permission("pos.report.view")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    summary = await ReportService(db).get_sales_range(current.company_id, date_from, date_to, branch_id)
    return ok(summary.model_dump())


@router.get("/sales/hourly")
async def get_hourly_sales(
    date_value: date | None = Query(default=None, alias="date"),
    branch_id: uuid.UUID | None = Query(default=None),
    current: TokenData = Depends(require_permission("pos.report.view")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    rows = await ReportService(db).get_hourly_sales(current.company_id, date_value or bkk_today(), branch_id)
    return ok([row.model_dump() for row in rows])


@router.get("/products/top")
async def get_top_products(
    date_from: date = Query(...),
    date_to: date = Query(...),
    branch_id: uuid.UUID | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    current: TokenData = Depends(require_permission("pos.report.view")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    report = await ReportService(db).get_top_products(current.company_id, date_from, date_to, branch_id, limit)
    return ok(report.model_dump())


@router.get("/shifts/{shift_id}")
async def get_shift_summary(
    shift_id: uuid.UUID,
    current: TokenData = Depends(require_permission("pos.report.view")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    summary = await ReportService(db).get_shift_summary(shift_id, current.company_id)
    return ok(summary.model_dump())


@router.get("/shifts/{shift_id}/pdf")
async def get_shift_summary_pdf(
    shift_id: uuid.UUID,
    current: TokenData = Depends(require_permission("pos.report.view")),
    db: AsyncSession = Depends(get_db),
) -> Response:
    summary = await ReportService(db).get_shift_summary(shift_id, current.company_id)
    html = shift_summary_html(summary)
    filename = f"shift_{summary.shift.shift_number}"
    try:
        from weasyprint import HTML

        pdf_bytes = HTML(string=html).write_pdf()
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename={filename}.pdf"},
        )
    except Exception:
        return Response(
            content=html.encode("utf-8"),
            media_type="text/html; charset=utf-8",
            headers={"Content-Disposition": f"attachment; filename={filename}.html"},
        )
