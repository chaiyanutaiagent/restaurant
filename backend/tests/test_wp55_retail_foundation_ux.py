from __future__ import annotations

from pathlib import Path
import unittest
import uuid
from unittest.mock import AsyncMock, MagicMock

from fastapi import HTTPException

from app.dependencies import TokenData
from app.routers.products import list_products
from app.services.dining_service import DiningService


ROOT = Path(__file__).resolve().parents[2]


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


def _current(*, business_type: str = "retail_pos", with_scope: bool = True) -> TokenData:
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


class RetailCatalogContractTests(unittest.IsolatedAsyncioTestCase):
    async def test_retail_catalog_is_server_scoped_and_excludes_restaurant_products(self) -> None:
        db = _RecordingDb()
        payload = await list_products(
            page=1,
            limit=100,
            search=None,
            category_id=None,
            product_type="menu_item",
            is_active=True,
            is_for_sale=False,
            catalog_scope="retail_sale",
            current=_current(),
            db=db,  # type: ignore[arg-type]
        )

        self.assertEqual(payload["data"], [])
        sql = "\n".join(str(statement) for statement in db.statements)
        self.assertIn("products.is_for_sale", sql)
        self.assertIn("products.brand_id", sql)
        self.assertNotIn("products.brand_id IS NULL", sql)
        self.assertIn("products.product_type NOT IN", sql)

    async def test_retail_catalog_rejects_unsigned_or_restaurant_context(self) -> None:
        mismatched_target = _current()
        mismatched_target.target_database = "restaurant"
        for current in (_current(with_scope=False), _current(business_type="restaurant"), mismatched_target):
            with self.subTest(current=current), self.assertRaises(HTTPException) as raised:
                await list_products(
                    page=1,
                    limit=20,
                    search=None,
                    category_id=None,
                    product_type=None,
                    is_active=True,
                    is_for_sale=None,
                    catalog_scope="retail_sale",
                    current=current,
                    db=_RecordingDb(),  # type: ignore[arg-type]
                )
            self.assertEqual(raised.exception.status_code, 403)

    async def test_public_restaurant_brand_resolution_is_unique_and_branch_scoped(self) -> None:
        brand_id = uuid.uuid4()
        rows = MagicMock()
        rows.all.return_value = [brand_id]
        db = AsyncMock()
        db.scalars.return_value = rows

        resolved = await DiningService(db)._resolve_restaurant_brand_id(uuid.uuid4(), uuid.uuid4())

        self.assertEqual(resolved, brand_id)
        sql = str(db.scalars.await_args.args[0])
        self.assertIn("brand_branches.branch_id", sql)
        self.assertIn("brands.business_type", sql)
        self.assertIn("brands.is_active IS true", sql)


class RetailShellContractTests(unittest.TestCase):
    def test_retail_shell_uses_signed_context_and_dedicated_catalog(self) -> None:
        page = (ROOT / "frontend/src/pages/pos/POSPage.tsx").read_text()
        self.assertIn('businessType === "retail_pos"', page)
        self.assertIn('"retail_sale" as const', page)
        self.assertIn("POS_CATALOG_ISOLATION_KEY", page)
        self.assertIn("Pilot · Production ใช้ Legacy", page)
        self.assertIn("signed Company / Brand / Branch", page)

    def test_retail_navigation_excludes_restaurant_surfaces(self) -> None:
        navigation = (ROOT / "frontend/src/components/pos/PosWorkspaceNav.tsx").read_text()
        retail_block = navigation.split('if (mode === "retail")', maxsplit=1)[1].split("return (", maxsplit=1)[0]
        for label in ("ขาย", "พักบิล", "บิล / คืนสินค้า", "กะ", "สถานะเครื่อง"):
            self.assertIn(label, retail_block)
        for forbidden in ("เปิดโต๊ะ", "KDS", "รับกลับ", "เดลิเวอรี"):
            self.assertNotIn(forbidden, retail_block)

    def test_retail_offline_checkout_and_cross_context_cache_fail_closed(self) -> None:
        page = (ROOT / "frontend/src/pages/pos/POSPage.tsx").read_text()
        self.assertIn("!isOnline || !retailContextValid || !catalogCacheTrusted", page)
        self.assertIn("ปิดการขายและไม่อ่าน Catalog จาก cache อื่น", page)
        self.assertIn("ปิดรับชำระ Offline", page)
        self.assertIn("สถานะ Browser ไม่ถือเป็นผลทดสอบอุปกรณ์จริง", page)

    def test_regression_runner_mounts_frontend_contract_sources(self) -> None:
        runner = (ROOT / "scripts/run-backend-regression.sh").read_text()
        self.assertIn('cp -R "$ROOT_DIR/frontend" "$DOCKER_SRC/frontend"', runner)
        self.assertIn('cp -R "$ROOT_DIR/scripts" "$DOCKER_SRC/scripts"', runner)
        self.assertIn('-v "$DOCKER_SRC:/workspace:ro"', runner)

    def test_restaurant_public_catalog_is_brand_scoped(self) -> None:
        service = (ROOT / "backend/app/services/dining_service.py").read_text()
        router = (ROOT / "backend/app/routers/restaurant.py").read_text()
        self.assertIn("Product.brand_id == brand_id", service)
        self.assertIn("Category.id.in_(category_ids)", service)
        self.assertIn("Brand.id == current.brand_id", router)
        self.assertIn("CategoryModel.id.in_(category_ids)", router)


if __name__ == "__main__":
    unittest.main()
