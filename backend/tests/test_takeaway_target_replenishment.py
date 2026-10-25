from datetime import date
from decimal import Decimal as D
from types import SimpleNamespace as NS
import unittest
import uuid
from unittest.mock import AsyncMock

from fastapi import HTTPException
from pydantic import ValidationError
from app.dependencies import TokenData
from app.schemas.takeaway import TakeawayReplenishmentPolicyUpsert, TakeawayReplenishmentGenerate, TakeawayStoreCentralOrderCreate
from app.services.takeaway_central_policy import target_replenishment_state
from app.services.takeaway_service import TakeawayService
from app.services.mobile_store_policy import enforce_store_request


class TargetPolicyTests(unittest.TestCase):
    def test_boundary_and_refill_to_fixed_target(self):
        for stock, alert, qty in [('100', False, '0'), ('70', False, '0'),
                ('30.0001', False, '0'), ('30', True, '70'), ('29', True, '71'), ('0', True, '100')]:
            with self.subTest(stock=stock):
                result = target_replenishment_state(target_stock_qty=D('100'), on_hand_qty=D(stock))
                self.assertEqual(result['is_low_stock'], alert)
                self.assertEqual(result['suggested_qty'], D(qty))
                self.assertEqual(result['reorder_threshold_qty'], D('30'))

    def test_raw_material_decimal_units_and_minimum_pack(self):
        result = target_replenishment_state(target_stock_qty=D('10'), on_hand_qty=D('3'),
            pack_size=D('2'), minimum_order_qty=D('9'))
        self.assertTrue(result['is_low_stock'])
        self.assertEqual(result['suggested_qty'], D('10'))
        self.assertFalse(target_replenishment_state(target_stock_qty=D('0.0001'),
            on_hand_qty=D('0.0001'))['is_low_stock'])

    def test_missing_target_does_not_guess_or_order(self):
        for target in (None, D('0')):
            result = target_replenishment_state(target_stock_qty=target, on_hand_qty=D('0'))
            self.assertFalse(result['is_low_stock'])
            self.assertFalse(result['target_configured'])
            self.assertEqual(result['suggested_qty'], 0)

    def test_incoming_prevents_duplicate_replenishment_not_warning(self):
        for incoming, quantity in [('20', '50'), ('70', '0'), ('120', '0')]:
            result = target_replenishment_state(target_stock_qty=D('100'), on_hand_qty=D('30'),
                confirmed_incoming_qty=D(incoming))
            self.assertTrue(result['is_low_stock'])
            self.assertEqual(result['suggested_qty'], D(quantity))

    def test_schema_rejects_zero_negative_and_excess_precision(self):
        scope = dict(brand_id=uuid.uuid4(), branch_id=uuid.uuid4(), item_id=uuid.uuid4())
        for quantity in ('0', '-1', '0.00001'):
            with self.assertRaises(ValidationError):
                TakeawayReplenishmentPolicyUpsert(**scope, target_stock_qty=quantity)
        self.assertNotIn('target_stock_qty', TakeawayReplenishmentPolicyUpsert(**scope).model_fields_set)

    def test_mobile_can_read_suggestions_not_modify_policy(self):
        payload = dict(client_surface='takeaway_store', company_id='a', branch_id='b', store_device_id='d')
        headers = {'x-company-id': 'a', 'x-branch-id': 'b', 'x-store-device-id': 'd'}
        enforce_store_request(payload, 'GET', '/api/v1/takeaway/replenishment/suggestions', headers)
        with self.assertRaises(HTTPException):
            enforce_store_request(payload, 'PUT', '/api/v1/takeaway/replenishment/policies', headers)


class TargetServiceTests(unittest.IsolatedAsyncioTestCase):
    def service(self):
        db = AsyncMock()
        current = TokenData(user_id=uuid.uuid4(), company_id=uuid.uuid4(),
            brand_id=uuid.uuid4(), branch_id=uuid.uuid4(), permissions=['*'],
            business_type='takeaway', target_database='takeaway')
        service = TakeawayService(db, current)
        service._validate_context = AsyncMock()
        return service, db, current

    async def test_suggestions_use_target_not_high_sales_forecast(self):
        service, db, current = self.service()
        item_id = uuid.uuid4()
        policy = NS(id=uuid.uuid4(), item_id=item_id, target_stock_qty=D('100'),
            pack_size=D('1'), minimum_order_qty=D('0'))
        db.scalars.side_effect = [[policy], [uuid.uuid4()],
            [NS(id=item_id, sku='RAW-01', name='วัตถุดิบ', unit='kg')]]
        db.execute.side_effect = [NS(all=lambda: [(item_id, D('7000'))]),
            NS(all=lambda: [(item_id, D('31'))]), NS(all=lambda: [])]
        rows = await service.replenishment_suggestions(brand_id=current.brand_id, branch_id=current.branch_id)
        self.assertFalse(rows[0]['is_low_stock'])
        self.assertEqual(rows[0]['suggested_qty'], 0)

    async def test_stock_alert_is_based_on_branch_total_not_single_lot(self):
        service, db, current = self.service()
        item_id, location = uuid.uuid4(), uuid.uuid4()
        lots = [NS(id=uuid.uuid4(), item_id=item_id, location_id=location, on_hand_qty=D('1'))]
        db.scalars.side_effect = [lots, [location]]
        service.replenishment_suggestions = AsyncMock(return_value=[dict(item_id=item_id,
            on_hand_qty=D('50'), is_low_stock=False, target_stock_qty=D('100'), reorder_threshold_qty=D('30'))])
        result = await service.list_stock(location_id=location)
        self.assertFalse(result[0].is_low_stock)
        self.assertEqual(result[0].store_on_hand_qty, D('50'))

    async def test_automatic_order_excludes_above_threshold_and_missing_targets(self):
        service, _, _ = self.service()
        service.replenishment_suggestions = AsyncMock(return_value=[dict(suggested_qty=D('0'))])
        service.create_central_round = AsyncMock()
        with self.assertRaises(HTTPException) as error:
            await service.generate_replenishment_order(TakeawayReplenishmentGenerate(
                business_date=date.today(), idempotency_key='test-target-policy'))
        self.assertEqual(error.exception.status_code, 409)
        service.create_central_round.assert_not_called()

    async def test_manual_order_does_not_require_low_stock(self):
        service, _, _ = self.service()
        service.replenishment_suggestions = AsyncMock(side_effect=AssertionError('Manual order must not check threshold'))
        service.create_central_round = AsyncMock(return_value=NS(id=uuid.uuid4(), status='open'))
        service.create_central_order = AsyncMock(return_value='manual-order')
        result = await service.create_store_central_order(TakeawayStoreCentralOrderCreate(
            business_date=date.today(), order_type='extra', idempotency_key='manual-high-stock',
            items=[dict(catalog_item_id=uuid.uuid4(), sku='RAW-01', item_name='สินค้า',
                        quantity='5', unit='kg', source_kind='catalog')]))
        self.assertEqual(result, 'manual-order')
        service.replenishment_suggestions.assert_not_called()


if __name__ == '__main__':
    unittest.main()
