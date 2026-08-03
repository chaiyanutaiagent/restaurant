from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
import unittest
import uuid

from fastapi import HTTPException
from pydantic import ValidationError

from app.config import validate_saas_billing_config
from app.schemas.saas_billing import (
    SaasBillingEventImport,
    SaasInvoiceCreate,
    SaasPlanUpsert,
)
from app.services.saas_billing_service import SaasBillingService, _event_digest


class SaasBillingConfigTests(unittest.TestCase):
    def test_live_collection_is_closed_until_provider_scope_is_approved(self) -> None:
        validate_saas_billing_config(provider="unconfigured", live_charging_enabled=False)
        with self.assertRaises(ValueError):
            validate_saas_billing_config(provider=" ", live_charging_enabled=False)
        with self.assertRaises(ValueError):
            validate_saas_billing_config(provider="example", live_charging_enabled=True)


class SaasBillingSchemaTests(unittest.TestCase):
    def test_money_is_integer_satang_and_raw_payload_is_rejected(self) -> None:
        invoice = SaasInvoiceCreate(
            subtotal_satang=12500,
            tax_satang=875,
            reason="manual test invoice",
        )
        self.assertEqual(invoice.subtotal_satang + invoice.tax_satang, 13375)
        with self.assertRaises(ValidationError):
            SaasInvoiceCreate(
                subtotal_satang=12.5,
                reason="float must not pass",
            )
        with self.assertRaises(ValidationError):
            SaasBillingEventImport(
                event_key="evt-raw",
                event_type="subscription.activated",
                source="manual.import",
                company_id=uuid.uuid4(),
                occurred_at=datetime.now(timezone.utc),
                reason="reject provider payload",
                raw_payload={"card": "must-not-be-stored"},
            )

    def test_plan_limits_reject_negative_or_boolean_values(self) -> None:
        with self.assertRaises(ValidationError):
            SaasPlanUpsert(
                code="starter",
                name="Starter",
                plan_limits={"users": -1},
                reason="invalid limit",
            )
        with self.assertRaises(ValidationError):
            SaasPlanUpsert(
                code="starter",
                name="Starter",
                plan_limits={"users": True},
                reason="boolean is not an integer limit",
            )


class SaasBillingEventTests(unittest.TestCase):
    def _event(self, event_type: str, **overrides: object) -> SaasBillingEventImport:
        values: dict[str, object] = {
            "event_key": "evt-one",
            "event_type": event_type,
            "source": "manual.import",
            "company_id": uuid.UUID("00000000-0000-4000-8000-000000000001"),
            "occurred_at": datetime(2026, 8, 3, tzinfo=timezone.utc),
            "reason": "normalized event",
        }
        values.update(overrides)
        return SaasBillingEventImport(**values)

    def test_digest_is_deterministic_and_excludes_reason(self) -> None:
        first = self._event("subscription.activated", reason="first operator note")
        second = self._event("subscription.activated", reason="another operator note")
        self.assertEqual(_event_digest(first), _event_digest(second))
        self.assertEqual(len(_event_digest(first)), 64)

    def test_invoice_transition_checks_amount_currency_and_state(self) -> None:
        invoice = SimpleNamespace(
            status="open",
            currency="THB",
            total_satang=10700,
            paid_satang=0,
            paid_at=None,
        )
        subscription = SimpleNamespace(status="active", cancelled_at=None)
        paid = self._event(
            "invoice.paid",
            invoice_id=uuid.uuid4(),
            amount_satang=10700,
            currency="THB",
        )
        self.assertTrue(SaasBillingService._apply_transition(paid, subscription, invoice))
        self.assertEqual(invoice.status, "paid")
        self.assertFalse(SaasBillingService._apply_transition(paid, subscription, invoice))

        invalid = self._event("invoice.voided", invoice_id=uuid.uuid4())
        with self.assertRaises(HTTPException) as caught:
            SaasBillingService._apply_transition(invalid, subscription, invoice)
        self.assertEqual(caught.exception.status_code, 409)

    def test_cancelled_subscription_cannot_be_reactivated_by_import(self) -> None:
        subscription = SimpleNamespace(status="cancelled", cancelled_at=None)
        with self.assertRaises(HTTPException) as caught:
            SaasBillingService._apply_transition(
                self._event("subscription.activated"), subscription, None
            )
        self.assertEqual(caught.exception.status_code, 409)


if __name__ == "__main__":
    unittest.main()
