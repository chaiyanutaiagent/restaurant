from __future__ import annotations

import unittest
from unittest.mock import AsyncMock
import uuid

from fastapi import HTTPException
from pydantic import ValidationError

from app.models.stock import StockLocation
from app.schemas.stock import StockLocationCreate, StockLocationUpdate
from app.services.stock_service import StockService


class StockLocationSchemaTests(unittest.TestCase):
    def test_create_normalizes_text_fields(self) -> None:
        payload = StockLocationCreate(
            branch_id=uuid.uuid4(),
            code=" central-ready ",
            name=" คลังพร้อมส่ง ",
            description="  ของพร้อมส่งสาขา  ",
        )
        self.assertEqual(payload.code, "CENTRAL-READY")
        self.assertEqual(payload.name, "คลังพร้อมส่ง")
        self.assertEqual(payload.description, "ของพร้อมส่งสาขา")

    def test_create_rejects_blank_code_and_name(self) -> None:
        with self.assertRaises(ValidationError):
            StockLocationCreate(branch_id=uuid.uuid4(), code="   ", name="   ")

    def test_update_allows_clearing_description(self) -> None:
        payload = StockLocationUpdate(description="   ")
        self.assertIsNone(payload.description)


class StockLocationServiceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.company_id = uuid.uuid4()
        self.branch_id = uuid.uuid4()
        self.location_id = uuid.uuid4()

    def location(self) -> StockLocation:
        return StockLocation(
            id=self.location_id,
            company_id=self.company_id,
            branch_id=self.branch_id,
            code="MAIN",
            name="คลังหลัก",
            is_active=True,
        )

    async def test_location_cannot_move_to_another_branch(self) -> None:
        db = AsyncMock()
        db.scalar.return_value = self.location()
        with self.assertRaises(HTTPException) as raised:
            await StockService(db).update_location(
                self.company_id,
                self.location_id,
                StockLocationUpdate(branch_id=uuid.uuid4()),
            )
        self.assertEqual(raised.exception.status_code, 409)

    async def test_referenced_location_cannot_be_deactivated(self) -> None:
        db = AsyncMock()
        db.scalar.side_effect = [self.location(), uuid.uuid4(), None]
        with self.assertRaises(HTTPException) as raised:
            await StockService(db).update_location(
                self.company_id,
                self.location_id,
                StockLocationUpdate(is_active=False),
            )
        self.assertEqual(raised.exception.status_code, 409)

    async def test_unused_zero_balance_location_can_be_deactivated(self) -> None:
        db = AsyncMock()
        location = self.location()
        db.scalar.side_effect = [location, None, None, None, None]
        updated = await StockService(db).update_location(
            self.company_id,
            self.location_id,
            StockLocationUpdate(is_active=False),
        )
        self.assertFalse(updated.is_active)
        db.commit.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
