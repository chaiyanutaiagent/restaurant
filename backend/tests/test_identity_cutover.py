from __future__ import annotations

import asyncio
import unittest
from unittest.mock import AsyncMock, patch
import uuid

from app.database import (
    AsyncSessionLocal,
    PlatformSessionLocal,
    RestaurantSessionLocal,
    identity_session_factory_for,
    restaurant_service_session_factory_for,
    validate_runtime_database_names,
)
from app.models.user import User
from app.services.auth_service import AuthService
from app.services.platform_reference_projection import ProjectionBatchResult
from app.services.reference_projector_worker import (
    ReferenceProjectorRuntimeState,
    run_reference_projector,
)
from app.routers.auth import ok


class IdentityCutoverTests(unittest.IsolatedAsyncioTestCase):
    def test_identity_session_factory_is_server_owned(self) -> None:
        self.assertIs(identity_session_factory_for("legacy"), AsyncSessionLocal)
        self.assertIs(identity_session_factory_for("platform_core"), PlatformSessionLocal)
        with self.assertRaisesRegex(ValueError, "Unsupported identity database"):
            identity_session_factory_for("client_selected_database")

    def test_restaurant_service_session_factory_is_server_owned(self) -> None:
        self.assertIs(
            restaurant_service_session_factory_for("legacy"),
            AsyncSessionLocal,
        )
        self.assertIs(
            restaurant_service_session_factory_for("restaurant"),
            RestaurantSessionLocal,
        )
        with self.assertRaisesRegex(ValueError, "Unsupported Restaurant service database"):
            restaurant_service_session_factory_for("client_selected_database")

    def test_restaurant_cutover_requires_platform_identity(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "IDENTITY_DATABASE=platform_core"):
            validate_runtime_database_names(
                identity_database="legacy",
                restaurant_service_database="restaurant",
                reference_projector_enabled=True,
                legacy_database_name="legacy",
                platform_database_name="platform",
                restaurant_database_name="restaurant",
            )

    def test_restaurant_cutover_accepts_safe_runtime_topology(self) -> None:
        validate_runtime_database_names(
            identity_database="platform_core",
            restaurant_service_database="restaurant",
            reference_projector_enabled=True,
            legacy_database_name="legacy",
            platform_database_name="platform",
            restaurant_database_name="restaurant",
        )

    def test_platform_mode_requires_projector(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "REFERENCE_PROJECTOR_ENABLED"):
            validate_runtime_database_names(
                identity_database="platform_core",
                reference_projector_enabled=False,
                legacy_database_name="legacy",
                platform_database_name="platform",
                restaurant_database_name="restaurant",
            )

    def test_cutover_requires_three_physical_databases(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "distinct legacy"):
            validate_runtime_database_names(
                identity_database="platform_core",
                reference_projector_enabled=True,
                legacy_database_name="shared",
                platform_database_name="shared",
                restaurant_database_name="restaurant",
            )

    def test_legacy_default_does_not_require_physical_split(self) -> None:
        validate_runtime_database_names(
            identity_database="legacy",
            reference_projector_enabled=False,
            legacy_database_name="shared",
            platform_database_name="shared",
            restaurant_database_name="shared",
        )

    def test_auth_metadata_exposes_server_owned_identity_source(self) -> None:
        response = ok({"message": "test"})
        self.assertEqual(response["meta"]["identity_database"], "legacy")

    async def test_platform_login_enqueues_user_in_same_session(self) -> None:
        company_id = uuid.uuid4()
        user = User(
            id=uuid.uuid4(),
            company_id=company_id,
            username="platform-user",
            hashed_password="hash",
            is_active=True,
        )
        session = AsyncMock()
        session.scalar.return_value = user

        with (
            patch("app.services.auth_service.verify_password", return_value=True),
            patch(
                "app.services.auth_service.enqueue_reference_event",
                new_callable=AsyncMock,
            ) as enqueue,
        ):
            authenticated = await AuthService(
                session,
                emit_reference_events=True,
            ).authenticate_user(company_id, user.username, "password")

        self.assertIs(authenticated, user)
        self.assertIsNotNone(user.last_login_at)
        session.flush.assert_awaited_once()
        enqueue.assert_awaited_once_with(
            session,
            aggregate_type="user",
            aggregate_id=user.id,
            company_id=company_id,
            payload={"source": "auth.login"},
        )
        session.commit.assert_not_awaited()

    async def test_legacy_login_does_not_touch_platform_outbox(self) -> None:
        company_id = uuid.uuid4()
        user = User(
            id=uuid.uuid4(),
            company_id=company_id,
            username="legacy-user",
            hashed_password="hash",
            is_active=True,
        )
        session = AsyncMock()
        session.scalar.return_value = user

        with (
            patch("app.services.auth_service.verify_password", return_value=True),
            patch(
                "app.services.auth_service.enqueue_reference_event",
                new_callable=AsyncMock,
            ) as enqueue,
        ):
            await AuthService(session).authenticate_user(
                company_id,
                user.username,
                "password",
            )

        enqueue.assert_not_awaited()

    async def test_projector_worker_tracks_successful_batch(self) -> None:
        stop_event = asyncio.Event()
        state = ReferenceProjectorRuntimeState()

        async def process(*, limit: int) -> ProjectionBatchResult:
            self.assertEqual(limit, 25)
            stop_event.set()
            return ProjectionBatchResult(claimed=2, applied=1, replayed=1, failed=0)

        with patch(
            "app.services.reference_projector_worker.process_projection_batch",
            side_effect=process,
        ):
            await run_reference_projector(
                stop_event,
                poll_seconds=0.1,
                batch_size=25,
                state=state,
            )

        self.assertFalse(state.running)
        self.assertEqual(state.batches, 1)
        self.assertEqual(state.claimed, 2)
        self.assertEqual(state.applied, 1)
        self.assertEqual(state.replayed, 1)
