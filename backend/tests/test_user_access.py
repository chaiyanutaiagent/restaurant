from __future__ import annotations

import unittest
import uuid

from fastapi import HTTPException
from pydantic import ValidationError

from app.models.restaurant import Brand
from app.models.user_access import UserAccessRequest
from app.schemas.user_access import UserAccessRejectRequest, UserAccessRequestCreate
from app.schemas.user_mgmt import RoleCreateFull, RoleUpdateFull
from app.services.admin_service import forbidden_branch_role_permissions
from app.services.user_access_service import UserAccessService


class UserAccessSchemaTests(unittest.TestCase):
    def test_request_requires_email_or_phone(self) -> None:
        with self.assertRaises(ValidationError):
            UserAccessRequestCreate(
                brand_slug="restaurant",
                requested_role_id=uuid.uuid4(),
                username="somchai",
                password="Password123!",
                first_name="Somchai",
                last_name="Cashier",
            )

    def test_request_normalizes_contact_and_names(self) -> None:
        payload = UserAccessRequestCreate(
            brand_slug="restaurant",
            requested_role_id=uuid.uuid4(),
            username="somchai",
            password="Password123!",
            first_name="  Somchai ",
            last_name=" Cashier  ",
            email="  STAFF@EXAMPLE.COM ",
        )
        self.assertEqual(payload.first_name, "Somchai")
        self.assertEqual(payload.last_name, "Cashier")
        self.assertEqual(payload.email, "staff@example.com")

    def test_request_rejects_blank_names_after_trimming(self) -> None:
        with self.assertRaises(ValidationError):
            UserAccessRequestCreate(
                brand_slug="restaurant",
                requested_role_id=uuid.uuid4(),
                username="somchai",
                password="Password123!",
                first_name="   ",
                last_name="Cashier",
                phone="0812345678",
            )

    def test_rejection_requires_non_blank_reason(self) -> None:
        with self.assertRaises(ValidationError):
            UserAccessRejectRequest(reason="   ")

    def test_development_password_123456_is_allowed(self) -> None:
        payload = UserAccessRequestCreate(
            brand_slug="restaurant",
            requested_role_id=uuid.uuid4(),
            username="cashier.dev",
            password="123456",
            first_name="Dev",
            last_name="Cashier",
            phone="0812345678",
        )
        self.assertEqual(payload.password, "123456")

    def test_role_payload_supports_branch_assignable_flag(self) -> None:
        created = RoleCreateFull(
            name="Store Manager",
            permission_ids=[],
            is_branch_assignable=True,
        )
        updated = RoleUpdateFull(is_branch_assignable=False)
        self.assertTrue(created.is_branch_assignable)
        self.assertFalse(updated.is_branch_assignable)


class BranchRolePermissionTests(unittest.TestCase):
    def test_safe_branch_permissions_are_allowed(self) -> None:
        self.assertEqual(
            forbidden_branch_role_permissions(
                {"brand.store.order.create", "system.user.request", "pos.sale.create"}
            ),
            [],
        )

    def test_central_permissions_are_rejected(self) -> None:
        blocked = forbidden_branch_role_permissions(
            {"system.user.approve", "system.role.edit", "inventory.transfer.approve"}
        )
        self.assertEqual(
            blocked,
            ["inventory.transfer.approve", "system.role.edit", "system.user.approve"],
        )


class BrandReviewScopeTests(unittest.TestCase):
    def test_brand_center_can_review_its_request(self) -> None:
        central_branch_id = uuid.uuid4()
        row = UserAccessRequest()
        row.brand = Brand(central_branch_id=central_branch_id)
        UserAccessService._require_review_scope(row, central_branch_id, False)

    def test_other_brand_center_cannot_review_request(self) -> None:
        row = UserAccessRequest()
        row.brand = Brand(central_branch_id=uuid.uuid4())
        with self.assertRaises(HTTPException) as context:
            UserAccessService._require_review_scope(row, uuid.uuid4(), False)
        self.assertEqual(context.exception.status_code, 404)

    def test_superuser_can_review_legacy_request_without_brand(self) -> None:
        row = UserAccessRequest()
        row.brand = None
        UserAccessService._require_review_scope(row, None, True)


if __name__ == "__main__":
    unittest.main()
