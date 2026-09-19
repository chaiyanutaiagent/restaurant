from __future__ import annotations

from datetime import datetime, timedelta, timezone
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.api_integration import WebhookEndpoint
from app.models.device import DeviceRegistration
from app.models.payment_gateway import PaymentGatewayConfig
from app.schemas.company_foundation import (
    OperationalComponentRead,
    OperationalState,
    OperationalStatusRead,
)


def resolve_device_operational_state(
    *,
    revoked_at: datetime | None,
    paired_at: datetime | None,
    last_seen_at: datetime | None,
    now: datetime,
) -> OperationalState:
    if revoked_at is not None:
        return "disabled"
    if paired_at is None or last_seen_at is None:
        return "offline"
    age = now - last_seen_at
    if age <= timedelta(minutes=2):
        return "online"
    if age <= timedelta(minutes=15):
        return "degraded"
    return "stale"


class CompanyOperationalStatusService:
    def __init__(self, identity_db: AsyncSession, operational_db: AsyncSession):
        self.identity_db = identity_db
        self.operational_db = operational_db

    async def read(
        self,
        company_id: uuid.UUID,
        *,
        branch_ids: list[uuid.UUID] | None = None,
    ) -> OperationalStatusRead:
        now = datetime.now(timezone.utc)
        device_filters = [DeviceRegistration.company_id == company_id]
        if branch_ids is not None:
            device_filters.append(DeviceRegistration.branch_id.in_(branch_ids))
        devices = (
            await self.identity_db.scalars(
                select(DeviceRegistration)
                .where(*device_filters)
                .order_by(DeviceRegistration.name.asc())
            )
        ).all()
        components = [
            OperationalComponentRead(
                id=f"device:{device.id}",
                component_type=device.device_type,
                name=device.name,
                state=resolve_device_operational_state(
                    revoked_at=device.revoked_at,
                    paired_at=device.paired_at,
                    last_seen_at=device.last_seen_at,
                    now=now,
                ),
                company_id=device.company_id,
                branch_id=device.branch_id,
                station_key=device.station_key,
                last_seen_at=device.last_seen_at,
                last_sync_at=device.last_seen_at,
                queue_size=0,
                error_code=("device_revoked" if device.revoked_at is not None else None),
                retryable=device.revoked_at is None,
                source_system="identity.device_registry",
                updated_at=device.updated_at,
            )
            for device in devices
        ]

        webhooks = []
        if branch_ids is None:
            webhooks = (
                await self.operational_db.scalars(
                    select(WebhookEndpoint)
                    .where(WebhookEndpoint.company_id == company_id)
                    .order_by(WebhookEndpoint.name.asc())
                )
            ).all()
        for webhook in webhooks:
            if not webhook.is_active:
                state: OperationalState = "disabled"
            elif webhook.failure_count >= 5:
                state = "error"
            elif webhook.failure_count > 0:
                state = "degraded"
            elif webhook.last_triggered_at is None:
                state = "offline"
            elif now - webhook.last_triggered_at > timedelta(days=1):
                state = "stale"
            else:
                state = "online"
            components.append(
                OperationalComponentRead(
                    id=f"webhook:{webhook.id}",
                    component_type="webhook",
                    name=webhook.name,
                    state=state,
                    company_id=webhook.company_id,
                    last_seen_at=webhook.last_triggered_at,
                    last_sync_at=webhook.last_triggered_at,
                    queue_size=webhook.failure_count,
                    error_code=("webhook_delivery_failed" if webhook.failure_count else None),
                    retryable=webhook.is_active,
                    source_system="erp.webhook",
                    updated_at=webhook.updated_at,
                )
            )

        payment = None
        if branch_ids is None:
            payment = await self.operational_db.scalar(
                select(PaymentGatewayConfig).where(PaymentGatewayConfig.company_id == company_id)
            )
        if payment is not None:
            payment_enabled = any(
                (
                    payment.omise_enabled,
                    payment.twoc2p_enabled,
                    payment.promptpay_enabled,
                    payment.scb_enabled,
                )
            )
            components.append(
                OperationalComponentRead(
                    id=f"payment:{payment.id}",
                    component_type="payment",
                    name="Payment configuration",
                    state="online" if payment_enabled else "disabled",
                    company_id=company_id,
                    source_system="erp.payment_gateway",
                    retryable=False,
                    updated_at=payment.updated_at,
                )
            )

        components.extend(
            [
                OperationalComponentRead(
                    id="integration:retail-data-source",
                    component_type="legacy_sync",
                    name="Retail data source",
                    state="online" if settings.retail_service_database == "legacy" else "pending_sync",
                    company_id=company_id,
                    source_system=settings.retail_service_database,
                    retryable=True,
                    updated_at=now,
                ),
                OperationalComponentRead(
                    id="integration:shared-reporting",
                    component_type="reporting_sync",
                    name="Shared reporting projector",
                    state="online" if settings.shared_reporting_projector_enabled else "disabled",
                    company_id=company_id,
                    source_system="platform.reporting_projection",
                    retryable=settings.shared_reporting_projector_enabled,
                    updated_at=now,
                ),
            ]
        )
        summary: dict[OperationalState, int] = {
            "online": 0,
            "offline": 0,
            "degraded": 0,
            "pending_sync": 0,
            "stale": 0,
            "error": 0,
            "disabled": 0,
        }
        for component in components:
            summary[component.state] += 1
        return OperationalStatusRead(
            components=components,
            summary=summary,
            generated_at=now,
        )
