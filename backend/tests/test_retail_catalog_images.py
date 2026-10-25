import unittest
import uuid
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
from starlette.datastructures import UploadFile
from app.models.product import Product, ProductImage
from app.services.retail_catalog_service import catalog_images
from app.services.retail_intake_service import intake
from tests.test_retail_intake import actor, payload


class RetailCatalogImageTests(unittest.IsolatedAsyncioTestCase):
    async def test_legacy_primary_image_then_active_variant_scoped_without_writes(self):
        company, first, second = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        db = AsyncMock()
        db.scalars.side_effect = [
            [SimpleNamespace(product_id=first, url='/uploads/primary.jpg'), SimpleNamespace(product_id=first, url='/uploads/secondary.jpg')],
            [SimpleNamespace(product_id=second, image_url='/uploads/variant.jpg')],
        ]
        self.assertEqual(await catalog_images(db, company, [first, second]),
                         {first:'/uploads/primary.jpg', second:'/uploads/variant.jpg'})
        for call in db.scalars.call_args_list:
            query = call.args[0].compile()
            self.assertIn(company, query.params.values())
            self.assertIn('company_id =', str(query))
            self.assertIn('product_id IN', str(query))
        db.commit.assert_not_called()

    async def test_no_missing_covers_means_no_query(self):
        db = AsyncMock()
        self.assertEqual(await catalog_images(db, uuid.uuid4(), []), {})
        db.scalars.assert_not_called()

    async def test_intake_sets_catalog_cover_and_retains_attachment(self):
        db = AsyncMock(); db.add = Mock()
        db.scalar.side_effect = [None, uuid.uuid4()]  # no replay receipt; valid unit
        with patch('app.services.retail_intake_service.find_code', new=AsyncMock(return_value=(None,None))), \
             patch('app.services.retail_intake_service.UploadService.save_image', new=AsyncMock(return_value='/uploads/new.jpg')):
            result = await intake(db, actor(), payload(), UploadFile(BytesIO(b'fixture'), filename='new.jpg'))
        product = next(call.args[0] for call in db.add.call_args_list if isinstance(call.args[0],Product))
        image = next(call.args[0] for call in db.add.call_args_list if isinstance(call.args[0],ProductImage))
        self.assertEqual(product.image_url, '/uploads/new.jpg')
        self.assertEqual(image.url, product.image_url)
        self.assertTrue(image.is_primary)
        self.assertEqual(result['image_url'], product.image_url)
        db.commit.assert_awaited_once()
