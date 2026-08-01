from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import date, datetime, time
from decimal import Decimal
import hashlib
import json
import re
from typing import Any
import uuid

from fastapi import HTTPException, status
from sqlalchemy import MetaData, Table, exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement


EXPORT_FORMAT = "restaurant-tenant-export"
EXPORT_FORMAT_VERSION = 1
REDACTED = "[REDACTED]"


@dataclass(frozen=True)
class TenantExportBoundary:
    name: str
    session: AsyncSession


def is_sensitive_export_column(column_name: str) -> bool:
    """Return true for credential material that must never leave a tenant export."""

    name = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", column_name).lower().replace("-", "_")
    return (
        name in {
            "api_key",
            "authorization",
            "cookie",
            "hashed_password",
            "initial_password_hash",
            "key_hash",
            "otp",
            "otp_code",
            "otp_hash",
            "password",
            "pin",
            "pin_hash",
            "private_key",
            "preview_token",
            "qr_token",
            "request_hash",
            "scb_api_key",
            "secret",
            "token",
            "token_hash",
        }
        or name.endswith("_password")
        or name.endswith("_hash")
        or name.endswith("_api_key")
        or name.endswith("_secret")
        or name.endswith("_secret_key")
        or name.endswith("_token")
        or name.endswith("_token_hash")
        or name.endswith("_credential_hash")
        or name.endswith("_pin_hash")
        or name.endswith("_otp")
        or name.endswith("_pin")
    )


def sanitize_export_value(value: Any) -> tuple[Any, int]:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value, 0
    if isinstance(value, (datetime, date, time)):
        return value.isoformat(), 0
    if isinstance(value, (Decimal, uuid.UUID)):
        return str(value), 0
    if isinstance(value, bytes):
        return {"encoding": "base64", "value": base64.b64encode(value).decode("ascii")}, 0
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        redactions = 0
        for key, item in value.items():
            key_name = str(key)
            if is_sensitive_export_column(key_name):
                sanitized[key_name] = REDACTED if item is not None else None
                redactions += int(item is not None)
                continue
            sanitized_item, nested_redactions = sanitize_export_value(item)
            sanitized[key_name] = sanitized_item
            redactions += nested_redactions
        return sanitized, redactions
    if isinstance(value, (list, tuple)):
        sanitized_items: list[Any] = []
        redactions = 0
        for item in value:
            sanitized_item, nested_redactions = sanitize_export_value(item)
            sanitized_items.append(sanitized_item)
            redactions += nested_redactions
        return sanitized_items, redactions
    return str(value), 0


def _ownership_filter(
    table: Table,
    company_id: uuid.UUID,
    *,
    visited: frozenset[str] = frozenset(),
) -> ColumnElement[bool] | None:
    """Resolve tenant ownership through company_id or a foreign-key parent chain."""

    if table.name in visited:
        return None
    if "company_id" in table.c:
        return table.c.company_id == company_id
    if table.name == "companies" and "id" in table.c:
        return table.c.id == company_id
    if table.name == "permissions" and {"role_permissions", "roles"}.issubset(
        table.metadata.tables
    ):
        role_permissions = table.metadata.tables["role_permissions"]
        roles = table.metadata.tables["roles"]
        return exists(
            select(1)
            .select_from(role_permissions.join(roles, role_permissions.c.role_id == roles.c.id))
            .where(
                role_permissions.c.permission_id == table.c.id,
                roles.c.company_id == company_id,
            )
            .correlate(table)
        )

    next_visited = visited | {table.name}
    for foreign_key in sorted(
        table.foreign_keys,
        key=lambda item: (item.parent.name, item.column.table.name, item.column.name),
    ):
        parent = foreign_key.column.table
        parent_filter = _ownership_filter(parent, company_id, visited=next_visited)
        if parent_filter is None:
            continue
        return exists(
            select(1)
            .select_from(parent)
            .where(foreign_key.parent == foreign_key.column, parent_filter)
            .correlate(table)
        )
    return None


async def _reflect(session: AsyncSession) -> MetaData:
    connection = await session.connection()
    metadata = MetaData()
    await connection.run_sync(lambda sync_connection: metadata.reflect(bind=sync_connection))
    return metadata


async def _export_boundary(
    boundary: TenantExportBoundary,
    company_id: uuid.UUID,
) -> tuple[str, dict[str, Any], int]:
    database_name = str(await boundary.session.scalar(func.current_database()) or "unknown")
    metadata = await _reflect(boundary.session)
    tables: dict[str, Any] = {}
    redacted_cells = 0

    for table_name in sorted(metadata.tables):
        table = metadata.tables[table_name]
        predicate = _ownership_filter(table, company_id)
        if predicate is None:
            continue
        statement = select(table).where(predicate)
        order_columns = list(table.primary_key.columns)
        if order_columns:
            statement = statement.order_by(*order_columns)
        rows = (await boundary.session.execute(statement)).mappings().all()
        if not rows and table_name != "companies":
            continue

        exported_rows: list[dict[str, Any]] = []
        redacted_columns: set[str] = set()
        for row in rows:
            exported_row: dict[str, Any] = {}
            for column_name, value in row.items():
                if is_sensitive_export_column(column_name):
                    exported_row[column_name] = REDACTED if value is not None else None
                    if value is not None:
                        redacted_cells += 1
                        redacted_columns.add(column_name)
                else:
                    exported_value, nested_redactions = sanitize_export_value(value)
                    exported_row[column_name] = exported_value
                    if nested_redactions:
                        redacted_cells += nested_redactions
                        redacted_columns.add(column_name)
            exported_rows.append(exported_row)
        tables[table_name] = {
            "row_count": len(exported_rows),
            "redacted_columns": sorted(redacted_columns),
            "rows": exported_rows,
        }

    return database_name, {"table_count": len(tables), "tables": tables}, redacted_cells


async def build_tenant_export(
    company_id: uuid.UUID,
    boundaries: list[TenantExportBoundary],
    *,
    reason: str,
    requested_by: str,
) -> dict[str, Any]:
    """Build a deterministic, credential-redacted tenant data portability artifact."""

    if not boundaries:
        raise ValueError("at least one tenant export boundary is required")

    exported_boundaries: dict[str, Any] = {}
    seen_databases: dict[str, str] = {}
    redacted_cells = 0
    company_found = False

    for boundary in boundaries:
        database_name = str(await boundary.session.scalar(func.current_database()) or "unknown")
        if database_name in seen_databases:
            exported_boundaries[seen_databases[database_name]]["aliases"].append(boundary.name)
            continue
        actual_database_name, payload, boundary_redactions = await _export_boundary(
            boundary,
            company_id,
        )
        seen_databases[actual_database_name] = boundary.name
        company_rows = payload["tables"].get("companies", {}).get("row_count", 0)
        company_found = company_found or company_rows == 1
        redacted_cells += boundary_redactions
        exported_boundaries[boundary.name] = {"aliases": [], **payload}

    if not company_found:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")

    content = {"company_id": str(company_id), "boundaries": exported_boundaries}
    canonical = json.dumps(
        content,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    total_tables = sum(item["table_count"] for item in exported_boundaries.values())
    total_rows = sum(
        table["row_count"]
        for item in exported_boundaries.values()
        for table in item["tables"].values()
    )
    return {
        "format": EXPORT_FORMAT,
        "format_version": EXPORT_FORMAT_VERSION,
        "generated_at": datetime.now().astimezone().isoformat(),
        "company_id": str(company_id),
        "request": {"reason": reason, "requested_by": requested_by},
        "redaction": {
            "policy": "credential-and-secret-columns",
            "marker": REDACTED,
            "redacted_cells": redacted_cells,
        },
        "summary": {
            "boundary_count": len(exported_boundaries),
            "table_count": total_tables,
            "row_count": total_rows,
        },
        "content_sha256": hashlib.sha256(canonical).hexdigest(),
        "boundaries": exported_boundaries,
    }
