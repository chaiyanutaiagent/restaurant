"""Guard tests for the deployed cash/manual-transfer policy (no provider activation)."""
from decimal import Decimal
import unittest
import uuid

from fastapi import HTTPException
from app.dependencies import TokenData
from app.routers.pos import _enforce_retail_payment_readiness
from app.schemas.pos import CreateSaleRequest
from app.services.sale_service import sale_request_hash
from app.services.pricing_service import canonical_hash


class ManualPaymentReleaseTests(unittest.TestCase):
    def setUp(self):
        self.actor = TokenData(user_id=uuid.uuid4(), company_id=uuid.uuid4(),
            brand_id=uuid.uuid4(), branch_id=uuid.uuid4(), business_type='retail_pos',
            target_database='retail_pos', permissions=['pos.sale.create'], scope_types=['branch'])

    def sale(self, method='bank_transfer', confirmed=True):
        return CreateSaleRequest(shift_id=uuid.uuid4(), location_id=uuid.uuid4(),
            items=[], payment_method=method, paid_amount=Decimal('25'),
            payments=[{'payment_method': method, 'amount': Decimal('25')}],
            manual_transfer_confirmed=confirmed)

    def test_cash_and_confirmed_transfer(self):
        for method in ('cash', 'bank_transfer'):
            _enforce_retail_payment_readiness(self.actor, self.sale(method))

    def test_unconfirmed_and_provider_methods_blocked(self):
        for payload in (self.sale(confirmed=False), self.sale('credit_card'), self.sale('promptpay'), self.sale('other')):
            with self.assertRaises(HTTPException):
                _enforce_retail_payment_readiness(self.actor, payload)

    def test_context_offline_and_mixed_tender_blocked(self):
        payload = self.sale()
        payload.is_offline = True
        with self.assertRaises(HTTPException):
            _enforce_retail_payment_readiness(self.actor, payload)
        payload.is_offline = False
        with self.assertRaises(HTTPException):
            _enforce_retail_payment_readiness(self.actor, payload, synchronized=True)
        payload.payments.append(self.sale('cash').payments[0])
        with self.assertRaises(HTTPException):
            _enforce_retail_payment_readiness(self.actor, payload)
        self.actor.branch_id = None
        with self.assertRaises(HTTPException):
            _enforce_retail_payment_readiness(self.actor, self.sale())

    def test_old_retry_hash_and_confirmation_evidence(self):
        payload = self.sale('cash', False)
        old = payload.model_dump(mode='json', exclude={'manual_transfer_confirmed', 'approval_token', 'price_override_approval_token'}, exclude_none=True)
        self.assertEqual(sale_request_hash(payload), canonical_hash(old))
        payload = self.sale(confirmed=False)
        previous = sale_request_hash(payload)
        payload.manual_transfer_confirmed = True
        self.assertNotEqual(previous, sale_request_hash(payload))
