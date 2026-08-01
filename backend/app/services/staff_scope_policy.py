from __future__ import annotations

from typing import Protocol
import uuid

from app.business_context import CanonicalBusinessContext


class AssignmentScope(Protocol):
    scope_type: str
    brand_id: uuid.UUID | None
    branch_id: uuid.UUID | None
    station_key: str | None


def normalized_station_key(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized.casefold() if normalized else None


def assignment_applies_to_context(
    assignment: AssignmentScope,
    context: CanonicalBusinessContext,
    station_key: str | None,
) -> bool:
    if assignment.scope_type == "company":
        return True
    if assignment.scope_type == "brand":
        return assignment.brand_id == context.brand_id
    if assignment.scope_type == "branch":
        return assignment.branch_id == context.branch_id
    if assignment.scope_type == "station":
        return (
            assignment.branch_id == context.branch_id
            and normalized_station_key(assignment.station_key)
            == normalized_station_key(station_key)
            and normalized_station_key(station_key) is not None
        )
    return False


def assignment_scope_key(
    *,
    company_id: uuid.UUID,
    scope_type: str,
    brand_id: uuid.UUID | None,
    branch_id: uuid.UUID | None,
    station_key: str | None,
) -> str:
    if scope_type == "company":
        return str(company_id)
    if scope_type == "brand" and brand_id is not None:
        return str(brand_id)
    if scope_type == "branch" and branch_id is not None:
        return str(branch_id)
    normalized_station = normalized_station_key(station_key)
    if scope_type == "station" and branch_id is not None and normalized_station is not None:
        return f"{branch_id}:{normalized_station}"
    raise ValueError("Incomplete assignment scope")
