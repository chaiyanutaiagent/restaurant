from decimal import Decimal as D
from types import SimpleNamespace as NS
from unittest import TestCase
from unittest.mock import patch
from uuid import uuid4
from fastapi import HTTPException
from pydantic import ValidationError
from app.dependencies import TokenData
from app.schemas.credit_sales import CreditSaleCreate, ReceiptRequest
from app.services.credit_sales_service import check_access, fingerprint, line_amounts


class CreditSalesTests(TestCase):
    def test_server_amounts_included_excluded_exempt_and_unregistered(self):
        p = NS(selling_price=D(107), vat_rate=D(7), vat_type="included")
        self.assertEqual(line_amounts(p, D(4), True), (D(400), D(28), D(428)))
        self.assertEqual(line_amounts(p, D(4), False), (D(428), D(0), D(428)))
        p.vat_type, p.selling_price = "excluded", D(100)
        self.assertEqual(line_amounts(p, D(4), True), (D(400), D(28), D(428)))
        p.vat_type = "exempt"
        self.assertEqual(line_amounts(p, D(4), True), (D(400), D(0), D(400)))

    def test_invalid_price_fails(self):
        with self.assertRaises(HTTPException):
            line_amounts(NS(selling_price=0, vat_type="included", vat_rate=7), D(1), True)

    def test_client_cannot_send_price_or_totals(self):
        with self.assertRaises(ValidationError):
            CreditSaleCreate(request_key=uuid4(), customer_id=uuid4(), description="test", due_date="2026-12-31",
                items=[{"product_id": uuid4(), "quantity": 1, "unit_price": "0.01"}])

    def test_receipt_rejects_zero_fractional_cents_and_blank_evidence(self):
        for changes in ({"amount": "0"}, {"amount": "1.001"}, {"reference": " "}):
            data = dict(request_key=uuid4(), reason="test", amount="1", method="cash", reference="test-1")
            data.update(changes)
            with self.assertRaises(ValidationError): ReceiptRequest(**data)

    def test_scope_permission_and_production_guard(self):
        current = TokenData(user_id=uuid4(), company_id=uuid4(), branch_id=uuid4(), permissions=["*"])
        with patch("app.services.credit_sales_service.settings", NS(environment="development", saas_public_base_url="https://uat-app.foodchainservice.com")):
            check_access(current)
            current.station_key = "counter"
            with self.assertRaises(HTTPException): check_access(current)
            current.station_key, current.permissions = None, []
            with self.assertRaises(HTTPException): check_access(current)
        current.permissions = ["*"]
        with patch("app.services.credit_sales_service.settings", NS(environment="production", saas_public_base_url="https://uat-app.foodchainservice.com")):
            with self.assertRaises(HTTPException): check_access(current)

    def test_fingerprint_order_independent_and_amount_sensitive(self):
        self.assertEqual(fingerprint({"x": 1, "y": 2}), fingerprint({"y": 2, "x": 1}))
        self.assertNotEqual(fingerprint({"amount": "1"}), fingerprint({"amount": "2"}))
