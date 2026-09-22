from __future__ import annotations

from decimal import Decimal
from pathlib import Path
import unittest
import uuid
from unittest.mock import patch

from fastapi import HTTPException

from app.cli.rotate_uat_user_password import require_bounded_uat
from app.cli.prepare_retail_uat_persona import require_bounded_uat as require_retail_persona_uat
from app.config import settings
from app.dependencies import TokenData
from app.routers.pos import _enforce_retail_payment_readiness
from app.routers.products import lookup_retail_product
from app.schemas.pos import CreateSaleRequest


ROOT = Path(__file__).resolve().parents[2]


def _current(business_type: str = "retail_pos") -> TokenData:
    return TokenData(
        user_id=uuid.uuid4(),
        company_id=uuid.uuid4(),
        branch_id=uuid.uuid4(),
        brand_id=uuid.uuid4(),
        business_type=business_type,
        target_database=business_type,
        permissions=["inventory.product.view", "pos.sale.create"],
        scope_types=["branch"],
    )


def _sale(method: str = "cash", *, offline: bool = False) -> CreateSaleRequest:
    return CreateSaleRequest(
        shift_id=uuid.uuid4(),
        location_id=uuid.uuid4(),
        items=[],
        payment_method=method,
        payments=[{"payment_method": method, "amount": Decimal("10")}],
        paid_amount=Decimal("10"),
        is_offline=offline,
        client_order_id="wp56-retail-sale",
    )


class RetailPaymentReadinessTests(unittest.TestCase):
    def test_retail_cash_is_the_only_enabled_pilot_payment(self) -> None:
        _enforce_retail_payment_readiness(_current(), _sale("cash"))

        with self.assertRaises(HTTPException) as raised:
            _enforce_retail_payment_readiness(_current(), _sale("promptpay"))
        self.assertEqual(raised.exception.status_code, 409)
        self.assertEqual(raised.exception.detail["code"], "retail_provider_not_ready")

    def test_retail_offline_and_sync_fail_closed(self) -> None:
        for payload, synchronized in ((_sale("cash", offline=True), False), (_sale("cash"), True)):
            with self.subTest(synchronized=synchronized), self.assertRaises(HTTPException) as raised:
                _enforce_retail_payment_readiness(_current(), payload, synchronized=synchronized)
            self.assertEqual(raised.exception.detail["code"], "retail_offline_not_authorized")

    def test_restaurant_payment_contract_is_unchanged(self) -> None:
        _enforce_retail_payment_readiness(_current("restaurant"), _sale("promptpay"))


class UatCredentialRotationGuardTests(unittest.TestCase):
    def test_rotation_requires_https_uat_platform_identity_and_no_bypass(self) -> None:
        safe_values = {
            "environment": "development",
            "saas_public_base_url": "https://uat-pos.foodchainservice.com",
            "identity_database": "platform_core",
            "uat_auth_bypass_enabled": False,
        }
        with patch.multiple(settings, **safe_values):
            require_bounded_uat(confirmed=True, password="safe-temporary-password")

        unsafe_values = (
            {**safe_values, "saas_public_base_url": "http://uat-pos.foodchainservice.com"},
            {**safe_values, "environment": "production"},
            {**safe_values, "identity_database": "legacy"},
            {**safe_values, "uat_auth_bypass_enabled": True},
        )
        for values in unsafe_values:
            with self.subTest(values=values), patch.multiple(settings, **values):
                with self.assertRaises(RuntimeError):
                    require_bounded_uat(confirmed=True, password="safe-temporary-password")

    def test_rotation_requires_confirmation_and_strong_minimum_length(self) -> None:
        safe_values = {
            "environment": "development",
            "saas_public_base_url": "https://uat-pos.foodchainservice.com",
            "identity_database": "platform_core",
            "uat_auth_bypass_enabled": False,
        }
        with patch.multiple(settings, **safe_values):
            with self.assertRaisesRegex(RuntimeError, "--yes"):
                require_bounded_uat(confirmed=False, password="safe-temporary-password")
            with self.assertRaisesRegex(RuntimeError, "at least 12"):
                require_bounded_uat(confirmed=True, password="short")


class RetailUatPersonaGuardTests(unittest.TestCase):
    def _args(self, *, confirmed: bool = True, disabled: bool = False):
        return type("Args", (), {"yes": confirmed, "disable": disabled})()

    def test_persona_requires_https_platform_identity_and_auth_bypass_off(self) -> None:
        safe_values = {
            "environment": "development",
            "saas_public_base_url": "https://uat-pos.foodchainservice.com",
            "identity_database": "platform_core",
            "uat_auth_bypass_enabled": False,
        }
        with patch.multiple(settings, **safe_values):
            require_retail_persona_uat(
                self._args(),
                password="safe-temporary-retail-password",
            )

        unsafe_values = (
            {**safe_values, "saas_public_base_url": "http://uat-pos.foodchainservice.com"},
            {**safe_values, "environment": "production"},
            {**safe_values, "identity_database": "legacy"},
            {**safe_values, "uat_auth_bypass_enabled": True},
        )
        for values in unsafe_values:
            with self.subTest(values=values), patch.multiple(settings, **values):
                with self.assertRaises(RuntimeError):
                    require_retail_persona_uat(
                        self._args(),
                        password="safe-temporary-retail-password",
                    )

    def test_persona_disable_does_not_require_password(self) -> None:
        safe_values = {
            "environment": "development",
            "saas_public_base_url": "https://uat-pos.foodchainservice.com",
            "identity_database": "platform_core",
            "uat_auth_bypass_enabled": False,
        }
        with patch.multiple(settings, **safe_values):
            require_retail_persona_uat(self._args(disabled=True), password="")

    def test_persona_maps_only_the_audited_retail_showcase_store(self) -> None:
        source = (ROOT / "backend/app/cli/prepare_retail_uat_persona.py").read_text()
        self.assertIn('StockLocation.code == "UI-MAIN"', source)
        self.assertIn("link.store_location_id = location.id", source)
        self.assertIn('action="uat.retail.store_location.prepare"', source)


class RetailLookupGuardTests(unittest.IsolatedAsyncioTestCase):
    async def test_lookup_rejects_unsigned_retail_context_before_database_access(self) -> None:
        current = _current()
        current.brand_id = None
        with self.assertRaises(HTTPException) as raised:
            await lookup_retail_product(
                code="8850000000001",
                location_id=uuid.uuid4(),
                qty=Decimal("1"),
                current=current,
                db=object(),  # type: ignore[arg-type]
            )
        self.assertEqual(raised.exception.status_code, 403)


class RetailUxContractTests(unittest.TestCase):
    def test_exception_and_payment_states_are_persistent_and_fail_closed(self) -> None:
        page = (ROOT / "frontend/src/pages/pos/POSPage.tsx").read_text()
        api = (ROOT / "frontend/src/lib/productApi.ts").read_text()
        self.assertIn("RetailExceptionState", page)
        self.assertIn("ราคามีการเปลี่ยนแปลง", page)
        self.assertIn("ไม่พบบาร์โค้ด", page)
        self.assertIn("ต้องเลือก Variant", page)
        self.assertIn("ขายได้สูงสุด", page)
        self.assertIn("Loyalty ยังไม่เปิดใน Retail Pilot", page)
        self.assertIn("รอ Provider/Policy UAT", page)
        self.assertIn("เครื่องพิมพ์และลิ้นชักเงินสด: ยังไม่ยืนยัน Physical UAT", page)
        self.assertIn('api.get<ApiResponse<RetailLookupResult>>("/products/retail/lookup"', api)

    def test_customer_search_masks_phone_and_retail_price_uses_server_quote(self) -> None:
        page = (ROOT / "frontend/src/pages/pos/POSPage.tsx").read_text()
        self.assertIn("maskPhone(customer.phone)", page)
        self.assertIn("pricedLine.authoritative_unit_price", page)
        self.assertIn("expected_price_version: line.priceVersion", page)
        self.assertIn("ใช้ราคา Server", page)
        self.assertIn('catalog_scope: "retail_sale"', page)
        self.assertIn("signedRows.find((item) => item.id === result.product?.id)", page)

    def test_retail_pricing_quote_schema_is_bounded_and_hold_waits_for_wp57(self) -> None:
        page = (ROOT / "frontend/src/pages/pos/POSPage.tsx").read_text()
        navigation = (ROOT / "frontend/src/components/pos/PosWorkspaceNav.tsx").read_text()
        retail_env = (ROOT / "backend/alembic_retail/env.py").read_text()
        migration = (
            ROOT
            / "backend/alembic_retail/versions/p10retail0004_add_server_authoritative_pricing.py"
        ).read_text()

        self.assertIn('enabled: Boolean(currentShift) && !isRetailMode', page)
        self.assertIn('holdEnabled={!isRetailMode}', page)
        self.assertIn('"พักบิล · WP57"', navigation)
        self.assertIn('"price_calculations"', retail_env)
        self.assertIn('down_revision: Union[str, None] = "p9retail0003"', migration)
        self.assertIn('op.create_table(\n        "price_calculations"', migration)


if __name__ == "__main__":
    unittest.main()
