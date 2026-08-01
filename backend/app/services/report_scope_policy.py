from __future__ import annotations

from typing import Protocol
import uuid

from fastapi import HTTPException, status


class ReportScopeContext(Protocol):
    branch_id: uuid.UUID | None
    brand_id: uuid.UUID | None
    permissions: list[str]
    scope_types: list[str]


def has_company_report_scope(current: ReportScopeContext) -> bool:
    return "*" in current.permissions or "company" in current.scope_types


def resolve_report_branch_id(
    current: ReportScopeContext,
    requested_branch_id: uuid.UUID | None,
) -> uuid.UUID | None:
    """Resolve generic reports to a server-owned Company or current-Branch scope."""
    if has_company_report_scope(current):
        return requested_branch_id
    if current.branch_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Branch context required for this report",
        )
    if requested_branch_id is not None and requested_branch_id != current.branch_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report scope not found")
    return current.branch_id


def require_brand_report_scope(
    current: ReportScopeContext,
    requested_brand_id: uuid.UUID,
) -> None:
    """Allow consolidated Brand reporting only to Company- or matching Brand-scoped staff."""
    if has_company_report_scope(current):
        return
    if "brand" in current.scope_types and current.brand_id == requested_brand_id:
        return
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report scope not found")
