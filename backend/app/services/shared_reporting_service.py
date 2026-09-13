from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
import hashlib
import json
from typing import Literal
import uuid
from zoneinfo import ZoneInfo

from fastapi import HTTPException, status
from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.dependencies import TokenData
from app.models.branch import Branch
from app.models.integration import OperationalOutboxEvent
from app.models.platform import (
    CompanyReportingEventReceipt,
    CompanyReportingFact,
    CompanyReportingSourceState,
)
from app.models.pos import SaleOrder
from app.models.restaurant import Brand, BrandBranch
from app.models.takeaway import TakeawayOperationalOutbox, TakeawayOrder
from app.schemas.shared_reporting import (
    ReportingModuleKey,
    SharedReportingFreshness,
    SharedSalesDailySummary,
    SharedSalesDocumentRead,
    SharedSalesMetrics,
    SharedSalesModuleSummary,
    SharedSalesReportRead,
    SharedSalesWorkspaceSummary,
)


BANGKOK = ZoneInfo("Asia/Bangkok")
TWOPLACES = Decimal("0.01")
MAX_REPORT_DAYS = 93
MAX_FAILURE_ATTEMPTS = 5
LEGACY_EVENT_TYPES = {
    "restaurant.sale.completed.v1",
    "pos.sale.state.changed.v1",
}
TAKEAWAY_EVENT_TYPES = {
    "takeaway.sale.paid.v1",
    "takeaway.sale.refunded.v1",
}
MODULE_BY_BUSINESS_TYPE: dict[str, ReportingModuleKey] = {
    "restaurant": "restaurant_pos",
    "takeaway": "takeaway_pos",
    "retail_pos": "retail_pos",
}
ENTRY_ROUTE_BY_MODULE: dict[str, str] = {
    "restaurant_pos": "/restaurant",
    "takeaway_pos": "/takeaway",
    "retail_pos": "/pos",
}


def q2(value: Decimal | int | float | str | None) -> Decimal:
    return Decimal(value or 0).quantize(TWOPLACES, rounding=ROUND_HALF_UP)


def require_shared_reporting(current: TokenData) -> None:
    if "*" in current.permissions or "system.company.edit" in current.permissions:
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Permission required: system.company.edit",
    )


class ReportingProjectionError(RuntimeError):
    def __init__(self, code: str):
        self.code = code[:120]
        super().__init__(self.code)


@dataclass(frozen=True)
class SourceReportingEvent:
    source_stream: str
    event_id: uuid.UUID
    company_id: uuid.UUID
    brand_id: uuid.UUID | None
    branch_id: uuid.UUID | None
    event_type: str
    aggregate_type: str
    aggregate_id: uuid.UUID
    payload: dict[str, object]
    created_at: datetime

    @property
    def payload_sha256(self) -> str:
        encoded = json.dumps(
            self.payload,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ReportingProjection:
    company_id: uuid.UUID
    module_key: ReportingModuleKey
    business_type: Literal["restaurant", "takeaway", "retail_pos"]
    brand_id: uuid.UUID
    branch_id: uuid.UUID
    business_date: date
    source_document_type: Literal["sale_order", "takeaway_order"]
    source_document_id: uuid.UUID
    document_number: str | None
    currency: str
    gross_sales: Decimal
    discount_amount: Decimal
    tax_amount: Decimal
    refund_amount: Decimal
    net_sales: Decimal
    source_status: Literal["completed", "paid", "partially_refunded", "refunded", "voided"]
    source_event_at: datetime


@dataclass(frozen=True)
class ReportingBatchResult:
    discovered: int = 0
    projected: int = 0
    replayed: int = 0
    failed: int = 0
    dead_lettered: int = 0


def source_event(row: OperationalOutboxEvent | TakeawayOperationalOutbox, stream: str) -> SourceReportingEvent:
    return SourceReportingEvent(
        source_stream=stream,
        event_id=row.id,
        company_id=row.company_id,
        brand_id=row.brand_id,
        branch_id=row.branch_id,
        event_type=row.event_type,
        aggregate_type=row.aggregate_type,
        aggregate_id=row.aggregate_id,
        payload=dict(row.payload or {}),
        created_at=row.created_at,
    )


async def normalize_legacy_event(
    db: AsyncSession,
    event: SourceReportingEvent,
) -> ReportingProjection:
    if event.event_type not in LEGACY_EVENT_TYPES or event.aggregate_type != "SaleOrder":
        raise ReportingProjectionError("unsupported_legacy_event")
    order = await db.scalar(
        select(SaleOrder).where(
            SaleOrder.id == event.aggregate_id,
            SaleOrder.company_id == event.company_id,
        )
    )
    if order is None or order.branch_id != event.branch_id:
        raise ReportingProjectionError("source_document_missing")
    brand = None
    if event.brand_id is not None:
        brand = await db.scalar(
            select(Brand).where(
                Brand.id == event.brand_id,
                Brand.company_id == event.company_id,
            )
        )
    if brand is None:
        brand = await db.scalar(
            select(Brand)
            .join(BrandBranch, BrandBranch.brand_id == Brand.id)
            .where(
                Brand.company_id == event.company_id,
                BrandBranch.company_id == event.company_id,
                BrandBranch.branch_id == order.branch_id,
                BrandBranch.is_active.is_(True),
            )
            .order_by(Brand.created_at, Brand.id)
            .limit(1)
        )
    if brand is None or brand.business_type not in {"restaurant", "retail_pos"}:
        raise ReportingProjectionError("workspace_dimension_missing")
    if order.status not in {"completed", "partially_refunded", "refunded", "voided"}:
        raise ReportingProjectionError("unsupported_sale_status")
    total = q2(order.total_amount)
    discount = q2(order.discount_amount)
    refunded = q2(order.refund_amount)
    net = Decimal("0.00") if order.status == "voided" else q2(max(Decimal("0"), total - refunded))
    created_at = order.created_at if order.created_at.tzinfo else order.created_at.replace(tzinfo=timezone.utc)
    return ReportingProjection(
        company_id=order.company_id,
        module_key=MODULE_BY_BUSINESS_TYPE[brand.business_type],
        business_type=brand.business_type,  # type: ignore[arg-type]
        brand_id=brand.id,
        branch_id=order.branch_id,
        business_date=created_at.astimezone(BANGKOK).date(),
        source_document_type="sale_order",
        source_document_id=order.id,
        document_number=order.order_number,
        currency="THB",
        gross_sales=q2(total + discount),
        discount_amount=discount,
        tax_amount=q2(order.vat_amount),
        refund_amount=refunded,
        net_sales=net,
        source_status=order.status,  # type: ignore[arg-type]
        source_event_at=event.created_at,
    )


async def normalize_takeaway_event(
    db: AsyncSession,
    event: SourceReportingEvent,
) -> ReportingProjection:
    if event.event_type not in TAKEAWAY_EVENT_TYPES or event.aggregate_type != "order":
        raise ReportingProjectionError("unsupported_takeaway_event")
    order = await db.scalar(
        select(TakeawayOrder).where(
            TakeawayOrder.id == event.aggregate_id,
            TakeawayOrder.company_id == event.company_id,
        )
    )
    if (
        order is None
        or order.brand_id != event.brand_id
        or order.branch_id != event.branch_id
    ):
        raise ReportingProjectionError("source_document_missing")
    if order.status not in {"paid", "refunded"}:
        raise ReportingProjectionError("unsupported_sale_status")
    total = q2(order.total_amount)
    refunded = total if order.status == "refunded" else Decimal("0.00")
    return ReportingProjection(
        company_id=order.company_id,
        module_key="takeaway_pos",
        business_type="takeaway",
        brand_id=order.brand_id,
        branch_id=order.branch_id,
        business_date=order.business_date,
        source_document_type="takeaway_order",
        source_document_id=order.id,
        document_number=order.order_number,
        currency="THB",
        gross_sales=q2(total + Decimal(order.discount_amount or 0)),
        discount_amount=q2(order.discount_amount),
        tax_amount=q2(order.tax_amount),
        refund_amount=refunded,
        net_sales=Decimal("0.00") if order.status == "refunded" else total,
        source_status=order.status,  # type: ignore[arg-type]
        source_event_at=event.created_at,
    )


async def apply_reporting_projection(
    db: AsyncSession,
    event: SourceReportingEvent,
    projection: ReportingProjection,
) -> bool:
    if projection.company_id != event.company_id:
        raise ReportingProjectionError("company_dimension_mismatch")
    if MODULE_BY_BUSINESS_TYPE.get(projection.business_type) != projection.module_key:
        raise ReportingProjectionError("module_dimension_mismatch")
    if event.brand_id is not None and event.brand_id != projection.brand_id:
        raise ReportingProjectionError("brand_dimension_mismatch")
    if event.branch_id is not None and event.branch_id != projection.branch_id:
        raise ReportingProjectionError("branch_dimension_mismatch")
    brand_exists = await db.scalar(
        select(Brand.id).where(
            Brand.id == projection.brand_id,
            Brand.company_id == projection.company_id,
            Brand.business_type == projection.business_type,
        )
    )
    branch_exists = await db.scalar(
        select(Branch.id).where(
            Branch.id == projection.branch_id,
            Branch.company_id == projection.company_id,
        )
    )
    workspace_exists = await db.scalar(
        select(BrandBranch.id).where(
            BrandBranch.company_id == projection.company_id,
            BrandBranch.brand_id == projection.brand_id,
            BrandBranch.branch_id == projection.branch_id,
            BrandBranch.is_active.is_(True),
        )
    )
    if brand_exists is None or branch_exists is None or workspace_exists is None:
        raise ReportingProjectionError("platform_dimension_missing")
    existing_receipt = await db.scalar(
        select(CompanyReportingEventReceipt).where(
            CompanyReportingEventReceipt.source_stream == event.source_stream,
            CompanyReportingEventReceipt.source_event_id == event.event_id,
        )
    )
    if existing_receipt is not None:
        if existing_receipt.payload_sha256 != event.payload_sha256:
            raise ReportingProjectionError("event_payload_digest_conflict")
        return False

    fact = await db.scalar(
        select(CompanyReportingFact)
        .where(
            CompanyReportingFact.company_id == projection.company_id,
            CompanyReportingFact.module_key == projection.module_key,
            CompanyReportingFact.source_document_type == projection.source_document_type,
            CompanyReportingFact.source_document_id == projection.source_document_id,
        )
        .with_for_update()
    )
    values = {
        "company_id": projection.company_id,
        "module_key": projection.module_key,
        "business_type": projection.business_type,
        "brand_id": projection.brand_id,
        "branch_id": projection.branch_id,
        "business_date": projection.business_date,
        "source_document_type": projection.source_document_type,
        "source_document_id": projection.source_document_id,
        "document_number": projection.document_number,
        "currency": projection.currency,
        "gross_sales": projection.gross_sales,
        "discount_amount": projection.discount_amount,
        "tax_amount": projection.tax_amount,
        "refund_amount": projection.refund_amount,
        "net_sales": projection.net_sales,
        "source_status": projection.source_status,
        "source_stream": event.source_stream,
        "last_source_event_id": event.event_id,
        "source_event_at": projection.source_event_at,
        "last_projected_at": datetime.now(timezone.utc),
    }
    if fact is None:
        db.add(CompanyReportingFact(**values))
    elif projection.source_event_at >= fact.source_event_at:
        for key, value in values.items():
            setattr(fact, key, value)
    db.add(
        CompanyReportingEventReceipt(
            source_stream=event.source_stream,
            source_event_id=event.event_id,
            company_id=event.company_id,
            module_key=projection.module_key,
            event_type=event.event_type,
            payload_sha256=event.payload_sha256,
            status="processed",
            error_code=None,
            source_created_at=event.created_at,
        )
    )
    await db.flush()
    return True


def _cursor_filter(model, state: CompanyReportingSourceState):
    if state.cursor_created_at is None or state.cursor_event_id is None:
        return True
    return or_(
        model.created_at > state.cursor_created_at,
        and_(model.created_at == state.cursor_created_at, model.id > state.cursor_event_id),
    )


async def process_reporting_source_batch(
    source_db: AsyncSession,
    platform_db: AsyncSession,
    *,
    source_stream: str,
    source_kind: Literal["legacy", "takeaway"],
    limit: int = 100,
) -> ReportingBatchResult:
    if limit < 1:
        raise ValueError("limit must be at least 1")
    state = await platform_db.scalar(
        select(CompanyReportingSourceState)
        .where(CompanyReportingSourceState.source_stream == source_stream)
        .with_for_update()
    )
    if state is None:
        state = CompanyReportingSourceState(source_stream=source_stream, status="idle")
        platform_db.add(state)
        await platform_db.flush()
    model = OperationalOutboxEvent if source_kind == "legacy" else TakeawayOperationalOutbox
    allowed = LEGACY_EVENT_TYPES if source_kind == "legacy" else TAKEAWAY_EVENT_TYPES
    rows = list(
        await source_db.scalars(
            select(model)
            .where(
                model.event_type.in_(allowed),
                _cursor_filter(model, state),
            )
            .order_by(model.created_at, model.id)
            .limit(limit)
        )
    )
    if not rows:
        state.last_polled_at = datetime.now(timezone.utc)
        if state.status not in {"failed", "degraded"}:
            state.status = "healthy"
        await platform_db.commit()
        return ReportingBatchResult()

    projected = replayed = failed = dead_lettered = 0
    for row in rows:
        event = source_event(row, source_stream)
        try:
            projection = (
                await normalize_legacy_event(source_db, event)
                if source_kind == "legacy"
                else await normalize_takeaway_event(source_db, event)
            )
            created = await apply_reporting_projection(platform_db, event, projection)
            state.cursor_created_at = event.created_at
            state.cursor_event_id = event.event_id
            state.last_polled_at = datetime.now(timezone.utc)
            state.last_success_at = state.last_polled_at
            state.last_event_at = event.created_at
            state.failed_event_id = None
            state.failure_attempts = 0
            state.last_error_code = None
            if state.status != "degraded":
                state.status = "healthy"
            await platform_db.commit()
            projected += int(created)
            replayed += int(not created)
        except ReportingProjectionError as exc:
            await platform_db.rollback()
            state = await platform_db.scalar(
                select(CompanyReportingSourceState)
                .where(CompanyReportingSourceState.source_stream == source_stream)
                .with_for_update()
            )
            if state is None:  # pragma: no cover - protected by the initial insert
                raise RuntimeError("Reporting source state disappeared")
            state.failure_attempts = (
                state.failure_attempts + 1
                if state.failed_event_id == event.event_id
                else 1
            )
            state.failed_event_id = event.event_id
            state.last_error_code = exc.code
            state.last_polled_at = datetime.now(timezone.utc)
            state.status = "failed"
            failed += 1
            was_dead_lettered = state.failure_attempts >= MAX_FAILURE_ATTEMPTS
            if was_dead_lettered:
                platform_db.add(
                    CompanyReportingEventReceipt(
                        source_stream=event.source_stream,
                        source_event_id=event.event_id,
                        company_id=event.company_id,
                        module_key=None,
                        event_type=event.event_type,
                        payload_sha256=event.payload_sha256,
                        status="dead_letter",
                        error_code=exc.code,
                        source_created_at=event.created_at,
                    )
                )
                state.cursor_created_at = event.created_at
                state.cursor_event_id = event.event_id
                state.status = "degraded"
                dead_lettered += 1
            await platform_db.commit()
            if not was_dead_lettered:
                break
    return ReportingBatchResult(
        discovered=len(rows),
        projected=projected,
        replayed=replayed,
        failed=failed,
        dead_lettered=dead_lettered,
    )


class SharedReportingService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def sales_report(
        self,
        current: TokenData,
        *,
        date_from: date,
        date_to: date,
        module_key: ReportingModuleKey | None = None,
        brand_id: uuid.UUID | None = None,
        branch_id: uuid.UUID | None = None,
    ) -> SharedSalesReportRead:
        require_shared_reporting(current)
        if date_to < date_from:
            raise HTTPException(status_code=400, detail="date_to must be on or after date_from")
        if (date_to - date_from).days >= MAX_REPORT_DAYS:
            raise HTTPException(status_code=400, detail="date range cannot exceed 93 days")
        filters = [
            CompanyReportingFact.company_id == current.company_id,
            CompanyReportingFact.business_date >= date_from,
            CompanyReportingFact.business_date <= date_to,
        ]
        if module_key is not None:
            filters.append(CompanyReportingFact.module_key == module_key)
        if brand_id is not None:
            filters.append(CompanyReportingFact.brand_id == brand_id)
        if branch_id is not None:
            filters.append(CompanyReportingFact.branch_id == branch_id)

        metric_columns = self._metric_columns()
        totals_row = (await self.db.execute(select(*metric_columns).where(*filters))).one()
        module_rows = (
            await self.db.execute(
                select(CompanyReportingFact.module_key, *metric_columns)
                .where(*filters)
                .group_by(CompanyReportingFact.module_key)
                .order_by(CompanyReportingFact.module_key)
            )
        ).all()
        workspace_rows = (
            await self.db.execute(
                select(
                    CompanyReportingFact.module_key,
                    CompanyReportingFact.brand_id,
                    CompanyReportingFact.branch_id,
                    *metric_columns,
                )
                .where(*filters)
                .group_by(
                    CompanyReportingFact.module_key,
                    CompanyReportingFact.brand_id,
                    CompanyReportingFact.branch_id,
                )
                .order_by(
                    CompanyReportingFact.module_key,
                    CompanyReportingFact.brand_id,
                    CompanyReportingFact.branch_id,
                )
            )
        ).all()
        daily_rows = (
            await self.db.execute(
                select(CompanyReportingFact.business_date, *metric_columns)
                .where(*filters)
                .group_by(CompanyReportingFact.business_date)
                .order_by(CompanyReportingFact.business_date)
            )
        ).all()
        documents = list(
            await self.db.scalars(
                select(CompanyReportingFact)
                .where(*filters)
                .order_by(
                    CompanyReportingFact.business_date.desc(),
                    CompanyReportingFact.source_event_at.desc(),
                )
                .limit(50)
            )
        )
        brand_ids = {row.brand_id for row in documents} | {row.brand_id for row in workspace_rows}
        branch_ids = {row.branch_id for row in documents} | {row.branch_id for row in workspace_rows}
        brand_names = {
            row.id: row.name
            for row in await self.db.scalars(
                select(Brand).where(
                    Brand.company_id == current.company_id,
                    Brand.id.in_(brand_ids),
                )
            )
        } if brand_ids else {}
        branch_names = {
            row.id: row.name
            for row in await self.db.scalars(
                select(Branch).where(
                    Branch.company_id == current.company_id,
                    Branch.id.in_(branch_ids),
                )
            )
        } if branch_ids else {}

        return SharedSalesReportRead(
            company_id=current.company_id,
            date_from=date_from,
            date_to=date_to,
            generated_at=datetime.now(timezone.utc),
            freshness=await self._freshness(filters),
            totals=self._metrics(totals_row),
            modules=[
                SharedSalesModuleSummary(
                    module_key=row.module_key,
                    **self._metrics(row).model_dump(),
                )
                for row in module_rows
            ],
            workspaces=[
                SharedSalesWorkspaceSummary(
                    module_key=row.module_key,
                    brand_id=row.brand_id,
                    brand_name=brand_names.get(row.brand_id, "Unknown Brand"),
                    branch_id=row.branch_id,
                    branch_name=branch_names.get(row.branch_id, "Unknown Branch"),
                    **self._metrics(row).model_dump(),
                )
                for row in workspace_rows
            ],
            daily=[
                SharedSalesDailySummary(
                    business_date=row.business_date,
                    **self._metrics(row).model_dump(),
                )
                for row in daily_rows
            ],
            recent_documents=[
                SharedSalesDocumentRead(
                    module_key=row.module_key,  # type: ignore[arg-type]
                    brand_id=row.brand_id,
                    brand_name=brand_names.get(row.brand_id, "Unknown Brand"),
                    branch_id=row.branch_id,
                    branch_name=branch_names.get(row.branch_id, "Unknown Branch"),
                    business_date=row.business_date,
                    source_document_type=row.source_document_type,
                    source_document_id=row.source_document_id,
                    document_number=row.document_number,
                    source_status=row.source_status,
                    gross_sales=row.gross_sales,
                    refund_amount=row.refund_amount,
                    net_sales=row.net_sales,
                    entry_route=ENTRY_ROUTE_BY_MODULE[row.module_key],
                )
                for row in documents
            ],
        )

    @staticmethod
    def _metric_columns():
        active = CompanyReportingFact.source_status != "voided"
        return (
            func.coalesce(func.sum(case((active, 1), else_=0)), 0).label("order_count"),
            func.coalesce(func.sum(case((CompanyReportingFact.source_status == "voided", 1), else_=0)), 0).label("void_count"),
            func.coalesce(func.sum(case((CompanyReportingFact.refund_amount > 0, 1), else_=0)), 0).label("refund_count"),
            func.coalesce(func.sum(case((active, CompanyReportingFact.gross_sales), else_=0)), 0).label("gross_sales"),
            func.coalesce(func.sum(case((active, CompanyReportingFact.discount_amount), else_=0)), 0).label("discount_amount"),
            func.coalesce(func.sum(case((active, CompanyReportingFact.tax_amount), else_=0)), 0).label("tax_amount"),
            func.coalesce(func.sum(case((active, CompanyReportingFact.refund_amount), else_=0)), 0).label("refund_amount"),
            func.coalesce(func.sum(CompanyReportingFact.net_sales), 0).label("net_sales"),
        )

    @staticmethod
    def _metrics(row) -> SharedSalesMetrics:
        return SharedSalesMetrics(
            order_count=int(row.order_count or 0),
            void_count=int(row.void_count or 0),
            refund_count=int(row.refund_count or 0),
            gross_sales=q2(row.gross_sales),
            discount_amount=q2(row.discount_amount),
            tax_amount=q2(row.tax_amount),
            refund_amount=q2(row.refund_amount),
            net_sales=q2(row.net_sales),
        )

    async def _freshness(self, filters: list[object]) -> SharedReportingFreshness:
        states = list(await self.db.scalars(select(CompanyReportingSourceState)))
        last_projected_at = await self.db.scalar(
            select(func.max(CompanyReportingFact.last_projected_at)).where(*filters)
        )
        polled = [row.last_polled_at for row in states if row.last_polled_at is not None]
        last_polled_at = min(polled) if polled else None
        failed_sources = [
            row.source_stream for row in states if row.status in {"failed", "degraded"}
        ]
        now = datetime.now(timezone.utc)
        if not settings.shared_reporting_projector_enabled:
            freshness_status = "disabled"
        elif not states:
            freshness_status = "no_data"
        elif failed_sources:
            freshness_status = "degraded"
        elif last_polled_at is None or (now - last_polled_at).total_seconds() > max(
            60,
            settings.shared_reporting_projector_poll_seconds * 3,
        ):
            freshness_status = "stale"
        else:
            freshness_status = "current"
        lag_seconds = (
            max(0, int((now - last_projected_at).total_seconds()))
            if last_projected_at is not None
            else None
        )
        return SharedReportingFreshness(
            status=freshness_status,  # type: ignore[arg-type]
            projector_enabled=settings.shared_reporting_projector_enabled,
            last_projected_at=last_projected_at,
            last_polled_at=last_polled_at,
            lag_seconds=lag_seconds,
            failed_sources=failed_sources,
        )
