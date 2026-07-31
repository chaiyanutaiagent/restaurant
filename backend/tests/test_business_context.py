from __future__ import annotations

import unittest
import uuid

from fastapi import HTTPException
from pydantic import ValidationError

from app.business_context import (
    CanonicalBusinessContext,
    assignment_matches_context,
    target_database_for,
)
from app.dependencies import TokenData, require_business_type
from app.schemas.restaurant import BrandCreateRequest
from app.utils.security import create_access_token, decode_token


class BusinessContextTests(unittest.TestCase):
    def setUp(self) -> None:
        self.context = CanonicalBusinessContext(
            company_id=uuid.uuid4(),
            brand_id=uuid.uuid4(),
            branch_id=uuid.uuid4(),
            business_type="restaurant",
            target_database="restaurant",
        )

    def test_target_database_is_server_mapped_from_business_type(self) -> None:
        self.assertEqual(target_database_for("restaurant"), "restaurant")
        self.assertEqual(target_database_for("retail_pos"), "retail_pos")
        self.assertEqual(target_database_for("takeaway"), "takeaway")
        with self.assertRaisesRegex(ValueError, "Unsupported business type"):
            target_database_for("frontend_selected_database")

    def test_legacy_null_assignment_can_inherit_canonical_context(self) -> None:
        self.assertTrue(
            assignment_matches_context(
                assignment_brand_id=None,
                assignment_business_type=None,
                assignment_target_database=None,
                context=self.context,
            )
        )

    def test_mismatched_brand_or_database_is_rejected(self) -> None:
        self.assertFalse(
            assignment_matches_context(
                assignment_brand_id=uuid.uuid4(),
                assignment_business_type="restaurant",
                assignment_target_database="restaurant",
                context=self.context,
            )
        )
        self.assertFalse(
            assignment_matches_context(
                assignment_brand_id=self.context.brand_id,
                assignment_business_type="restaurant",
                assignment_target_database="retail_pos",
                context=self.context,
            )
        )

    def test_restaurant_brand_schema_rejects_other_business_types(self) -> None:
        with self.assertRaises(ValidationError):
            BrandCreateRequest(
                slug="retail-brand",
                name="Retail Brand",
                business_type="retail_pos",  # type: ignore[arg-type]
            )

    def test_access_token_contains_canonical_routing_claims(self) -> None:
        token = create_access_token(
            subject=str(uuid.uuid4()),
            company_id=str(self.context.company_id),
            branch_id=str(self.context.branch_id),
            permissions=["fb.order.create"],
            brand_id=str(self.context.brand_id),
            business_type=self.context.business_type,
            target_database=self.context.target_database,
        )
        payload = decode_token(token)
        self.assertEqual(payload["brand_id"], str(self.context.brand_id))
        self.assertEqual(payload["business_type"], "restaurant")
        self.assertEqual(payload["target_database"], "restaurant")


class BusinessTypeGuardTests(unittest.IsolatedAsyncioTestCase):
    async def test_guard_accepts_matching_context(self) -> None:
        current = TokenData(
            user_id=uuid.uuid4(),
            company_id=uuid.uuid4(),
            branch_id=uuid.uuid4(),
            permissions=["fb.order.create"],
            business_type="restaurant",
            target_database="restaurant",
        )
        checker = require_business_type("restaurant")
        self.assertIs(await checker(current), current)

    async def test_guard_rejects_cross_business_context(self) -> None:
        current = TokenData(
            user_id=uuid.uuid4(),
            company_id=uuid.uuid4(),
            branch_id=uuid.uuid4(),
            permissions=["fb.order.create"],
            business_type="retail_pos",
            target_database="retail_pos",
        )
        checker = require_business_type("restaurant")
        with self.assertRaises(HTTPException) as context:
            await checker(current)
        self.assertEqual(context.exception.status_code, 403)


if __name__ == "__main__":
    unittest.main()
