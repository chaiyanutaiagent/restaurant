from decimal import Decimal
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import uuid

from app.dependencies import TokenData
from app.routers.pos import _sale_service
from app.services.report_service import net_order_total


class RetailPOSCutoverTests(unittest.TestCase):
    def _token(self, target_database: str) -> TokenData:
        return TokenData(
            user_id=uuid.uuid4(),
            company_id=uuid.uuid4(),
            branch_id=uuid.uuid4(),
            permissions=[],
            brand_id=uuid.uuid4(),
            business_type="retail_pos",
            target_database=target_database,
        )

    def test_retail_database_disables_legacy_only_sale_side_effects(self) -> None:
        with patch("app.routers.pos.settings.retail_service_database", "retail"):
            service = _sale_service(object(), self._token("retail_pos"))  # type: ignore[arg-type]
        self.assertFalse(service.legacy_side_effects_enabled)

    def test_legacy_route_keeps_existing_sale_side_effects(self) -> None:
        with patch("app.routers.pos.settings.retail_service_database", "legacy"):
            service = _sale_service(object(), self._token("retail_pos"))  # type: ignore[arg-type]
        self.assertTrue(service.legacy_side_effects_enabled)

    def test_report_total_is_net_of_refund_and_never_negative(self) -> None:
        self.assertEqual(
            net_order_total(SimpleNamespace(total_amount=107, refund_amount=25.5)),
            Decimal("81.50"),
        )
        self.assertEqual(
            net_order_total(SimpleNamespace(total_amount=107, refund_amount=107)),
            Decimal("0.00"),
        )
        self.assertEqual(
            net_order_total(SimpleNamespace(total_amount=107, refund_amount=200)),
            Decimal("0.00"),
        )


if __name__ == "__main__":
    unittest.main()
