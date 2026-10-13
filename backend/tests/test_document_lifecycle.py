from datetime import date
from types import SimpleNamespace as NS
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import AsyncMock, MagicMock, patch
import uuid

from fastapi import HTTPException
from app.dependencies import TokenData
from app.models.purchase import PurchaseOrder
from app.services.document_lifecycle_service import append_event, next_number, require_reason
from app.services.document_archive_service import archive_source, evidence_for, export_document, copy_html


def context():
    source = NS(id=uuid.uuid4(), company_id=uuid.uuid4(), branch_id=uuid.uuid4(), status="approved")
    actor = TokenData(user_id=uuid.uuid4(), company_id=source.company_id, branch_id=source.branch_id, permissions=["inventory.purchase.view"])
    return source, actor


class PolicyTests(TestCase):
    def test_reason_required_bounded_and_trimmed(self):
        for value in [None, " ", "x" * 1001]:
            with self.assertRaises(HTTPException): require_reason(value)
        self.assertEqual(require_reason(" แก้ไข "), "แก้ไข")

    def test_cancelled_copy_visible_without_mutating_snapshot(self):
        snapshot = NS(rendered_html="<body>frozen</body>", content_sha256="abc")
        source, _ = context()
        source.status = "cancelled"
        result = copy_html(snapshot, source)
        self.assertIn("CANCELLED", result)
        self.assertIn("COPY", result)
        self.assertEqual(snapshot.rendered_html, "<body>frozen</body>")


class LifecycleTests(IsolatedAsyncioTestCase):
    async def test_sequence_locked_and_transaction_not_committed(self):
        source, actor = context()
        db = MagicMock(execute=AsyncMock(), scalar=AsyncMock(return_value=5), flush=AsyncMock(), commit=AsyncMock())
        event = await append_event(db, source, "purchase_order", "cancelled", actor.user_id, "ผิด")
        self.assertEqual(event.sequence, 6)
        self.assertEqual(event.actor_id, actor.user_id)
        self.assertIn("pg_advisory_xact_lock", str(db.execute.call_args.args[0]))
        db.commit.assert_not_awaited()

    async def test_numbers_use_max_global_suffix_not_count_or_python_hash(self):
        db = MagicMock(execute=AsyncMock(), scalars=AsyncMock(return_value=NS(all=lambda: ["PO20261013-0001", "PO20261013-0009"])))
        result = await next_number(db, "PO", PurchaseOrder, PurchaseOrder.po_number, date(2026, 10, 13))
        self.assertEqual(result, "PO20261013-0010")
        self.assertNotIn("company_id", str(db.scalars.call_args.args[0]))
        first = db.execute.call_args.args[1]
        await next_number(db, "PO", PurchaseOrder, PurchaseOrder.po_number, date(2026, 10, 13))
        self.assertEqual(db.execute.call_args.args[1], first)

    async def test_scope_predicates_and_permission(self):
        source, actor = context()
        db = NS(scalar=AsyncMock(return_value=source))
        await archive_source(db, actor, "purchase_order", source.id, lock=True)
        query = str(db.scalar.call_args.args[0])
        for predicate in ["company_id =", "branch_id =", "FOR UPDATE"]: self.assertIn(predicate, query)
        actor.permissions = []
        with self.assertRaises(HTTPException): await archive_source(db, actor, "purchase_order", source.id)

    async def test_missing_issued_snapshot_fails_closed(self):
        source, actor = context()
        db = NS(scalar=AsyncMock(side_effect=[None, uuid.uuid4()]))
        with self.assertRaises(HTTPException) as error: await evidence_for(db, actor, "purchase_order", source)
        self.assertEqual(error.exception.status_code, 409)

    async def test_legacy_no_snapshot_is_not_backfilled(self):
        source, actor = context()
        db = MagicMock(scalar=AsyncMock(return_value=None))
        self.assertIsNone(await evidence_for(db, actor, "purchase_order", source))
        db.add.assert_not_called()

    async def test_original_reprint_blocked(self):
        source, actor = context()
        snapshot = NS(document_number="PO-1", content_sha256="abc", rendered_html="<body>original</body>")
        db = MagicMock(scalar=AsyncMock(return_value=uuid.uuid4()), commit=AsyncMock())
        with patch("app.services.document_archive_service.archive_source", AsyncMock(return_value=source)), patch("app.services.document_archive_service.evidence_for", AsyncMock(return_value=snapshot)):
            with self.assertRaises(HTTPException): await export_document(db, actor, "purchase_order", source.id, "original")
        db.commit.assert_not_awaited()

    async def test_export_commits_only_after_render_and_event(self):
        source, actor = context()
        snapshot = NS(document_number="PO-1", content_sha256="abc", rendered_html="<body>original</body>")
        db = MagicMock(commit=AsyncMock())
        with patch("app.services.document_archive_service.archive_source", AsyncMock(return_value=source)), patch("app.services.document_archive_service.evidence_for", AsyncMock(return_value=snapshot)), patch("app.services.document_archive_service.append_event", AsyncMock(return_value=NS(sequence=2))) as event, patch("app.services.document_archive_service.html_to_pdf_or_html", return_value=(b"PDF", "application/pdf")):
            result = await export_document(db, actor, "purchase_order", source.id, "copy")
        self.assertEqual(result[0], b"PDF")
        self.assertEqual(event.call_args.args[3], "print_copy")
        db.commit.assert_awaited_once()

    async def test_failed_render_does_not_consume_original(self):
        source, actor = context()
        snapshot = NS(document_number="PO-1", content_sha256="abc", rendered_html="<body>original</body>")
        db = MagicMock(scalar=AsyncMock(return_value=None), commit=AsyncMock())
        with patch("app.services.document_archive_service.archive_source", AsyncMock(return_value=source)), patch("app.services.document_archive_service.evidence_for", AsyncMock(return_value=snapshot)), patch("app.services.document_archive_service.append_event", AsyncMock()) as event, patch("app.services.document_archive_service.html_to_pdf_or_html", side_effect=RuntimeError("renderer")):
            with self.assertRaises(RuntimeError): await export_document(db, actor, "purchase_order", source.id, "original")
        event.assert_not_awaited()
        db.commit.assert_not_awaited()
