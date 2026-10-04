from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import json
import logging
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.models.api_integration import WebhookDelivery, WebhookEndpoint
from app.utils.integration_security import decrypt_integration_secret, webhook_signature

logger = logging.getLogger(__name__)
MAX_WEBHOOK_ATTEMPTS = 5


def serialize_payload(payload: dict) -> bytes:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")


def sign_payload(payload: dict, secret: str, timestamp: int | None = None) -> str:
    issued_at = timestamp if timestamp is not None else int(datetime.now(timezone.utc).timestamp())
    return webhook_signature(secret, issued_at, serialize_payload(payload))


async def dispatch_webhook(
    delivery: WebhookDelivery,
    endpoint: WebhookEndpoint,
    db: AsyncSession,
) -> bool:
    del db
    now = datetime.now(timezone.utc)
    delivery.attempt_count = int(delivery.attempt_count or 0) + 1
    delivery.failed_at = None
    delivery.next_retry_at = None
    delivery.last_error_code = None
    timestamp = int(now.timestamp())
    body = serialize_payload(delivery.payload)
    headers = {
        "Content-Type": "application/json",
        "X-ERP-Event": delivery.event_type,
        "X-ERP-Delivery": str(delivery.id),
        "X-ERP-Timestamp": str(timestamp),
    }
    try:
        secret = decrypt_integration_secret(endpoint.secret_ciphertext)
        if secret is None:
            raise ValueError("webhook_secret_missing")
        headers["X-ERP-Signature"] = f"sha256={webhook_signature(secret, timestamp, body)}"
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(endpoint.url, content=body, headers=headers)
        delivery.response_status = response.status_code
        delivery.response_body = f"HTTP {response.status_code}"
        if response.is_success:
            delivery.status = "delivered"
            delivery.delivered_at = now
            endpoint.failure_count = 0
            endpoint.last_triggered_at = now
            return True
        delivery.last_error_code = f"http_{response.status_code}"
    except ValueError as exc:
        delivery.last_error_code = str(exc)[:120]
    except (httpx.TimeoutException, httpx.NetworkError):
        delivery.last_error_code = "network_error"
    except Exception:
        logger.exception("Webhook delivery failed for %s", endpoint.id)
        delivery.last_error_code = "unexpected_error"

    delivery.failed_at = now
    endpoint.failure_count = int(endpoint.failure_count or 0) + 1
    if delivery.attempt_count >= MAX_WEBHOOK_ATTEMPTS or delivery.last_error_code in {
        "webhook_secret_missing",
        "Integration secret is not encrypted; rotate it before use",
        "Integration secret cannot be decrypted",
    }:
        delivery.status = "dead_letter"
        delivery.next_retry_at = None
    else:
        delivery.status = "retry_scheduled"
        delay_minutes = min(60, 2 ** (delivery.attempt_count - 1))
        delivery.next_retry_at = now + timedelta(minutes=delay_minutes)
    return False


async def trigger_event(
    db: AsyncSession,
    company_id: UUID,
    event_type: str,
    payload: dict,
) -> None:
    endpoints = list(
        (
            await db.scalars(
                select(WebhookEndpoint).where(
                    WebhookEndpoint.company_id == company_id,
                    WebhookEndpoint.is_active.is_(True),
                    WebhookEndpoint.failure_count < 10,
                )
            )
        ).all()
    )
    for endpoint in (row for row in endpoints if event_type in (row.events or [])):
        delivery = WebhookDelivery(
            webhook_id=endpoint.id,
            company_id=company_id,
            event_type=event_type,
            payload=payload,
            status="pending",
            attempt_count=0,
        )
        db.add(delivery)
        await db.flush()
        await dispatch_webhook(delivery, endpoint, db)


async def retry_due_webhooks(*, limit: int = 50) -> int:
    now = datetime.now(timezone.utc)
    processed = 0
    async with AsyncSessionLocal() as db:
        deliveries = list(
            (
                await db.scalars(
                    select(WebhookDelivery)
                    .where(
                        WebhookDelivery.status == "retry_scheduled",
                        WebhookDelivery.next_retry_at.is_not(None),
                        WebhookDelivery.next_retry_at <= now,
                        WebhookDelivery.attempt_count < MAX_WEBHOOK_ATTEMPTS,
                    )
                    .order_by(WebhookDelivery.next_retry_at.asc())
                    .limit(limit)
                    .with_for_update(skip_locked=True)
                )
            ).all()
        )
        for delivery in deliveries:
            endpoint = await db.scalar(
                select(WebhookEndpoint).where(
                    WebhookEndpoint.id == delivery.webhook_id,
                    WebhookEndpoint.is_active.is_(True),
                )
            )
            if endpoint is None:
                delivery.status = "dead_letter"
                delivery.last_error_code = "endpoint_inactive_or_missing"
                delivery.next_retry_at = None
                continue
            await dispatch_webhook(delivery, endpoint, db)
            processed += 1
        await db.commit()
    return processed


async def run_webhook_retry_worker(stop_event: asyncio.Event, *, poll_seconds: int = 30) -> None:
    while not stop_event.is_set():
        try:
            await retry_due_webhooks()
        except Exception:
            logger.exception("Webhook retry worker failed")
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=poll_seconds)
        except TimeoutError:
            continue
