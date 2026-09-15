from __future__ import annotations

from datetime import datetime, timezone
import unittest
from unittest.mock import AsyncMock, patch
import uuid

from app.services.retail_reference_projector import (
    RETAIL_USER_PASSWORD_SENTINEL,
    _scope_clause,
    _upsert_sql,
    canonical_reference_digest,
    retail_reference_columns,
    validate_retail_reference_readiness,
)


class RetailReferenceProjectorTests(unittest.IsolatedAsyncioTestCase):
    def test_user_projection_never_reads_or_updates_password_hash(self) -> None:
        columns = retail_reference_columns("user")
        statement = _upsert_sql("user")

        self.assertNotIn("hashed_password", columns)
        self.assertIn("hashed_password", statement.split("VALUES", maxsplit=1)[0])
        self.assertNotIn("hashed_password = EXCLUDED.hashed_password", statement)
        self.assertTrue(RETAIL_USER_PASSWORD_SENTINEL.startswith("!"))

    def test_reference_digest_is_canonical(self) -> None:
        record_id = uuid.uuid4()
        updated_at = datetime(2026, 9, 15, 8, 0, tzinfo=timezone.utc)
        first = {
            "id": record_id,
            "updated_at": updated_at,
            "theme_config": {"accent": "blue", "nested": {"b": 2, "a": 1}},
        }
        second = {
            "theme_config": {"nested": {"a": 1, "b": 2}, "accent": "blue"},
            "updated_at": updated_at,
            "id": record_id,
        }
        self.assertEqual(
            canonical_reference_digest(first),
            canonical_reference_digest(second),
        )

    def test_scope_clause_is_server_owned(self) -> None:
        company_id = uuid.uuid4()
        brand_id = uuid.uuid4()
        branch_id = uuid.uuid4()
        link_id = uuid.uuid4()
        from app.services.retail_reference_projector import RetailReferenceScope

        scope = RetailReferenceScope(
            company_ids=(company_id,),
            brand_ids=(brand_id,),
            branch_ids=(branch_id,),
            brand_branch_ids=(link_id,),
        )
        user_clause, user_parameters = _scope_clause("user", scope)
        brand_clause, brand_parameters = _scope_clause("brand", scope)

        self.assertIn("company_id", user_clause)
        self.assertEqual(user_parameters["scope_ids"], [company_id])
        self.assertIn("id", brand_clause)
        self.assertEqual(brand_parameters["scope_ids"], [brand_id])
        with self.assertRaisesRegex(ValueError, "Unsupported Retail reference"):
            _scope_clause("client_selected_table", scope)

    async def test_readiness_fails_closed_on_digest_mismatch(self) -> None:
        parity = {
            "company": (1, 1, ()),
            "brand": (1, 1, (str(uuid.uuid4()),)),
        }
        with patch(
            "app.services.retail_reference_projector.verify_retail_reference_parity",
            new=AsyncMock(return_value=parity),
        ):
            with self.assertRaisesRegex(RuntimeError, "brand"):
                await validate_retail_reference_readiness()

    async def test_readiness_accepts_exact_projection(self) -> None:
        parity = {
            "company": (1, 1, ()),
            "branch": (1, 1, ()),
            "brand": (1, 1, ()),
            "brand_branch": (1, 1, ()),
            "user": (2, 2, ()),
        }
        with patch(
            "app.services.retail_reference_projector.verify_retail_reference_parity",
            new=AsyncMock(return_value=parity),
        ):
            await validate_retail_reference_readiness()
