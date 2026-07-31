from __future__ import annotations

from dataclasses import dataclass
import uuid


RESTAURANT = "restaurant"
RETAIL_POS = "retail_pos"
TAKEAWAY = "takeaway"
BUSINESS_TYPES = (RESTAURANT, RETAIL_POS, TAKEAWAY)

TARGET_DATABASE_BY_BUSINESS_TYPE = {
    RESTAURANT: "restaurant",
    RETAIL_POS: "retail_pos",
    TAKEAWAY: "takeaway",
}


def target_database_for(business_type: str) -> str:
    try:
        return TARGET_DATABASE_BY_BUSINESS_TYPE[business_type]
    except KeyError as exc:
        raise ValueError(f"Unsupported business type: {business_type}") from exc


@dataclass(frozen=True)
class CanonicalBusinessContext:
    company_id: uuid.UUID
    brand_id: uuid.UUID
    branch_id: uuid.UUID
    business_type: str
    target_database: str


def assignment_matches_context(
    *,
    assignment_brand_id: uuid.UUID | None,
    assignment_business_type: str | None,
    assignment_target_database: str | None,
    context: CanonicalBusinessContext,
) -> bool:
    return (
        assignment_brand_id in {None, context.brand_id}
        and assignment_business_type in {None, context.business_type}
        and assignment_target_database in {None, context.target_database}
    )
