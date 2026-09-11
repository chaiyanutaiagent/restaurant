import unittest
from unittest.mock import patch
import uuid

from fastapi import HTTPException

from app.database import AsyncSessionLocal
from app.dependencies import TokenData, operational_session_factory_for


def context(target_database: str | None) -> TokenData:
    return TokenData(
        user_id=uuid.uuid4(),
        company_id=uuid.uuid4(),
        branch_id=uuid.uuid4() if target_database else None,
        permissions=[],
        target_database=target_database,
    )


class OperationalDatabaseRoutingTests(unittest.TestCase):
    def test_restaurant_context_uses_restaurant_factory(self) -> None:
        sentinel = object()
        with patch(
            "app.dependencies.active_restaurant_service_session_factory",
            return_value=sentinel,
        ):
            self.assertIs(operational_session_factory_for(context("restaurant")), sentinel)

    def test_retail_and_unselected_company_context_remain_legacy_compatible(self) -> None:
        self.assertIs(operational_session_factory_for(context("retail_pos")), AsyncSessionLocal)
        self.assertIs(operational_session_factory_for(context(None)), AsyncSessionLocal)

    def test_takeaway_context_uses_server_owned_factory_when_enabled(self) -> None:
        sentinel = object()
        with patch(
            "app.dependencies.active_takeaway_service_session_factory",
            return_value=sentinel,
        ):
            self.assertIs(operational_session_factory_for(context("takeaway")), sentinel)

    def test_takeaway_context_fails_closed_when_disabled(self) -> None:
        with patch(
            "app.dependencies.active_takeaway_service_session_factory",
            side_effect=ValueError("disabled"),
        ):
            with self.assertRaises(HTTPException) as raised:
                operational_session_factory_for(context("takeaway"))
        self.assertEqual(raised.exception.status_code, 503)

    def test_unknown_operational_context_is_rejected(self) -> None:
        with self.assertRaises(HTTPException) as raised:
            operational_session_factory_for(context("client_selected_database"))
        self.assertEqual(raised.exception.status_code, 403)


if __name__ == "__main__":
    unittest.main()
