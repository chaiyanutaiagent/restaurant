from __future__ import annotations

import uuid

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.api_integration import WebhookEndpoint
from app.models.payment_gateway import PaymentGatewayConfig
from app.utils.rate_limiter import get_redis


async def get_system_health(db: AsyncSession, company_id: uuid.UUID) -> dict:
    checks: dict[str, dict] = {}

    try:
        await db.execute(text("SELECT 1"))
        checks["database"] = {"status": "ok", "label": "PostgreSQL"}
    except Exception as exc:  # pragma: no cover - runtime health failure path
        checks["database"] = {"status": "error", "label": "PostgreSQL", "error": str(exc)}

    try:
        redis = await get_redis()
        await redis.ping()
        checks["redis"] = {"status": "ok", "label": "Redis"}
    except Exception as exc:  # pragma: no cover - runtime health failure path
        checks["redis"] = {"status": "error", "label": "Redis", "error": str(exc)}

    try:
        version = await db.scalar(text("SELECT version_num FROM alembic_version LIMIT 1"))
        checks["migrations"] = {"status": "ok" if version else "error", "version": version}
    except Exception as exc:  # pragma: no cover
        checks["migrations"] = {"status": "error", "error": str(exc)}

    config = await db.scalar(
        select(PaymentGatewayConfig).where(PaymentGatewayConfig.company_id == company_id)
    )
    checks["api"] = {"status": "ok", "label": "FastAPI"}
    checks["promptpay"] = {"status": "ok" if (config and config.promptpay_enabled) else "disabled"}
    checks["omise"] = {"status": "ok" if (config and config.omise_enabled) else "disabled"}
    checks["line_notify"] = {"status": "ok" if (config and config.line_notify_enabled) else "disabled"}
    checks["smtp"] = {"status": "ok" if (config and config.smtp_enabled) else "disabled"}

    active_webhooks = int(
        (
            await db.scalar(
                select(func.count(WebhookEndpoint.id)).where(
                    WebhookEndpoint.company_id == company_id,
                    WebhookEndpoint.is_active.is_(True),
                )
            )
        )
        or 0
    )
    checks["webhooks"] = {"status": "ok", "active": active_webhooks}
    return checks
