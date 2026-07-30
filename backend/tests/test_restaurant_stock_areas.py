import uuid
import unittest
from unittest.mock import AsyncMock

from fastapi import HTTPException

from app.models.restaurant import Brand
from app.models.stock import StockLocation
from app.routers.restaurant import _resolve_brand_stock_area_location


class RestaurantStockAreaTests(unittest.IsolatedAsyncioTestCase):
    async def test_production_area_resolves_central_raw_location(self) -> None:
        company_id = uuid.uuid4()
        branch_id = uuid.uuid4()
        location_id = uuid.uuid4()
        brand = Brand(
            company_id=company_id,
            slug="restaurant",
            name="RESTAURANT",
            central_location_id=location_id,
            is_active=True,
        )
        location = StockLocation(
            id=location_id,
            company_id=company_id,
            branch_id=branch_id,
            code="RESTAURANT-CENTRAL-RAW",
            name="ฝ่ายผลิต",
            is_active=True,
            deleted_at=None,
        )
        db = AsyncMock()
        db.get.return_value = location

        result = await _resolve_brand_stock_area_location(
            db,
            company_id,
            brand,
            "production",
        )

        self.assertIs(result, location)
        db.get.assert_awaited_once_with(StockLocation, location_id)

    async def test_storefront_area_requires_branch(self) -> None:
        brand = Brand(
            company_id=uuid.uuid4(),
            slug="restaurant",
            name="RESTAURANT",
            is_active=True,
        )
        db = AsyncMock()

        with self.assertRaises(HTTPException) as raised:
            await _resolve_brand_stock_area_location(
                db,
                brand.company_id,
                brand,
                "storefront",
            )

        self.assertEqual(raised.exception.status_code, 400)

    async def test_storefront_location_must_belong_to_selected_branch(self) -> None:
        company_id = uuid.uuid4()
        selected_branch_id = uuid.uuid4()
        location_id = uuid.uuid4()
        brand = Brand(
            id=uuid.uuid4(),
            company_id=company_id,
            slug="restaurant",
            name="RESTAURANT",
            is_active=True,
        )
        location = StockLocation(
            id=location_id,
            company_id=company_id,
            branch_id=uuid.uuid4(),
            code="STORE",
            name="หน้าร้าน",
            is_active=True,
            deleted_at=None,
        )
        db = AsyncMock()
        db.scalar.return_value = location_id
        db.get.return_value = location

        with self.assertRaises(HTTPException) as raised:
            await _resolve_brand_stock_area_location(
                db,
                company_id,
                brand,
                "storefront",
                selected_branch_id,
            )

        self.assertEqual(raised.exception.status_code, 409)
