from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
import unittest
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import HTTPException

from app.dependencies import TokenData
from app.models.platform import (
    CompanyReportingEventReceipt,
    CompanyReportingFact,
    CompanyReportingSourceState,
)
from app.services.shared_reporting_service import (
    ReportingProjection,
    ReportingProjectionError,
    SourceReportingEvent,
    apply_reporting_projection,
    normalize_legacy_event,
    normalize_takeaway_event,
    process_reporting_source_batch,
    q2,
    require_shared_reporting,
)


class SharedReportingContractTests(unittest.TestCase):
    def test_money_rounding_is_stable(self) -> None:
        self.assertEqual(q2("10.125"), Decimal("10.13"))
        self.assertEqual(q2(None), Decimal("0.00"))

    def test_only_company_admin_can_read_shared_report(self) -> None:
        require_shared_reporting(TokenData(
            user_id=uuid.uuid4(), company_id=uuid.uuid4(), branch_id=None,
            permissions=["system.company.edit"],
        ))
        with self.assertRaises(HTTPException) as raised:
            require_shared_reporting(TokenData(
                user_id=uuid.uuid4(), company_id=uuid.uuid4(), branch_id=None,
                permissions=["pos.report.view"],
            ))
        self.assertEqual(raised.exception.status_code, 403)

    def test_event_digest_is_deterministic_and_does_not_expose_payload(self) -> None:
        event_id = uuid.uuid4()
        company_id = uuid.uuid4()
        event = SourceReportingEvent(
            source_stream="legacy_pos",
            event_id=event_id,
            company_id=company_id,
            brand_id=uuid.uuid4(),
            branch_id=uuid.uuid4(),
            event_type="restaurant.sale.completed.v1",
            aggregate_type="SaleOrder",
            aggregate_id=uuid.uuid4(),
            payload={"order": "SO-001", "nested": {"b": 2, "a": 1}},
            created_at=datetime.now(timezone.utc),
        )
        reordered = SourceReportingEvent(
            **{**event.__dict__, "payload": {"nested": {"a": 1, "b": 2}, "order": "SO-001"}}
        )
        self.assertEqual(event.payload_sha256, reordered.payload_sha256)
        self.assertEqual(len(event.payload_sha256), 64)
        self.assertNotIn("SO-001", event.payload_sha256)


class SharedReportingProjectionTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.company_id = uuid.uuid4()
        self.brand_id = uuid.uuid4()
        self.branch_id = uuid.uuid4()
        self.event = SourceReportingEvent(
            source_stream="legacy_pos",
            event_id=uuid.uuid4(),
            company_id=self.company_id,
            brand_id=self.brand_id,
            branch_id=self.branch_id,
            event_type="restaurant.sale.completed.v1",
            aggregate_type="SaleOrder",
            aggregate_id=uuid.uuid4(),
            payload={"schema": "restaurant.sale.completed", "version": 1},
            created_at=datetime(2026, 9, 14, 10, tzinfo=timezone.utc),
        )
        self.projection = ReportingProjection(
            company_id=self.company_id,
            module_key="restaurant_pos",
            business_type="restaurant",
            brand_id=self.brand_id,
            branch_id=self.branch_id,
            business_date=date(2026, 9, 14),
            source_document_type="sale_order",
            source_document_id=self.event.aggregate_id,
            document_number="SO-001",
            currency="THB",
            gross_sales=Decimal("120.00"),
            discount_amount=Decimal("10.00"),
            tax_amount=Decimal("7.00"),
            refund_amount=Decimal("0.00"),
            net_sales=Decimal("110.00"),
            source_status="completed",
            source_event_at=self.event.created_at,
        )

    async def test_projection_checks_dimensions_and_deduplicates_receipt(self) -> None:
        db = AsyncMock()
        db.add = MagicMock()
        db.scalar.side_effect = [self.brand_id, self.branch_id, uuid.uuid4(), None, None]
        created = await apply_reporting_projection(db, self.event, self.projection)
        self.assertTrue(created)
        added = [call.args[0] for call in db.add.call_args_list]
        fact = next(row for row in added if isinstance(row, CompanyReportingFact))
        receipt = next(row for row in added if isinstance(row, CompanyReportingEventReceipt))
        self.assertEqual(fact.company_id, self.company_id)
        self.assertEqual(fact.module_key, "restaurant_pos")
        self.assertEqual(receipt.payload_sha256, self.event.payload_sha256)
        self.assertFalse(hasattr(receipt, "payload"))
        db.flush.assert_awaited_once()

        replay_db = AsyncMock()
        replay_db.add = MagicMock()
        replay_db.scalar.side_effect = [
            self.brand_id,
            self.branch_id,
            uuid.uuid4(),
            SimpleNamespace(payload_sha256=self.event.payload_sha256),
        ]
        replayed = await apply_reporting_projection(replay_db, self.event, self.projection)
        self.assertFalse(replayed)
        replay_db.add.assert_not_called()

    async def test_projection_rejects_cross_tenant_and_module_spoofing(self) -> None:
        db = AsyncMock()
        db.add = MagicMock()
        cross_tenant = ReportingProjection(
            **{**self.projection.__dict__, "company_id": uuid.uuid4()}
        )
        with self.assertRaisesRegex(ReportingProjectionError, "company_dimension_mismatch"):
            await apply_reporting_projection(db, self.event, cross_tenant)
        wrong_module = ReportingProjection(
            **{**self.projection.__dict__, "module_key": "retail_pos"}
        )
        with self.assertRaisesRegex(ReportingProjectionError, "module_dimension_mismatch"):
            await apply_reporting_projection(db, self.event, wrong_module)
        db.scalar.assert_not_awaited()

    async def test_projection_rejects_missing_platform_dimension(self) -> None:
        db = AsyncMock()
        db.scalar.side_effect = [None, self.branch_id, uuid.uuid4()]
        with self.assertRaisesRegex(ReportingProjectionError, "platform_dimension_missing"):
            await apply_reporting_projection(db, self.event, self.projection)

    async def test_legacy_source_derives_module_and_bangkok_business_date(self) -> None:
        order = SimpleNamespace(
            id=self.event.aggregate_id,
            company_id=self.company_id,
            branch_id=self.branch_id,
            status="partially_refunded",
            total_amount=Decimal("100"),
            discount_amount=Decimal("10"),
            refund_amount=Decimal("20"),
            vat_amount=Decimal("7"),
            created_at=datetime(2026, 9, 13, 18, 30, tzinfo=timezone.utc),
            order_number="SO-TZ-001",
        )
        brand = SimpleNamespace(
            id=self.brand_id,
            company_id=self.company_id,
            business_type="restaurant",
        )
        db = AsyncMock()
        db.scalar.side_effect = [order, brand]
        result = await normalize_legacy_event(db, self.event)
        self.assertEqual(result.module_key, "restaurant_pos")
        self.assertEqual(result.business_date, date(2026, 9, 14))
        self.assertEqual(result.gross_sales, Decimal("110.00"))
        self.assertEqual(result.refund_amount, Decimal("20.00"))
        self.assertEqual(result.net_sales, Decimal("80.00"))

    async def test_takeaway_source_derives_refund_snapshot(self) -> None:
        takeaway_event = SourceReportingEvent(
            source_stream="takeaway_pos",
            event_id=uuid.uuid4(),
            company_id=self.company_id,
            brand_id=self.brand_id,
            branch_id=self.branch_id,
            event_type="takeaway.sale.refunded.v1",
            aggregate_type="order",
            aggregate_id=uuid.uuid4(),
            payload={"schema": "takeaway.sale.refunded", "version": 1},
            created_at=datetime.now(timezone.utc),
        )
        order = SimpleNamespace(
            id=takeaway_event.aggregate_id,
            company_id=self.company_id,
            brand_id=self.brand_id,
            branch_id=self.branch_id,
            status="refunded",
            total_amount=Decimal("80"),
            discount_amount=Decimal("5"),
            tax_amount=Decimal("4.67"),
            business_date=date(2026, 9, 14),
            order_number="TAKE-001",
        )
        db = AsyncMock()
        db.scalar.return_value = order
        result = await normalize_takeaway_event(db, takeaway_event)
        self.assertEqual(result.module_key, "takeaway_pos")
        self.assertEqual(result.gross_sales, Decimal("85.00"))
        self.assertEqual(result.refund_amount, Decimal("80.00"))
        self.assertEqual(result.net_sales, Decimal("0.00"))

    async def test_first_bad_event_keeps_source_state_and_records_failure(self) -> None:
        row = SimpleNamespace(
            id=self.event.event_id,
            company_id=self.event.company_id,
            brand_id=self.event.brand_id,
            branch_id=self.event.branch_id,
            event_type=self.event.event_type,
            aggregate_type=self.event.aggregate_type,
            aggregate_id=self.event.aggregate_id,
            payload=self.event.payload,
            created_at=self.event.created_at,
        )
        persisted_state = CompanyReportingSourceState(
            source_stream="legacy_pos",
            status="idle",
            failure_attempts=0,
        )
        source_db = AsyncMock()
        source_db.scalars.return_value = [row]
        platform_db = AsyncMock()
        platform_db.add = MagicMock()
        platform_db.scalar.side_effect = [None, persisted_state]

        with patch(
            "app.services.shared_reporting_service.normalize_legacy_event",
            AsyncMock(side_effect=ReportingProjectionError("source_document_missing")),
        ):
            result = await process_reporting_source_batch(
                source_db,
                platform_db,
                source_stream="legacy_pos",
                source_kind="legacy",
            )

        self.assertEqual(result.failed, 1)
        self.assertEqual(persisted_state.status, "failed")
        self.assertEqual(persisted_state.last_error_code, "source_document_missing")
        self.assertEqual(persisted_state.failure_attempts, 1)
        self.assertGreaterEqual(platform_db.commit.await_count, 2)
        platform_db.rollback.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
