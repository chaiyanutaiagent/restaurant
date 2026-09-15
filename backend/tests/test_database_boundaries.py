import unittest

from app.config import (
    Settings,
    effective_database_url,
    settings,
    validate_shared_reporting_runtime_config,
    validate_retail_runtime_config,
    validate_takeaway_runtime_config,
)
from app.database import (
    AsyncSessionLocal,
    PlatformSessionLocal,
    RestaurantSessionLocal,
    RetailSessionLocal,
    TakeawaySessionLocal,
    active_identity_session_factory,
    active_restaurant_service_session_factory,
    active_retail_service_session_factory,
    active_takeaway_service_session_factory,
    session_factory_for,
)
from app.models.integration import OperationalOutboxEvent
from app.models.takeaway import TakeawayOrder, TakeawayStockBalance


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
        self.assertEqual(settings.retail_service_database, "legacy")
        self.assertFalse(settings.reference_projector_enabled)
        self.assertEqual(settings.takeaway_service_database, "disabled")
        self.assertFalse(settings.takeaway_feature_enabled)
        self.assertFalse(settings.shared_reporting_projector_enabled)
        self.assertIs(active_identity_session_factory(), AsyncSessionLocal)
        self.assertIs(
            active_restaurant_service_session_factory(),
            AsyncSessionLocal,
        )
        self.assertIs(active_retail_service_session_factory(), AsyncSessionLocal)

    def test_restaurant_handoff_has_no_cross_database_foreign_key(self) -> None:
        self.assertEqual(list(OperationalOutboxEvent.__table__.foreign_keys), [])
        table_names = {
            foreign_key.column.table.name
            for foreign_key in OperationalOutboxEvent.__table__.foreign_keys
        }
        self.assertFalse({"retail", "takeaway"} & table_names)

    def test_takeaway_models_have_no_cross_database_foreign_keys(self) -> None:
        self.assertEqual(list(TakeawayOrder.__table__.foreign_keys), [])
        self.assertEqual(list(TakeawayStockBalance.__table__.foreign_keys), [])

    def test_takeaway_boundary_is_explicit_and_dark_by_default(self) -> None:
        self.assertEqual(settings.takeaway_service_database, "disabled")
        self.assertFalse(settings.takeaway_feature_enabled)
        with self.assertRaisesRegex(ValueError, "not enabled"):
            active_takeaway_service_session_factory()
        if settings.takeaway_database_url is None:
            self.assertIsNone(TakeawaySessionLocal)
        with self.assertRaisesRegex(ValueError, "TAKEAWAY_SERVICE_DATABASE"):
            validate_takeaway_runtime_config(
                environment="development",
                enabled=True,
                service_database="disabled",
                database_url="postgresql+asyncpg://db/takeaway",
                identity_database="platform_core",
                reference_projector_enabled=True,
            )
        with self.assertRaisesRegex(ValueError, "TAKEAWAY_DATABASE_URL"):
            validate_takeaway_runtime_config(
                environment="development",
                enabled=True,
                service_database="takeaway",
                database_url=None,
                identity_database="platform_core",
                reference_projector_enabled=True,
            )

    def test_retail_boundary_is_explicit_and_cutover_is_fail_closed(self) -> None:
        self.assertEqual(settings.retail_service_database, "legacy")
        self.assertIs(active_retail_service_session_factory(), AsyncSessionLocal)
        if settings.retail_database_url is None:
            self.assertIsNone(RetailSessionLocal)
        with self.assertRaisesRegex(ValueError, "RETAIL_DATABASE_URL"):
            validate_retail_runtime_config(
                environment="development",
                service_database="retail",
                database_url=None,
                identity_database="platform_core",
                reference_projector_enabled=True,
            )
        with self.assertRaisesRegex(ValueError, "IDENTITY_DATABASE"):
            validate_retail_runtime_config(
                environment="development",
                service_database="retail",
                database_url="postgresql+asyncpg://db/retail",
                identity_database="legacy",
                reference_projector_enabled=True,
            )
        validate_retail_runtime_config(
            environment="development",
            service_database="retail",
            database_url="postgresql+asyncpg://db/retail",
            identity_database="platform_core",
            reference_projector_enabled=True,
        )

    def test_shared_reporting_projector_requires_platform_identity_projection(self) -> None:
        validate_shared_reporting_runtime_config(
            enabled=False,
            identity_database="legacy",
            reference_projector_enabled=False,
        )
        with self.assertRaisesRegex(ValueError, "IDENTITY_DATABASE"):
            validate_shared_reporting_runtime_config(
                enabled=True,
                identity_database="legacy",
                reference_projector_enabled=True,
            )
        with self.assertRaisesRegex(ValueError, "REFERENCE_PROJECTOR_ENABLED"):
            validate_shared_reporting_runtime_config(
                enabled=True,
                identity_database="platform_core",
                reference_projector_enabled=False,
            )
        validate_shared_reporting_runtime_config(
            enabled=True,
            identity_database="platform_core",
            reference_projector_enabled=True,
        )
