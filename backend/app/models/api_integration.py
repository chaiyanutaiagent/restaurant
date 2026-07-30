from __future__ import annotations

from datetime import datetime
from decimal import Decimal
import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.company import Company
    from app.models.pos import SaleOrder
    from app.models.user import User


class APIKey(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "api_keys"
    __table_args__ = (
        Index("ix_api_keys_company_id_key_prefix", "company_id", "key_prefix"),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    key_prefix: Mapped[str] = mapped_column(String(8), nullable=False)
    key_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    scopes: Mapped[list[str]] = mapped_column(JSON, nullable=False, server_default=text("'[]'::json"))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)

    company: Mapped["Company"] = relationship("Company")
    creator: Mapped["User"] = relationship("User", foreign_keys=[created_by])
    revoker: Mapped["User | None"] = relationship("User", foreign_keys=[revoked_by])


class WebhookEndpoint(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "webhook_endpoints"

    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    url: Mapped[str] = mapped_column(String(500), nullable=False)
    events: Mapped[list[str]] = mapped_column(JSON, nullable=False, server_default=text("'[]'::json"))
    secret: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    last_triggered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failure_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))

    company: Mapped["Company"] = relationship("Company")


class WebhookDelivery(UUIDMixin, Base):
    __tablename__ = "webhook_deliveries"
    __table_args__ = (
        Index("ix_webhook_deliveries_webhook_id_created_at", "webhook_id", "created_at"),
        Index("ix_webhook_deliveries_event_type", "event_type"),
    )

    webhook_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("webhook_endpoints.id"), nullable=False, index=True)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    response_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_body: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

    webhook: Mapped["WebhookEndpoint"] = relationship("WebhookEndpoint")
    company: Mapped["Company"] = relationship("Company")


class ExternalOrder(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "external_orders"
    __table_args__ = (
        UniqueConstraint("company_id", "source", "external_order_id", name="uq_external_orders_company_source_external_order_id"),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(50), nullable=False, server_default=text("'blifehealthy'"))
    external_order_id: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'pending'"))
    customer_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    customer_phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    customer_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    customer_address: Mapped[str | None] = mapped_column(Text, nullable=True)
    items_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    payment_method: Mapped[str | None] = mapped_column(String(50), nullable=True)
    payment_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    sale_order_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("sale_orders.id"), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_payload: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    company: Mapped["Company"] = relationship("Company")
    sale_order: Mapped["SaleOrder | None"] = relationship("SaleOrder")
