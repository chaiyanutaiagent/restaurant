from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import os
import uuid

from sqlalchemy import func, select

from app.database import PlatformSessionLocal
from app.dependencies import TokenData
from app.models.branch import Branch
from app.models.company import Company
from app.models.platform import (
    CompanyReportingEventReceipt,
    CompanyReportingFact,
    CompanyReportingSourceState,
)
from app.models.restaurant import Brand, BrandBranch
from app.services.shared_reporting_service import (
    ReportingProjection,
    ReportingProjectionError,
    SharedReportingService,
    SourceReportingEvent,
    apply_reporting_projection,
)


DATABASE_PREFIX = "restaurant_wp4_reporting_"


async def seed_workspace(
    db,
    company: Company,
    *,
    marker: str,
    business_type: str,
    suffix: str,
) -> tuple[Brand, Branch]:
    brand = Brand(
        company_id=company.id,
        slug=f"wp4-{marker}-{suffix}",
        name=f"WP4 {suffix.title()}",
        business_type=business_type,
        storefront_mode="food_stall",
        is_active=True,
    )
    branch = Branch(
        company_id=company.id,
        code=f"WP4-{suffix[:3].upper()}-{marker[:4]}",
        name=f"WP4 {suffix.title()} Branch",
        is_active=True,
    )
    db.add_all([brand, branch])
    await db.flush()
    db.add(BrandBranch(
        company_id=company.id,
        brand_id=brand.id,
        branch_id=branch.id,
        branch_type="company_owned",
        is_active=True,
    ))
    await db.flush()
    return brand, branch


def event(
    *,
    stream: str,
    company_id: uuid.UUID,
    brand_id: uuid.UUID,
    branch_id: uuid.UUID,
    document_id: uuid.UUID,
    event_type: str,
    at: datetime,
) -> SourceReportingEvent:
    return SourceReportingEvent(
        source_stream=stream,
        event_id=uuid.uuid4(),
        company_id=company_id,
        brand_id=brand_id,
        branch_id=branch_id,
        event_type=event_type,
        aggregate_type="order" if stream == "takeaway_pos" else "SaleOrder",
        aggregate_id=document_id,
        payload={"schema": event_type.removesuffix(".v1"), "version": 1},
        created_at=at,
    )


def projection(
    source: SourceReportingEvent,
    *,
    module_key: str,
    business_type: str,
    document_type: str,
    number: str,
    business_date: date,
    gross: str,
    discount: str,
    tax: str,
    refund: str,
    net: str,
    status: str,
) -> ReportingProjection:
    return ReportingProjection(
        company_id=source.company_id,
        module_key=module_key,  # type: ignore[arg-type]
        business_type=business_type,  # type: ignore[arg-type]
        brand_id=source.brand_id,  # type: ignore[arg-type]
        branch_id=source.branch_id,  # type: ignore[arg-type]
        business_date=business_date,
        source_document_type=document_type,  # type: ignore[arg-type]
        source_document_id=source.aggregate_id,
        document_number=number,
        currency="THB",
        gross_sales=Decimal(gross),
        discount_amount=Decimal(discount),
        tax_amount=Decimal(tax),
        refund_amount=Decimal(refund),
        net_sales=Decimal(net),
        source_status=status,  # type: ignore[arg-type]
        source_event_at=source.created_at,
    )


async def main_async() -> None:
    configured_database = os.environ.get("WP4_REPORTING_DATABASE_NAME", "")
    if not configured_database.startswith(DATABASE_PREFIX):
        raise RuntimeError("WP4 reporting smoke refuses to write a non-isolated database")

    async with PlatformSessionLocal() as db:
        actual_database = await db.scalar(func.current_database())
        if actual_database != configured_database:
            raise RuntimeError(f"WP4 database mismatch: {actual_database} != {configured_database}")

        marker = uuid.uuid4().hex[:8]
        company = Company(name="WP4 Reporting Company", business_slug=f"wp4-report-{marker}", is_active=True)
        foreign = Company(name="WP4 Foreign Company", business_slug=f"wp4-foreign-{marker}", is_active=True)
        db.add_all([company, foreign])
        await db.flush()
        restaurant_brand, restaurant_branch = await seed_workspace(
            db, company, marker=marker, business_type="restaurant", suffix="restaurant"
        )
        takeaway_brand, takeaway_branch = await seed_workspace(
            db, company, marker=marker, business_type="takeaway", suffix="takeaway"
        )
        retail_brand, retail_branch = await seed_workspace(
            db, company, marker=marker, business_type="retail_pos", suffix="retail"
        )
        foreign_brand, foreign_branch = await seed_workspace(
            db, foreign, marker=marker, business_type="restaurant", suffix="foreign"
        )
        await db.commit()

        day = date(2026, 9, 14)
        base = datetime(2026, 9, 14, 3, tzinfo=timezone.utc)
        restaurant_document = uuid.uuid4()
        restaurant_paid = event(
            stream="legacy_pos", company_id=company.id, brand_id=restaurant_brand.id,
            branch_id=restaurant_branch.id, document_id=restaurant_document,
            event_type="restaurant.sale.completed.v1", at=base,
        )
        restaurant_paid_projection = projection(
            restaurant_paid, module_key="restaurant_pos", business_type="restaurant",
            document_type="sale_order", number="WP4-R-001", business_date=day,
            gross="120", discount="10", tax="7", refund="0", net="110", status="completed",
        )
        if not await apply_reporting_projection(db, restaurant_paid, restaurant_paid_projection):
            raise RuntimeError("Initial Restaurant projection was not created")
        await db.commit()
        if await apply_reporting_projection(db, restaurant_paid, restaurant_paid_projection):
            raise RuntimeError("Exact replay created a duplicate reporting row")

        restaurant_refund = event(
            stream="legacy_pos", company_id=company.id, brand_id=restaurant_brand.id,
            branch_id=restaurant_branch.id, document_id=restaurant_document,
            event_type="pos.sale.state.changed.v1", at=base + timedelta(minutes=1),
        )
        await apply_reporting_projection(db, restaurant_refund, projection(
            restaurant_refund, module_key="restaurant_pos", business_type="restaurant",
            document_type="sale_order", number="WP4-R-001", business_date=day,
            gross="120", discount="10", tax="7", refund="20", net="90",
            status="partially_refunded",
        ))

        takeaway_document = uuid.uuid4()
        takeaway_paid = event(
            stream="takeaway_pos", company_id=company.id, brand_id=takeaway_brand.id,
            branch_id=takeaway_branch.id, document_id=takeaway_document,
            event_type="takeaway.sale.paid.v1", at=base + timedelta(minutes=2),
        )
        await apply_reporting_projection(db, takeaway_paid, projection(
            takeaway_paid, module_key="takeaway_pos", business_type="takeaway",
            document_type="takeaway_order", number="WP4-T-001", business_date=day,
            gross="80", discount="0", tax="5", refund="0", net="80", status="paid",
        ))
        takeaway_refund = event(
            stream="takeaway_pos", company_id=company.id, brand_id=takeaway_brand.id,
            branch_id=takeaway_branch.id, document_id=takeaway_document,
            event_type="takeaway.sale.refunded.v1", at=base + timedelta(minutes=3),
        )
        await apply_reporting_projection(db, takeaway_refund, projection(
            takeaway_refund, module_key="takeaway_pos", business_type="takeaway",
            document_type="takeaway_order", number="WP4-T-001", business_date=day,
            gross="80", discount="0", tax="5", refund="80", net="0", status="refunded",
        ))

        retail_document = uuid.uuid4()
        retail_paid = event(
            stream="legacy_pos", company_id=company.id, brand_id=retail_brand.id,
            branch_id=retail_branch.id, document_id=retail_document,
            event_type="restaurant.sale.completed.v1", at=base + timedelta(minutes=4),
        )
        await apply_reporting_projection(db, retail_paid, projection(
            retail_paid, module_key="retail_pos", business_type="retail_pos",
            document_type="sale_order", number="WP4-L-001", business_date=day,
            gross="50", discount="0", tax="3", refund="0", net="50", status="completed",
        ))

        void_document = uuid.uuid4()
        void_event = event(
            stream="legacy_pos", company_id=company.id, brand_id=restaurant_brand.id,
            branch_id=restaurant_branch.id, document_id=void_document,
            event_type="pos.sale.state.changed.v1", at=base + timedelta(minutes=5),
        )
        await apply_reporting_projection(db, void_event, projection(
            void_event, module_key="restaurant_pos", business_type="restaurant",
            document_type="sale_order", number="WP4-R-VOID", business_date=day,
            gross="30", discount="0", tax="2", refund="0", net="0", status="voided",
        ))

        foreign_event = event(
            stream="legacy_pos", company_id=foreign.id, brand_id=foreign_brand.id,
            branch_id=foreign_branch.id, document_id=uuid.uuid4(),
            event_type="restaurant.sale.completed.v1", at=base + timedelta(minutes=6),
        )
        await apply_reporting_projection(db, foreign_event, projection(
            foreign_event, module_key="restaurant_pos", business_type="restaurant",
            document_type="sale_order", number="WP4-FOREIGN", business_date=day,
            gross="999", discount="0", tax="0", refund="0", net="999", status="completed",
        ))

        old_correction = event(
            stream="legacy_pos", company_id=company.id, brand_id=restaurant_brand.id,
            branch_id=restaurant_branch.id, document_id=restaurant_document,
            event_type="pos.sale.state.changed.v1", at=base - timedelta(minutes=1),
        )
        await apply_reporting_projection(db, old_correction, replace(
            restaurant_paid_projection,
            source_event_at=old_correction.created_at,
            refund_amount=Decimal("0"),
            net_sales=Decimal("110"),
        ))

        for source_stream in ("legacy_pos", "takeaway_pos"):
            db.add(CompanyReportingSourceState(
                source_stream=source_stream,
                status="healthy",
                last_polled_at=datetime.now(timezone.utc),
                last_success_at=datetime.now(timezone.utc),
            ))
        await db.commit()

        current = TokenData(
            user_id=uuid.uuid4(), company_id=company.id, branch_id=None,
            permissions=["system.company.edit"],
        )
        report = await SharedReportingService(db).sales_report(
            current, date_from=day, date_to=day,
        )
        if report.totals.order_count != 3 or report.totals.void_count != 1:
            raise RuntimeError(f"Unexpected document totals: {report.totals}")
        if report.totals.refund_count != 2:
            raise RuntimeError(f"Unexpected refund count: {report.totals.refund_count}")
        if report.totals.gross_sales != Decimal("250.00"):
            raise RuntimeError(f"Unexpected gross sales: {report.totals.gross_sales}")
        if report.totals.refund_amount != Decimal("100.00"):
            raise RuntimeError(f"Unexpected refunds: {report.totals.refund_amount}")
        if report.totals.net_sales != Decimal("140.00"):
            raise RuntimeError(f"Unexpected net sales: {report.totals.net_sales}")
        if {row.module_key for row in report.modules} != {
            "restaurant_pos", "takeaway_pos", "retail_pos"
        }:
            raise RuntimeError("Module dimensions are incomplete")
        if any(row.document_number == "WP4-FOREIGN" for row in report.recent_documents):
            raise RuntimeError("Foreign tenant document leaked into Company report")

        stored_restaurant = await db.scalar(select(CompanyReportingFact).where(
            CompanyReportingFact.company_id == company.id,
            CompanyReportingFact.source_document_id == restaurant_document,
        ))
        if stored_restaurant is None or stored_restaurant.net_sales != Decimal("90.00"):
            raise RuntimeError("Older correction regressed the latest reporting fact")
        company_fact_count = int(await db.scalar(
            select(func.count()).select_from(CompanyReportingFact).where(
                CompanyReportingFact.company_id == company.id
            )
        ) or 0)
        receipt_count = int(await db.scalar(
            select(func.count()).select_from(CompanyReportingEventReceipt).where(
                CompanyReportingEventReceipt.company_id == company.id
            )
        ) or 0)
        if company_fact_count != 4 or receipt_count != 7:
            raise RuntimeError(
                f"Unexpected fact/receipt counts: {company_fact_count}/{receipt_count}"
            )

        spoofed = replace(restaurant_paid_projection, company_id=foreign.id)
        try:
            await apply_reporting_projection(db, restaurant_paid, spoofed)
        except ReportingProjectionError as exc:
            if exc.code != "company_dimension_mismatch":
                raise
        else:
            raise RuntimeError("Cross-tenant projection was not rejected")

        print(
            "wp4_shared_reporting=ok "
            f"company={company.id} facts={company_fact_count} receipts={receipt_count} "
            "dedupe=ok correction=ok reversal=ok tenant_isolation=ok totals=ok"
        )


if __name__ == "__main__":
    asyncio.run(main_async())
