from __future__ import annotations

import unittest
import uuid

from fastapi import HTTPException

from app.dependencies import TokenData
from app.services.report_scope_policy import (
    require_brand_report_scope,
    resolve_report_branch_id,
)


class ReportScopePolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.company_id = uuid.uuid4()
        self.brand_id = uuid.uuid4()
        self.branch_id = uuid.uuid4()

    def current(
        self,
        scope_types: list[str],
        *,
        branch_id: uuid.UUID | None = None,
        brand_id: uuid.UUID | None = None,
        permissions: list[str] | None = None,
    ) -> TokenData:
        return TokenData(
            user_id=uuid.uuid4(),
            company_id=self.company_id,
            branch_id=branch_id,
            brand_id=brand_id,
            permissions=permissions or ["pos.report.view", "fb.report.view"],
            scope_types=scope_types,
        )

    def test_company_scope_can_aggregate_or_select_a_branch(self) -> None:
        current = self.current(["company"], branch_id=self.branch_id)
        self.assertIsNone(resolve_report_branch_id(current, None))
        requested = uuid.uuid4()
        self.assertEqual(resolve_report_branch_id(current, requested), requested)

    def test_superuser_keeps_company_report_scope(self) -> None:
        current = self.current([], permissions=["*"])
        self.assertIsNone(resolve_report_branch_id(current, None))
        require_brand_report_scope(current, uuid.uuid4())

    def test_brand_scope_generic_report_is_locked_to_current_branch(self) -> None:
        current = self.current(
            ["brand"],
            branch_id=self.branch_id,
            brand_id=self.brand_id,
        )
        self.assertEqual(resolve_report_branch_id(current, None), self.branch_id)
        self.assertEqual(resolve_report_branch_id(current, self.branch_id), self.branch_id)
        with self.assertRaises(HTTPException) as raised:
            resolve_report_branch_id(current, uuid.uuid4())
        self.assertEqual(raised.exception.status_code, 404)

    def test_branch_and_station_scopes_cannot_request_another_branch(self) -> None:
        for scope_type in ("branch", "station"):
            with self.subTest(scope_type=scope_type):
                current = self.current([scope_type], branch_id=self.branch_id, brand_id=self.brand_id)
                self.assertEqual(resolve_report_branch_id(current, None), self.branch_id)
                with self.assertRaises(HTTPException) as raised:
                    resolve_report_branch_id(current, uuid.uuid4())
                self.assertEqual(raised.exception.status_code, 404)
                self.assertEqual(raised.exception.detail, "Report scope not found")

    def test_non_company_scope_requires_branch_context(self) -> None:
        with self.assertRaises(HTTPException) as raised:
            resolve_report_branch_id(self.current(["brand"], brand_id=self.brand_id), None)
        self.assertEqual(raised.exception.status_code, 403)

    def test_only_company_or_matching_brand_scope_can_use_consolidated_report(self) -> None:
        require_brand_report_scope(self.current(["company"]), uuid.uuid4())
        require_brand_report_scope(
            self.current(["brand"], branch_id=self.branch_id, brand_id=self.brand_id),
            self.brand_id,
        )

        denied_contexts = (
            self.current(["brand"], branch_id=self.branch_id, brand_id=uuid.uuid4()),
            self.current(["branch"], branch_id=self.branch_id, brand_id=self.brand_id),
            self.current(["station"], branch_id=self.branch_id, brand_id=self.brand_id),
        )
        for current in denied_contexts:
            with self.subTest(scope_types=current.scope_types), self.assertRaises(HTTPException) as raised:
                require_brand_report_scope(current, self.brand_id)
            self.assertEqual(raised.exception.status_code, 404)


if __name__ == "__main__":
    unittest.main()
