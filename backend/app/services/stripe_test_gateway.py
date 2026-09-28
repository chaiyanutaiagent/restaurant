from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
import hashlib
import hmac
import json
import time
from typing import Any

import httpx
from fastapi import HTTPException, status


TWOPLACES = Decimal("0.01")
STRIPE_API_VERSION = "2026-02-25.clover"


@dataclass(frozen=True)
class StripePromptPayIntent:
    id: str
    status: str
    amount_satang: int
    currency: str
    qr_payload: str | None
    hosted_instructions_url: str | None
    expires_at: datetime | None


def baht_to_satang(value: Decimal | int | float | str) -> int:
    amount = Decimal(value).quantize(TWOPLACES, rounding=ROUND_HALF_UP)
    if amount <= 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Stripe PromptPay amount must be greater than zero",
        )
    return int(amount * 100)


def verify_stripe_webhook(
    payload: bytes,
    signature_header: str | None,
    secret: str | None,
    *,
    tolerance_seconds: int = 300,
    now: int | None = None,
) -> dict[str, Any]:
    """Verify Stripe's signed raw request before parsing provider data."""
    if not secret or not secret.startswith("whsec_"):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Stripe Test Mode webhook is not configured",
        )
    if not signature_header:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing Stripe-Signature header",
        )

    timestamp: int | None = None
    signatures: list[str] = []
    for part in signature_header.split(","):
        key, separator, value = part.strip().partition("=")
        if not separator:
            continue
        if key == "t":
            try:
                timestamp = int(value)
            except ValueError:
                timestamp = None
        elif key == "v1":
            signatures.append(value)

    if timestamp is None or not signatures:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid Stripe-Signature header",
        )
    current_time = int(time.time()) if now is None else now
    if abs(current_time - timestamp) > tolerance_seconds:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Stripe webhook timestamp is outside the accepted window",
        )

    signed_payload = f"{timestamp}.".encode("utf-8") + payload
    expected = hmac.new(secret.encode("utf-8"), signed_payload, hashlib.sha256).hexdigest()
    if not any(hmac.compare_digest(expected, candidate) for candidate in signatures):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid Stripe webhook signature",
        )
    try:
        event = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Stripe webhook payload is not valid JSON",
        ) from exc
    if (
        not isinstance(event, dict)
        or not isinstance(event.get("id"), str)
        or not isinstance(event.get("type"), str)
        or not isinstance(event.get("data"), dict)
        or not isinstance(event["data"].get("object"), dict)
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Stripe webhook event contract is invalid",
        )
    return event


class StripeTestClient:
    def __init__(
        self,
        *,
        secret_key: str,
        api_base_url: str = "https://api.stripe.com/v1",
        connected_account_id: str | None = None,
    ) -> None:
        if not secret_key.startswith("sk_test_"):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Stripe Test Mode secret key is not configured",
            )
        self.secret_key = secret_key
        self.api_base_url = api_base_url.rstrip("/")
        self.connected_account_id = connected_account_id

    async def create_promptpay_intent(
        self,
        *,
        amount_satang: int,
        metadata: dict[str, str],
        idempotency_key: str,
        description: str,
    ) -> StripePromptPayIntent:
        if amount_satang <= 0:
            raise HTTPException(status_code=422, detail="Stripe amount must be positive")
        headers = {
            "Authorization": f"Bearer {self.secret_key}",
            "Idempotency-Key": idempotency_key,
            "Stripe-Version": STRIPE_API_VERSION,
        }
        if self.connected_account_id:
            headers["Stripe-Account"] = self.connected_account_id
        form: list[tuple[str, str]] = [
            ("amount", str(amount_satang)),
            ("currency", "thb"),
            ("payment_method_types[]", "promptpay"),
            ("payment_method_data[type]", "promptpay"),
            ("confirm", "true"),
            ("description", description[:500]),
        ]
        form.extend((f"metadata[{key}]", value) for key, value in sorted(metadata.items()))
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.post(
                    f"{self.api_base_url}/payment_intents",
                    headers=headers,
                    data=form,
                )
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Stripe Test Mode is temporarily unreachable",
            ) from exc
        try:
            result = response.json()
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Stripe returned an invalid response",
            ) from exc
        if response.status_code >= 400:
            provider_message = "Stripe rejected the Test Mode request"
            if isinstance(result, dict) and isinstance(result.get("error"), dict):
                message = result["error"].get("message")
                if isinstance(message, str) and message:
                    provider_message = message[:300]
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=provider_message,
            )
        return self._parse_promptpay_intent(result, expected_amount=amount_satang)

    @staticmethod
    def _parse_promptpay_intent(
        data: Any,
        *,
        expected_amount: int,
    ) -> StripePromptPayIntent:
        if not isinstance(data, dict) or not isinstance(data.get("id"), str):
            raise HTTPException(status_code=502, detail="Stripe PaymentIntent response is invalid")
        if data.get("livemode") is not False:
            raise HTTPException(status_code=502, detail="Stripe PaymentIntent is not explicitly Test Mode")
        amount = data.get("amount")
        currency = str(data.get("currency") or "").lower()
        if amount != expected_amount or currency != "thb":
            raise HTTPException(status_code=502, detail="Stripe PaymentIntent amount or currency mismatch")
        next_action = data.get("next_action") if isinstance(data.get("next_action"), dict) else {}
        qr = (
            next_action.get("promptpay_display_qr_code")
            if isinstance(next_action.get("promptpay_display_qr_code"), dict)
            else {}
        )
        expires_at = qr.get("expires_at")
        qr_payload = qr.get("data") if isinstance(qr.get("data"), str) else None
        hosted_url = (
            qr.get("hosted_instructions_url")
            if isinstance(qr.get("hosted_instructions_url"), str)
            else None
        )
        if str(data.get("status") or "") == "requires_action" and not (qr_payload or hosted_url):
            raise HTTPException(status_code=502, detail="Stripe PromptPay response is missing QR instructions")
        return StripePromptPayIntent(
            id=data["id"],
            status=str(data.get("status") or "requires_action"),
            amount_satang=amount,
            currency="THB",
            qr_payload=qr_payload,
            hosted_instructions_url=hosted_url,
            expires_at=(
                datetime.fromtimestamp(expires_at, tz=timezone.utc)
                if isinstance(expires_at, int)
                else None
            ),
        )
