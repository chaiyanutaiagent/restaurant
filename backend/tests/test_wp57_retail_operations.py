from __future__ import annotations

from pathlib import Path
import unittest
import uuid

from fastapi import HTTPException

from app.dependencies import TokenData
from app.routers.pos import (
    _enforce_retail_refund_readiness,
    _require_retail_operational_context,
)
from app.services.refund_service import RefundService


ROOT = Path(__file__).resolve().parents[2]


def _current(
    *,
    business_type: str = "retail_pos",
    target_database: str = "retail_pos",
    brand_id: uuid.UUID | None = None,
    branch_id: uuid.UUID | None = None,
) -> TokenData:
    return TokenData(
        user_id=uuid.uuid4(),
        company_id=uuid.uuid4(),
        brand_id=brand_id if brand_id is not None else uuid.uuid4(),
        branch_id=branch_id if branch_id is not None else uuid.uuid4(),
        business_type=business_type,
        target_database=target_database,
        permissions=["pos.sale.create", "pos.refund.request"],
        scope_types=["branch"],
    )


class RetailContextGateTests(unittest.TestCase):
    def test_exact_signed_retail_context_is_required(self) -> None:
        self.assertTrue(_require_retail_operational_context(_current()))
        restaurant = _current(business_type="restaurant", target_database="restaurant")
        self.assertFalse(_require_retail_operational_context(restaurant))

        invalid = (
            _current(business_type="retail_pos", target_database="restaurant"),
            _current(business_type="restaurant", target_database="retail_pos"),
        )
        for current in invalid:
            with self.subTest(current=current), self.assertRaises(HTTPException) as raised:
                _require_retail_operational_context(current)
            self.assertEqual(raised.exception.status_code, 403)
            self.assertEqual(raised.exception.detail["code"], "retail_context_required")

    def test_only_cash_return_state_machine_is_open(self) -> None:
        for capability in ("quote", "execute", "cash_confirm"):
            _enforce_retail_refund_readiness(_current(), capability=capability)
        for capability in ("legacy", "provider_inquiry", "provider_retry", "tax_retry", "exchange"):
            with self.subTest(capability=capability), self.assertRaises(HTTPException) as raised:
                _enforce_retail_refund_readiness(_current(), capability=capability)
            self.assertEqual(raised.exception.detail["code"], "retail_return_capability_not_available")

    def test_retail_refund_service_has_explicit_bounded_mode(self) -> None:
        service = RefundService(object(), retail_cash_pilot=True)  # type: ignore[arg-type]
        self.assertTrue(service.retail_cash_pilot)


class RetailSchemaContractTests(unittest.TestCase):
    def test_migration_chain_adds_hold_and_cash_return_tables(self) -> None:
        hold = (
            ROOT
            / "backend/alembic_retail/versions/p12retail0006_add_server_backed_hold_drafts.py"
        ).read_text()
        refund = (
            ROOT
            / "backend/alembic_retail/versions/p13retail0007_add_cash_return_contract.py"
        ).read_text()
        env = (ROOT / "backend/alembic_retail/env.py").read_text()

        self.assertIn('down_revision: Union[str, None] = "p11retail0005"', hold)
        self.assertIn('op.create_table(\n        "pos_hold_drafts"', hold)
        self.assertIn('op.create_table(\n        "pos_hold_draft_audits"', hold)
        self.assertIn("append-only", hold)
        self.assertIn('down_revision: Union[str, None] = "p12retail0006"', refund)
        for table in (
            "refund_quotes",
            "refund_operations",
            "refund_operation_items",
            "refund_payment_legs",
            "refund_tax_links",
            "refund_operation_audits",
        ):
            self.assertIn(f'"{table}"', refund)
            self.assertIn(f'"{table}"', env)
        self.assertIn("ck_retail_refund_payment_legs_cash_only", refund)
        self.assertIn("ck_retail_refund_tax_links_non_fiscal", refund)
        self.assertNotIn("provider_refund_attempts", refund)
        self.assertNotIn("tax_documents.id", refund)
        self.assertNotIn("points_transactions.id", refund)

    def test_shift_and_return_side_effects_are_bounded(self) -> None:
        sale = (ROOT / "backend/app/services/sale_service.py").read_text()
        refund = (ROOT / "backend/app/services/refund_service.py").read_text()
        router = (ROOT / "backend/app/routers/pos.py").read_text()

        self.assertIn("if include_journal:", sale)
        self.assertIn('"journal_state": "posted" if journal else "not_applicable"', sale)
        self.assertIn("retail_cash_pilot", refund)
        self.assertIn('"retail_provider_not_ready"', refund)
        self.assertIn('status="not_required"', refund)
        self.assertIn("simulated\": not self.retail_cash_pilot", refund)
        self.assertIn("include_journal=current.target_database != \"retail_pos\"", router)


class RetailUxContractTests(unittest.TestCase):
    def test_retail_hold_return_and_shift_are_available_with_fail_closed_copy(self) -> None:
        page = (ROOT / "frontend/src/pages/pos/POSPage.tsx").read_text()
        navigation = (ROOT / "frontend/src/components/pos/PosWorkspaceNav.tsx").read_text()
        refund = (ROOT / "frontend/src/components/pos/RefundWorkspaceDialog.tsx").read_text()
        bill = (ROOT / "frontend/src/components/pos/BillReceiptCenterDialog.tsx").read_text()

        self.assertIn("holdEnabled", page)
        self.assertIn("Retail ต้องเชื่อมต่อ Server ก่อนพักบิล", page)
        self.assertIn("cashPilot={isRetailMode}", page)
        self.assertIn('"บิล / คืนสินค้า"', navigation)
        self.assertIn("Retail Cash Pilot", refund)
        self.assertIn("Provider, Exchange, Loyalty และเอกสารภาษีจริงยังปิดอยู่", refund)
        self.assertIn("Atomic exchange contract", bill)
        self.assertIn("จัดการกะ", page)


if __name__ == "__main__":
    unittest.main()
