from __future__ import annotations

from datetime import datetime, timezone
import unittest
from unittest.mock import patch
import uuid

from app.services.platform_reference_projection import (
    EVENT_TYPE,
    OutboxEvent,
    REFERENCE_COLUMNS,
    _upsert_sql,
    enqueue_reference_event,
    process_projection_batch,
    projection_backoff_seconds,
    sanitized_projection_error,
    snapshot_event_id,
    validate_aggregate_type,
)


class _ScalarResult:
    def __init__(self, value: object) -> None:
        self.value = value

    def scalar_one_or_none(self) -> object:
        return self.value


class _RecordingSession:
    def __init__(self) -> None:
        self.parameters: dict[str, object] | None = None

    async def execute(self, statement: object, parameters: dict[str, object]) -> _ScalarResult:
        self.parameters = parameters
        return _ScalarResult(parameters["id"])


class _LifecycleSession:
    def __init__(self, name: str, lifecycle: list[str]) -> None:
        self.name = name
        self.lifecycle = lifecycle

    async def commit(self) -> None:
        self.lifecycle.append(f"{self.name}:commit")


class _LifecycleContext:
    def __init__(self, session: _LifecycleSession) -> None:
        self.session = session

    async def __aenter__(self) -> _LifecycleSession:
        self.session.lifecycle.append(f"{self.session.name}:enter")
        return self.session

    async def __aexit__(self, *args: object) -> None:
        self.session.lifecycle.append(f"{self.session.name}:exit")


class _LifecycleFactory:
    def __init__(self, prefix: str, lifecycle: list[str]) -> None:
        self.prefix = prefix
        self.lifecycle = lifecycle
        self.calls = 0

    def __call__(self) -> _LifecycleContext:
        self.calls += 1
        return _LifecycleContext(
            _LifecycleSession(f"{self.prefix}{self.calls}", self.lifecycle)
        )


class PlatformReferenceProjectionTests(unittest.IsolatedAsyncioTestCase):
    def test_snapshot_event_id_is_deterministic_and_revision_sensitive(self) -> None:
        aggregate_id = uuid.uuid4()
        first_revision = datetime(2026, 8, 1, 1, 0, tzinfo=timezone.utc)
        next_revision = datetime(2026, 8, 1, 1, 1, tzinfo=timezone.utc)

        first = snapshot_event_id("branch", aggregate_id, first_revision)
        self.assertEqual(first, snapshot_event_id("branch", aggregate_id, first_revision))
        self.assertNotEqual(first, snapshot_event_id("branch", aggregate_id, next_revision))

    def test_unknown_aggregate_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "Unsupported aggregate type"):
            validate_aggregate_type("frontend_selected_database")

    def test_backoff_is_bounded(self) -> None:
        self.assertEqual(projection_backoff_seconds(1), 1)
        self.assertEqual(projection_backoff_seconds(3), 4)
        self.assertEqual(projection_backoff_seconds(100), 300)

    def test_error_is_sanitized_without_exception_message(self) -> None:
        error = RuntimeError("hashed_password=must-never-be-persisted")
        rendered = sanitized_projection_error(error)
        self.assertEqual(rendered, "builtins.RuntimeError")
        self.assertNotIn("hashed_password", rendered)

    def test_operational_location_columns_are_not_projected(self) -> None:
        self.assertNotIn("central_location_id", REFERENCE_COLUMNS["brand"])
        self.assertNotIn("central_ready_location_id", REFERENCE_COLUMNS["brand"])
        self.assertNotIn("store_location_id", REFERENCE_COLUMNS["brand_branch"])
        self.assertNotIn("central_location_id", _upsert_sql("brand"))
        self.assertNotIn("store_location_id", _upsert_sql("brand_branch"))

    async def test_enqueue_rejects_credentials_before_database_write(self) -> None:
        session = _RecordingSession()
        with self.assertRaisesRegex(ValueError, "forbidden credential"):
            await enqueue_reference_event(  # type: ignore[arg-type]
                session,
                aggregate_type="user",
                aggregate_id=uuid.uuid4(),
                company_id=uuid.uuid4(),
                payload={"trace": {"refreshToken": "secret"}},
            )
        self.assertIsNone(session.parameters)

    async def test_enqueue_payload_contains_only_explicit_metadata(self) -> None:
        session = _RecordingSession()
        inserted = await enqueue_reference_event(  # type: ignore[arg-type]
            session,
            aggregate_type="company",
            aggregate_id=uuid.uuid4(),
            company_id=uuid.uuid4(),
            payload={"source": "unit_test"},
        )
        self.assertTrue(inserted)
        assert session.parameters is not None
        self.assertEqual(session.parameters["payload"], '{"source": "unit_test"}')
        self.assertNotIn("entity", session.parameters)

    async def test_processor_closes_source_transaction_before_target_write(self) -> None:
        lifecycle: list[str] = []
        platform_factory = _LifecycleFactory("platform", lifecycle)
        restaurant_factory = _LifecycleFactory("restaurant", lifecycle)
        event = OutboxEvent(
            id=uuid.uuid4(),
            event_type=EVENT_TYPE,
            aggregate_type="company",
            aggregate_id=uuid.uuid4(),
            company_id=uuid.uuid4(),
            schema_version=1,
            occurred_at=datetime.now(timezone.utc),
            attempt_count=1,
        )

        async def claim(session: object, *, limit: int) -> list[OutboxEvent]:
            lifecycle.append("claim")
            return [event]

        async def load(session: object, claimed_event: OutboxEvent) -> dict[str, object]:
            lifecycle.append("load")
            return {"id": claimed_event.aggregate_id}

        async def apply(
            session: object,
            claimed_event: OutboxEvent,
            source: dict[str, object],
        ) -> bool:
            lifecycle.append("apply")
            return True

        async def mark(session: object, event_id: uuid.UUID) -> None:
            lifecycle.append("mark")

        with (
            patch(
                "app.services.platform_reference_projection.claim_outbox_events",
                side_effect=claim,
            ),
            patch(
                "app.services.platform_reference_projection.load_platform_reference",
                side_effect=load,
            ),
            patch(
                "app.services.platform_reference_projection.apply_restaurant_projection",
                side_effect=apply,
            ),
            patch(
                "app.services.platform_reference_projection.mark_outbox_processed",
                side_effect=mark,
            ),
        ):
            result = await process_projection_batch(  # type: ignore[arg-type]
                limit=1,
                platform_session_factory=platform_factory,
                restaurant_session_factory=restaurant_factory,
            )

        self.assertEqual(result.applied, 1)
        self.assertLess(
            lifecycle.index("platform2:exit"),
            lifecycle.index("restaurant1:enter"),
        )
        self.assertLess(
            lifecycle.index("restaurant1:exit"),
            lifecycle.index("platform3:enter"),
        )
