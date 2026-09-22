from __future__ import annotations

import json
import hmac
import re
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Path, Request, status
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.models.api_integration import ExternalOrder, WebhookEndpoint
from app.schemas.api_integration import PublicOrderCreate
from app.services.external_order_validation_service import validate_external_order
from app.utils.integration_security import (
    decrypt_integration_secret,
    verify_webhook_timestamp,
    webhook_signature,
)
from app.utils.rate_limiter import is_webhook_rate_limited

router = APIRouter(prefix="/webhooks", tags=["incoming-webhooks"])
SOURCE_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{1,48}[a-z0-9]$")


def normalize_source(source: str) -> str:
    value = source.strip().lower()
    if not SOURCE_PATTERN.fullmatch(value):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="source must be 3-50 chars using lowercase letters, numbers, underscores, or hyphens",
        )
    return value


async def resolve_incoming_company(
    source: str,
    body_bytes: bytes,
    signature: str,
    timestamp: int,
    db: AsyncSession,
) -> WebhookEndpoint | None:
    endpoint = await db.scalar(
        select(WebhookEndpoint).where(
            WebhookEndpoint.incoming_source == source,
            WebhookEndpoint.is_active.is_(True),
            WebhookEndpoint.secret_ciphertext.is_not(None),
        )
    )
    if endpoint is None:
        return None
    try:
        secret = decrypt_integration_secret(endpoint.secret_ciphertext)
    except ValueError:
        return None
    if secret is None:
        return None
    provided = signature.removeprefix("sha256=")
    expected = webhook_signature(secret, timestamp, body_bytes)
    return endpoint if hmac.compare_digest(expected, provided) else None


@router.post("/{source}/orders")
async def receive_external_order(
    request: Request,
    source: str = Path(...),
    x_erp_signature: str | None = Header(default=None, alias="X-ERP-Signature"),
    x_blife_signature: str | None = Header(default=None, alias="X-Blife-Signature"),
    x_erp_timestamp: str | None = Header(default=None, alias="X-ERP-Timestamp"),
) -> dict[str, Any]:
    source_value = normalize_source(source)
    signature = x_erp_signature or x_blife_signature
    source_ip = request.client.host if request.client else "unknown"
    is_limited, _remaining = await is_webhook_rate_limited(source_ip)
    if is_limited:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Rate limit exceeded")
    if not signature or not x_erp_timestamp:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Signature and timestamp required")
    try:
        timestamp_value = verify_webhook_timestamp(x_erp_timestamp)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc

    body_bytes = await request.body()
    async with AsyncSessionLocal() as db:
        endpoint = await resolve_incoming_company(source_value, body_bytes, signature, timestamp_value, db)
        if endpoint is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid signature")
        try:
            payload = PublicOrderCreate.model_validate(json.loads(body_bytes.decode("utf-8")))
        except (json.JSONDecodeError, UnicodeDecodeError, ValidationError) as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid JSON payload") from exc
        existing = await db.scalar(
            select(ExternalOrder).where(
                ExternalOrder.company_id == endpoint.company_id,
                ExternalOrder.source == source_value,
                ExternalOrder.external_order_id == payload.external_order_id,
            )
        )
        if existing is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Duplicate external_order_id")
        items, server_total, review_reasons = await validate_external_order(db, endpoint.company_id, payload)
        row = ExternalOrder(
            company_id=endpoint.company_id,
            source=source_value,
            external_order_id=payload.external_order_id,
            status="needs_review" if review_reasons else "accepted",
            customer_name=payload.customer_name,
            customer_phone=payload.customer_phone,
            customer_email=payload.customer_email,
            customer_address=payload.customer_address,
            items_json=items,
            total_amount=payload.total_amount,
            server_total_amount=server_total,
            review_reasons=review_reasons,
            payment_method=payload.payment_method,
            payment_status=payload.payment_status,
            notes=payload.notes,
            raw_payload=payload.model_dump(mode="json"),
        )
        db.add(row)
        await db.commit()
    return {"received": True, "status": row.status, "requires_review": bool(row.review_reasons)}
