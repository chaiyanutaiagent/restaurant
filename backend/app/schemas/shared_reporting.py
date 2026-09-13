from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal
import uuid

from app.schemas import BaseSchema


ReportingModuleKey = Literal["restaurant_pos", "takeaway_pos", "retail_pos"]
ReportingFreshnessStatus = Literal["disabled", "no_data", "current", "stale", "degraded"]


class SharedSalesMetrics(BaseSchema):
    order_count: int
    void_count: int
    refund_count: int
    gross_sales: Decimal
    discount_amount: Decimal
    tax_amount: Decimal
    refund_amount: Decimal
    net_sales: Decimal


class SharedSalesModuleSummary(SharedSalesMetrics):
    module_key: ReportingModuleKey


class SharedSalesWorkspaceSummary(SharedSalesMetrics):
    module_key: ReportingModuleKey
    brand_id: uuid.UUID
    brand_name: str
    branch_id: uuid.UUID
    branch_name: str


class SharedSalesDailySummary(SharedSalesMetrics):
    business_date: date


class SharedSalesDocumentRead(BaseSchema):
    module_key: ReportingModuleKey
    brand_id: uuid.UUID
    brand_name: str
    branch_id: uuid.UUID
    branch_name: str
    business_date: date
    source_document_type: str
    source_document_id: uuid.UUID
    document_number: str | None
    source_status: str
    gross_sales: Decimal
    refund_amount: Decimal
    net_sales: Decimal
    entry_route: str


class SharedReportingFreshness(BaseSchema):
    status: ReportingFreshnessStatus
    projector_enabled: bool
    projection_mode: Literal["shadow"] = "shadow"
    is_source_of_truth: bool = False
    last_projected_at: datetime | None
    last_polled_at: datetime | None
    lag_seconds: int | None
    failed_sources: list[str]


class SharedSalesReportRead(BaseSchema):
    company_id: uuid.UUID
    date_from: date
    date_to: date
    generated_at: datetime
    freshness: SharedReportingFreshness
    totals: SharedSalesMetrics
    modules: list[SharedSalesModuleSummary]
    workspaces: list[SharedSalesWorkspaceSummary]
    daily: list[SharedSalesDailySummary]
    recent_documents: list[SharedSalesDocumentRead]
