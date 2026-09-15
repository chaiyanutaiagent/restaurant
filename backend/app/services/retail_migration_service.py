from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
import hashlib
import json
from typing import Any
import uuid

from sqlalchemy import MetaData, Table, and_, func, select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
)

from app.database import engine as legacy_engine
from app.database import platform_engine, retail_engine
from app.services.retail_reference_projector import (
    RetailReferenceScope,
    resolve_retail_reference_scope,
    verify_retail_reference_parity,
)


RETAIL_OPERATIONAL_TABLES = (
    "units",
    "categories",
    "price_lists",
    "branch_settings",
    "stock_locations",
    "products",
    "product_variants",
    "product_images",
    "price_list_items",
    "cashier_shifts",
    "sale_orders",
    "payments",
    "sale_order_items",
    "stock_balances",
    "stock_count_sessions",
    "stock_count_items",
    "stock_movements",
    "approval_grant_usages",
    "audit_logs",
    "operational_outbox_events",
)


@dataclass(frozen=True)
class RetailOperationalScope:
    references: RetailReferenceScope
    product_ids: tuple[uuid.UUID, ...]
    unit_ids: tuple[uuid.UUID, ...]
    category_ids: tuple[uuid.UUID, ...]
    price_list_ids: tuple[uuid.UUID, ...]
    location_ids: tuple[uuid.UUID, ...]
    shift_ids: tuple[uuid.UUID, ...]
    order_ids: tuple[uuid.UUID, ...]
    stock_count_session_ids: tuple[uuid.UUID, ...]


@dataclass(frozen=True)
class RetailTableParity:
    table_name: str
    source_count: int
    target_count: int
    source_digest: str
    target_digest: str

    @property
    def matches(self) -> bool:
        return (
            self.source_count == self.target_count
            and self.source_digest == self.target_digest
        )


@dataclass(frozen=True)
class RetailMigrationResult:
    run_id: uuid.UUID
    scope: RetailOperationalScope
    table_parity: tuple[RetailTableParity, ...]


def _uuid_tuple(values: list[Any] | tuple[Any, ...]) -> tuple[uuid.UUID, ...]:
    return tuple(sorted({uuid.UUID(str(value)) for value in values}, key=str))


def _normalize_value(value: Any) -> Any:
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, dict):
        return {key: _normalize_value(item) for key, item in sorted(value.items())}
    if isinstance(value, (list, tuple)):
        return [_normalize_value(item) for item in value]
    return value


def retail_rows_digest(rows: list[dict[str, Any]]) -> str:
    normalized = [
        {key: _normalize_value(value) for key, value in sorted(row.items())}
        for row in rows
    ]
    normalized.sort(key=lambda row: str(row.get("id", "")))
    payload = json.dumps(
        normalized,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


async def _reflect_tables(
    connection: AsyncConnection,
    table_names: tuple[str, ...],
) -> dict[str, Table]:
    metadata = MetaData()
    await connection.run_sync(
        lambda sync_connection: metadata.reflect(
            bind=sync_connection,
            only=list(table_names),
        )
    )
    missing = sorted(set(table_names) - set(metadata.tables))
    if missing:
        raise RuntimeError("Retail migration table is missing: " + ", ".join(missing))
    return {name: metadata.tables[name] for name in table_names}


async def _column_values(
    connection: AsyncConnection,
    table: Table,
    column_name: str,
    where_clause,
) -> tuple[uuid.UUID, ...]:
    values = (
        await connection.execute(
            select(table.c[column_name]).where(where_clause).order_by(table.c[column_name])
        )
    ).scalars().all()
    return _uuid_tuple(values)


async def resolve_retail_operational_scope(
    source: AsyncConnection,
    source_tables: dict[str, Table],
    references: RetailReferenceScope,
) -> RetailOperationalScope:
    products = source_tables["products"]
    product_ids = await _column_values(
        source,
        products,
        "id",
        products.c.brand_id.in_(references.brand_ids),
    )
    if not product_ids:
        raise ValueError("Selected Retail scope has no brand-owned products in Legacy")

    units = source_tables["units"]
    unit_ids = _uuid_tuple(
        list(
            (
                await source.execute(
                    select(products.c.unit_id).where(
                        products.c.id.in_(product_ids),
                        products.c.unit_id.is_not(None),
                    )
                )
            ).scalars()
        )
    )
    if unit_ids:
        existing_unit_count = int(
            await source.scalar(
                select(func.count()).select_from(units).where(units.c.id.in_(unit_ids))
            )
            or 0
        )
        if existing_unit_count != len(unit_ids):
            raise RuntimeError("Retail products reference missing Unit rows")

    categories = source_tables["categories"]
    category_rows = (
        await source.execute(
            select(categories.c.id, categories.c.parent_id).where(
                categories.c.company_id.in_(references.company_ids)
            )
        )
    ).mappings().all()
    parent_by_id = {
        uuid.UUID(str(row["id"])): (
            uuid.UUID(str(row["parent_id"])) if row["parent_id"] is not None else None
        )
        for row in category_rows
    }
    selected_categories = {
        uuid.UUID(str(value))
        for value in (
            await source.execute(
                select(products.c.category_id).where(
                    products.c.id.in_(product_ids),
                    products.c.category_id.is_not(None),
                )
            )
        ).scalars()
    }
    unresolved = list(selected_categories)
    while unresolved:
        current = unresolved.pop()
        if current not in parent_by_id:
            raise RuntimeError("Retail products reference a missing Category row")
        parent_id = parent_by_id[current]
        if parent_id is not None and parent_id not in selected_categories:
            selected_categories.add(parent_id)
            unresolved.append(parent_id)
    category_ids = tuple(sorted(selected_categories, key=str))

    stock_locations = source_tables["stock_locations"]
    location_ids = await _column_values(
        source,
        stock_locations,
        "id",
        stock_locations.c.branch_id.in_(references.branch_ids),
    )
    if not location_ids:
        raise ValueError("Selected Retail Branches have no stock locations in Legacy")

    branch_settings = source_tables["branch_settings"]
    default_price_list_ids = _uuid_tuple(
        list(
            (
                await source.execute(
                    select(branch_settings.c.pos_default_price_list_id).where(
                        branch_settings.c.branch_id.in_(references.branch_ids),
                        branch_settings.c.pos_default_price_list_id.is_not(None),
                    )
                )
            ).scalars()
        )
    )
    price_list_items = source_tables["price_list_items"]
    product_price_list_ids = _uuid_tuple(
        list(
            (
                await source.execute(
                    select(price_list_items.c.price_list_id).where(
                        price_list_items.c.product_id.in_(product_ids)
                    )
                )
            ).scalars()
        )
    )
    price_list_ids = _uuid_tuple(list(default_price_list_ids + product_price_list_ids))

    cashier_shifts = source_tables["cashier_shifts"]
    shift_ids = await _column_values(
        source,
        cashier_shifts,
        "id",
        cashier_shifts.c.branch_id.in_(references.branch_ids),
    )
    sale_orders = source_tables["sale_orders"]
    order_ids = await _column_values(
        source,
        sale_orders,
        "id",
        sale_orders.c.branch_id.in_(references.branch_ids),
    )
    stock_count_sessions = source_tables["stock_count_sessions"]
    stock_count_session_ids = await _column_values(
        source,
        stock_count_sessions,
        "id",
        stock_count_sessions.c.branch_id.in_(references.branch_ids),
    )

    scope = RetailOperationalScope(
        references=references,
        product_ids=product_ids,
        unit_ids=unit_ids,
        category_ids=category_ids,
        price_list_ids=price_list_ids,
        location_ids=location_ids,
        shift_ids=shift_ids,
        order_ids=order_ids,
        stock_count_session_ids=stock_count_session_ids,
    )
    await validate_retail_source_isolation(source, source_tables, scope)
    return scope


async def validate_retail_source_isolation(
    source: AsyncConnection,
    source_tables: dict[str, Table],
    scope: RetailOperationalScope,
) -> None:
    branches = scope.references.branch_ids
    product_ids = scope.product_ids
    checks = []
    sale_orders = source_tables["sale_orders"]
    sale_items = source_tables["sale_order_items"]
    checks.append(
        (
            "sale_order_items",
            select(func.count())
            .select_from(sale_items.join(sale_orders, sale_items.c.order_id == sale_orders.c.id))
            .where(
                sale_orders.c.branch_id.in_(branches),
                sale_items.c.product_id.not_in(product_ids),
            ),
        )
    )
    for table_name in ("stock_balances", "stock_movements"):
        table = source_tables[table_name]
        checks.append(
            (
                table_name,
                select(func.count()).select_from(table).where(
                    table.c.branch_id.in_(branches),
                    table.c.product_id.not_in(product_ids),
                ),
            )
        )
    stock_count_sessions = source_tables["stock_count_sessions"]
    stock_count_items = source_tables["stock_count_items"]
    checks.append(
        (
            "stock_count_items",
            select(func.count())
            .select_from(
                stock_count_items.join(
                    stock_count_sessions,
                    stock_count_items.c.session_id == stock_count_sessions.c.id,
                )
            )
            .where(
                stock_count_sessions.c.branch_id.in_(branches),
                stock_count_items.c.product_id.not_in(product_ids),
            ),
        )
    )
    violations = []
    for table_name, statement in checks:
        count = int(await source.scalar(statement) or 0)
        if count:
            violations.append(f"{table_name}={count}")
    if violations:
        raise RuntimeError(
            "Retail Branches reference Products outside the selected Retail Brands: "
            + ", ".join(violations)
        )


def _table_filter(table_name: str, table: Table, scope: RetailOperationalScope):
    references = scope.references
    if table_name == "units":
        return table.c.id.in_(scope.unit_ids)
    if table_name == "categories":
        return table.c.id.in_(scope.category_ids)
    if table_name == "price_lists":
        return table.c.id.in_(scope.price_list_ids)
    if table_name == "branch_settings":
        return table.c.branch_id.in_(references.branch_ids)
    if table_name == "stock_locations":
        return table.c.id.in_(scope.location_ids)
    if table_name == "products":
        return table.c.id.in_(scope.product_ids)
    if table_name in {"product_variants", "product_images"}:
        return table.c.product_id.in_(scope.product_ids)
    if table_name == "price_list_items":
        return and_(
            table.c.product_id.in_(scope.product_ids),
            table.c.price_list_id.in_(scope.price_list_ids),
        )
    if table_name == "cashier_shifts":
        return table.c.id.in_(scope.shift_ids)
    if table_name == "sale_orders":
        return table.c.id.in_(scope.order_ids)
    if table_name in {"payments", "sale_order_items"}:
        return table.c.order_id.in_(scope.order_ids)
    if table_name in {"stock_balances", "stock_movements"}:
        return and_(
            table.c.branch_id.in_(references.branch_ids),
            table.c.product_id.in_(scope.product_ids),
        )
    if table_name == "stock_count_sessions":
        return table.c.id.in_(scope.stock_count_session_ids)
    if table_name == "stock_count_items":
        return table.c.session_id.in_(scope.stock_count_session_ids)
    if table_name in {
        "approval_grant_usages",
        "audit_logs",
        "operational_outbox_events",
    }:
        return table.c.branch_id.in_(references.branch_ids)
    raise ValueError(f"Unsupported Retail migration table: {table_name}")


async def _read_rows(
    connection: AsyncConnection,
    table: Table,
    where_clause,
) -> list[dict[str, Any]]:
    rows = (
        await connection.execute(select(table).where(where_clause).order_by(table.c.id))
    ).mappings()
    return [dict(row) for row in rows]


async def _upsert_rows(
    connection: AsyncConnection,
    table: Table,
    rows: list[dict[str, Any]],
    *,
    batch_size: int,
) -> None:
    for offset in range(0, len(rows), batch_size):
        batch = rows[offset : offset + batch_size]
        statement = insert(table).values(batch)
        updates = {
            column.name: getattr(statement.excluded, column.name)
            for column in table.columns
            if column.name != "id"
        }
        await connection.execute(
            statement.on_conflict_do_update(
                index_elements=[table.c.id],
                set_=updates,
            )
        )


def _order_rows_for_copy(
    table_name: str,
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    parent_column = {
        "categories": "parent_id",
        "payments": "original_payment_id",
    }.get(table_name)
    if parent_column is None or not rows:
        return rows

    pending = {row["id"]: row for row in rows}
    ordered: list[dict[str, Any]] = []
    copied_ids: set[Any] = set()
    while pending:
        ready_ids = sorted(
            (
                row_id
                for row_id, row in pending.items()
                if row[parent_column] is None or row[parent_column] in copied_ids
            ),
            key=str,
        )
        if not ready_ids:
            raise RuntimeError(
                f"Retail {table_name} has a missing or cyclic {parent_column} dependency"
            )
        for row_id in ready_ids:
            ordered.append(pending.pop(row_id))
            copied_ids.add(row_id)
    return ordered


async def _sync_operational_brand_fields(
    source: AsyncConnection,
    target: AsyncConnection,
    source_tables: dict[str, Table],
    target_tables: dict[str, Table],
    scope: RetailOperationalScope,
) -> None:
    for table_name, fields, ids in (
        (
            "brands",
            ("central_branch_id", "central_location_id", "central_ready_location_id"),
            scope.references.brand_ids,
        ),
        (
            "brand_branches",
            ("store_location_id",),
            scope.references.brand_branch_ids,
        ),
    ):
        source_table = source_tables[table_name]
        target_table = target_tables[table_name]
        rows = (
            await source.execute(
                select(source_table.c.id, *(source_table.c[field] for field in fields)).where(
                    source_table.c.id.in_(ids)
                )
            )
        ).mappings()
        for row in rows:
            safe_values: dict[str, Any] = {}
            for field in fields:
                value = row[field]
                if field == "central_branch_id" and value not in scope.references.branch_ids:
                    value = None
                if field in {
                    "central_location_id",
                    "central_ready_location_id",
                    "store_location_id",
                } and value not in scope.location_ids:
                    value = None
                safe_values[field] = value
            await target.execute(
                update(target_table)
                .where(target_table.c.id == row["id"])
                .values(**safe_values)
            )


async def _record_run_start(
    target_engine: AsyncEngine,
    run_id: uuid.UUID,
    scope: RetailReferenceScope,
    source_database: str,
    target_database: str,
) -> None:
    async with target_engine.begin() as connection:
        await connection.execute(
            text(
                """
                INSERT INTO retail_migration_runs (
                    id, company_id, selected_brand_ids, selected_branch_ids,
                    source_database, target_database, status
                )
                VALUES (
                    :id, :company_id, CAST(:brand_ids AS jsonb), CAST(:branch_ids AS jsonb),
                    :source_database, :target_database, 'running'
                )
                """
            ),
            {
                "id": run_id,
                "company_id": scope.company_ids[0] if len(scope.company_ids) == 1 else None,
                "brand_ids": json.dumps([str(value) for value in scope.brand_ids]),
                "branch_ids": json.dumps([str(value) for value in scope.branch_ids]),
                "source_database": source_database,
                "target_database": target_database,
            },
        )


async def _record_run_result(
    target_engine: AsyncEngine,
    run_id: uuid.UUID,
    *,
    status: str,
    parity: tuple[RetailTableParity, ...] = (),
    error: BaseException | None = None,
) -> None:
    counts = {
        report.table_name: report.source_count for report in parity
    }
    digests = {
        report.table_name: report.source_digest for report in parity
    }
    error_name = (
        f"{type(error).__module__}.{type(error).__name__}"[:255]
        if error is not None
        else None
    )
    async with target_engine.begin() as connection:
        await connection.execute(
            text(
                """
                UPDATE retail_migration_runs
                SET status = :status,
                    table_counts = CAST(:counts AS jsonb),
                    table_digests = CAST(:digests AS jsonb),
                    last_error = :last_error,
                    completed_at = :completed_at
                WHERE id = :id
                """
            ),
            {
                "id": run_id,
                "status": status,
                "counts": json.dumps(counts, sort_keys=True),
                "digests": json.dumps(digests, sort_keys=True),
                "last_error": error_name,
                "completed_at": datetime.now(timezone.utc),
            },
        )


async def reconcile_retail_operational_data(
    *,
    company_id: uuid.UUID | None = None,
    brand_ids: tuple[uuid.UUID, ...] = (),
    source_engine: AsyncEngine = legacy_engine,
    platform_source_engine: AsyncEngine = platform_engine,
    target_engine: AsyncEngine | None = retail_engine,
) -> tuple[RetailOperationalScope, tuple[RetailTableParity, ...]]:
    if target_engine is None:
        raise RuntimeError("Retail database is not configured")
    async with platform_source_engine.connect() as platform_connection:
        references = await resolve_retail_reference_scope(
            platform_connection,
            company_id=company_id,
            brand_ids=brand_ids,
        )
    table_names = RETAIL_OPERATIONAL_TABLES + ("brands", "brand_branches")
    async with source_engine.connect() as source, target_engine.connect() as target:
        source_tables = await _reflect_tables(source, table_names)
        target_tables = await _reflect_tables(target, table_names)
        scope = await resolve_retail_operational_scope(source, source_tables, references)
        reports = []
        for table_name in RETAIL_OPERATIONAL_TABLES:
            source_table = source_tables[table_name]
            target_table = target_tables[table_name]
            source_rows = await _read_rows(
                source,
                source_table,
                _table_filter(table_name, source_table, scope),
            )
            target_rows = await _read_rows(
                target,
                target_table,
                _table_filter(table_name, target_table, scope),
            )
            reports.append(
                RetailTableParity(
                    table_name=table_name,
                    source_count=len(source_rows),
                    target_count=len(target_rows),
                    source_digest=retail_rows_digest(source_rows),
                    target_digest=retail_rows_digest(target_rows),
                )
            )
    return scope, tuple(reports)


async def migrate_retail_operational_data(
    *,
    company_id: uuid.UUID | None = None,
    brand_ids: tuple[uuid.UUID, ...] = (),
    batch_size: int = 250,
    source_engine: AsyncEngine = legacy_engine,
    platform_source_engine: AsyncEngine = platform_engine,
    target_engine: AsyncEngine | None = retail_engine,
) -> RetailMigrationResult:
    if target_engine is None:
        raise RuntimeError("Retail database is not configured")
    if batch_size < 1 or batch_size > 1000:
        raise ValueError("batch_size must be between 1 and 1000")
    parity = await verify_retail_reference_parity(
        company_id=company_id,
        brand_ids=brand_ids,
        platform_session_factory=async_sessionmaker(
            platform_source_engine,
            expire_on_commit=False,
            class_=AsyncSession,
        ),
        retail_session_factory=async_sessionmaker(
            target_engine,
            expire_on_commit=False,
            class_=AsyncSession,
        ),
    )
    if any(report[0] != report[1] or bool(report[2]) for report in parity.values()):
        raise RuntimeError("Retail reference projection parity must pass before data migration")

    async with platform_source_engine.connect() as platform_connection:
        references = await resolve_retail_reference_scope(
            platform_connection,
            company_id=company_id,
            brand_ids=brand_ids,
        )
    table_names = RETAIL_OPERATIONAL_TABLES + ("brands", "brand_branches")
    async with source_engine.connect() as source, target_engine.connect() as target:
        source_database = str(await source.scalar(func.current_database()) or "")
        target_database = str(await target.scalar(func.current_database()) or "")
    if not source_database or not target_database or source_database == target_database:
        raise RuntimeError("Retail migration requires distinct source and target databases")

    run_id = uuid.uuid4()
    await _record_run_start(
        target_engine,
        run_id,
        references,
        source_database,
        target_database,
    )
    reports: tuple[RetailTableParity, ...] = ()
    try:
        async with source_engine.connect() as source, target_engine.begin() as target:
            source_tables = await _reflect_tables(source, table_names)
            target_tables = await _reflect_tables(target, table_names)
            scope = await resolve_retail_operational_scope(source, source_tables, references)
            for table_name in RETAIL_OPERATIONAL_TABLES:
                source_table = source_tables[table_name]
                target_table = target_tables[table_name]
                rows = await _read_rows(
                    source,
                    source_table,
                    _table_filter(table_name, source_table, scope),
                )
                rows = _order_rows_for_copy(table_name, rows)
                await _upsert_rows(target, target_table, rows, batch_size=batch_size)
                if table_name == "stock_locations":
                    await _sync_operational_brand_fields(
                        source,
                        target,
                        source_tables,
                        target_tables,
                        scope,
                    )
        scope, reports = await reconcile_retail_operational_data(
            company_id=company_id,
            brand_ids=brand_ids,
            source_engine=source_engine,
            platform_source_engine=platform_source_engine,
            target_engine=target_engine,
        )
        mismatches = [report.table_name for report in reports if not report.matches]
        if mismatches:
            raise RuntimeError(
                "Retail operational parity failed: " + ", ".join(mismatches)
            )
        await _record_run_result(target_engine, run_id, status="completed", parity=reports)
        return RetailMigrationResult(run_id=run_id, scope=scope, table_parity=reports)
    except Exception as exc:
        await _record_run_result(
            target_engine,
            run_id,
            status="failed",
            parity=reports,
            error=exc,
        )
        raise
