from __future__ import annotations

import unittest
import uuid
from unittest.mock import AsyncMock

from fastapi import HTTPException

from app.services.business_directory_service import allocate_business_slug
from app.utils.business_slug import normalize_business_slug, suggest_business_slug


class BusinessSlugTests(unittest.TestCase):
    def test_normalizes_valid_slug(self) -> None:
        self.assertEqual(normalize_business_slug(" Coffee-House "), "coffee-house")

    def test_rejects_reserved_ambiguous_and_non_ascii_values(self) -> None:
        for value in ("admin", "platform", "ab", "coffee--house", "ร้านกาแฟ", "-coffee"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                normalize_business_slug(value)

    def test_suggests_ascii_name_or_deterministic_fallback(self) -> None:
        self.assertEqual(
            suggest_business_slug("Coffee & House", fallback_suffix="12345678"),
            "coffee-house",
        )
        self.assertEqual(
            suggest_business_slug("ร้านกาแฟ", fallback_suffix="12345678"),
            "business-12345678",
        )


class BusinessSlugAllocationTests(unittest.IsolatedAsyncioTestCase):
    async def test_requested_duplicate_is_rejected(self) -> None:
        db = AsyncMock()
        db.scalar.return_value = uuid.uuid4()
        with self.assertRaises(HTTPException) as raised:
            await allocate_business_slug(
                db,
                requested_slug="coffee-house",
                business_name="Coffee House",
                company_id=uuid.uuid4(),
            )
        self.assertEqual(raised.exception.status_code, 409)

    async def test_generated_collision_receives_company_suffix(self) -> None:
        company_id = uuid.UUID("12345678-1234-1234-1234-123456789abc")
        db = AsyncMock()
        db.scalar.side_effect = [uuid.uuid4(), None]
        slug = await allocate_business_slug(
            db,
            requested_slug=None,
            business_name="Coffee House",
            company_id=company_id,
        )
        self.assertEqual(slug, "coffee-house-12345678")

    async def test_generated_suffix_collision_receives_deterministic_counter(self) -> None:
        company_id = uuid.UUID("12345678-1234-1234-1234-123456789abc")
        db = AsyncMock()
        db.scalar.side_effect = [uuid.uuid4(), uuid.uuid4(), None]
        slug = await allocate_business_slug(
            db,
            requested_slug=None,
            business_name="Coffee House",
            company_id=company_id,
        )
        self.assertEqual(slug, "coffee-house-12345678-2")


if __name__ == "__main__":
    unittest.main()
