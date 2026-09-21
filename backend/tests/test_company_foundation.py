from __future__ import annotations

from datetime import datetime, timedelta, timezone
import unittest
import uuid
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException

from app.dependencies import TokenData
from app.services.company_context_service import (
    default_route_for_permissions,
    scoped_branch_ids,
)
from app.services.company_module_access_service import (
    COMPANY_MODULES_BY_KEY,
    canonical_runtime_environment,
    module_allowed_actions,
    module_readiness,
)
from app.services.company_operational_status_service import (
    resolve_device_operational_state,
)
from app.schemas.module_access import CompanyModuleAccessRead
from app.services.company_overview_service import CompanyOverviewService
from app.services.company_owner_policy import CompanyOwnerPolicy


class CompanyContextContractTests(unittest.TestCase):
    def test_default_route_prefers_signed_business_context(self) -> None:
        permissions = ["fb.order.create", "takeaway.kitchen.manage", "pos.sale.view"]
        self.assertEqual(
            default_route_for_permissions(permissions, business_type="restaurant"),
            "/restaurant",
        )
        self.assertEqual(
            default_route_for_permissions(permissions, business_type="takeaway"),
            "/takeaway",
        )
        self.assertEqual(
            default_route_for_permissions(permissions, business_type="retail_pos"),
            "/pos",
        )

    def test_company_admin_and_empty_permission_routes_fail_safely(self) -> None:
        self.assertEqual(default_route_for_permissions(["system.company.view"]), "/company")
        self.assertEqual(default_route_for_permissions([]), "/403")

    def test_restaurant_cashier_does_not_land_in_takeaway(self) -> None:
        permissions = ["pos.sale.create", "takeaway.sale.create", "takeaway.shift.manage"]
        self.assertEqual(
            default_route_for_permissions(permissions, business_type="restaurant"),
            "/pos",
        )

    def test_runtime_environment_is_canonical(self) -> None:
        self.assertEqual(canonical_runtime_environment("production"), "production")
        self.assertEqual(canonical_runtime_environment("development"), "uat")
        self.assertEqual(canonical_runtime_environment("uat"), "uat")


class CompanyScopeContractTests(unittest.IsolatedAsyncioTestCase):
    async def test_company_scope_is_unrestricted_and_brand_scope_is_allowlisted(self) -> None:
        company_id = uuid.uuid4()
        user_id = uuid.uuid4()
        brand_id = uuid.uuid4()
        branch_ids = [uuid.uuid4(), uuid.uuid4()]
        db = AsyncMock()
        db.scalars.return_value = branch_ids

        company_scope = TokenData(
            user_id=user_id,
            company_id=company_id,
            branch_id=None,
            permissions=["system.company.view"],
            scope_types=["company"],
        )
        self.assertIsNone(await scoped_branch_ids(company_scope, db))
        db.scalars.assert_not_awaited()

        brand_scope = TokenData(
            user_id=user_id,
            company_id=company_id,
            branch_id=None,
            brand_id=brand_id,
            permissions=["pos.report.view"],
            scope_types=["brand"],
        )
        self.assertEqual(await scoped_branch_ids(brand_scope, db), branch_ids)
        db.scalars.assert_awaited_once()

    async def test_missing_scope_fails_closed(self) -> None:
        current = TokenData(
            user_id=uuid.uuid4(),
            company_id=uuid.uuid4(),
            branch_id=None,
            permissions=["pos.report.view"],
            scope_types=[],
        )
        self.assertEqual(await scoped_branch_ids(current, AsyncMock()), [])


class ProductReadinessContractTests(unittest.TestCase):
    def test_read_only_and_dark_launch_actions_fail_closed(self) -> None:
        central = COMPANY_MODULES_BY_KEY["central_kitchen"]
        takeaway = COMPANY_MODULES_BY_KEY["takeaway_pos"]
        self.assertEqual(
            module_allowed_actions(
                central,
                readiness="read_only",
                effective_access=True,
                permissions=["company.kitchen.manage"],
            ),
            ["view", "export"],
        )
        self.assertEqual(
            module_allowed_actions(
                takeaway,
                readiness="dark_launch",
                effective_access=True,
                permissions=["takeaway.sale.create"],
            ),
            [],
        )

    def test_central_kitchen_readiness_requires_both_write_gates(self) -> None:
        definition = COMPANY_MODULES_BY_KEY["central_kitchen"]
        with (
            patch(
                "app.services.company_module_access_service.settings.company_kitchen_writes_enabled",
                True,
            ),
            patch(
                "app.services.company_module_access_service.settings.company_distribution_writes_enabled",
                False,
            ),
        ):
            self.assertEqual(module_readiness(definition), "read_only")
        with (
            patch(
                "app.services.company_module_access_service.settings.company_kitchen_writes_enabled",
                True,
            ),
            patch(
                "app.services.company_module_access_service.settings.company_distribution_writes_enabled",
                True,
            ),
        ):
            self.assertEqual(module_readiness(definition), "pilot")

    def test_module_actions_ignore_permissions_from_another_product(self) -> None:
        restaurant = COMPANY_MODULES_BY_KEY["restaurant_pos"]
        self.assertEqual(
            module_allowed_actions(
                restaurant,
                readiness="pilot",
                effective_access=True,
                permissions=["fb.menu.view", "system.company.edit"],
            ),
            ["view"],
        )
        self.assertEqual(
            module_allowed_actions(
                COMPANY_MODULES_BY_KEY["erp"],
                readiness="production",
                effective_access=True,
                permissions=[],
            ),
            ["view"],
        )


class OperationalStateContractTests(unittest.TestCase):
    def test_device_state_thresholds_and_revocation(self) -> None:
        now = datetime.now(timezone.utc)
        self.assertEqual(
            resolve_device_operational_state(
                revoked_at=now,
                paired_at=now,
                last_seen_at=now,
                now=now,
            ),
            "disabled",
        )
        self.assertEqual(
            resolve_device_operational_state(
                revoked_at=None,
                paired_at=now,
                last_seen_at=now - timedelta(minutes=1),
                now=now,
            ),
            "online",
        )
        self.assertEqual(
            resolve_device_operational_state(
                revoked_at=None,
                paired_at=now,
                last_seen_at=now - timedelta(minutes=10),
                now=now,
            ),
            "degraded",
        )
        self.assertEqual(
            resolve_device_operational_state(
                revoked_at=None,
                paired_at=now,
                last_seen_at=now - timedelta(hours=1),
                now=now,
            ),
            "stale",
        )


class CompanyOverviewContractTests(unittest.TestCase):
    def test_erp_metrics_do_not_expose_unpermitted_counts(self) -> None:
        module = CompanyModuleAccessRead(
            module_key="erp",
            lifecycle="active",
            readiness="production",
            environment="uat",
            company_enabled=True,
            plan_included=True,
            runtime_ready=True,
            user_permitted=True,
            effective_access=True,
            reason_code="enabled",
            updated_at=datetime.now(timezone.utc),
        )
        section = CompanyOverviewService._section(
            module,
            counts={
                "branches": 4,
                "users": 30,
                "purchase_pending": 2,
                "transfer_pending": 3,
                "tax_open": 1,
                "restaurant_sessions": 0,
                "kitchen_tickets": 0,
                "production_demands": 0,
                "production_orders": 0,
                "devices": 0,
            },
            device_attention=0,
            permissions=[],
            now=datetime.now(timezone.utc),
        )

        self.assertEqual([metric.key for metric in section.metrics], ["access"])

    def test_erp_metrics_follow_effective_permissions(self) -> None:
        module = CompanyModuleAccessRead(
            module_key="erp",
            lifecycle="active",
            company_enabled=True,
            plan_included=True,
            runtime_ready=True,
            user_permitted=True,
            effective_access=True,
            reason_code="enabled",
            updated_at=datetime.now(timezone.utc),
        )
        section = CompanyOverviewService._section(
            module,
            counts={
                "branches": 4,
                "users": 30,
                "purchase_pending": 2,
                "transfer_pending": 3,
                "tax_open": 1,
                "restaurant_sessions": 0,
                "kitchen_tickets": 0,
                "production_demands": 0,
                "production_orders": 0,
                "devices": 0,
            },
            device_attention=0,
            permissions=["inventory.purchase.view"],
            now=datetime.now(timezone.utc),
        )

        self.assertEqual([metric.key for metric in section.metrics], ["purchase_pending"])


class LastCompanyOwnerPolicyTests(unittest.IsolatedAsyncioTestCase):
    async def test_last_owner_cannot_be_deactivated(self) -> None:
        policy = CompanyOwnerPolicy(AsyncMock())
        policy._lock_company = AsyncMock()
        policy._is_active_owner = AsyncMock(return_value=True)
        policy._active_owner_count = AsyncMock(return_value=1)

        with self.assertRaises(HTTPException) as raised:
            await policy.ensure_user_can_be_deactivated(uuid.uuid4(), uuid.uuid4())

        self.assertEqual(raised.exception.status_code, 409)
        self.assertEqual(raised.exception.detail["code"], "last_company_owner")

    async def test_non_owner_deactivation_is_not_blocked(self) -> None:
        policy = CompanyOwnerPolicy(AsyncMock())
        policy._lock_company = AsyncMock()
        policy._is_active_owner = AsyncMock(return_value=False)
        policy._active_owner_count = AsyncMock()

        await policy.ensure_user_can_be_deactivated(uuid.uuid4(), uuid.uuid4())

        policy._active_owner_count.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
