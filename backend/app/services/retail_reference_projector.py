from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import logging
from typing import Any
import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.database import (
    PlatformSessionLocal,
    RetailSessionLocal,
    validate_retail_schema_readiness,
)
from app.services.platform_reference_projection import (
    REFERENCE_COLUMNS,
    REFERENCE_PRIORITY,
    REFERENCE_TABLES,
)


logger = logging.getLogger(__name__)
RETAIL_USER_PASSWORD_SENTINEL = "!retail-operational-reference-no-login!"


@dataclass(frozen=True)
class RetailReferenceScope:
    company_ids: tuple[uuid.UUID, ...]
    brand_ids: tuple[uuid.UUID, ...]
    branch_ids: tuple[uuid.UUID, ...]
    brand_branch_ids: tuple[uuid.UUID, ...]


@dataclass(frozen=True)
class RetailProjectionResult:
    scanned: int = 0
    applied: int = 0
    unchanged: int = 0


@dataclass
class RetailProjectorRuntimeState:
    running: bool = False
    batches: int = 0
    scanned: int = 0
    applied: int = 0
    unchanged: int = 0
    loop_errors: int = 0
    last_error_type: str | None = None


retail_projector_state = RetailProjectorRuntimeState()


async def validate_retail_projection_boundary(
    *,
    platform_session_factory: async_sessionmaker[AsyncSession],
    retail_session_factory: async_sessionmaker[AsyncSession] | None,
) -> None:
    if retail_session_factory is None:
        raise RuntimeError("Retail database is not configured")
    await validate_retail_schema_readiness(retail_session_factory)
    async with (
        platform_session_factory() as platform_session,
        retail_session_factory() as retail_session,
    ):
        platform_database = str(
            await platform_session.scalar(text("SELECT current_database()")) or ""
        )
        retail_database = str(
            await retail_session.scalar(text("SELECT current_database()")) or ""
        )
    if not platform_database or not retail_database or platform_database == retail_database:
        raise RuntimeError(
            "Retail reference projection requires distinct Platform and Retail databases"
        )


def retail_reference_columns(aggregate_type: str) -> tuple[str, ...]:
    columns = REFERENCE_COLUMNS[aggregate_type]
    if aggregate_type == "user":
        return tuple(column for column in columns if column != "hashed_password")
    return columns


def canonical_reference_digest(row: dict[str, Any]) -> str:
    normalized = json.loads(json.dumps(row, default=str, sort_keys=True))
    canonical = json.dumps(
        normalized,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


async def resolve_retail_reference_scope(
    session: AsyncSession,
    *,
    company_id: uuid.UUID | None = None,
    brand_ids: tuple[uuid.UUID, ...] = (),
) -> RetailReferenceScope:
    conditions = ["business_type = 'retail_pos'"]
    parameters: dict[str, object] = {}
    if company_id is not None:
        conditions.append("company_id = :company_id")
        parameters["company_id"] = company_id
    if brand_ids:
        conditions.append("id = ANY(CAST(:brand_ids AS uuid[]))")
        parameters["brand_ids"] = list(brand_ids)
    brands = (
        await session.execute(
            text(
                "SELECT id, company_id FROM brands WHERE "
                + " AND ".join(conditions)
                + " ORDER BY id"
            ),
            parameters,
        )
    ).mappings().all()
    resolved_brand_ids = tuple(uuid.UUID(str(row["id"])) for row in brands)
    if brand_ids and set(resolved_brand_ids) != set(brand_ids):
        raise ValueError("Every selected Brand must exist and use business_type=retail_pos")
    if not resolved_brand_ids:
        raise ValueError("No Retail Brand matched the selected migration scope")
    company_ids = tuple(
        sorted(
            {uuid.UUID(str(row["company_id"])) for row in brands},
            key=str,
        )
    )
    links = (
        await session.execute(
            text(
                "SELECT id, branch_id FROM brand_branches "
                "WHERE brand_id = ANY(CAST(:brand_ids AS uuid[])) ORDER BY id"
            ),
            {"brand_ids": list(resolved_brand_ids)},
        )
    ).mappings().all()
    if not links:
        raise ValueError("Selected Retail Brands have no Branch assignments")
    branch_ids = tuple(
        sorted({uuid.UUID(str(row["branch_id"])) for row in links}, key=str)
    )
    conflicting_links = (
        await session.execute(
            text(
                "SELECT DISTINCT brand_id, branch_id FROM brand_branches "
                "WHERE branch_id = ANY(CAST(:branch_ids AS uuid[])) "
                "AND NOT (brand_id = ANY(CAST(:brand_ids AS uuid[])))"
            ),
            {
                "branch_ids": list(branch_ids),
                "brand_ids": list(resolved_brand_ids),
            },
        )
    ).mappings().all()
    if conflicting_links:
        raise ValueError(
            "Selected Retail Branches are shared with Brands outside the migration scope"
        )
    return RetailReferenceScope(
        company_ids=company_ids,
        brand_ids=resolved_brand_ids,
        branch_ids=branch_ids,
        brand_branch_ids=tuple(uuid.UUID(str(row["id"])) for row in links),
    )


def _scope_clause(
    aggregate_type: str,
    scope: RetailReferenceScope,
) -> tuple[str, dict[str, object]]:
    if aggregate_type == "company":
        return "id = ANY(CAST(:scope_ids AS uuid[]))", {"scope_ids": list(scope.company_ids)}
    if aggregate_type == "brand":
        return "id = ANY(CAST(:scope_ids AS uuid[]))", {"scope_ids": list(scope.brand_ids)}
    if aggregate_type == "branch":
        return "id = ANY(CAST(:scope_ids AS uuid[]))", {"scope_ids": list(scope.branch_ids)}
    if aggregate_type == "brand_branch":
        return "id = ANY(CAST(:scope_ids AS uuid[]))", {
            "scope_ids": list(scope.brand_branch_ids)
        }
    if aggregate_type == "user":
        return "company_id = ANY(CAST(:scope_ids AS uuid[]))", {
            "scope_ids": list(scope.company_ids)
        }
    raise ValueError(f"Unsupported Retail reference aggregate: {aggregate_type}")


async def _source_rows(
    session: AsyncSession,
    aggregate_type: str,
    scope: RetailReferenceScope,
) -> list[dict[str, Any]]:
    table_name = REFERENCE_TABLES[aggregate_type]
    columns = retail_reference_columns(aggregate_type)
    where_sql, parameters = _scope_clause(aggregate_type, scope)
    rows = (
        await session.execute(
            text(
                f"SELECT {', '.join(columns)} FROM {table_name} "
                f"WHERE {where_sql} ORDER BY updated_at, id"
            ),
            parameters,
        )
    ).mappings()
    return [dict(row) for row in rows]


def _upsert_sql(aggregate_type: str) -> str:
    table_name = REFERENCE_TABLES[aggregate_type]
    columns = list(retail_reference_columns(aggregate_type))
    if aggregate_type == "user":
        insert_columns = columns[:]
        insert_columns.insert(insert_columns.index("first_name"), "hashed_password")
    else:
        insert_columns = columns
    insert_values = []
    for column in insert_columns:
        if column == "theme_config":
            insert_values.append("CAST(:theme_config AS jsonb)")
        elif column == "hashed_password":
            insert_values.append(":hashed_password")
        else:
            insert_values.append(f":{column}")
    update_columns = ", ".join(
        f"{column} = EXCLUDED.{column}"
        for column in columns
        if column != "id"
    )
    return (
        f"INSERT INTO {table_name} ({', '.join(insert_columns)}) "
        f"VALUES ({', '.join(insert_values)}) "
        f"ON CONFLICT (id) DO UPDATE SET {update_columns}"
    )


async def _apply_reference(
    session: AsyncSession,
    aggregate_type: str,
    row: dict[str, Any],
    digest: str,
) -> None:
    parameters = dict(row)
    if aggregate_type == "brand":
        parameters["theme_config"] = json.dumps(row["theme_config"], sort_keys=True)
    if aggregate_type == "user":
        parameters["hashed_password"] = RETAIL_USER_PASSWORD_SENTINEL
    await session.execute(text(_upsert_sql(aggregate_type)), parameters)
    aggregate_id = uuid.UUID(str(row["id"]))
    company_id = aggregate_id if aggregate_type == "company" else row.get("company_id")
    await session.execute(
        text(
            """
            INSERT INTO retail_reference_projection_receipts (
                id, aggregate_type, aggregate_id, company_id,
                source_updated_at, source_digest, projected_at
            )
            VALUES (
                :id, :aggregate_type, :aggregate_id, :company_id,
                :source_updated_at, :source_digest, now()
            )
            ON CONFLICT (aggregate_type, aggregate_id) DO UPDATE SET
                company_id = EXCLUDED.company_id,
                source_updated_at = EXCLUDED.source_updated_at,
                source_digest = EXCLUDED.source_digest,
                projected_at = now()
            """
        ),
        {
            "id": uuid.uuid4(),
            "aggregate_type": aggregate_type,
            "aggregate_id": aggregate_id,
            "company_id": company_id,
            "source_updated_at": row["updated_at"],
            "source_digest": digest,
        },
    )


async def _target_reference_digest(
    session: AsyncSession,
    aggregate_type: str,
    aggregate_id: uuid.UUID,
) -> str | None:
    table_name = REFERENCE_TABLES[aggregate_type]
    columns = retail_reference_columns(aggregate_type)
    row = (
        await session.execute(
            text(
                f"SELECT {', '.join(columns)} FROM {table_name} "
                "WHERE id = :aggregate_id"
            ),
            {"aggregate_id": aggregate_id},
        )
    ).mappings().one_or_none()
    return canonical_reference_digest(dict(row)) if row is not None else None


async def project_retail_reference_snapshot(
    *,
    company_id: uuid.UUID | None = None,
    brand_ids: tuple[uuid.UUID, ...] = (),
    platform_session_factory: async_sessionmaker[AsyncSession] = PlatformSessionLocal,
    retail_session_factory: async_sessionmaker[AsyncSession] | None = RetailSessionLocal,
) -> RetailProjectionResult:
    await validate_retail_projection_boundary(
        platform_session_factory=platform_session_factory,
        retail_session_factory=retail_session_factory,
    )
    assert retail_session_factory is not None
    async with platform_session_factory() as source_session:
        scope = await resolve_retail_reference_scope(
            source_session,
            company_id=company_id,
            brand_ids=brand_ids,
        )
    scanned = 0
    applied = 0
    unchanged = 0
    for aggregate_type in sorted(REFERENCE_TABLES, key=REFERENCE_PRIORITY.__getitem__):
        async with platform_session_factory() as source_session:
            rows = await _source_rows(source_session, aggregate_type, scope)
        scanned += len(rows)
        async with retail_session_factory() as target_session:
            for row in rows:
                digest = canonical_reference_digest(row)
                current_digest = await target_session.scalar(
                    text(
                        "SELECT source_digest FROM retail_reference_projection_receipts "
                        "WHERE aggregate_type = :aggregate_type AND aggregate_id = :aggregate_id"
                    ),
                    {
                        "aggregate_type": aggregate_type,
                        "aggregate_id": row["id"],
                    },
                )
                target_digest = await _target_reference_digest(
                    target_session,
                    aggregate_type,
                    uuid.UUID(str(row["id"])),
                )
                if current_digest == digest and target_digest == digest:
                    unchanged += 1
                    continue
                await _apply_reference(target_session, aggregate_type, row, digest)
                applied += 1
            await target_session.commit()
    return RetailProjectionResult(scanned=scanned, applied=applied, unchanged=unchanged)


async def verify_retail_reference_parity(
    *,
    company_id: uuid.UUID | None = None,
    brand_ids: tuple[uuid.UUID, ...] = (),
    platform_session_factory: async_sessionmaker[AsyncSession] = PlatformSessionLocal,
    retail_session_factory: async_sessionmaker[AsyncSession] | None = RetailSessionLocal,
) -> dict[str, tuple[int, int, tuple[str, ...]]]:
    await validate_retail_projection_boundary(
        platform_session_factory=platform_session_factory,
        retail_session_factory=retail_session_factory,
    )
    assert retail_session_factory is not None
    async with platform_session_factory() as source_session:
        scope = await resolve_retail_reference_scope(
            source_session,
            company_id=company_id,
            brand_ids=brand_ids,
        )
    result: dict[str, tuple[int, int, tuple[str, ...]]] = {}
    for aggregate_type in sorted(REFERENCE_TABLES, key=REFERENCE_PRIORITY.__getitem__):
        async with platform_session_factory() as source_session:
            source_rows = await _source_rows(source_session, aggregate_type, scope)
        expected = {
            str(row["id"]): canonical_reference_digest(row) for row in source_rows
        }
        target_rows: list[dict[str, Any]] = []
        receipt_rows: list[tuple[Any, Any]] = []
        if expected:
            async with retail_session_factory() as target_session:
                table_name = REFERENCE_TABLES[aggregate_type]
                columns = retail_reference_columns(aggregate_type)
                target_rows = [
                    dict(row)
                    for row in (
                        await target_session.execute(
                            text(
                                f"SELECT {', '.join(columns)} FROM {table_name} "
                                "WHERE id = ANY(CAST(:aggregate_ids AS uuid[]))"
                            ),
                            {
                                "aggregate_ids": [
                                    uuid.UUID(value) for value in expected
                                ],
                            },
                        )
                    ).mappings()
                ]
                receipt_rows = (
                    await target_session.execute(
                        text(
                            "SELECT aggregate_id, source_digest "
                            "FROM retail_reference_projection_receipts "
                            "WHERE aggregate_type = :aggregate_type "
                            "AND aggregate_id = ANY(CAST(:aggregate_ids AS uuid[]))"
                        ),
                        {
                            "aggregate_type": aggregate_type,
                            "aggregate_ids": [uuid.UUID(value) for value in expected],
                        },
                    )
                ).all()
        actual = {
            str(row["id"]): canonical_reference_digest(row) for row in target_rows
        }
        receipts = {str(row[0]): str(row[1]) for row in receipt_rows}
        mismatches = tuple(
            aggregate_id
            for aggregate_id in sorted(expected)
            if expected[aggregate_id] != actual.get(aggregate_id)
            or expected[aggregate_id] != receipts.get(aggregate_id)
        )
        result[aggregate_type] = (len(expected), len(actual), mismatches)
    return result


async def validate_retail_reference_readiness(
    *,
    platform_session_factory: async_sessionmaker[AsyncSession] = PlatformSessionLocal,
    retail_session_factory: async_sessionmaker[AsyncSession] | None = RetailSessionLocal,
) -> None:
    parity = await verify_retail_reference_parity(
        platform_session_factory=platform_session_factory,
        retail_session_factory=retail_session_factory,
    )
    mismatched = [
        aggregate_type
        for aggregate_type, report in parity.items()
        if report[0] != report[1] or bool(report[2])
    ]
    if mismatched:
        raise RuntimeError(
            "Retail reference projection is not cutover-ready: "
            + ", ".join(sorted(mismatched))
        )


async def run_retail_reference_projector(
    stop_event: asyncio.Event,
    *,
    poll_seconds: float,
    state: RetailProjectorRuntimeState = retail_projector_state,
) -> None:
    state.running = True
    state.last_error_type = None
    try:
        while not stop_event.is_set():
            try:
                batch = await project_retail_reference_snapshot()
                state.batches += 1
                state.scanned += batch.scanned
                state.applied += batch.applied
                state.unchanged += batch.unchanged
                state.last_error_type = None
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # pragma: no cover - runtime dependency failure path
                state.loop_errors += 1
                state.last_error_type = f"{type(exc).__module__}.{type(exc).__name__}"
                logger.error("Retail reference projector failed: %s", state.last_error_type)
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=poll_seconds)
            except TimeoutError:
                pass
    finally:
        state.running = False
