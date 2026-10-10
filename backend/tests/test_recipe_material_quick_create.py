from __future__ import annotations

import unittest
import uuid
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient
from pydantic import ValidationError
from app.config import settings
from app.database import get_db
from app.dependencies import TokenData, get_current_user
from app.main import app
from app.services.recipe_material_service import RecipeMaterialQuickCreate, material_identity


class QuickMaterialSchemaTests(unittest.TestCase):
    def test_optional_sku_and_normalized_name(self):
        row = RecipeMaterialQuickCreate(name="  หมู   สด  ", inventory_role="central_raw", idempotency_key=uuid.uuid4())
        self.assertEqual(row.name, "หมู สด")
        self.assertEqual(row.sku, "")

    def test_invalid_fields(self):
        for update in ({"name": " "}, {"cost_price": -1}, {"unit": "bag"}, {"inventory_role": "not_stocked"}):
            with self.subTest(update=update), self.assertRaises(ValidationError):
                RecipeMaterialQuickCreate(**{**dict(name="หมู", inventory_role="central_raw", idempotency_key=uuid.uuid4()), **update})

    def test_replay_identity_is_tenant_and_brand_scoped(self):
        company, brand, key = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        identity = material_identity(company, brand, key)
        self.assertEqual(identity, material_identity(company, brand, key))
        self.assertNotEqual(identity, material_identity(uuid.uuid4(), brand, key))
        self.assertNotEqual(identity, material_identity(company, uuid.uuid4(), key))


class QuickMaterialApiTests(unittest.TestCase):
    def setUp(self):
        self.company, self.actor, self.brand = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        self.permissions = ["fb.recipe.manage"]
        self.db = MagicMock()
        async def current():
            return TokenData(user_id=self.actor, company_id=self.company, branch_id=None, permissions=self.permissions, brand_id=self.brand)
        async def database():
            return self.db
        app.dependency_overrides[get_current_user] = current
        app.dependency_overrides[get_db] = database
        feature = patch("app.dependencies.TenantControlPolicy.require_feature", new_callable=AsyncMock)
        feature.start()
        self.addCleanup(feature.stop)
        self.client = TestClient(app)
        self.flag = settings.company_kitchen_writes_enabled
        self.payload = dict(name="หมู", unit="kg", inventory_role="central_raw", idempotency_key=str(uuid.uuid4()))

    def tearDown(self):
        self.client.close()
        app.dependency_overrides.clear()
        settings.company_kitchen_writes_enabled = self.flag

    def test_cashier_denied_before_service(self):
        self.permissions = ["pos.sale.create"]
        with patch("app.routers.restaurant.create_recipe_material", new_callable=AsyncMock) as service:
            response = self.client.post("/api/v1/restaurant/raw-materials/quick-create", json=self.payload)
        self.assertEqual(response.status_code, 403, response.text)
        service.assert_not_awaited()

    def test_uses_signed_company_and_no_client_company(self):
        with patch("app.routers.restaurant.create_recipe_material", new_callable=AsyncMock, return_value={"id": "new"}) as service:
            response = self.client.post("/api/v1/restaurant/raw-materials/quick-create", json={**self.payload, "company_id": str(uuid.uuid4())})
        self.assertEqual(response.status_code, 201, response.text)
        self.assertEqual(service.await_args.args[1:3], (self.company, self.actor))

    def test_shared_mapping_needs_additional_permission(self):
        with patch("app.routers.restaurant.create_recipe_material", new_callable=AsyncMock) as service:
            response = self.client.post("/api/v1/restaurant/raw-materials/quick-create", json={**self.payload, "use_company_kitchen": True})
        self.assertEqual(response.status_code, 403, response.text)
        service.assert_not_awaited()

    def test_shared_mapping_respects_existing_write_gate(self):
        self.permissions.append("company.kitchen.manage")
        settings.company_kitchen_writes_enabled = False
        with patch("app.routers.restaurant.create_recipe_material", new_callable=AsyncMock) as service:
            response = self.client.post("/api/v1/restaurant/raw-materials/quick-create", json={**self.payload, "use_company_kitchen": True})
        self.assertEqual(response.status_code, 409, response.text)
        service.assert_not_awaited()

    def test_other_brand_not_disclosed_or_created(self):
        foreign_brand = MagicMock(id=uuid.uuid4())
        with patch("app.routers.restaurant._load_brand_for_slug", new_callable=AsyncMock, return_value=foreign_brand), patch("app.routers.restaurant.create_recipe_material", new_callable=AsyncMock) as service:
            response = self.client.post("/api/v1/restaurant/central/other/raw-materials/quick-create", json=self.payload)
        self.assertEqual(response.status_code, 404, response.text)
        service.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
