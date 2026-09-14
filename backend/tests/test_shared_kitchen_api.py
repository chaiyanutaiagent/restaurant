from __future__ import annotations

from datetime import date
import unittest
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from app.config import settings
from app.database import get_db
from app.dependencies import TokenData, get_current_user
from app.main import app


class SharedKitchenApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.company_id = uuid.uuid4()
        self.user_id = uuid.uuid4()
        self.db = MagicMock()

        async def current_user() -> TokenData:
            return TokenData(
                user_id=self.user_id,
                company_id=self.company_id,
                branch_id=None,
                permissions=["system.company.edit"],
            )

        async def legacy_db():
            return self.db

        app.dependency_overrides[get_current_user] = current_user
        app.dependency_overrides[get_db] = legacy_db
        self.client = TestClient(app)
        self.original_write_flag = settings.company_kitchen_writes_enabled

    def tearDown(self) -> None:
        settings.company_kitchen_writes_enabled = self.original_write_flag
        self.client.close()
        app.dependency_overrides.clear()

    def test_dashboard_uses_signed_company_and_exposes_dark_launch_state(self) -> None:
        settings.company_kitchen_writes_enabled = False
        service = MagicMock()
        service.dashboard = AsyncMock(return_value={
            "kitchen": None,
            "ingredients": [],
            "aliases": [],
            "demands": [],
            "orders": [],
            "setup_options": {"branches": [], "locations": [], "brands": [], "brand_branches": [], "products": []},
        })
        with patch("app.routers.company_kitchen.SharedKitchenService", return_value=service):
            response = self.client.get(
                "/api/v1/company-kitchen/dashboard",
                params={"company_id": str(uuid.uuid4())},
            )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertFalse(response.json()["data"]["write_enabled"])
        self.assertEqual(service.dashboard.await_args.args[0], self.company_id)

    def test_report_forwards_server_scoped_company_and_business_dates(self) -> None:
        service = MagicMock()
        service.report = AsyncMock(return_value={
            "date_from": date(2026, 9, 1),
            "date_to": date(2026, 9, 14),
            "production_by_brand": [],
            "ingredient_usage": [],
            "orders": [],
        })
        with patch("app.routers.company_kitchen.SharedKitchenService", return_value=service):
            response = self.client.get(
                "/api/v1/company-kitchen/report",
                params={"date_from": "2026-09-01", "date_to": "2026-09-14"},
            )

        self.assertEqual(response.status_code, 200, response.text)
        service.report.assert_awaited_once_with(
            self.company_id,
            date(2026, 9, 1),
            date(2026, 9, 14),
        )

    def test_write_endpoint_fails_closed_before_service_call(self) -> None:
        settings.company_kitchen_writes_enabled = False
        service = MagicMock()
        service.receive = AsyncMock()
        with patch("app.routers.company_kitchen.SharedKitchenService", return_value=service):
            response = self.client.post(
                "/api/v1/company-kitchen/receipts",
                json={
                    "ingredient_id": str(uuid.uuid4()),
                    "lot_code": "PORK-LOT-01",
                    "qty": "1000",
                    "unit_cost": "0.10",
                    "idempotency_key": "api-dark-launch-001",
                    "reference_type": "goods_receipt",
                    "reference_id": "GR-001",
                },
            )

        self.assertEqual(response.status_code, 409, response.text)
        service.receive.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
