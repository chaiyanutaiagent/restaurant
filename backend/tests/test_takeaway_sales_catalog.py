import unittest
import uuid
from unittest.mock import AsyncMock, MagicMock
from decimal import Decimal
from app.services.takeaway_catalog_policy import sale_eligible

class SalesCatalogPolicyTests(unittest.TestCase):
    def allowed(self, meta=None, price="20", active=True, assigned=True):
        return sale_eligible(meta if meta is not None else {"product_type": "menu_item", "is_for_sale": True}, price, active=active, assigned=assigned)

    def test_finished_menu_and_positive_price(self):
        for kind in ("menu_item", "FINISHED_GOODS", "FG"):
            self.assertTrue(self.allowed({"item_kind": kind, "is_for_sale": True}))

    def test_raw_supply_non_sellable_and_unknown_fail_closed(self):
        for kind in ("RAW", "INGREDIENT", "PACKAGING", "raw_material", "supply", "unknown"):
            self.assertFalse(self.allowed({"item_kind": kind, "is_for_sale": True}))
        for value in (False, None, "true"):
            self.assertFalse(self.allowed({"product_type": "menu_item", "is_for_sale": value}))
        self.assertFalse(self.allowed({}))

    def test_central_only_rejected_even_with_positive_price(self):
        for extra in ({"central_only": True}, {"inventory_role": "central_raw"}, {"brand_scope": "central"}):
            self.assertFalse(self.allowed({"product_type": "menu_item", "is_for_sale": True, **extra}))

    def test_price_active_and_assignment_fail_closed(self):
        for value in ("0", "-1", "NaN", "Infinity", None, "invalid"):
            self.assertFalse(self.allowed(price=value))
        self.assertFalse(self.allowed(active=False))
        self.assertFalse(self.allowed(assigned=False))

    def test_approved_chambo_prices(self):
        from app.cli.reconcile_chambo_store_catalog import MENUS
        expected = {"ข้าวเหนียวหมูย่าง": "20", "ข้าวกล่องหมูย่าง": "40", "ข้าวหมูน้ำตก": "50", "น้ำตกหมู": "80", "หมูย่าง 1 ขีด": "35"}
        actual = {row[1]: row[2] for row in MENUS}
        self.assertTrue(expected.items() <= actual.items())
        self.assertTrue(all(Decimal(row[2]) > 0 for row in MENUS))

class CatalogScopeQueryTests(unittest.IsolatedAsyncioTestCase):
    async def test_store_query_scopes_item_and_assignment_to_company_brand_branch(self):
        from sqlalchemy.dialects import postgresql
        from app.dependencies import TokenData
        from app.services.takeaway_service import TakeawayService
        company, brand, branch = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        current = TokenData(user_id=uuid.uuid4(), company_id=company, brand_id=brand,
            branch_id=branch, business_type="takeaway", target_database="takeaway",
            client_surface="takeaway_store", permissions=["takeaway.catalog.view"])
        db = AsyncMock()
        db.execute.return_value = MagicMock(all=lambda: [])
        service = TakeawayService(db, current)
        service._validate_context = AsyncMock()
        service._sale_location_id = AsyncMock(return_value=uuid.uuid4())
        await service.list_catalog(brand)
        service._validate_context.assert_awaited_once_with(brand_id=brand, branch_id=branch)
        sql = str(db.execute.call_args.args[0].compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))
        for table in ("takeaway_catalog_items", "takeaway_branch_catalog_items"):
            self.assertIn(f"{table}.company_id = '{company}'", sql)
            self.assertIn(f"{table}.brand_id = '{brand}'", sql)
        self.assertIn(f"takeaway_branch_catalog_items.branch_id = '{branch}'", sql)
        self.assertIn("coalesce(takeaway_branch_catalog_items.is_available, false)", sql)
