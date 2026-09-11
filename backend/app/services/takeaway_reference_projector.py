from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
import logging
from typing import Any
import uuid

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.database import PlatformSessionLocal, TakeawaySessionLocal
from app.models.takeaway import TakeawayReferenceProjection
from app.services.platform_reference_projection import (
    REFERENCE_COLUMNS,
    REFERENCE_PRIORITY,
    REFERENCE_TABLES,
)


logger = logging.getLogger(__name__)
SENSITIVE_COLUMN_FRAGMENTS = ("password", "token", "secret", "credential")


@dataclass(frozen=True)
class TakeawayProjectionResult:
    scanned: int = 0
    applied: int = 0
    unchanged: int = 0


@dataclass
class TakeawayProjectorRuntimeState:
    running: bool = False
    batches: int = 0
    scanned: int = 0
    applied: int = 0
    unchanged: int = 0
    loop_errors: int = 0
    last_error_type: str | None = None


takeaway_projector_state = TakeawayProjectorRuntimeState()


def safe_reference_columns(aggregate_type: str) -> tuple[str, ...]:
    return tuple(
        column
        for column in REFERENCE_COLUMNS[aggregate_type]
        if not any(fragment in column.lower() for fragment in SENSITIVE_COLUMN_FRAGMENTS)
    )


def canonical_reference_payload(row: dict[str, Any]) -> tuple[dict[str, Any], str]:
    normalized = json.loads(json.dumps(row, default=str, sort_keys=True))
    canonical = json.dumps(
        normalized,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return normalized, hashlib.sha256(canonical.encode("utf-8")).hexdigest()


async def _source_rows(
    session: AsyncSession,
    aggregate_type: str,
) -> list[dict[str, Any]]:
    table_name = REFERENCE_TABLES[aggregate_type]
    columns = safe_reference_columns(aggregate_type)
    rows = (
        await session.execute(
            text(
                f"SELECT {', '.join(columns)} FROM {table_name} "
                "ORDER BY updated_at, id"
            )
        )
    ).mappings()
    return [dict(row) for row in rows]


async def project_takeaway_reference_snapshot(
    *,
    platform_session_factory: async_sessionmaker[AsyncSession] = PlatformSessionLocal,
    takeaway_session_factory: async_sessionmaker[AsyncSession] | None = TakeawaySessionLocal,
) -> TakeawayProjectionResult:
    if takeaway_session_factory is None:
        raise RuntimeError("Takeaway database is not configured")

    scanned = 0
    applied = 0
    unchanged = 0
    for aggregate_type in sorted(REFERENCE_TABLES, key=REFERENCE_PRIORITY.__getitem__):
        async with platform_session_factory() as source_session:
            rows = await _source_rows(source_session, aggregate_type)
        scanned += len(rows)
        async with takeaway_session_factory() as target_session:
            for row in rows:
                payload, digest = canonical_reference_payload(row)
                aggregate_id = uuid.UUID(str(row["id"]))
                company_id = (
                    aggregate_id
                    if aggregate_type == "company"
                    else uuid.UUID(str(row["company_id"]))
                )
                current_digest = await target_session.scalar(
                    select(TakeawayReferenceProjection.source_digest).where(
                        TakeawayReferenceProjection.aggregate_type == aggregate_type,
                        TakeawayReferenceProjection.aggregate_id == aggregate_id,
                    )
                )
                if current_digest == digest:
                    unchanged += 1
                    continue
                await target_session.execute(
                    insert(TakeawayReferenceProjection)
                    .values(
                        id=uuid.uuid4(),
                        aggregate_type=aggregate_type,
                        aggregate_id=aggregate_id,
                        company_id=company_id,
                        source_updated_at=row["updated_at"],
                        payload=payload,
                        source_digest=digest,
                    )
                    .on_conflict_do_update(
                        constraint="uq_takeaway_reference_projection_aggregate",
                        set_={
                            "company_id": company_id,
                            "source_updated_at": row["updated_at"],
                            "payload": payload,
                            "source_digest": digest,
                            "updated_at": datetime.now().astimezone(),
                        },
                    )
                )
                applied += 1
            await target_session.commit()
    return TakeawayProjectionResult(
        scanned=scanned,
        applied=applied,
        unchanged=unchanged,
    )


async def verify_takeaway_reference_parity(
    *,
    platform_session_factory: async_sessionmaker[AsyncSession] = PlatformSessionLocal,
    takeaway_session_factory: async_sessionmaker[AsyncSession] | None = TakeawaySessionLocal,
) -> dict[str, tuple[int, int, tuple[str, ...]]]:
    if takeaway_session_factory is None:
        raise RuntimeError("Takeaway database is not configured")
    result: dict[str, tuple[int, int, tuple[str, ...]]] = {}
    for aggregate_type in sorted(REFERENCE_TABLES, key=REFERENCE_PRIORITY.__getitem__):
        async with platform_session_factory() as source_session:
            source_rows = await _source_rows(source_session, aggregate_type)
        expected = {
            str(row["id"]): canonical_reference_payload(row)[1] for row in source_rows
        }
        async with takeaway_session_factory() as target_session:
            target_rows = (
                await target_session.execute(
                    select(
                        TakeawayReferenceProjection.aggregate_id,
                        TakeawayReferenceProjection.source_digest,
                    ).where(TakeawayReferenceProjection.aggregate_type == aggregate_type)
                )
            ).all()
        actual = {str(row.aggregate_id): row.source_digest for row in target_rows}
        mismatches = tuple(
            aggregate_id
            for aggregate_id in sorted(set(expected) | set(actual))
            if expected.get(aggregate_id) != actual.get(aggregate_id)
        )
        result[aggregate_type] = (len(expected), len(actual), mismatches)
    return result


async def run_takeaway_reference_projector(
    stop_event: asyncio.Event,
    *,
    poll_seconds: float,
    state: TakeawayProjectorRuntimeState = takeaway_projector_state,
) -> None:
    state.running = True
    state.last_error_type = None
    try:
        while not stop_event.is_set():
            try:
                batch = await project_takeaway_reference_snapshot()
                state.batches += 1
                state.scanned += batch.scanned
                state.applied += batch.applied
                state.unchanged += batch.unchanged
                state.last_error_type = None
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # pragma: no cover - dependency failure path
                state.loop_errors += 1
                state.last_error_type = f"{type(exc).__module__}.{type(exc).__name__}"
                logger.error("Takeaway reference projector failed: %s", state.last_error_type)
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=poll_seconds)
            except TimeoutError:
                pass
    finally:
        state.running = False
