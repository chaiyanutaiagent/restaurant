from __future__ import annotations

from collections.abc import Iterable
from typing import Any


CENTRAL_STOCK_PERMISSIONS = {
    "brand.central.raw_stock.view",
    "brand.central.raw_stock.manage",
    "brand.central.ready_stock.view",
    "brand.central.ready_stock.manage",
}
CENTRAL_PRODUCTION_PERMISSIONS = {
    "brand.central.production.view",
    "brand.central.production.manage",
}
CENTRAL_NAVIGATION_PERMISSIONS = {
    *CENTRAL_STOCK_PERMISSIONS,
    *CENTRAL_PRODUCTION_PERMISSIONS,
    "fb.kitchen.manage",
    "fb.recipe.manage",
    "system.user.approve",
}


def _permission_codes(assignment: Any) -> set[str]:
    role = assignment.role
    if role is None or role.deleted_at is not None:
        return set()
    return {permission.code for permission in role.permissions}


def _assignment_is_active(assignment: Any) -> bool:
    branch = assignment.branch
    return (
        assignment.deleted_at is None
        and branch is not None
        and branch.deleted_at is None
        and branch.is_active
    )


def _assignment_matches_brand(
    assignment: Any,
    brand: Any,
    *,
    is_superuser: bool,
) -> bool:
    if is_superuser:
        return True
    return assignment.brand_id is None or assignment.brand_id == brand.id


def _central_landing_path(
    permission_codes: set[str],
    *,
    is_superuser: bool,
) -> str | None:
    if is_superuser or permission_codes.intersection(CENTRAL_STOCK_PERMISSIONS):
        return "stock"
    if permission_codes.intersection(CENTRAL_PRODUCTION_PERMISSIONS):
        return "production"
    if "fb.kitchen.manage" in permission_codes:
        return "orders"
    if "fb.recipe.manage" in permission_codes:
        return "recipes"
    if "system.user.approve" in permission_codes:
        return "staff"
    return None


def _store_landing_path(
    permission_codes: set[str],
    *,
    is_superuser: bool,
) -> str | None:
    if is_superuser or permission_codes.intersection(
        {"brand.store.order.create", "fb.order.create"}
    ):
        return "orders"
    if permission_codes.intersection(
        {"brand.store.stock.view", "brand.store.stock.adjust"}
    ):
        return "stock"
    if permission_codes.intersection(
        {
            "brand.store.replenishment.submit",
            "brand.store.delivery.receive",
        }
    ):
        return "replenishment-orders"
    if "brand.store.shift.close" in permission_codes:
        return "close-shift"
    if "system.user.request" in permission_codes:
        return "staff"
    return None


def build_brand_navigation(
    brands: Iterable[Any],
    assignments: Iterable[Any],
    current: Any,
) -> list[dict[str, Any]]:
    is_superuser = "*" in current.permissions
    active_assignments = [
        assignment for assignment in assignments if _assignment_is_active(assignment)
    ]
    data: list[dict[str, Any]] = []

    for brand in brands:
        if not brand.is_active:
            continue

        brand_assignments = [
            assignment
            for assignment in active_assignments
            if _assignment_matches_brand(
                assignment,
                brand,
                is_superuser=is_superuser,
            )
        ]
        central_assignment = next(
            (
                assignment
                for assignment in brand_assignments
                if brand.central_branch_id is not None
                and assignment.branch_id == brand.central_branch_id
                and (
                    is_superuser
                    or _permission_codes(assignment).intersection(
                        CENTRAL_NAVIGATION_PERMISSIONS
                    )
                )
            ),
            None,
        )
        central_permissions = (
            _permission_codes(central_assignment)
            if central_assignment is not None
            else set()
        )
        central_landing_path = _central_landing_path(
            central_permissions,
            is_superuser=is_superuser,
        )

        branches: list[dict[str, Any]] = []
        for brand_branch in brand.branches:
            branch = brand_branch.branch
            if (
                not brand_branch.is_active
                or branch is None
                or branch.deleted_at is not None
                or not branch.is_active
            ):
                continue
            assignment = next(
                (
                    candidate
                    for candidate in brand_assignments
                    if candidate.branch_id == brand_branch.branch_id
                ),
                None,
            )
            if assignment is None:
                continue
            landing_path = _store_landing_path(
                _permission_codes(assignment),
                is_superuser=is_superuser,
            )
            if landing_path is None:
                continue
            branches.append(
                {
                    "branch_id": str(branch.id),
                    "branch_code": branch.code,
                    "branch_name": branch.name,
                    "branch_type": brand_branch.branch_type,
                    "store_location_configured": (
                        brand_branch.store_location_id is not None
                    ),
                    "landing_path": landing_path,
                    "is_current": branch.id == current.branch_id,
                }
            )

        branches.sort(
            key=lambda item: (
                not item["is_current"],
                item["branch_name"].casefold(),
                item["branch_code"].casefold(),
            )
        )
        if central_landing_path is None and not branches:
            continue

        data.append(
            {
                "id": str(brand.id),
                "slug": brand.slug,
                "name": brand.name,
                "central_branch_id": (
                    str(central_assignment.branch_id)
                    if central_assignment is not None
                    else None
                ),
                "central_landing_path": central_landing_path,
                "branches": branches,
            }
        )

    data.sort(key=lambda item: item["name"].casefold())
    return data
