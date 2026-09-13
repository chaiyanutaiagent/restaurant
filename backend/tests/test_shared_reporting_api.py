from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
import unittest
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from app.database import get_platform_db
from app.dependencies import TokenData, get_current_user
from app.main import app
from app.schemas.shared_reporting import (
    SharedReportingFreshness,
    SharedSalesMetrics,
    SharedSalesReportRead,
)


class SharedReportingApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.company_id = uuid.uuid4()
        self.db = MagicMock()

        async def current_user() -> TokenData:
            return TokenData(
                user_id=uuid.uuid4(),
                company_id=self.company_id,
                branch_id=None,
                permissions=["system.company.edit"],
            )

        async def platform_db():
            return self.db

        app.dependency_overrides[get_current_user] = current_user
        app.dependency_overrides[get_platform_db] = platform_db
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.client.close()
        app.dependency_overrides.clear()

    def test_report_uses_signed_company_and_server_validated_filters(self) -> None:
        metrics = SharedSalesMetrics(
            order_count=0,
            void_count=0,
            refund_count=0,
            gross_sales=Decimal("0.00"),
            discount_amount=Decimal("0.00"),
            tax_amount=Decimal("0.00"),
            refund_amount=Decimal("0.00"),
            net_sales=Decimal("0.00"),
        )
        report = SharedSalesReportRead(
            company_id=self.company_id,
            date_from=date(2026, 9, 1),
            date_to=date(2026, 9, 14),
            generated_at=datetime.now(timezone.utc),
            freshness=SharedReportingFreshness(
                status="disabled",
                projector_enabled=False,
                last_projected_at=None,
                last_polled_at=None,
                lag_seconds=None,
                failed_sources=[],
            ),
            totals=metrics,
            modules=[],
            workspaces=[],
            daily=[],
            recent_documents=[],
        )
        service = MagicMock()
        service.sales_report = AsyncMock(return_value=report)
        with patch("app.routers.membership.SharedReportingService", return_value=service):
            response = self.client.get(
                "/api/v1/membership/reports/shared-sales",
                params={
                    "date_from": "2026-09-01",
                    "date_to": "2026-09-14",
                    "module_key": "restaurant_pos",
                    "company_id": str(uuid.uuid4()),
                },
            )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["data"]["company_id"], str(self.company_id))
        call = service.sales_report.await_args
        self.assertEqual(call.args[0].company_id, self.company_id)
        self.assertEqual(call.kwargs["module_key"], "restaurant_pos")
        self.assertNotIn("company_id", call.kwargs)

    def test_unknown_module_is_rejected(self) -> None:
        response = self.client.get(
            "/api/v1/membership/reports/shared-sales",
            params={
                "date_from": "2026-09-01",
                "date_to": "2026-09-14",
                "module_key": "hotel_pms",
            },
        )
        self.assertEqual(response.status_code, 422, response.text)


if __name__ == "__main__":
    unittest.main()
