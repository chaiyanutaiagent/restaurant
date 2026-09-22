from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
import logging
import unittest
import uuid
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException
from pydantic import ValidationError
from starlette.requests import Request

from app.models.api_integration import APIKey, WebhookDelivery, WebhookEndpoint
from app.models.product import Product
from app.schemas.api_integration import APIKeyCreate, PublicOrderCreate
from app.services.company_governance_service import CompanyGovernanceService, coverage_matrix
from app.services.external_order_validation_service import validate_external_order
from app.utils.api_key_auth import get_api_key_auth, verify_api_key
from app.utils.access_log_redaction import AccessLogSecretFilter, redact_access_path
from app.utils.integration_security import (
    decrypt_integration_secret,
    encrypt_integration_secret,
    verify_webhook_timestamp,
    webhook_signature,
)
from app.utils.webhook_dispatcher import MAX_WEBHOOK_ATTEMPTS, dispatch_webhook


class _ScalarResult:
    def __init__(self, values):
        self.values = values

    def all(self):
        return self.values


class _ProductDb:
    def __init__(self, products):
        self.products = products

    async def scalars(self, _statement):
        return _ScalarResult(self.products)


class IntegrationSecurityTests(unittest.TestCase):
    def test_access_log_redacts_rejected_query_credentials(self) -> None:
        raw = "/api/public/v1/products?limit=1&api_key=erppos_ABCDEF12_sensitive&token=also-sensitive"
        redacted = redact_access_path(raw)
        self.assertNotIn("sensitive", redacted)
        self.assertEqual(redacted.count("[REDACTED]"), 2)
        record = logging.LogRecord(
            "uvicorn.access",
            logging.INFO,
            __file__,
            1,
            '%s - "%s %s HTTP/%s" %d',
            ("127.0.0.1:1", "GET", raw, "1.1", 401),
            None,
        )
        self.assertTrue(AccessLogSecretFilter().filter(record))
        self.assertNotIn("sensitive", str(record.args))

    def test_secret_is_encrypted_and_plaintext_fails_closed(self) -> None:
        secret = "s" * 40
        ciphertext = encrypt_integration_secret(secret)
        self.assertNotIn(secret, ciphertext)
        self.assertEqual(decrypt_integration_secret(ciphertext), secret)
        with self.assertRaises(ValueError):
            decrypt_integration_secret(secret)

    def test_signature_binds_timestamp_and_replay_window(self) -> None:
        body = b'{"order":"A"}'
        first = webhook_signature("s" * 40, 100, body)
        second = webhook_signature("s" * 40, 101, body)
        self.assertNotEqual(first, second)
        now = datetime.now(timezone.utc)
        self.assertEqual(verify_webhook_timestamp(str(int(now.timestamp())), now=now), int(now.timestamp()))
        with self.assertRaises(ValueError):
            verify_webhook_timestamp(str(int((now - timedelta(minutes=6)).timestamp())), now=now)

    def test_api_key_contract_requires_owner_expiry_and_explicit_scope(self) -> None:
        future = datetime.now(timezone.utc) + timedelta(days=30)
        with self.assertRaises(ValidationError):
            APIKeyCreate(name="unsafe", purpose="sync", owner_contact="ops@example.com", scopes=["*"], expires_at=future)
        valid = APIKeyCreate(name="safe", purpose="catalog sync", owner_contact="ops@example.com", scopes=["products:read"], expires_at=future)
        self.assertEqual(valid.scopes, ["products:read"])


class APIKeyTransportTests(unittest.IsolatedAsyncioTestCase):
    async def test_query_parameter_is_not_accepted_as_credential(self) -> None:
        request = Request({"type": "http", "method": "GET", "path": "/", "query_string": b"api_key=leaked", "headers": []})
        with self.assertRaises(HTTPException) as raised:
            await get_api_key_auth(request, AsyncMock())
        self.assertEqual(raised.exception.status_code, 401)

    async def test_legacy_unowned_or_non_expiring_key_fails_closed(self) -> None:
        legacy = APIKey(
            id=uuid.uuid4(),
            company_id=uuid.uuid4(),
            name="legacy",
            purpose="integration",
            owner_contact="unassigned",
            key_prefix="ABCDEF12",
            key_hash="hash",
            scopes=["products:read"],
            is_active=True,
            expires_at=None,
            created_by=uuid.uuid4(),
        )
        db = AsyncMock()
        db.scalars.return_value = _ScalarResult([legacy])
        with patch("app.utils.api_key_auth.verify_password", return_value=True):
            self.assertIsNone(await verify_api_key("erppos_ABCDEF12_value", db))


class ExternalOrderAuthorityTests(unittest.IsolatedAsyncioTestCase):
    async def test_client_price_and_total_are_never_authoritative(self) -> None:
        company_id = uuid.uuid4()
        product = Product(
            id=uuid.uuid4(), company_id=company_id, sku="WP65-ITEM", name="WP65",
            selling_price=Decimal("125"), cost_price=Decimal("50"), vat_type="included",
            vat_rate=Decimal("7"), is_active=True, is_for_sale=True, is_for_purchase=True,
        )
        payload = PublicOrderCreate(
            external_order_id="EXT-65", items=[{"sku": "WP65-ITEM", "qty": 2, "unit_price": 1}],
            total_amount=Decimal("2"), payment_status="paid",
        )
        items, server_total, reasons = await validate_external_order(_ProductDb([product]), company_id, payload)  # type: ignore[arg-type]
        self.assertEqual(server_total, Decimal("250.00"))
        self.assertEqual(items[0]["server_unit_price"], "125.00")
        self.assertIn("price_mismatch:WP65-ITEM", reasons)
        self.assertIn("total_mismatch", reasons)


class WebhookDeliveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_unencrypted_secret_goes_directly_to_dead_letter(self) -> None:
        endpoint = WebhookEndpoint(
            id=uuid.uuid4(), company_id=uuid.uuid4(), name="legacy", url="https://example.invalid",
            events=["test"], secret_ciphertext="legacy-plaintext-secret", is_active=True, failure_count=0,
        )
        delivery = WebhookDelivery(
            id=uuid.uuid4(), webhook_id=endpoint.id, company_id=endpoint.company_id,
            event_type="test", payload={}, status="pending", attempt_count=0,
        )
        result = await dispatch_webhook(delivery, endpoint, AsyncMock())
        self.assertFalse(result)
        self.assertEqual(delivery.status, "dead_letter")
        self.assertIsNone(delivery.next_retry_at)

    async def test_retry_is_bounded_at_five_attempts(self) -> None:
        endpoint = WebhookEndpoint(
            id=uuid.uuid4(), company_id=uuid.uuid4(), name="safe", url="https://example.invalid",
            events=["test"], secret_ciphertext=encrypt_integration_secret("s" * 40), is_active=True, failure_count=0,
        )
        delivery = WebhookDelivery(
            id=uuid.uuid4(), webhook_id=endpoint.id, company_id=endpoint.company_id,
            event_type="test", payload={}, status="retry_scheduled", attempt_count=MAX_WEBHOOK_ATTEMPTS - 1,
        )
        with patch("app.utils.webhook_dispatcher.httpx.AsyncClient") as client:
            client.return_value.__aenter__.return_value.post = AsyncMock(side_effect=Exception("network down"))
            result = await dispatch_webhook(delivery, endpoint, AsyncMock())
        self.assertFalse(result)
        self.assertEqual(delivery.attempt_count, MAX_WEBHOOK_ATTEMPTS)
        self.assertEqual(delivery.status, "dead_letter")


class GovernanceContractTests(unittest.TestCase):
    def test_coverage_has_all_non_hotel_domains(self) -> None:
        coverage = coverage_matrix()
        self.assertEqual(len(coverage), 10)
        self.assertEqual({item.key for item in coverage}, {"platform", "company", "erp", "restaurant", "retail", "takeaway", "kitchen", "supply_chain", "public", "integration_reporting"})

    def test_production_and_owner_decisions_remain_hold(self) -> None:
        gates = CompanyGovernanceService._release_gates(physical_approved=False, tax_blockers=0)
        by_key = {gate.key: gate for gate in gates}
        self.assertEqual(by_key["production"].state, "hold")
        self.assertEqual(by_key["retention_policy"].state, "planned")
        self.assertEqual(by_key["physical_devices"].state, "hold")


if __name__ == "__main__":
    unittest.main()
