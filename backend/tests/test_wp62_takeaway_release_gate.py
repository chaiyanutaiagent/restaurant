from __future__ import annotations

from types import SimpleNamespace
import unittest
from unittest.mock import patch
import uuid

from fastapi import HTTPException

from app.config import validate_takeaway_write_activation_config
from app.dependencies import TokenData
from app.routers.takeaway import (
    public_router,
    require_takeaway_write_activation,
    router,
    takeaway_status,
)


def request(method: str, path: str) -> SimpleNamespace:
    return SimpleNamespace(method=method, url=SimpleNamespace(path=path))


class TakeawayReleaseGateTests(unittest.IsolatedAsyncioTestCase):
    async def test_reads_and_non_mutating_previews_remain_available(self) -> None:
        for method, path in (
            ("GET", "/api/v1/takeaway/orders"),
            ("POST", "/api/v1/takeaway/imports/dry-run"),
            ("POST", "/api/v1/takeaway/cutover/preview"),
        ):
            await require_takeaway_write_activation(request(method, path))

    async def test_transaction_write_fails_closed_by_default(self) -> None:
        with patch("app.routers.takeaway.settings.takeaway_uat_transaction_writes_enabled", False):
            with self.assertRaises(HTTPException) as denied:
                await require_takeaway_write_activation(
                    request("POST", "/api/v1/takeaway/sales")
                )
        self.assertEqual(denied.exception.status_code, 409)
        self.assertEqual(denied.exception.detail["code"], "takeaway_write_hold")

    async def test_explicit_uat_write_gate_allows_mutation(self) -> None:
        with patch("app.routers.takeaway.settings.takeaway_uat_transaction_writes_enabled", True):
            await require_takeaway_write_activation(
                request("POST", "/api/v1/takeaway/kitchen/tickets/example/ready")
            )

    async def test_status_exposes_release_state_and_holds(self) -> None:
        current = TokenData(
            user_id=uuid.uuid4(),
            company_id=uuid.uuid4(),
            brand_id=uuid.uuid4(),
            branch_id=uuid.uuid4(),
            business_type="takeaway",
            target_database="takeaway",
            permissions=["takeaway.catalog.view"],
        )
        with (
            patch("app.routers.takeaway.settings.takeaway_feature_enabled", True),
            patch("app.routers.takeaway.settings.takeaway_uat_transaction_writes_enabled", False),
        ):
            result = await takeaway_status(current)
        self.assertTrue(result["data"]["enabled"])
        self.assertFalse(result["data"]["writes_enabled"])
        self.assertEqual(result["data"]["release_stage"], "dark_launch")
        self.assertIn("owner_canary_signoff", result["data"]["hard_holds"])

    def test_every_takeaway_route_carries_server_release_gate(self) -> None:
        for current_router in (router, public_router):
            for route in current_router.routes:
                calls = [dependency.call for dependency in route.dependant.dependencies]
                self.assertIn(
                    require_takeaway_write_activation,
                    calls,
                    msg=f"missing release gate: {getattr(route, 'path', 'unknown')}",
                )


class TakeawayWriteActivationConfigTests(unittest.TestCase):
    def test_activation_is_uat_development_only(self) -> None:
        with self.assertRaisesRegex(ValueError, "UAT development"):
            validate_takeaway_write_activation_config(
                environment="production",
                enabled=True,
                feature_enabled=True,
                public_base_url="https://pos.foodchainservice.com",
            )
        with self.assertRaisesRegex(ValueError, "uat-\*"):
            validate_takeaway_write_activation_config(
                environment="development",
                enabled=True,
                feature_enabled=True,
                public_base_url="https://pos.foodchainservice.com",
            )
        validate_takeaway_write_activation_config(
            environment="development",
            enabled=True,
            feature_enabled=True,
            public_base_url="https://uat-pos.foodchainservice.com",
        )

    def test_activation_requires_takeaway_feature(self) -> None:
        with self.assertRaisesRegex(ValueError, "TAKEAWAY_FEATURE_ENABLED"):
            validate_takeaway_write_activation_config(
                environment="development",
                enabled=True,
                feature_enabled=False,
                public_base_url="https://uat-pos.foodchainservice.com",
            )


if __name__ == "__main__":
    unittest.main()
