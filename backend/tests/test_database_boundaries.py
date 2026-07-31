import unittest

from app.config import effective_database_url, settings
from app.database import (
    AsyncSessionLocal,
    PlatformSessionLocal,
    RestaurantSessionLocal,
    session_factory_for,
)


class DatabaseBoundaryTests(unittest.TestCase):
    def test_explicit_urls_fall_back_to_legacy_database_url(self) -> None:
        self.assertEqual(effective_database_url(None, "legacy"), "legacy")
        self.assertEqual(effective_database_url("explicit", "legacy"), "explicit")

        self.assertEqual(
            settings.platform_database_url_effective,
            settings.platform_database_url or settings.database_url,
        )
        self.assertEqual(
            settings.restaurant_database_url_effective,
            settings.restaurant_database_url or settings.database_url,
        )

    def test_server_owned_target_database_registry(self) -> None:
        self.assertIs(session_factory_for("platform_core"), PlatformSessionLocal)
        self.assertIs(session_factory_for("restaurant"), RestaurantSessionLocal)

        with self.assertRaisesRegex(ValueError, "Unsupported target database"):
            session_factory_for("frontend_selected_database")

    def test_legacy_session_factory_remains_available_during_boundary_slice(self) -> None:
        self.assertIsNot(AsyncSessionLocal, None)
