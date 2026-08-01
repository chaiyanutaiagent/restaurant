import unittest

from app.config import Settings, effective_database_url, settings
from app.database import (
    AsyncSessionLocal,
    PlatformSessionLocal,
    RestaurantSessionLocal,
    active_identity_session_factory,
    active_restaurant_service_session_factory,
    session_factory_for,
)
from app.models.integration import OperationalOutboxEvent


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

    def test_shared_env_can_include_database_bootstrap_variables(self) -> None:
        self.assertEqual(Settings.model_config.get("extra"), "ignore")

    def test_identity_database_defaults_to_legacy(self) -> None:
        self.assertEqual(settings.identity_database, "legacy")
        self.assertEqual(settings.restaurant_service_database, "legacy")
        self.assertFalse(settings.reference_projector_enabled)
        self.assertIs(active_identity_session_factory(), AsyncSessionLocal)
        self.assertIs(
            active_restaurant_service_session_factory(),
            AsyncSessionLocal,
        )

    def test_restaurant_handoff_has_no_cross_database_foreign_key(self) -> None:
        self.assertEqual(list(OperationalOutboxEvent.__table__.foreign_keys), [])
        table_names = {
            foreign_key.column.table.name
            for foreign_key in OperationalOutboxEvent.__table__.foreign_keys
        }
        self.assertFalse({"retail", "takeaway"} & table_names)
