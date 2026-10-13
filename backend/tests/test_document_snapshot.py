from datetime import date
from decimal import Decimal
from types import SimpleNamespace as NS
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import AsyncMock, MagicMock, patch
import uuid

from fastapi import HTTPException
from app.dependencies import TokenData
from app.services.document_snapshot_service import (
    capture_payment_snapshots, load_snapshot, make_payment_snapshots, require_document_scope, snapshot_digest,
)


def fixture():
    company = NS(id=uuid.uuid4(), name="บริษัทเดิม <script>", tax_id="0123456789012", address="ที่อยู่เดิม")
    supplier = NS(id=uuid.uuid4(), name="ผู้รับเดิม", tax_id="1234567890123", address="ที่อยู่ผู้รับ")
    payment = NS(id=uuid.uuid4(), company_id=company.id, branch_id=uuid.uuid4(), payment_number="PAY-1",
                 payment_date=date(2026, 10, 13), payment_method="transfer", bank_account="123", reference_no="ref",
                 total_amount=Decimal("1040.00"), note="ทดสอบ")
    invoice = NS(id=uuid.uuid4(), supplier_id=supplier.id, supplier=supplier, invoice_number="SINV-1")
    allocation = NS(invoice_id=invoice.id, allocated_amount=Decimal("1070.00"), wht_amount=Decimal("30.00"),
                    wht_rate=Decimal("3"), wht_type="ค่าบริการ")
    cert = NS(id=uuid.uuid4(), payment_id=payment.id, supplier_id=supplier.id, certificate_number="WHT-1",
              issue_date=payment.payment_date, wht_type="ค่าบริการ", wht_rate=Decimal("3"), base_amount=Decimal("1000"),
              wht_amount=Decimal("30"), income_type="ค่าบริการ")
    return company, payment, [allocation], {invoice.id: invoice}, [cert], uuid.uuid4()


class SnapshotContentTests(TestCase):
    def test_evidence_is_frozen_after_source_changes(self):
        values = fixture()
        rows = make_payment_snapshots(*values)
        hashes = [row.content_sha256 for row in rows]
        values[0].name = "บริษัทใหม่"
        next(iter(values[3].values())).supplier.name = "ผู้รับใหม่"
        values[1].total_amount = Decimal("99999")
        values[4][0].base_amount = Decimal("99999")
        self.assertEqual([snapshot_digest(row) for row in rows], hashes)
        self.assertEqual(rows[0].payload["payment"]["total_amount"], "1040.00")
        self.assertEqual(rows[1].payload["certificate"]["base_amount"], "1000")
        for row in rows:
            self.assertNotIn("บริษัทใหม่", row.rendered_html)
            self.assertNotIn("ผู้รับใหม่", row.rendered_html)
            self.assertNotIn("<script>", row.rendered_html)
            self.assertIn("&lt;script&gt;", row.rendered_html)
            self.assertNotIn("@import", row.rendered_html)

    def test_zero_wht_creates_only_voucher_and_no_synthetic_certificate(self):
        args = list(fixture())
        args[4] = []
        self.assertEqual([r.document_kind for r in make_payment_snapshots(*args)], ["payment_voucher"])

    def test_integrity_covers_payload_template_scope_and_html(self):
        for field, replacement in [("rendered_html", "changed"), ("payload", {}), ("template_version", "v2"),
                                    ("company_id", uuid.uuid4()), ("branch_id", uuid.uuid4())]:
            row = make_payment_snapshots(*fixture())[0]
            setattr(row, field, replacement)
            self.assertNotEqual(snapshot_digest(row), row.content_sha256)

    def test_scope_does_not_expand_to_other_branch_or_station(self):
        _, source, *_ = fixture()
        actor = TokenData(user_id=uuid.uuid4(), company_id=source.company_id, branch_id=source.branch_id, permissions=["accounting.payment.view"])
        require_document_scope(actor, source)
        actor.branch_id = uuid.uuid4()
        with self.assertRaises(HTTPException): require_document_scope(actor, source)
        actor.branch_id = None
        with self.assertRaises(HTTPException): require_document_scope(actor, source)
        actor.scope_types = ["company"]
        require_document_scope(actor, source)
        actor.station_key = "counter"
        with self.assertRaises(HTTPException): require_document_scope(actor, source)


class SnapshotServiceTests(IsolatedAsyncioTestCase):
    async def test_capture_joins_existing_transaction_without_commit(self):
        args = fixture()
        db = MagicMock(get=AsyncMock(return_value=args[0]), flush=AsyncMock(), commit=AsyncMock())
        with patch("app.services.document_lifecycle_service.append_event", new_callable=AsyncMock) as event:
            rows = await capture_payment_snapshots(db, *args[1:])
            self.assertEqual(event.await_count, 2)
        self.assertEqual(len(rows), 2)
        db.add_all.assert_called_once_with(rows)
        db.flush.assert_awaited_once()
        db.commit.assert_not_awaited()

    async def test_missing_company_does_not_capture(self):
        args = fixture()
        db = MagicMock(get=AsyncMock(return_value=None), flush=AsyncMock())
        with self.assertRaises(HTTPException): await capture_payment_snapshots(db, *args[1:])
        db.flush.assert_not_awaited()

    async def test_missing_expected_evidence_fails_closed_but_legacy_is_explicit(self):
        _, source, *_ = fixture()
        actor = TokenData(user_id=uuid.uuid4(), company_id=source.company_id, branch_id=source.branch_id, permissions=["*"])
        db = NS(scalar=AsyncMock(return_value=None), scalars=AsyncMock(return_value=NS(all=lambda: [])))
        self.assertIsNone(await load_snapshot(db, actor, "payment_voucher", source, source.id))
        db.scalars.return_value = NS(all=lambda: [NS(new_value={"document_snapshot_version": 1})])
        with self.assertRaises(HTTPException) as raised:
            await load_snapshot(db, actor, "payment_voucher", source, source.id)
        self.assertEqual(raised.exception.status_code, 409)

    async def test_valid_snapshot_read_and_tampering_rejected(self):
        args = fixture()
        source = args[1]
        actor = TokenData(user_id=uuid.uuid4(), company_id=source.company_id, branch_id=source.branch_id, permissions=["*"])
        row = make_payment_snapshots(*args)[0]
        db = NS(scalar=AsyncMock(return_value=row))
        self.assertIs(await load_snapshot(db, actor, "payment_voucher", source, source.id), row)
        row.rendered_html += "tampered"
        with self.assertRaises(HTTPException): await load_snapshot(db, actor, "payment_voucher", source, source.id)
