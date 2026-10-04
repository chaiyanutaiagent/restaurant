from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace
import unittest
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.database import get_db
from app.dependencies import TokenData, get_current_user
from app.main import app
from app.schemas.payable import SupplierInvoiceCreate
from app.schemas.tax_operations import TaxLedgerIngest
from app.services.role_preset_service import COMPANY_OWNER_PERMISSION_CODES
from app.services.tax_operations_service import TaxOperationsService, month_bounds, payload_hash


class TaxOperationsValidationTests(unittest.TestCase):
    def test_month_bounds_handles_year_boundary(self) -> None:
        self.assertEqual(month_bounds(2026, 12), (date(2026, 12, 1), date(2027, 1, 1)))

    def test_payload_hash_is_stable_for_different_key_order(self) -> None:
        self.assertEqual(payload_hash({"a": 1, "b": 2}), payload_hash({"b": 2, "a": 1}))

    def test_ledger_requires_balanced_amounts(self) -> None:
        with self.assertRaisesRegex(ValidationError, "ยอดฐานภาษี"):
            TaxLedgerIngest(
                source_module="takeaway_pos",
                tax_direction="output",
                source_document_type="takeaway_order",
                source_document_id="ORDER-1",
                document_number="TK-1",
                document_date=date(2026, 9, 16),
                base_amount=Decimal("100"),
                tax_amount=Decimal("7"),
                total_amount=Decimal("108"),
                vat_rate=Decimal("7"),
            )

    def test_zero_rate_cannot_contain_tax(self) -> None:
        with self.assertRaisesRegex(ValidationError, "ต้องไม่มีภาษี"):
            TaxLedgerIngest(
                source_module="retail_pos",
                tax_direction="output",
                tax_category="zero",
                source_document_type="sale_order",
                source_document_id="ORDER-2",
                document_number="RT-2",
                document_date=date(2026, 9, 16),
                base_amount=Decimal("100"),
                tax_amount=Decimal("7"),
                total_amount=Decimal("107"),
                vat_rate=Decimal("0"),
            )

    def test_nonclaimable_input_vat_requires_reason(self) -> None:
        with self.assertRaisesRegex(ValidationError, "เหตุผล"):
            SupplierInvoiceCreate(
                supplier_id=uuid.uuid4(),
                branch_id=uuid.uuid4(),
                invoice_date=date(2026, 9, 16),
                subtotal=Decimal("100"),
                vat_amount=Decimal("7"),
                input_vat_claimable=False,
            )

    def test_company_owner_has_tax_operations_permissions(self) -> None:
        self.assertIn("accounting.tax.view", COMPANY_OWNER_PERMISSION_CODES)
        self.assertIn("accounting.tax.manage", COMPANY_OWNER_PERMISSION_CODES)

    def test_reconcile_keeps_ignored_warning_ignored(self) -> None:
        resolved_at = object()
        resolved_by = uuid.uuid4()
        row = SimpleNamespace(
            status="ignored",
            message="old",
            resolved_at=resolved_at,
            resolved_by=resolved_by,
            resolution_note="accepted for UAT",
        )

        TaxOperationsService._refresh_detected_issue(
            row,
            {
                "issue_code": "ETAX_MISSING",
                "severity": "warning",
                "status": "open",
                "message": "updated",
            },
        )

        self.assertEqual(row.status, "ignored")
        self.assertEqual(row.message, "updated")
        self.assertIs(row.resolved_at, resolved_at)
        self.assertEqual(row.resolved_by, resolved_by)
        self.assertEqual(row.resolution_note, "accepted for UAT")

    def test_reconcile_reopens_non_ignored_issue(self) -> None:
        row = SimpleNamespace(
            status="resolved",
            resolved_at=object(),
            resolved_by=uuid.uuid4(),
            resolution_note="previously fixed",
        )

        TaxOperationsService._refresh_detected_issue(
            row,
            {
                "issue_code": "ETAX_MISSING",
                "severity": "warning",
                "status": "open",
                "message": "detected again",
            },
        )

        self.assertEqual(row.status, "open")
        self.assertIsNone(row.resolved_at)
        self.assertIsNone(row.resolved_by)
        self.assertIsNone(row.resolution_note)


class TaxOperationsApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.company_id = uuid.uuid4()
        self.user_id = uuid.uuid4()

        async def current_user() -> TokenData:
            return TokenData(
                user_id=self.user_id,
                company_id=self.company_id,
                branch_id=None,
                permissions=["accounting.tax.manage", "accounting.tax.view"],
            )

        async def legacy_db():
            return MagicMock()

        app.dependency_overrides[get_current_user] = current_user
        app.dependency_overrides[get_db] = legacy_db
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.client.close()
        app.dependency_overrides.clear()

    def test_sync_uses_signed_company_and_actor(self) -> None:
        service = MagicMock()
        service.sync_legacy = AsyncMock(return_value={"sales": 4, "purchases": 2})
        with patch("app.routers.tax_operations.TaxOperationsService", return_value=service):
            response = self.client.post(
                "/api/v1/tax-operations/sync/legacy",
                json={"year": 2026, "month": 9},
            )
        self.assertEqual(response.status_code, 200, response.text)
        args = service.sync_legacy.await_args.args
        self.assertEqual(args[:2], (self.company_id, self.user_id))

    def test_invalid_export_type_is_rejected(self) -> None:
        response = self.client.post(
            "/api/v1/tax-operations/exports",
            json={"year": 2026, "month": 9, "export_type": "submit_to_revenue_department"},
        )
        self.assertEqual(response.status_code, 422, response.text)


if __name__ == "__main__":
    unittest.main()
