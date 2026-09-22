from __future__ import annotations

import inspect
import unittest
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException
from starlette.requests import Request

from app.routers import restaurant
from app.routers.storefront import PUBLIC_EXPERIENCE_HOLDS, public_experience_contract
from app.utils.public_rate_limit import public_request_rate_key, require_public_rate_limit


def request_for(ip: str = "203.0.113.10") -> Request:
    return Request({"type": "http", "method": "GET", "path": "/", "headers": [], "client": (ip, 1234)})


class PublicExperienceContractTests(unittest.TestCase):
    def test_storefront_is_explicitly_catalog_only(self) -> None:
        contract = public_experience_contract()
        self.assertEqual(contract.mode, "catalog_locator")
        self.assertEqual(contract.release_stage, "public_read_only")
        self.assertTrue(contract.capabilities.catalog)
        self.assertTrue(contract.capabilities.branch_locator)
        self.assertFalse(contract.capabilities.ecommerce)
        self.assertFalse(contract.capabilities.checkout)
        self.assertFalse(contract.capabilities.payment)
        self.assertIn("owner_ecommerce_mode_decision", PUBLIC_EXPERIENCE_HOLDS)
        self.assertIn("privacy_and_consent_center", contract.hard_holds)

    def test_restaurant_public_routes_all_apply_rate_limit(self) -> None:
        functions = [
            restaurant.public_get_menu,
            restaurant.public_place_order,
            restaurant.public_order_status,
            restaurant.public_request_bill,
            restaurant.qs_get_menu,
            restaurant.qs_place_order,
            restaurant.qs_order_status,
        ]
        for function in functions:
            with self.subTest(function=function.__name__):
                self.assertIn("require_public_rate_limit", inspect.getsource(function))


class PublicRateLimitTests(unittest.IsolatedAsyncioTestCase):
    def test_key_does_not_retain_ip_or_token(self) -> None:
        key = public_request_rate_key(request_for(), "restaurant-menu", "secret-public-token")
        self.assertTrue(key.startswith("restaurant-menu:"))
        self.assertNotIn("203.0.113.10", key)
        self.assertNotIn("secret-public-token", key)

    async def test_rejected_request_returns_429(self) -> None:
        with patch("app.utils.public_rate_limit.check_public_rate_limit", new=AsyncMock(return_value=False)):
            with self.assertRaises(HTTPException) as raised:
                await require_public_rate_limit(
                    request_for(),
                    "storefront-summary",
                    subject="foodchain-demo",
                    limit=120,
                )
        self.assertEqual(raised.exception.status_code, 429)


if __name__ == "__main__":
    unittest.main()
