from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
from decimal import Decimal
import unittest
import uuid

from app.services.retail_migration_service import (
    RETAIL_OPERATIONAL_TABLES,
    RetailTableParity,
    _order_rows_for_copy,
    retail_rows_digest,
)
from app.utils.migrate_retail_data import validate_scope_args


class RetailMigrationTests(unittest.TestCase):
    def test_operational_manifest_covers_retail_sale_lifecycle(self) -> None:
        required = {
            "products",
            "product_variants",
            "price_lists",
            "price_list_items",
            "stock_locations",
            "stock_balances",
            "stock_movements",
            "stock_count_sessions",
            "stock_count_items",
            "cashier_shifts",
            "sale_orders",
            "sale_order_items",
            "payments",
            "approval_grant_usages",
            "audit_logs",
            "operational_outbox_events",
        }
        self.assertTrue(required.issubset(set(RETAIL_OPERATIONAL_TABLES)))
        self.assertEqual(len(RETAIL_OPERATIONAL_TABLES), len(set(RETAIL_OPERATIONAL_TABLES)))

    def test_row_digest_handles_database_types_and_is_order_independent(self) -> None:
        first_id = uuid.uuid4()
        second_id = uuid.uuid4()
        first = [
            {
                "id": first_id,
                "business_date": date(2026, 9, 15),
                "created_at": datetime(2026, 9, 15, 8, 0, tzinfo=timezone.utc),
                "amount": Decimal("107.0000"),
                "metadata": {"b": 2, "a": 1},
            },
            {"id": second_id, "amount": Decimal("0.00")},
        ]
        second = [
            {"amount": Decimal("0.00"), "id": second_id},
            {
                "metadata": {"a": 1, "b": 2},
                "amount": Decimal("107.0000"),
                "created_at": datetime(2026, 9, 15, 8, 0, tzinfo=timezone.utc),
                "business_date": date(2026, 9, 15),
                "id": first_id,
            },
        ]
        self.assertEqual(retail_rows_digest(first), retail_rows_digest(second))

    def test_table_parity_requires_both_count_and_digest(self) -> None:
        self.assertTrue(RetailTableParity("products", 1, 1, "same", "same").matches)
        self.assertFalse(RetailTableParity("products", 1, 2, "same", "same").matches)
        self.assertFalse(RetailTableParity("products", 1, 1, "a", "b").matches)

    def test_self_references_are_copied_parent_first_across_batches(self) -> None:
        parent_id = uuid.uuid4()
        child_id = uuid.uuid4()
        rows = [
            {"id": child_id, "parent_id": parent_id},
            {"id": parent_id, "parent_id": None},
        ]
        ordered = _order_rows_for_copy("categories", rows)
        self.assertEqual([row["id"] for row in ordered], [parent_id, child_id])

    def test_missing_self_reference_fails_closed(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "missing or cyclic"):
            _order_rows_for_copy(
                "payments",
                [{"id": uuid.uuid4(), "original_payment_id": uuid.uuid4()}],
            )

    def test_cli_requires_explicit_scope_or_confirmed_all_retail(self) -> None:
        empty = argparse.Namespace(
            all_retail=False,
            company_id=None,
            brand_id=[],
            yes=False,
        )
        with self.assertRaisesRegex(ValueError, "Select"):
            validate_scope_args(empty)

        unconfirmed_all = argparse.Namespace(
            all_retail=True,
            company_id=None,
            brand_id=[],
            yes=False,
        )
        with self.assertRaisesRegex(ValueError, "requires --yes"):
            validate_scope_args(unconfirmed_all)

        confirmed_all = argparse.Namespace(
            all_retail=True,
            company_id=None,
            brand_id=[],
            yes=True,
        )
        validate_scope_args(confirmed_all)
