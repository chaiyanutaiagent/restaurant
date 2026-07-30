from __future__ import annotations

from types import SimpleNamespace
import unittest
import uuid

from app.services.brand_navigation import build_brand_navigation


def permission(code: str) -> SimpleNamespace:
    return SimpleNamespace(code=code)


def role(*codes: str) -> SimpleNamespace:
    return SimpleNamespace(
        deleted_at=None,
        permissions=[permission(code) for code in codes],
    )


def branch(
    branch_id: uuid.UUID,
    *,
    code: str,
    name: str,
    is_active: bool = True,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=branch_id,
        code=code,
        name=name,
        is_active=is_active,
        deleted_at=None,
    )


def assignment(
    branch_row: SimpleNamespace,
    assignment_role: SimpleNamespace,
    *,
    brand_id: uuid.UUID | None,
) -> SimpleNamespace:
    return SimpleNamespace(
        branch_id=branch_row.id,
        branch=branch_row,
        brand_id=brand_id,
        role=assignment_role,
        deleted_at=None,
    )


def brand_branch(
    brand_id: uuid.UUID,
    branch_row: SimpleNamespace,
    *,
    store_location_id: uuid.UUID | None = None,
    is_active: bool = True,
) -> SimpleNamespace:
    return SimpleNamespace(
        brand_id=brand_id,
        branch_id=branch_row.id,
        branch=branch_row,
        branch_type="company_owned",
        store_location_id=store_location_id,
        is_active=is_active,
    )


class BrandNavigationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.company_id = uuid.uuid4()
        self.user_id = uuid.uuid4()
        self.brand_id = uuid.uuid4()
        self.central_branch = branch(
            uuid.uuid4(),
            code="CENTRAL",
            name="ส่วนกลาง",
        )
        self.store_branch = branch(
            uuid.uuid4(),
            code="BKK",
            name="สาขากรุงเทพ",
        )

    def token(
        self,
        permissions: list[str],
        *,
        branch_id: uuid.UUID | None = None,
    ) -> SimpleNamespace:
        return SimpleNamespace(
            user_id=self.user_id,
            company_id=self.company_id,
            branch_id=branch_id,
            permissions=permissions,
        )

    def brand(self, *, brand_id: uuid.UUID | None = None) -> SimpleNamespace:
        target_brand_id = brand_id or self.brand_id
        return SimpleNamespace(
            id=target_brand_id,
            slug="restaurant",
            name="RESTAURANT",
            is_active=True,
            central_branch_id=self.central_branch.id,
            branches=[
                brand_branch(
                    target_brand_id,
                    self.store_branch,
                    store_location_id=uuid.uuid4(),
                )
            ],
        )

    def test_returns_central_and_store_navigation_for_brand_assignments(self) -> None:
        assignments = [
            assignment(
                self.central_branch,
                role("brand.central.raw_stock.view"),
                brand_id=self.brand_id,
            ),
            assignment(
                self.store_branch,
                role("brand.store.stock.view"),
                brand_id=self.brand_id,
            ),
        ]

        result = build_brand_navigation(
            [self.brand()],
            assignments,
            self.token(
                ["brand.store.stock.view"],
                branch_id=self.store_branch.id,
            ),
        )

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["central_landing_path"], "stock")
        self.assertEqual(
            result[0]["central_branch_id"],
            str(self.central_branch.id),
        )
        self.assertEqual(len(result[0]["branches"]), 1)
        self.assertEqual(result[0]["branches"][0]["landing_path"], "stock")
        self.assertTrue(result[0]["branches"][0]["is_current"])
        self.assertTrue(
            result[0]["branches"][0]["store_location_configured"]
        )

    def test_brand_scoped_assignment_does_not_leak_to_another_brand(self) -> None:
        other_brand_id = uuid.uuid4()
        assignments = [
            assignment(
                self.store_branch,
                role("brand.store.order.create"),
                brand_id=self.brand_id,
            )
        ]

        result = build_brand_navigation(
            [self.brand(brand_id=other_brand_id)],
            assignments,
            self.token(["brand.store.order.create"]),
        )

        self.assertEqual(result, [])

    def test_assignment_without_brand_scope_supports_legacy_branch_roles(self) -> None:
        assignments = [
            assignment(
                self.store_branch,
                role("fb.order.create"),
                brand_id=None,
            )
        ]

        result = build_brand_navigation(
            [self.brand()],
            assignments,
            self.token(["fb.order.create"]),
        )

        self.assertEqual(result[0]["branches"][0]["landing_path"], "orders")

    def test_branch_without_brand_permissions_is_hidden(self) -> None:
        assignments = [
            assignment(
                self.store_branch,
                role("inventory.stock.view"),
                brand_id=self.brand_id,
            )
        ]

        result = build_brand_navigation(
            [self.brand()],
            assignments,
            self.token(["inventory.stock.view"]),
        )

        self.assertEqual(result, [])

    def test_superuser_still_requires_branch_assignment_for_switching(self) -> None:
        assignments = [
            assignment(
                self.store_branch,
                role(),
                brand_id=None,
            )
        ]

        result = build_brand_navigation(
            [self.brand()],
            assignments,
            self.token(["*"]),
        )

        self.assertEqual(result[0]["central_landing_path"], "stock")
        self.assertIsNone(result[0]["central_branch_id"])
        self.assertEqual(result[0]["branches"][0]["landing_path"], "orders")


if __name__ == "__main__":
    unittest.main()
