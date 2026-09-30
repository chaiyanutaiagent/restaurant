from __future__ import annotations

from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch
import uuid

from fastapi import HTTPException

from app.config import validate_takeaway_write_activation_config
from app.dependencies import TokenData
from app.routers.takeaway import (
    public_router,
    require_public_takeaway_write_activation,
    require_takeaway_write_activation,
    router,
    takeaway_write_allowed,
    takeaway_status,
)


def request(method: str, path: str) -> SimpleNamespace:
    return SimpleNamespace(method=method, url=SimpleNamespace(path=path))


def token_data(
    *,
    company_id: uuid.UUID | None = None,
    brand_id: uuid.UUID | None = None,
    branch_id: uuid.UUID | None = None,
) -> TokenData:
    return TokenData(
        user_id=uuid.uuid4(),
        company_id=company_id or uuid.uuid4(),
        brand_id=brand_id or uuid.uuid4(),
        branch_id=branch_id or uuid.uuid4(),
        business_type="takeaway",
        target_database="takeaway",
        permissions=["takeaway.catalog.view"],
    )


class TakeawayReleaseGateTests(unittest.IsolatedAsyncioTestCase):
    async def test_reads_and_non_mutating_previews_remain_available(self) -> None:
        current = token_data()
        for method, path in (
            ("GET", "/api/v1/takeaway/orders"),
            ("POST", "/api/v1/takeaway/imports/dry-run"),
            ("POST", "/api/v1/takeaway/cutover/preview"),
        ):
            await require_takeaway_write_activation(request(method, path), current)

    async def test_transaction_write_fails_closed_by_default(self) -> None:
        with (
            patch("app.routers.takeaway.settings.takeaway_uat_transaction_writes_enabled", False),
            patch("app.routers.takeaway.settings.takeaway_transaction_write_mode", "hold"),
        ):
            with self.assertRaises(HTTPException) as denied:
                await require_takeaway_write_activation(
                    request("POST", "/api/v1/takeaway/sales"),
                    token_data(),
                )
        self.assertEqual(denied.exception.status_code, 409)
        self.assertEqual(denied.exception.detail["code"], "takeaway_write_hold")

    async def test_explicit_uat_write_gate_allows_mutation(self) -> None:
        with (
            patch("app.routers.takeaway.settings.takeaway_uat_transaction_writes_enabled", True),
            patch("app.routers.takeaway.settings.takeaway_transaction_write_mode", "hold"),
        ):
            await require_takeaway_write_activation(
                request("POST", "/api/v1/takeaway/kitchen/tickets/example/ready"),
                token_data(),
            )

    async def test_canary_requires_all_three_server_context_allowlists(self) -> None:
        company_id, brand_id, branch_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        current = token_data(
            company_id=company_id,
            brand_id=brand_id,
            branch_id=branch_id,
        )
        patches = (
            patch("app.routers.takeaway.settings.takeaway_uat_transaction_writes_enabled", False),
            patch("app.routers.takeaway.settings.takeaway_transaction_write_mode", "canary"),
            patch("app.routers.takeaway.settings.takeaway_transaction_company_allowlist", str(company_id)),
            patch("app.routers.takeaway.settings.takeaway_transaction_brand_allowlist", str(brand_id)),
            patch("app.routers.takeaway.settings.takeaway_transaction_branch_allowlist", str(branch_id)),
        )
        with patches[0], patches[1], patches[2], patches[3], patches[4]:
            await require_takeaway_write_activation(
                request("POST", "/api/v1/takeaway/sales"),
                current,
            )
            self.assertTrue(
                takeaway_write_allowed(
                    company_id=company_id,
                    brand_id=brand_id,
                    branch_id=branch_id,
                )
            )
            self.assertFalse(
                takeaway_write_allowed(
                    company_id=company_id,
                    brand_id=brand_id,
                    branch_id=uuid.uuid4(),
                )
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
            patch("app.routers.takeaway.settings.takeaway_transaction_write_mode", "hold"),
        ):
            platform_db = AsyncMock()
            platform_db.scalar.return_value = None
            result = await takeaway_status(current, platform_db)
        self.assertTrue(result["data"]["enabled"])
        self.assertFalse(result["data"]["writes_enabled"])
        self.assertEqual(result["data"]["release_stage"], "dark_launch")
        self.assertEqual(result["data"]["fulfillment_mode"], "counter_combined")
        self.assertIn("owner_canary_signoff", result["data"]["hard_holds"])

    async def test_status_uses_branch_fulfillment_mode(self) -> None:
        branch_id = uuid.uuid4()
        current = TokenData(
            user_id=uuid.uuid4(), company_id=uuid.uuid4(), brand_id=uuid.uuid4(),
            branch_id=branch_id, business_type="takeaway", target_database="takeaway",
            permissions=["takeaway.sale.create"],
        )
        platform_db = AsyncMock()
        platform_db.scalar.return_value = {
            "takeaway_fulfillment_mode": "counter_combined",
            "takeaway_branch_fulfillment_modes": {str(branch_id): "separate_stations"},
        }
        result = await takeaway_status(current, platform_db)
        self.assertEqual(result["data"]["fulfillment_mode"], "separate_stations")

    def test_every_takeaway_route_carries_server_release_gate(self) -> None:
        for route in router.routes:
            calls = [dependency.call for dependency in route.dependant.dependencies]
            self.assertIn(
                require_takeaway_write_activation,
                calls,
                msg=f"missing release gate: {getattr(route, 'path', 'unknown')}",
            )
        for route in public_router.routes:
            if not set(route.methods or set()).intersection({"POST", "PUT", "PATCH", "DELETE"}):
                continue
            calls = [dependency.call for dependency in route.dependant.dependencies]
            self.assertIn(
                require_public_takeaway_write_activation,
                calls,
                msg=f"missing public release gate: {getattr(route, 'path', 'unknown')}",
            )


class TakeawayWriteActivationConfigTests(unittest.TestCase):
    def test_activation_is_uat_development_only(self) -> None:
        with self.assertRaisesRegex(ValueError, "UAT development"):
            validate_takeaway_write_activation_config(
                environment="production",
                legacy_uat_enabled=True,
                mode="hold",
                feature_enabled=True,
                public_base_url="https://pos.foodchainservice.com",
                company_allowlist="",
                brand_allowlist="",
                branch_allowlist="",
                approval_reference=None,
            )
        with self.assertRaisesRegex(ValueError, "exact approved HTTPS Foodchainservice UAT"):
            validate_takeaway_write_activation_config(
                environment="development",
                legacy_uat_enabled=True,
                mode="hold",
                feature_enabled=True,
                public_base_url="https://pos.foodchainservice.com",
                company_allowlist="",
                brand_allowlist="",
                branch_allowlist="",
                approval_reference=None,
            )
        validate_takeaway_write_activation_config(
            environment="development",
            legacy_uat_enabled=True,
            mode="hold",
            feature_enabled=True,
            public_base_url="https://uat-pos.foodchainservice.com",
            company_allowlist="",
            brand_allowlist="",
            branch_allowlist="",
            approval_reference=None,
        )

    def test_activation_requires_takeaway_feature(self) -> None:
        with self.assertRaisesRegex(ValueError, "TAKEAWAY_FEATURE_ENABLED"):
            validate_takeaway_write_activation_config(
                environment="development",
                legacy_uat_enabled=True,
                mode="hold",
                feature_enabled=False,
                public_base_url="https://uat-pos.foodchainservice.com",
                company_allowlist="",
                brand_allowlist="",
                branch_allowlist="",
                approval_reference=None,
            )

    def test_production_canary_requires_approval_and_complete_allowlists(self) -> None:
        identifier = str(uuid.uuid4())
        with self.assertRaisesRegex(ValueError, "approval reference"):
            validate_takeaway_write_activation_config(
                environment="production",
                legacy_uat_enabled=False,
                mode="canary",
                feature_enabled=True,
                public_base_url="https://takeaway.foodchainservice.com",
                company_allowlist=identifier,
                brand_allowlist=identifier,
                branch_allowlist=identifier,
                approval_reference=None,
            )
        with self.assertRaisesRegex(ValueError, "Branch allowlist"):
            validate_takeaway_write_activation_config(
                environment="production",
                legacy_uat_enabled=False,
                mode="canary",
                feature_enabled=True,
                public_base_url="https://takeaway.foodchainservice.com",
                company_allowlist=identifier,
                brand_allowlist=identifier,
                branch_allowlist="",
                approval_reference="OWNER-2026-09-27",
            )
        validate_takeaway_write_activation_config(
            environment="production",
            legacy_uat_enabled=False,
            mode="canary",
            feature_enabled=True,
            public_base_url="https://takeaway.foodchainservice.com",
            company_allowlist=identifier,
            brand_allowlist=identifier,
            branch_allowlist=identifier,
            approval_reference="OWNER-2026-09-27",
        )


if __name__ == "__main__":
    unittest.main()
