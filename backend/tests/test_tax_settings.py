from __future__ import annotations

from datetime import date
from decimal import Decimal
import unittest
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.database import get_db
from app.dependencies import TokenData, get_current_user
from app.main import app
from app.schemas.tax_settings import (
    BranchTaxProfileUpdate,
    CompanyTaxProfileRead,
    CompanyTaxProfileUpdate,
    TaxRateRuleCreate,
)
from app.services.tax_settings_service import tax_periods_overlap
from app.services.tax_settings_service import TaxSettingsService


class TaxSettingsValidationTests(unittest.TestCase):
    def test_company_tax_id_is_normalized_to_thirteen_digits(self) -> None:
        row = CompanyTaxProfileUpdate(
            legal_name="บริษัท ฟู้ดเชนเซอร์วิส จำกัด",
            tax_id="0-1055-55123-45-6",
            vat_registered=True,
            vat_registration_date=date(2026, 1, 1),
            registered_address="กรุงเทพมหานคร",
            default_price_vat_type="included",
            default_vat_rate=Decimal("7"),
            vat_filing_mode="separate",
            consolidated_filing_approved=False,
            effective_from=date(2026, 1, 1),
            reason="กำหนดค่าเริ่มต้น",
        )
        self.assertEqual(row.tax_id, "0105555123456")

    def test_vat_registration_requires_tax_id_and_address(self) -> None:
        with self.assertRaisesRegex(ValidationError, "เลขผู้เสียภาษี"):
            CompanyTaxProfileUpdate(
                legal_name="กิจการทดสอบ",
                vat_registered=True,
                registered_address="กรุงเทพมหานคร",
                effective_from=date(2026, 1, 1),
                reason="ทดสอบกฎ",
            )

    def test_consolidated_filing_requires_approval(self) -> None:
        with self.assertRaisesRegex(ValidationError, "ได้รับอนุมัติ"):
            CompanyTaxProfileUpdate(
                legal_name="กิจการทดสอบ",
                vat_filing_mode="consolidated",
                consolidated_filing_approved=False,
                effective_from=date(2026, 1, 1),
                reason="ทดสอบกฎ",
            )

    def test_head_office_must_use_tax_branch_zero(self) -> None:
        with self.assertRaisesRegex(ValidationError, "00000"):
            BranchTaxProfileUpdate(
                tax_branch_code="00001",
                is_head_office=True,
                effective_from=date(2026, 1, 1),
                reason="ทดสอบกฎ",
            )

    def test_tax_rule_normalizes_code_and_enforces_exempt_values(self) -> None:
        row = TaxRateRuleCreate(
            code="vat_zero",
            name="VAT 0%",
            tax_category="zero",
            rate=0,
            price_vat_type="excluded",
            effective_from=date(2026, 1, 1),
            reason="เพิ่มอัตรา",
        )
        self.assertEqual(row.code, "VAT_ZERO")
        with self.assertRaisesRegex(ValidationError, "ยกเว้น VAT"):
            TaxRateRuleCreate(
                code="VAT_EXEMPT",
                name="ยกเว้น VAT",
                tax_category="exempt",
                rate=0,
                price_vat_type="included",
                effective_from=date(2026, 1, 1),
                reason="ทดสอบกฎ",
            )

    def test_effective_period_overlap_is_inclusive(self) -> None:
        self.assertTrue(
            tax_periods_overlap(
                date(2026, 1, 1),
                date(2026, 1, 31),
                date(2026, 1, 31),
                None,
            )
        )
        self.assertFalse(
            tax_periods_overlap(
                date(2026, 1, 1),
                date(2026, 1, 31),
                date(2026, 2, 1),
                None,
            )
        )


class TaxSettingsSeedTests(unittest.IsolatedAsyncioTestCase):
    async def test_standard_company_seeds_three_rates_with_standard_default(self) -> None:
        db = MagicMock()
        db.scalar = AsyncMock(return_value=None)
        service = TaxSettingsService(db)
        data = CompanyTaxProfileUpdate(
            legal_name="กิจการทดสอบ",
            default_price_vat_type="included",
            default_vat_rate=Decimal("7"),
            effective_from=date(2026, 1, 1),
            reason="ตั้งค่าเริ่มต้น",
        )

        await service._seed_rates_if_empty(uuid.uuid4(), data)

        rows = db.add_all.call_args.args[0]
        self.assertEqual([row.code for row in rows], ["VAT_STANDARD", "VAT_ZERO", "VAT_EXEMPT"])
        self.assertEqual([row.code for row in rows if row.is_default], ["VAT_STANDARD"])

    async def test_exempt_company_does_not_seed_invalid_standard_rule(self) -> None:
        db = MagicMock()
        db.scalar = AsyncMock(return_value=None)
        service = TaxSettingsService(db)
        data = CompanyTaxProfileUpdate(
            legal_name="กิจการทดสอบ",
            default_price_vat_type="exempt",
            default_vat_rate=Decimal("0"),
            effective_from=date(2026, 1, 1),
            reason="ตั้งค่าเริ่มต้น",
        )

        await service._seed_rates_if_empty(uuid.uuid4(), data)

        rows = db.add_all.call_args.args[0]
        self.assertEqual([row.code for row in rows], ["VAT_ZERO", "VAT_EXEMPT"])
        self.assertEqual([row.code for row in rows if row.is_default], ["VAT_EXEMPT"])


class TaxSettingsApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.company_id = uuid.uuid4()
        self.user_id = uuid.uuid4()

        async def current_user() -> TokenData:
            return TokenData(
                user_id=self.user_id,
                company_id=self.company_id,
                branch_id=None,
                permissions=["system.company.edit"],
            )

        async def legacy_db():
            return MagicMock()

        app.dependency_overrides[get_current_user] = current_user
        app.dependency_overrides[get_db] = legacy_db
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.client.close()
        app.dependency_overrides.clear()

    def test_company_update_uses_signed_company_and_actor(self) -> None:
        company_read = CompanyTaxProfileRead(
            id=uuid.uuid4(),
            configured=True,
            company_id=self.company_id,
            legal_name="บริษัท ฟู้ดเชนเซอร์วิส จำกัด",
            tax_id="0105555123456",
            vat_registered=True,
            vat_registration_date=date(2026, 1, 1),
            registered_address="กรุงเทพมหานคร",
            default_price_vat_type="included",
            default_vat_rate=Decimal("7"),
            vat_filing_mode="separate",
            consolidated_filing_approved=False,
        )
        service = MagicMock()
        service.update_company_profile = AsyncMock(return_value=company_read)
        with patch("app.routers.tax_settings.TaxSettingsService", return_value=service):
            response = self.client.put(
                "/api/v1/tax-settings/company",
                json={
                    "legal_name": "บริษัท ฟู้ดเชนเซอร์วิส จำกัด",
                    "tax_id": "0105555123456",
                    "vat_registered": True,
                    "vat_registration_date": "2026-01-01",
                    "registered_address": "กรุงเทพมหานคร",
                    "default_price_vat_type": "included",
                    "default_vat_rate": 7,
                    "vat_filing_mode": "separate",
                    "consolidated_filing_approved": False,
                    "effective_from": "2026-01-01",
                    "reason": "กำหนดค่าภาษีบริษัท",
                },
            )

        self.assertEqual(response.status_code, 200, response.text)
        args = service.update_company_profile.await_args.args
        self.assertEqual(args[0], self.company_id)
        self.assertEqual(args[1], self.user_id)

    def test_invalid_branch_tax_code_is_rejected_before_service(self) -> None:
        response = self.client.put(
            f"/api/v1/tax-settings/branches/{uuid.uuid4()}",
            json={
                "tax_branch_code": "12",
                "is_head_office": False,
                "filing_enabled": True,
                "effective_from": "2026-01-01",
                "reason": "ทดสอบ validation",
            },
        )
        self.assertEqual(response.status_code, 422, response.text)


if __name__ == "__main__":
    unittest.main()
