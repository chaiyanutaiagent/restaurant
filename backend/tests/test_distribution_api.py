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


class DistributionApiTests(unittest.TestCase):
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
        self.original_flag = settings.company_distribution_writes_enabled

    def tearDown(self) -> None:
        settings.company_distribution_writes_enabled = self.original_flag
        self.client.close()
        app.dependency_overrides.clear()

    def test_dashboard_uses_signed_company_and_exposes_dark_launch(self) -> None:
        settings.company_distribution_writes_enabled = False
        service = MagicMock()
        service.dashboard = AsyncMock(return_value={"demands": [], "shipments": [], "setup_options": {}})
        with patch("app.routers.company_distribution.DistributionService", return_value=service):
            response = self.client.get(
                "/api/v1/company-distribution/dashboard",
                params={"company_id": str(uuid.uuid4())},
            )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertFalse(response.json()["data"]["write_enabled"])
        service.dashboard.assert_awaited_once_with(self.company_id)

    def test_report_forwards_signed_company_and_dates(self) -> None:
        service = MagicMock()
        service.report = AsyncMock(return_value={"date_from": "2026-09-01", "date_to": "2026-09-14", "totals": {}, "by_workspace": [], "shipments": []})
        with patch("app.routers.company_distribution.DistributionService", return_value=service):
            response = self.client.get(
                "/api/v1/company-distribution/report",
                params={"date_from": "2026-09-01", "date_to": "2026-09-14"},
            )
        self.assertEqual(response.status_code, 200, response.text)
        service.report.assert_awaited_once_with(self.company_id, date(2026, 9, 1), date(2026, 9, 14))

    def test_write_endpoint_fails_closed_before_service_call(self) -> None:
        settings.company_distribution_writes_enabled = False
        service = MagicMock()
        service.create_demand = AsyncMock()
        with patch("app.routers.company_distribution.DistributionService", return_value=service):
            response = self.client.post("/api/v1/company-distribution/demands", json={
                "source_module": "restaurant_pos",
                "brand_id": str(uuid.uuid4()),
                "branch_id": str(uuid.uuid4()),
                "product_id": str(uuid.uuid4()),
                "needed_on": "2026-09-15",
                "requested_qty": "10",
                "unit_code": "ea",
                "source_type": "restaurant_replenishment",
                "source_id": "REQ-001",
                "idempotency_key": "wp6-api-demand-001",
            })
        self.assertEqual(response.status_code, 409, response.text)
        service.create_demand.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
