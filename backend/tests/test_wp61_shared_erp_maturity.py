from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
import unittest
import uuid
from unittest.mock import AsyncMock

from fastapi import HTTPException

from app.schemas.purchase import ApprovePORequest
from app.schemas.tax_operations import TaxPeriodAction
from app.schemas.transfer import ApproveTORequest
from app.services.accounting_service import AccountingService
from app.services.company_erp_maturity_service import ERP_READ_PERMISSIONS, _age_hours
from app.services.purchase_service import PurchaseService
from app.services.tax_operations_service import TaxOperationsService
from app.services.transfer_service import TransferService


ROOT = Path(__file__).resolve().parents[2]


class WP61MakerCheckerAuthorityTests(unittest.IsolatedAsyncioTestCase):
    async def test_purchase_creator_cannot_approve_own_po(self) -> None:
        actor_id = uuid.uuid4()
        service = PurchaseService(AsyncMock())
        service._get_po_entity = AsyncMock(return_value=SimpleNamespace(status="pending_approval", created_by=actor_id))

        with self.assertRaises(HTTPException) as raised:
            await service.approve_po(uuid.uuid4(), uuid.uuid4(), actor_id, ApprovePORequest())

        self.assertEqual(raised.exception.status_code, 409)
        self.assertEqual(raised.exception.detail["code"], "maker_checker_conflict")
        service.db.commit.assert_not_awaited()

    async def test_transfer_requester_cannot_approve_before_reservation(self) -> None:
        actor_id = uuid.uuid4()
        service = TransferService(AsyncMock())
        service._get_to_entity = AsyncMock(return_value=SimpleNamespace(status="pending_approval", requested_by=actor_id))
        service.stock_service._get_or_create_balance = AsyncMock()

        with self.assertRaises(HTTPException) as raised:
            await service.approve_to(uuid.uuid4(), uuid.uuid4(), actor_id, ApproveTORequest(items=[]))

        self.assertEqual(raised.exception.status_code, 409)
        self.assertEqual(raised.exception.detail["code"], "maker_checker_conflict")
        service.stock_service._get_or_create_balance.assert_not_awaited()

    async def test_tax_reviewer_cannot_close_own_review(self) -> None:
        actor_id = uuid.uuid4()
        service = TaxOperationsService(AsyncMock())
        service._get_period = AsyncMock(return_value=SimpleNamespace(status="review", reviewed_by=actor_id))

        with self.assertRaises(HTTPException) as raised:
            await service.change_period(
                uuid.uuid4(), actor_id, "close", TaxPeriodAction(year=2026, month=9)
            )

        self.assertEqual(raised.exception.status_code, 409)
        self.assertEqual(raised.exception.detail["code"], "maker_checker_conflict")
        service.db.commit.assert_not_awaited()

    async def test_manual_journal_creator_cannot_reverse_own_entry(self) -> None:
        actor_id = uuid.uuid4()
        service = AccountingService(AsyncMock())
        service.get_entry = AsyncMock(return_value=SimpleNamespace(
            is_reversed=False,
            entry_type="manual",
            created_by=actor_id,
        ))

        with self.assertRaises(HTTPException) as raised:
            await service.reverse_entry(uuid.uuid4(), uuid.uuid4(), actor_id)

        self.assertEqual(raised.exception.status_code, 409)
        self.assertEqual(raised.exception.detail["code"], "maker_checker_conflict")
        service.db.commit.assert_not_awaited()


class WP61ReadinessContractTests(unittest.TestCase):
    def test_exception_age_is_server_derived_and_non_negative(self) -> None:
        now = datetime.now(timezone.utc)
        self.assertEqual(_age_hours(now - timedelta(hours=26, minutes=10), now), 26)
        self.assertEqual(_age_hours(now + timedelta(minutes=5), now), 0)

    def test_erp_permissions_are_explicit_and_do_not_open_with_pos_only(self) -> None:
        self.assertIn("inventory.purchase.view", ERP_READ_PERMISSIONS)
        self.assertIn("accounting.report.view", ERP_READ_PERMISSIONS)
        self.assertNotIn("pos.sale.create", ERP_READ_PERMISSIONS)

    def test_frontend_exposes_required_states_and_holds(self) -> None:
        page = (ROOT / "frontend/src/pages/company/CompanyErpPage.tsx").read_text()
        service = (ROOT / "backend/app/services/company_erp_maturity_service.py").read_text()

        for marker in (
            "company-erp-loading",
            "permission_denied",
            "erp-offline-state",
            "erp-stale-state",
            'kind="empty"',
        ):
            self.assertIn(marker, page)
        for hold in (
            "real_tax_documents",
            "live_payment_provider",
            "accountant_signoff",
            "retail_source_cutover",
            "takeaway_central_writes",
        ):
            self.assertIn(hold, service)

    def test_erp_routes_use_company_shell(self) -> None:
        app = (ROOT / "frontend/src/App.tsx").read_text()
        home = (ROOT / "frontend/src/pages/company/CompanyHomePage.tsx").read_text()
        launcher = (ROOT / "frontend/src/pages/company/CompanyAppsPage.tsx").read_text()
        self.assertIn('path="/company/erp"', app)
        self.assertIn('erp: "/company/erp"', home)
        self.assertIn('route: "/company/erp"', launcher)


if __name__ == "__main__":
    unittest.main()
