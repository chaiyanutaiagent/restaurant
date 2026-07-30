from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID
import hashlib
import hmac
import json
import logging

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.api_integration import WebhookDelivery, WebhookEndpoint

logger = logging.getLogger(__name__)


def sign_payload(payload: dict, secret: str) -> str:
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()


async def dispatch_webhook(
    delivery: WebhookDelivery,
    endpoint: WebhookEndpoint,
    db: AsyncSession,
) -> bool:
    del db
    headers = {
        "Content-Type": "application/json",
        "X-ERP-Event": delivery.event_type,
        "X-ERP-Delivery": str(delivery.id),
    }
    if endpoint.secret:
        headers["X-ERP-Signature"] = sign_payload(delivery.payload, endpoint.secret)

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(endpoint.url, json=delivery.payload, headers=headers)
        delivery.response_status = response.status_code
        delivery.response_body = response.text[:500]
        if response.is_success:
            delivery.delivered_at = datetime.now(timezone.utc)
            endpoint.failure_count = 0
            endpoint.last_triggered_at = datetime.now(timezone.utc)
            return True
        raise httpx.HTTPStatusError("Webhook delivery failed", request=response.request, response=response)
    except Exception as exc:
        logger.warning("Webhook delivery failed for %s: %s", endpoint.id, exc)
        delivery.failed_at = datetime.now(timezone.utc)
        delivery.next_retry_at = datetime.now(timezone.utc) + timedelta(minutes=5)
        endpoint.failure_count = int(endpoint.failure_count or 0) + 1
        return False


async def trigger_event(
    db: AsyncSession,
    company_id: UUID,
    event_type: str,
    payload: dict,
) -> None:
    result = await db.scalars(
        select(WebhookEndpoint).where(
            WebhookEndpoint.company_id == company_id,
            WebhookEndpoint.is_active.is_(True),
            WebhookEndpoint.failure_count < 10,
        )
    )
    endpoints = result.all()
    subscribed = [endpoint for endpoint in endpoints if event_type in (endpoint.events or [])]

    for endpoint in subscribed:
        delivery = WebhookDelivery(
            webhook_id=endpoint.id,
            company_id=company_id,
            event_type=event_type,
            payload=payload,
        )
        db.add(delivery)
        await db.flush()
        await dispatch_webhook(delivery, endpoint, db)
