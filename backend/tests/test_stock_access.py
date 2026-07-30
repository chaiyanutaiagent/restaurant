from __future__ import annotations

import unittest
from unittest.mock import AsyncMock
import uuid

from fastapi import HTTPException

from app.dependencies import TokenData
from app.services.stock_access_service import StockAccessService, has_central_stock_access


class _Rows:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class StockAccessServiceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.company_id = uuid.uuid4()
        self.branch_id = uuid.uuid4()
        self.other_branch_id = uuid.uuid4()
        self.brand_id = uuid.uuid4()
        self.other_brand_id = uuid.uuid4()
        self.store_location_id = uuid.uuid4()
        self.raw_location_id = uuid.uuid4()
        self.ready_location_id = uuid.uuid4()
        self.other_store_location_id = uuid.uuid4()
        self.other_raw_location_id = uuid.uuid4()
        self.other_ready_location_id = uuid.uuid4()

    def token(
        self,
        permissions: list[str],
        *,
        brand_id: uuid.UUID | None = None,
    ) -> TokenData:
        return TokenData(
            user_id=uuid.uuid4(),
            company_id=self.company_id,
            branch_id=self.branch_id,
            permissions=permissions,
            brand_id=self.brand_id if brand_id is None else brand_id,
        )

    def db(self):
        db = AsyncMock()
        db.scalars.side_effect = [
            _Rows(
                [
                    self.store_location_id,
                    self.raw_location_id,
                    self.ready_location_id,
                    self.other_store_location_id,
                    self.other_raw_location_id,
                    self.other_ready_location_id,
                ]
            ),
            _Rows([self.store_location_id]),
        ]
        db.execute.return_value = _Rows(
            [
                (
                    self.brand_id,
                    self.branch_id,
                    self.raw_location_id,
                    self.ready_location_id,
                ),
                (
                    self.other_brand_id,
                    self.branch_id,
                    self.other_raw_location_id,
                    self.other_ready_location_id,
                ),
            ]
        )
        return db

    def test_central_permission_detection(self) -> None:
        self.assertFalse(has_central_stock_access(self.token(["inventory.stock.view"])))
        self.assertTrue(
            has_central_stock_access(
                self.token(["inventory.stock.view", "brand.central.raw_stock.view"])
            )
        )
        self.assertTrue(has_central_stock_access(self.token(["*"])))

    async def test_store_scope_excludes_central_locations(self) -> None:
        scope = await StockAccessService(self.db()).resolve_scope(
            self.token(["inventory.stock.view"])
        )
        self.assertEqual(scope.branch_id, self.branch_id)
        self.assertEqual(scope.location_ids, (self.store_location_id,))

    async def test_legacy_shared_location_remains_visible_until_ready_cutover(self) -> None:
        db = AsyncMock()
        db.scalars.side_effect = [
            _Rows([self.raw_location_id]),
            _Rows([self.raw_location_id]),
        ]
        db.execute.return_value = _Rows(
            [
                (
                    self.brand_id,
                    self.branch_id,
                    self.raw_location_id,
                    None,
                )
            ]
        )
        scope = await StockAccessService(db).resolve_scope(
            self.token(["brand.store.stock.view"])
        )
        self.assertEqual(scope.location_ids, (self.raw_location_id,))

    async def test_store_cannot_request_central_location(self) -> None:
        with self.assertRaises(HTTPException) as raised:
            await StockAccessService(self.db()).resolve_scope(
                self.token(["inventory.stock.view"]),
                requested_location_id=self.raw_location_id,
            )
        self.assertEqual(raised.exception.status_code, 404)

    async def test_central_scope_can_access_raw_and_ready(self) -> None:
        scope = await StockAccessService(self.db()).resolve_scope(
            self.token(
                [
                    "brand.central.raw_stock.view",
                    "brand.central.ready_stock.view",
                ]
            )
        )
        self.assertEqual(
            scope.location_ids,
            (self.raw_location_id, self.ready_location_id),
        )

    async def test_production_permission_can_view_raw_and_ready(self) -> None:
        scope = await StockAccessService(self.db()).resolve_scope(
            self.token(["brand.central.production.manage"])
        )
        self.assertEqual(
            scope.location_ids,
            (self.raw_location_id, self.ready_location_id),
        )

    async def test_central_ready_permission_does_not_leak_raw(self) -> None:
        scope = await StockAccessService(self.db()).resolve_scope(
            self.token(["brand.central.ready_stock.view"])
        )
        self.assertEqual(scope.location_ids, (self.ready_location_id,))

    async def test_manage_scope_uses_manage_permissions_only(self) -> None:
        with self.assertRaises(HTTPException) as raised:
            await StockAccessService(self.db()).resolve_scope(
                self.token(
                    [
                        "brand.central.raw_stock.manage",
                        "brand.central.ready_stock.view",
                    ]
                ),
                requested_location_id=self.ready_location_id,
                manage=True,
            )
        self.assertEqual(raised.exception.status_code, 404)

    async def test_branch_user_cannot_request_another_branch(self) -> None:
        with self.assertRaises(HTTPException) as raised:
            await StockAccessService(self.db()).resolve_scope(
                self.token(["inventory.stock.view"]),
                requested_branch_id=self.other_branch_id,
            )
        self.assertEqual(raised.exception.status_code, 404)

    async def test_superuser_scope_is_unrestricted(self) -> None:
        db = self.db()
        scope = await StockAccessService(db).resolve_scope(
            self.token(["*"]),
            requested_branch_id=self.other_branch_id,
        )
        self.assertEqual(scope.branch_id, self.other_branch_id)
        self.assertIsNone(scope.location_ids)
        db.scalars.assert_not_awaited()
        db.execute.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
