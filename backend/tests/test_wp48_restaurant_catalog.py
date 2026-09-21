from __future__ import annotations

import unittest
import uuid

from fastapi import HTTPException

from app.dependencies import TokenData
from app.routers.products import list_products


class _Rows:
    def all(self) -> list[object]:
        return []


class _RecordingDb:
    def __init__(self) -> None:
        self.statements: list[object] = []

    async def scalar(self, statement: object) -> int:
        self.statements.append(statement)
        return 0

    async def scalars(self, statement: object) -> _Rows:
        self.statements.append(statement)
        return _Rows()


def _current(*, business_type: str = "restaurant", with_scope: bool = True) -> TokenData:
    return TokenData(
        user_id=uuid.uuid4(),
        company_id=uuid.uuid4(),
        branch_id=uuid.uuid4() if with_scope else None,
        brand_id=uuid.uuid4() if with_scope else None,
        business_type=business_type,
        target_database=business_type,
        permissions=["inventory.product.view"],
        scope_types=["branch"],
    )


class RestaurantCatalogScopeTests(unittest.IsolatedAsyncioTestCase):
    async def test_restaurant_menu_is_server_scoped_to_saleable_menu_items_and_signed_brand(self) -> None:
        db = _RecordingDb()
        current = _current()

        payload = await list_products(
            page=1,
            limit=100,
            search=None,
            category_id=None,
            product_type="raw_material",
            is_active=True,
            is_for_sale=False,
            catalog_scope="restaurant_menu",
            current=current,
            db=db,  # type: ignore[arg-type]
        )

        self.assertEqual(payload["data"], [])
        sql = "\n".join(str(statement) for statement in db.statements)
        self.assertIn("products.product_type", sql)
        self.assertIn("products.is_for_sale", sql)
        self.assertIn("products.brand_id", sql)
        self.assertIn("products.brand_id IS NULL", sql)

    async def test_restaurant_menu_rejects_unsigned_or_non_restaurant_context(self) -> None:
        for current in (_current(with_scope=False), _current(business_type="retail_pos")):
            with self.subTest(current=current), self.assertRaises(HTTPException) as raised:
                await list_products(
                    page=1,
                    limit=20,
                    search=None,
                    category_id=None,
                    product_type=None,
                    is_active=True,
                    is_for_sale=None,
                    catalog_scope="restaurant_menu",
                    current=current,
                    db=_RecordingDb(),  # type: ignore[arg-type]
                )
            self.assertEqual(raised.exception.status_code, 403)


if __name__ == "__main__":
    unittest.main()
