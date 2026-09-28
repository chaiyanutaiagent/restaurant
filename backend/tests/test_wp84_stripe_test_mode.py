from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import hmac
import json
from types import SimpleNamespace
import unittest
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import HTTPException

from app.config import settings, stripe_pos_test_context_enabled, validate_stripe_test_mode_config
from app.routers.payment_gateway import _stripe_operational_session_factory
from app.services.payment_gateway_service import PaymentGatewayService
from app.services.saas_billing_service import SaasBillingService
from app.services.saas_stripe_test_service import SaasStripeTestService
from app.services.stripe_test_gateway import (
    StripePromptPayIntent,
    StripeTestClient,
    baht_to_satang,
    verify_stripe_webhook,
)


WEBHOOK_SECRET = "whsec_test_webhook_secret"


def signed(payload: bytes, timestamp: int) -> str:
    digest = hmac.new(
        WEBHOOK_SECRET.encode(),
        f"{timestamp}.".encode() + payload,
        hashlib.sha256,
    ).hexdigest()
    return f"t={timestamp},v1={digest}"


class StripeContractTests(unittest.TestCase):
    def test_test_mode_config_is_closed_in_production_and_requires_test_secrets(self) -> None:
        validate_stripe_test_mode_config(
            environment="development",
            mode="disabled",
            secret_key=None,
            webhook_secret=None,
            scope="POS",
        )
        validate_stripe_test_mode_config(
            environment="development",
            mode="test",
            secret_key="sk_test_example",
            webhook_secret=WEBHOOK_SECRET,
            scope="POS",
            provider_account_id="acct_pos_test",
            company_allowlist=str(uuid.uuid4()),
            branch_allowlist=str(uuid.uuid4()),
        )
        with self.assertRaises(ValueError):
            validate_stripe_test_mode_config(
                environment="production",
                mode="test",
                secret_key="sk_test_example",
                webhook_secret=WEBHOOK_SECRET,
                scope="POS",
                provider_account_id="acct_pos_test",
                company_allowlist=str(uuid.uuid4()),
                branch_allowlist=str(uuid.uuid4()),
            )
        with self.assertRaises(ValueError):
            validate_stripe_test_mode_config(
                environment="development",
                mode="test",
                secret_key="sk_live_forbidden",
                webhook_secret=WEBHOOK_SECRET,
                scope="POS",
                provider_account_id="acct_pos_test",
                company_allowlist=str(uuid.uuid4()),
                branch_allowlist=str(uuid.uuid4()),
            )

    def test_webhook_signature_checks_raw_payload_tampering_and_timestamp(self) -> None:
        event = {"id": "evt_test", "type": "payment_intent.succeeded", "data": {"object": {}}}
        payload = json.dumps(event, separators=(",", ":")).encode()
        parsed = verify_stripe_webhook(
            payload,
            signed(payload, 1_000),
            WEBHOOK_SECRET,
            now=1_000,
        )
        self.assertEqual(parsed["id"], "evt_test")
        with self.assertRaises(HTTPException):
            verify_stripe_webhook(
                payload + b" ",
                signed(payload, 1_000),
                WEBHOOK_SECRET,
                now=1_000,
            )
        with self.assertRaises(HTTPException):
            verify_stripe_webhook(
                payload,
                signed(payload, 1_000),
                WEBHOOK_SECRET,
                now=1_301,
                tolerance_seconds=300,
            )

    def test_amount_and_provider_response_are_server_authoritative(self) -> None:
        self.assertEqual(baht_to_satang(Decimal("107.00")), 10_700)
        with self.assertRaises(HTTPException):
            baht_to_satang(Decimal("0"))
        intent = StripeTestClient._parse_promptpay_intent(
            {
                "id": "pi_test",
                "livemode": False,
                "status": "requires_action",
                "amount": 10_700,
                "currency": "thb",
                "next_action": {
                    "promptpay_display_qr_code": {
                        "data": "000201-test",
                        "hosted_instructions_url": "https://payments.stripe.test/qr",
                        "expires_at": 1_800_000_000,
                    }
                },
            },
            expected_amount=10_700,
        )
        self.assertEqual(intent.qr_payload, "000201-test")
        with self.assertRaises(HTTPException):
            StripeTestClient._parse_promptpay_intent(
                {"id": "pi_test", "livemode": False, "amount": 10_699, "currency": "thb"},
                expected_amount=10_700,
            )

    def test_provider_response_requires_explicit_test_mode_and_qr_instructions(self) -> None:
        with self.assertRaises(HTTPException):
            StripeTestClient._parse_promptpay_intent(
                {"id": "pi_test", "amount": 10_700, "currency": "thb"},
                expected_amount=10_700,
            )

    def test_pos_test_context_is_exact_company_and_branch_allowlist(self) -> None:
        company_id = uuid.uuid4()
        branch_id = uuid.uuid4()
        self.assertTrue(
            stripe_pos_test_context_enabled(
                mode="test",
                company_allowlist=str(company_id),
                branch_allowlist=str(branch_id),
                company_id=company_id,
                branch_id=branch_id,
            )
        )
        self.assertFalse(
            stripe_pos_test_context_enabled(
                mode="test",
                company_allowlist=str(company_id),
                branch_allowlist=str(branch_id),
                company_id=company_id,
                branch_id=uuid.uuid4(),
            )
        )
        with self.assertRaises(HTTPException):
            StripeTestClient._parse_promptpay_intent(
                {
                    "id": "pi_test",
                    "livemode": False,
                    "status": "requires_action",
                    "amount": 10_700,
                    "currency": "thb",
                },
                expected_amount=10_700,
            )


class StripePosWebhookTests(unittest.IsolatedAsyncioTestCase):
    async def test_pos_creation_is_bound_to_server_order_and_idempotency_key(self) -> None:
        company_id = uuid.uuid4()
        branch_id = uuid.uuid4()
        order_id = uuid.uuid4()
        branch = SimpleNamespace(id=branch_id, company_id=company_id)
        order = SimpleNamespace(
            id=order_id,
            company_id=company_id,
            branch_id=branch_id,
            total_amount=Decimal("107.00"),
            paid_amount=Decimal("0.00"),
            status="pending_payment",
        )
        db = AsyncMock()
        db.scalar.side_effect = [branch, order, None, 0, None]
        provider_result = StripePromptPayIntent(
            id="pi_test_pos",
            status="requires_action",
            amount_satang=10_700,
            currency="THB",
            qr_payload="000201-pos",
            hosted_instructions_url=None,
            expires_at=None,
        )
        stored = SimpleNamespace(id=uuid.uuid4())
        service = PaymentGatewayService(db)
        service._create_session = AsyncMock(return_value=stored)
        with (
            patch.object(settings, "stripe_pos_mode", "test"),
            patch.object(settings, "stripe_pos_secret_key", "sk_test_pos"),
            patch.object(settings, "stripe_pos_account_id", "acct_pos_test"),
            patch.object(settings, "stripe_pos_company_allowlist", str(company_id)),
            patch.object(settings, "stripe_pos_branch_allowlist", str(branch_id)),
            patch.object(StripeTestClient, "create_promptpay_intent", AsyncMock(return_value=provider_result)) as create,
        ):
            result = await service.create_promptpay_session(
                company_id,
                branch_id,
                Decimal("107.00"),
                "SaleOrder",
                str(order_id),
                uuid.uuid4(),
                "checkout:order-001",
                "retail_pos",
            )
        self.assertIs(result, stored)
        self.assertEqual(create.await_args.kwargs["amount_satang"], 10_700)
        self.assertEqual(create.await_args.kwargs["metadata"]["company_id"], str(company_id))
        self.assertEqual(create.await_args.kwargs["metadata"]["target_database"], "retail_pos")
        self.assertEqual(create.await_args.kwargs["metadata"]["attempt_no"], "1")
        self.assertEqual(
            service._create_session.await_args.kwargs["session_ref"],
            create.await_args.kwargs["metadata"]["session_ref"],
        )
        self.assertEqual(service._create_session.await_args.kwargs["provider_account_id"], "acct_pos_test")
        self.assertEqual(
            service._create_session.await_args.kwargs["gateway_payload"]["target_database"],
            "retail_pos",
        )

    def test_webhook_database_routing_rejects_unsigned_boundary_names(self) -> None:
        with self.assertRaises(HTTPException) as caught:
            _stripe_operational_session_factory("platform")
        self.assertEqual(caught.exception.status_code, 422)

    async def test_manual_confirmation_cannot_bypass_stripe_webhook(self) -> None:
        session = SimpleNamespace(gateway="stripe_promptpay")
        service = PaymentGatewayService(AsyncMock())
        service.get_session = AsyncMock(return_value=session)
        with self.assertRaises(HTTPException) as caught:
            await service.confirm_payment(uuid.uuid4(), uuid.uuid4())
        self.assertEqual(caught.exception.status_code, 409)

    async def test_stripe_session_rejects_sale_already_completed_by_local_qr_path(self) -> None:
        company_id = uuid.uuid4()
        branch_id = uuid.uuid4()
        order_id = uuid.uuid4()
        db = AsyncMock()
        db.scalar.side_effect = [
            SimpleNamespace(id=branch_id, company_id=company_id),
            SimpleNamespace(
                id=order_id,
                company_id=company_id,
                branch_id=branch_id,
                total_amount=Decimal("107.00"),
                paid_amount=Decimal("107.00"),
                status="completed",
            ),
        ]
        with (
            patch.object(settings, "stripe_pos_mode", "test"),
            patch.object(settings, "stripe_pos_company_allowlist", str(company_id)),
            patch.object(settings, "stripe_pos_branch_allowlist", str(branch_id)),
        ):
            with self.assertRaises(HTTPException) as caught:
                await PaymentGatewayService(db).create_promptpay_session(
                    company_id,
                    branch_id,
                    Decimal("107.00"),
                    "SaleOrder",
                    str(order_id),
                    uuid.uuid4(),
                    "checkout:local-bypass",
                )
        self.assertEqual(caught.exception.status_code, 409)

    async def test_pos_webhook_rejects_provider_account_mismatch(self) -> None:
        company_id = uuid.uuid4()
        branch_id = uuid.uuid4()
        session = SimpleNamespace(
            id=uuid.uuid4(),
            company_id=company_id,
            branch_id=branch_id,
            session_ref="PS-ACCOUNT",
            gateway="stripe_promptpay",
            gateway_ref="pi_account",
            gateway_payload={"connected_account": True},
            provider_account_id="acct_expected",
            provider_mode="test",
        )
        db = AsyncMock()
        db.scalar.return_value = session
        event = {
            "id": "evt_account",
            "livemode": False,
            "account": "acct_wrong",
            "type": "payment_intent.processing",
            "data": {"object": {"id": "pi_account"}},
        }
        with self.assertRaises(HTTPException) as caught:
            await PaymentGatewayService(db).handle_stripe_promptpay_event(
                event,
                payload_sha256="payload-account",
            )
        self.assertEqual(caught.exception.status_code, 422)

    async def test_verified_payment_intent_completes_once_and_cannot_regress(self) -> None:
        company_id = uuid.uuid4()
        branch_id = uuid.uuid4()
        session = SimpleNamespace(
            id=uuid.uuid4(),
            company_id=company_id,
            branch_id=branch_id,
            session_ref="PS-TEST",
            gateway="stripe_promptpay",
            gateway_ref="pi_test_pos",
            gateway_status="requires_action",
            gateway_payload={
                "provider": "stripe",
                "mode": "test",
                "connected_account": False,
                "target_database": "retail_pos",
                "attempt_no": 1,
            },
            provider_account_id="acct_pos_test",
            provider_mode="test",
            amount=Decimal("107.00"),
            currency="THB",
            status="pending",
            completed_at=None,
            failed_at=None,
            reference_type="SaleOrder",
            reference_id=str(uuid.uuid4()),
        )
        receipt = SimpleNamespace(payload_sha256="payload-a", result_status="processing", processed_at=None)
        db = AsyncMock()
        db.scalar.side_effect = [session, session, receipt, session]
        inserted = MagicMock()
        inserted.scalar_one_or_none.return_value = uuid.uuid4()
        duplicate = MagicMock()
        duplicate.scalar_one_or_none.return_value = None
        inserted_late = MagicMock()
        inserted_late.scalar_one_or_none.return_value = uuid.uuid4()
        db.execute.side_effect = [inserted, duplicate, inserted_late]
        db.get.return_value = receipt
        service = PaymentGatewayService(db)
        service.get_session = AsyncMock(return_value=session)
        event = {
            "id": "evt_pos_paid",
            "livemode": False,
            "type": "payment_intent.succeeded",
            "data": {
                "object": {
                    "id": "pi_test_pos",
                    "status": "succeeded",
                    "amount": 10_700,
                    "amount_received": 10_700,
                    "currency": "thb",
                    "metadata": {
                        "context": "pos",
                        "company_id": str(company_id),
                        "branch_id": str(branch_id),
                        "session_ref": "PS-TEST",
                        "reference_type": "SaleOrder",
                        "reference_id": session.reference_id,
                        "target_database": "retail_pos",
                        "attempt_no": "1",
                    },
                }
            },
        }
        completed_order = SimpleNamespace(user_id=uuid.uuid4())
        with (
            patch("app.services.sale_service.SaleService.finalize_pending_provider_sale", AsyncMock(return_value=completed_order)) as finalize,
            patch("app.services.sale_service.SaleService._ensure_accounting_handoff", AsyncMock()) as accounting,
        ):
            result = await service.handle_stripe_promptpay_event(event, payload_sha256="payload-a")
        self.assertIs(result, session)
        self.assertEqual(session.status, "completed")
        finalize.assert_awaited_once()
        accounting.assert_awaited_once()
        db.commit.assert_awaited_once()

        db.commit.reset_mock()
        duplicate_result = await service.handle_stripe_promptpay_event(event, payload_sha256="payload-a")
        self.assertIs(duplicate_result, session)
        db.commit.assert_not_awaited()

        event["id"] = "evt_pos_late_failure"
        event["type"] = "payment_intent.payment_failed"
        event["data"]["object"]["status"] = "requires_payment_method"
        await service.handle_stripe_promptpay_event(event, payload_sha256="payload-b")
        self.assertEqual(session.status, "completed")


class SaasStripeTestModeTests(unittest.IsolatedAsyncioTestCase):
    async def test_saas_invoice_session_uses_separate_test_account_and_idempotency(self) -> None:
        company_id = uuid.uuid4()
        subscription_id = uuid.uuid4()
        invoice = SimpleNamespace(
            id=uuid.uuid4(),
            company_id=company_id,
            subscription_id=subscription_id,
            invoice_number="SINV-TEST-1",
            status="open",
            currency="THB",
            total_satang=10_700,
        )
        subscription = SimpleNamespace(id=subscription_id, company_id=company_id)
        db = AsyncMock()
        db.add = MagicMock()
        async def assign_attempt_id(attempt: object) -> None:
            attempt.id = uuid.uuid4()
        db.refresh.side_effect = assign_attempt_id
        db.scalar.side_effect = [invoice, subscription, None, 0]
        provider_result = StripePromptPayIntent(
            id="pi_test_saas",
            status="requires_action",
            amount_satang=10_700,
            currency="THB",
            qr_payload="000201-saas",
            hosted_instructions_url=None,
            expires_at=None,
        )
        with (
            patch.object(settings, "saas_stripe_mode", "test"),
            patch.object(settings, "saas_billing_provider", "stripe_test"),
            patch.object(settings, "saas_billing_live_charging_enabled", False),
            patch.object(settings, "saas_stripe_secret_key", "sk_test_saas"),
            patch.object(settings, "saas_stripe_account_id", "acct_saas_test"),
            patch.object(StripeTestClient, "create_promptpay_intent", AsyncMock(return_value=provider_result)) as create,
        ):
            result = await SaasStripeTestService(db).create_invoice_promptpay_session(
                company_id=company_id,
                invoice_id=invoice.id,
            )
        self.assertEqual(result.payment_intent_id, "pi_test_saas")
        self.assertEqual(result.amount_satang, 10_700)
        self.assertIn(str(invoice.id), create.await_args.kwargs["idempotency_key"])
        self.assertEqual(create.await_args.kwargs["metadata"]["context"], "saas_billing")
        db.commit.assert_awaited_once()

    async def test_expired_saas_attempt_creates_a_new_attempt(self) -> None:
        company_id = uuid.uuid4()
        subscription_id = uuid.uuid4()
        invoice = SimpleNamespace(
            id=uuid.uuid4(),
            company_id=company_id,
            subscription_id=subscription_id,
            invoice_number="SINV-TEST-EXPIRED",
            status="open",
            currency="THB",
            total_satang=10_700,
        )
        subscription = SimpleNamespace(id=subscription_id, company_id=company_id)
        expired = SimpleNamespace(
            attempt_no=1,
            expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
            status="requires_action",
        )
        db = AsyncMock()
        db.add = MagicMock()
        async def assign_attempt_id(attempt: object) -> None:
            attempt.id = uuid.uuid4()
        db.refresh.side_effect = assign_attempt_id
        db.scalar.side_effect = [invoice, subscription, expired, 1]
        provider_result = StripePromptPayIntent(
            id="pi_test_saas_retry",
            status="requires_action",
            amount_satang=10_700,
            currency="THB",
            qr_payload="000201-saas-retry",
            hosted_instructions_url=None,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
        )
        with (
            patch.object(settings, "saas_stripe_mode", "test"),
            patch.object(settings, "saas_billing_provider", "stripe_test"),
            patch.object(settings, "saas_billing_live_charging_enabled", False),
            patch.object(settings, "saas_stripe_secret_key", "sk_test_saas"),
            patch.object(settings, "saas_stripe_account_id", "acct_saas_test"),
            patch.object(StripeTestClient, "create_promptpay_intent", AsyncMock(return_value=provider_result)) as create,
        ):
            result = await SaasStripeTestService(db).create_invoice_promptpay_session(
                company_id=company_id,
                invoice_id=invoice.id,
            )
        self.assertEqual(expired.status, "expired")
        self.assertEqual(result.attempt_no, 2)
        self.assertIn("-2-", create.await_args.kwargs["idempotency_key"])

    async def test_paid_saas_webhook_applies_invoice_then_subscription(self) -> None:
        company_id = uuid.uuid4()
        subscription_id = uuid.uuid4()
        invoice_id = uuid.uuid4()
        invoice = SimpleNamespace(
            id=invoice_id,
            company_id=company_id,
            subscription_id=subscription_id,
            total_satang=10_700,
            currency="THB",
        )
        attempt = SimpleNamespace(
            id=uuid.uuid4(),
            company_id=company_id,
            subscription_id=subscription_id,
            invoice_id=invoice_id,
            provider_mode="test",
            provider_account_id="acct_saas_test",
            provider_payment_intent_id="pi_test_saas",
            amount_satang=10_700,
            currency="THB",
            status="requires_action",
            completed_at=None,
        )
        db = AsyncMock()
        db.scalar.side_effect = [attempt, invoice]
        applied_invoice = SimpleNamespace(id=uuid.uuid4())
        applied_subscription = SimpleNamespace(id=uuid.uuid4())
        event = {
            "id": "evt_saas_paid",
            "livemode": False,
            "type": "payment_intent.succeeded",
            "created": 1_800_000_000,
            "data": {
                "object": {
                    "id": "pi_test_saas",
                    "amount": 10_700,
                    "amount_received": 10_700,
                    "currency": "thb",
                    "metadata": {
                        "context": "saas_billing",
                        "company_id": str(company_id),
                        "internal_invoice_id": str(invoice_id),
                        "internal_subscription_id": str(subscription_id),
                    },
                }
            },
        }
        with (
            patch.object(settings, "saas_stripe_mode", "test"),
            patch.object(settings, "saas_billing_provider", "stripe_test"),
            patch.object(settings, "saas_billing_live_charging_enabled", False),
            patch.object(settings, "saas_stripe_account_id", "acct_saas_test"),
            patch.object(
                SaasBillingService,
                "apply_event",
                AsyncMock(side_effect=[applied_invoice, applied_subscription]),
            ) as apply_event,
        ):
            result = await SaasStripeTestService(db).apply_webhook_event(
                event,
                ip_address="127.0.0.1",
                user_agent="test",
            )
        self.assertEqual(result, [applied_invoice, applied_subscription])
        self.assertEqual(apply_event.await_count, 2)
        invoice_event = apply_event.await_args_list[0].args[0]
        subscription_event = apply_event.await_args_list[1].args[0]
        self.assertEqual(invoice_event.event_type, "invoice.paid")
        self.assertEqual(invoice_event.amount_satang, 10_700)
        self.assertEqual(subscription_event.event_type, "subscription.activated")
        self.assertEqual(attempt.status, "paid")
        db.commit.assert_awaited_once()

    async def test_unknown_saas_payment_intent_is_rejected(self) -> None:
        db = AsyncMock()
        db.scalar.return_value = None
        event = {
            "id": "evt_unknown",
            "livemode": False,
            "type": "payment_intent.succeeded",
            "data": {"object": {"id": "pi_unknown"}},
        }
        with (
            patch.object(settings, "saas_stripe_mode", "test"),
            patch.object(settings, "saas_billing_provider", "stripe_test"),
            patch.object(settings, "saas_billing_live_charging_enabled", False),
            patch.object(settings, "saas_stripe_account_id", "acct_saas_test"),
        ):
            with self.assertRaises(HTTPException) as caught:
                await SaasStripeTestService(db).apply_webhook_event(
                    event,
                    ip_address=None,
                    user_agent=None,
                )
        self.assertEqual(caught.exception.status_code, 404)


if __name__ == "__main__":
    unittest.main()
