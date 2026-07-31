from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any
import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.database import PlatformSessionLocal, RestaurantSessionLocal


EVENT_TYPE = "platform.reference.changed.v1"
SCHEMA_VERSION = 1
CLAIM_TIMEOUT_SECONDS = 300
MAX_BACKOFF_SECONDS = 300
SNAPSHOT_EVENT_NAMESPACE = uuid.UUID("bc3d628c-6225-4e02-aad3-a3649f8cf817")

REFERENCE_COLUMNS: dict[str, tuple[str, ...]] = {
    "company": (
        "id",
        "name",
        "name_en",
        "tax_id",
        "vat_registered",
        "address",
        "address_en",
        "phone",
        "email",
        "logo_url",
        "website",
        "currency",
        "timezone",
        "fiscal_year_start",
        "is_active",
        "created_at",
        "updated_at",
    ),
    "branch": (
        "id",
        "company_id",
        "code",
        "name",
        "name_en",
        "address",
        "landmark",
        "phone",
        "email",
        "latitude",
        "longitude",
        "google_maps_url",
        "is_warehouse",
        "is_active",
        "sort_order",
        "created_at",
        "updated_at",
        "deleted_at",
    ),
    "brand": (
        "id",
        "company_id",
        "central_branch_id",
        "slug",
        "name",
        "business_type",
        "storefront_mode",
        "theme_config",
        "is_active",
        "created_at",
        "updated_at",
    ),
    "brand_branch": (
        "id",
        "company_id",
        "brand_id",
        "branch_id",
        "branch_type",
        "is_active",
        "created_at",
        "updated_at",
    ),
    "user": (
        "id",
        "company_id",
        "employee_code",
        "username",
        "email",
        "phone",
        "hashed_password",
        "first_name",
        "last_name",
        "display_name",
        "avatar_url",
        "is_active",
        "is_superuser",
        "last_login_at",
        "password_changed_at",
        "created_at",
        "updated_at",
        "deleted_at",
    ),
}

REFERENCE_TABLES = {
    "company": "companies",
    "branch": "branches",
    "brand": "brands",
    "brand_branch": "brand_branches",
    "user": "users",
}

REFERENCE_PRIORITY = {
    "company": 10,
    "branch": 20,
    "brand": 30,
    "brand_branch": 40,
    "user": 50,
}


class UnsupportedAggregateType(ValueError):
    pass


class ProjectionSourceMissing(RuntimeError):
    pass


@dataclass(frozen=True)
class OutboxEvent:
    id: uuid.UUID
    event_type: str
    aggregate_type: str
    aggregate_id: uuid.UUID
    company_id: uuid.UUID | None
    schema_version: int
    occurred_at: datetime
    attempt_count: int


@dataclass(frozen=True)
class ProjectionBatchResult:
    claimed: int = 0
    applied: int = 0
    replayed: int = 0
    failed: int = 0


@dataclass(frozen=True)
class AggregateParity:
    aggregate_type: str
    source_count: int
    target_count: int
    mismatched_ids: tuple[str, ...]

    @property
    def matches(self) -> bool:
        return self.source_count == self.target_count and not self.mismatched_ids


def validate_aggregate_type(aggregate_type: str) -> None:
    if aggregate_type not in REFERENCE_TABLES:
        raise UnsupportedAggregateType(f"Unsupported aggregate type: {aggregate_type}")


def projection_backoff_seconds(attempt_count: int) -> int:
    return min(MAX_BACKOFF_SECONDS, max(1, 2 ** max(0, attempt_count - 1)))


def sanitized_projection_error(exc: BaseException) -> str:
    return f"{type(exc).__module__}.{type(exc).__name__}"[:255]


def _payload_contains_forbidden_key(value: Any) -> bool:
    forbidden_fragments = ("password", "token", "secret", "credential")
    if isinstance(value, dict):
        for key, nested_value in value.items():
            normalized_key = str(key).lower()
            if any(fragment in normalized_key for fragment in forbidden_fragments):
                return True
            if _payload_contains_forbidden_key(nested_value):
                return True
    elif isinstance(value, (list, tuple)):
        return any(_payload_contains_forbidden_key(item) for item in value)
    return False


def snapshot_event_id(
    aggregate_type: str,
    aggregate_id: uuid.UUID,
    updated_at: datetime,
) -> uuid.UUID:
    validate_aggregate_type(aggregate_type)
    identity = f"{aggregate_type}:{aggregate_id}:{updated_at.isoformat()}"
    return uuid.uuid5(SNAPSHOT_EVENT_NAMESPACE, identity)


async def enqueue_reference_event(
    session: AsyncSession,
    *,
    aggregate_type: str,
    aggregate_id: uuid.UUID,
    company_id: uuid.UUID | None,
    event_id: uuid.UUID | None = None,
    payload: dict[str, Any] | None = None,
) -> bool:
    """Enqueue metadata in the caller's Platform transaction.

    Entity state and credentials deliberately never enter the outbox payload. Callers
    may include non-sensitive trace metadata only.
    """
    validate_aggregate_type(aggregate_type)
    safe_payload = payload or {}
    if _payload_contains_forbidden_key(safe_payload):
        raise ValueError("Outbox payload contains a forbidden credential field")

    result = await session.execute(
        text(
            """
            INSERT INTO reference_outbox (
                id, event_type, aggregate_type, aggregate_id, company_id,
                schema_version, payload
            )
            VALUES (
                :id, :event_type, :aggregate_type, :aggregate_id, :company_id,
                :schema_version, CAST(:payload AS jsonb)
            )
            ON CONFLICT (id) DO NOTHING
            RETURNING id
            """
        ),
        {
            "id": event_id or uuid.uuid4(),
            "event_type": EVENT_TYPE,
            "aggregate_type": aggregate_type,
            "aggregate_id": aggregate_id,
            "company_id": company_id,
            "schema_version": SCHEMA_VERSION,
            "payload": json.dumps(safe_payload, sort_keys=True),
        },
    )
    return result.scalar_one_or_none() is not None


async def seed_snapshot_events(session: AsyncSession) -> int:
    inserted = 0
    for aggregate_type in sorted(REFERENCE_TABLES, key=REFERENCE_PRIORITY.__getitem__):
        table_name = REFERENCE_TABLES[aggregate_type]
        company_expression = "id AS company_id" if aggregate_type == "company" else "company_id"
        rows = (
            await session.execute(
                text(
                    f"SELECT id, {company_expression}, updated_at "
                    f"FROM {table_name} ORDER BY id"
                )
            )
        ).mappings()
        for row in rows:
            was_inserted = await enqueue_reference_event(
                session,
                aggregate_type=aggregate_type,
                aggregate_id=row["id"],
                company_id=row["company_id"],
                event_id=snapshot_event_id(
                    aggregate_type,
                    row["id"],
                    row["updated_at"],
                ),
                payload={"source": "snapshot_seed"},
            )
            inserted += int(was_inserted)
    return inserted


async def claim_outbox_events(
    session: AsyncSession,
    *,
    limit: int,
    claim_timeout_seconds: int = CLAIM_TIMEOUT_SECONDS,
) -> list[OutboxEvent]:
    if limit < 1:
        raise ValueError("limit must be at least 1")
    result = await session.execute(
        text(
            """
            WITH candidates AS (
                SELECT id
                FROM reference_outbox
                WHERE processed_at IS NULL
                  AND available_at <= now()
                  AND (
                      claimed_at IS NULL
                      OR claimed_at < now() - (:claim_timeout_seconds * interval '1 second')
                  )
                ORDER BY
                    CASE aggregate_type
                        WHEN 'company' THEN 10
                        WHEN 'branch' THEN 20
                        WHEN 'brand' THEN 30
                        WHEN 'brand_branch' THEN 40
                        WHEN 'user' THEN 50
                    END,
                    occurred_at,
                    id
                FOR UPDATE SKIP LOCKED
                LIMIT :limit
            )
            UPDATE reference_outbox AS event
            SET claimed_at = now(),
                attempt_count = event.attempt_count + 1
            FROM candidates
            WHERE event.id = candidates.id
            RETURNING
                event.id,
                event.event_type,
                event.aggregate_type,
                event.aggregate_id,
                event.company_id,
                event.schema_version,
                event.occurred_at,
                event.attempt_count
            """
        ),
        {"limit": limit, "claim_timeout_seconds": claim_timeout_seconds},
    )
    events = [OutboxEvent(**dict(row)) for row in result.mappings()]
    return sorted(
        events,
        key=lambda event: (
            REFERENCE_PRIORITY[event.aggregate_type],
            event.occurred_at,
            str(event.id),
        ),
    )


async def load_platform_reference(
    session: AsyncSession,
    event: OutboxEvent,
) -> dict[str, Any]:
    validate_aggregate_type(event.aggregate_type)
    table_name = REFERENCE_TABLES[event.aggregate_type]
    columns = ", ".join(REFERENCE_COLUMNS[event.aggregate_type])
    row = (
        await session.execute(
            text(f"SELECT {columns} FROM {table_name} WHERE id = :aggregate_id"),
            {"aggregate_id": event.aggregate_id},
        )
    ).mappings().one_or_none()
    if row is None:
        raise ProjectionSourceMissing(
            f"Platform {event.aggregate_type} {event.aggregate_id} is missing; hard deletes are unsupported"
        )
    return dict(row)


def _upsert_sql(aggregate_type: str) -> str:
    validate_aggregate_type(aggregate_type)
    table_name = REFERENCE_TABLES[aggregate_type]
    columns = REFERENCE_COLUMNS[aggregate_type]
    insert_columns = ", ".join(columns)
    insert_values = ", ".join(
        "CAST(:theme_config AS jsonb)" if column == "theme_config" else f":{column}"
        for column in columns
    )
    update_columns = ", ".join(
        f"{column} = EXCLUDED.{column}" for column in columns if column != "id"
    )
    return (
        f"INSERT INTO {table_name} ({insert_columns}) VALUES ({insert_values}) "
        f"ON CONFLICT (id) DO UPDATE SET {update_columns}"
    )


async def apply_restaurant_projection(
    session: AsyncSession,
    event: OutboxEvent,
    source: dict[str, Any],
) -> bool:
    ledger_result = await session.execute(
        text(
            """
            INSERT INTO platform_projection_events (
                event_id, event_type, aggregate_type, aggregate_id,
                schema_version, source_occurred_at
            )
            VALUES (
                :event_id, :event_type, :aggregate_type, :aggregate_id,
                :schema_version, :source_occurred_at
            )
            ON CONFLICT (event_id) DO NOTHING
            RETURNING event_id
            """
        ),
        {
            "event_id": event.id,
            "event_type": event.event_type,
            "aggregate_type": event.aggregate_type,
            "aggregate_id": event.aggregate_id,
            "schema_version": event.schema_version,
            "source_occurred_at": event.occurred_at,
        },
    )
    if ledger_result.scalar_one_or_none() is None:
        return False

    parameters = dict(source)
    if event.aggregate_type == "brand":
        parameters["theme_config"] = json.dumps(source["theme_config"], sort_keys=True)
    await session.execute(text(_upsert_sql(event.aggregate_type)), parameters)
    return True


async def mark_outbox_processed(session: AsyncSession, event_id: uuid.UUID) -> None:
    await session.execute(
        text(
            """
            UPDATE reference_outbox
            SET processed_at = now(), claimed_at = NULL, last_error = NULL
            WHERE id = :event_id AND processed_at IS NULL
            """
        ),
        {"event_id": event_id},
    )


async def mark_outbox_failed(session: AsyncSession, event: OutboxEvent, exc: BaseException) -> None:
    await session.execute(
        text(
            """
            UPDATE reference_outbox
            SET claimed_at = NULL,
                available_at = now() + (:backoff_seconds * interval '1 second'),
                last_error = :last_error
            WHERE id = :event_id AND processed_at IS NULL
            """
        ),
        {
            "event_id": event.id,
            "backoff_seconds": projection_backoff_seconds(event.attempt_count),
            "last_error": sanitized_projection_error(exc),
        },
    )


async def process_projection_batch(
    *,
    limit: int = 100,
    platform_session_factory: async_sessionmaker[AsyncSession] = PlatformSessionLocal,
    restaurant_session_factory: async_sessionmaker[AsyncSession] = RestaurantSessionLocal,
) -> ProjectionBatchResult:
    async with platform_session_factory() as platform_session:
        events = await claim_outbox_events(platform_session, limit=limit)
        await platform_session.commit()

    applied = 0
    replayed = 0
    failed = 0
    for event in events:
        try:
            # Close the Platform read transaction before opening the Restaurant write
            # transaction. This is deliberately not a distributed transaction.
            async with platform_session_factory() as platform_session:
                source = await load_platform_reference(platform_session, event)

            async with restaurant_session_factory() as restaurant_session:
                was_applied = await apply_restaurant_projection(
                    restaurant_session,
                    event,
                    source,
                )
                await restaurant_session.commit()

            async with platform_session_factory() as platform_session:
                await mark_outbox_processed(platform_session, event.id)
                await platform_session.commit()

            if was_applied:
                applied += 1
            else:
                replayed += 1
        except Exception as exc:
            failed += 1
            async with platform_session_factory() as platform_session:
                await mark_outbox_failed(platform_session, event, exc)
                await platform_session.commit()

    return ProjectionBatchResult(
        claimed=len(events),
        applied=applied,
        replayed=replayed,
        failed=failed,
    )


async def _load_parity_rows(
    session: AsyncSession,
    aggregate_type: str,
) -> dict[uuid.UUID, dict[str, Any]]:
    table_name = REFERENCE_TABLES[aggregate_type]
    columns = REFERENCE_COLUMNS[aggregate_type]
    rows = (
        await session.execute(
            text(f"SELECT {', '.join(columns)} FROM {table_name} ORDER BY id")
        )
    ).mappings()
    return {row["id"]: dict(row) for row in rows}


async def verify_projection_parity(
    *,
    platform_session_factory: async_sessionmaker[AsyncSession] = PlatformSessionLocal,
    restaurant_session_factory: async_sessionmaker[AsyncSession] = RestaurantSessionLocal,
) -> tuple[AggregateParity, ...]:
    reports: list[AggregateParity] = []
    for aggregate_type in sorted(REFERENCE_TABLES, key=REFERENCE_PRIORITY.__getitem__):
        async with platform_session_factory() as platform_session:
            source_rows = await _load_parity_rows(platform_session, aggregate_type)
        async with restaurant_session_factory() as restaurant_session:
            target_rows = await _load_parity_rows(restaurant_session, aggregate_type)

        all_ids = sorted(set(source_rows) | set(target_rows), key=str)
        mismatches = tuple(
            str(aggregate_id)
            for aggregate_id in all_ids
            if source_rows.get(aggregate_id) != target_rows.get(aggregate_id)
        )
        reports.append(
            AggregateParity(
                aggregate_type=aggregate_type,
                source_count=len(source_rows),
                target_count=len(target_rows),
                mismatched_ids=mismatches,
            )
        )
    return tuple(reports)
