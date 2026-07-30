from __future__ import annotations

from datetime import datetime
from decimal import Decimal
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, JSON, Numeric, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.branch import Branch
    from app.models.company import Company
    from app.models.user import User


class PaymentGatewayConfig(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "payment_gateway_configs"

    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, unique=True)
    omise_public_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    omise_secret_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    omise_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    twoc2p_merchant_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    twoc2p_secret_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    twoc2p_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    promptpay_target: Mapped[str | None] = mapped_column(String(20), nullable=True)
    promptpay_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    promptpay_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    scb_api_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    scb_api_secret: Mapped[str | None] = mapped_column(String(500), nullable=True)
    scb_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    line_notify_token: Mapped[str | None] = mapped_column(String(500), nullable=True)
    line_notify_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    smtp_host: Mapped[str | None] = mapped_column(String(255), nullable=True)
    smtp_port: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("587"))
    smtp_username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    smtp_password: Mapped[str | None] = mapped_column(String(500), nullable=True)
    smtp_from_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    smtp_from_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    smtp_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))

    company: Mapped["Company"] = relationship("Company")


class PaymentSession(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "payment_sessions"
    __table_args__ = (
        Index("ix_payment_sessions_company_id_session_ref", "company_id", "session_ref"),
        Index("ix_payment_sessions_status", "status"),
        Index("ix_payment_sessions_gateway_ref", "gateway_ref"),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    branch_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=False, index=True)
    session_ref: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    gateway: Mapped[str] = mapped_column(String(20), nullable=False)
    method: Mapped[str] = mapped_column(String(30), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, server_default=text("'THB'"))
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'pending'"))
    reference_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    reference_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    gateway_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    gateway_status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    gateway_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    qr_payload: Mapped[str | None] = mapped_column(Text, nullable=True)
    redirect_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)

    company: Mapped["Company"] = relationship("Company")
    branch: Mapped["Branch"] = relationship("Branch")
    creator: Mapped["User | None"] = relationship("User")


class NotificationLog(UUIDMixin, Base):
    __tablename__ = "notification_logs"

    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    channel: Mapped[str] = mapped_column(String(20), nullable=False)
    recipient: Mapped[str] = mapped_column(String(255), nullable=False)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    subject: Mapped[str | None] = mapped_column(String(255), nullable=True)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'sent'"))
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    reference_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    reference_id: Mapped[str | None] = mapped_column(String(100), nullable=True)

    company: Mapped["Company"] = relationship("Company")
