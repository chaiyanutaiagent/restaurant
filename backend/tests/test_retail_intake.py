import unittest
import uuid
from decimal import Decimal
from unittest.mock import AsyncMock

from fastapi import HTTPException
from pydantic import ValidationError

from app.dependencies import TokenData
from app.schemas.retail_intake import RetailIntakeRequest, RetailProductBrandCreate
from app.services.retail_intake_service import attribute_key
from app.services.retail_intake_service import intake, require_retail


def actor(**changes):
    values = dict(user_id=uuid.uuid4(), company_id=uuid.uuid4(), brand_id=uuid.uuid4(),
                  branch_id=uuid.uuid4(), business_type="retail_pos", target_database="retail_pos",
                  permissions=["inventory.product.create"])
    return TokenData(**{**values, **changes})


def payload(**changes):
    return RetailIntakeRequest(**{**dict(request_id=uuid.uuid4(), barcode="0000123456789",
        name="Water", unit_id=uuid.uuid4()), **changes})


class RetailIntakeValidationTests(unittest.TestCase):
    def test_preserves_leading_zero_and_trims(self):
        self.assertEqual(payload(barcode=" 0000123456789 ").barcode, "0000123456789")

    def test_rejects_invalid_amounts_and_incomplete_stock(self):
        for changes in ({"qty":-1}, {"selling_price":"NaN"}, {"cost_price":"Infinity"},
                        {"qty":1}, {"name":" "}, {"barcode":" "}, {"unit_id":None},
                        {"existing_product_id":uuid.uuid4()}, {"vat_rate":101}):
            with self.subTest(changes=changes), self.assertRaises(ValidationError):
                payload(**changes)

    def test_zero_stock_is_allowed(self):
        self.assertEqual(payload().qty, Decimal(0))

    def test_custom_options_and_brand_normalization(self):
        request = payload(product_type="variant", attributes={" สี ":" ดำ ","ไซซ์":"M"})
        self.assertEqual(request.attributes, {"สี":"ดำ","ไซซ์":"M"})
        self.assertEqual(attribute_key({" Size ":" M "}), attribute_key({"size":"m"}))
        self.assertEqual(RetailProductBrandCreate(name="  Test   Brand ").name, "Test Brand")
        for changes in ({"product_type":"variant"}, {"attributes":{"สี":"ดำ"}},
            {"product_type":"variant","attributes":{"Size":"M"," size ":"L"}},
            {"product_type":"variant","attributes":{"สี":" "}},
            {"existing_variant_id":uuid.uuid4()},
            {"product_type":"variant","attributes":{str(i):"x" for i in range(6)}}):
            with self.subTest(changes=changes), self.assertRaises(ValidationError):
                payload(**changes)

    def test_retail_context_is_mandatory(self):
        for changes in ({"target_database":"legacy"}, {"business_type":"restaurant"},
                        {"branch_id":None}, {"brand_id":None}):
            with self.subTest(changes=changes), self.assertRaises(HTTPException):
                require_retail(actor(**changes))


class RetailIntakePermissionTests(unittest.IsolatedAsyncioTestCase):
    async def test_create_and_stock_permissions_before_database_access(self):
        db = AsyncMock()
        for current, request in ((actor(permissions=[]), payload()),
                                 (actor(), payload(qty=1, location_id=uuid.uuid4()))):
            with self.assertRaises(HTTPException) as raised:
                await intake(db, current, request)
            self.assertEqual(raised.exception.status_code, 403)
        db.execute.assert_not_awaited()

    async def test_central_only_permission_cannot_receive_retail_stock(self):
        db = AsyncMock()
        with self.assertRaises(HTTPException) as raised:
            await intake(db, actor(permissions=["inventory.product.create","brand.central.raw_stock.manage"]),
                payload(qty=1, location_id=uuid.uuid4()))
        self.assertEqual(raised.exception.status_code, 403)
        db.execute.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
