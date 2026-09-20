from __future__ import annotations

from datetime import datetime
from decimal import Decimal
import uuid

from sqlalchemy import DateTime, ForeignKey, Index, Integer, JSON, Numeric, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin, UUIDMixin


class RefundQuote(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "refund_quotes"
    __table_args__ = (
        UniqueConstraint("company_id", "branch_id", "requester_id", "idempotency_key", name="uq_refund_quotes_idempotency"),
        Index("ix_refund_quotes_order_status", "order_id", "status", "expires_at"),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    branch_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=False, index=True)
    order_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sale_orders.id"), nullable=False, index=True)
    requester_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    shift_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("cashier_shifts.id"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'active'"))
    currency: Mapped[str] = mapped_column(String(3), nullable=False, server_default=text("'THB'"))
    order_version: Mapped[int] = mapped_column(Integer, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(100), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    quote_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    items_snapshot: Mapped[list] = mapped_column(JSON, nullable=False)
    payment_snapshot: Mapped[list] = mapped_column(JSON, nullable=False)
    totals_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    policy_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class RefundOperation(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "refund_operations"
    __table_args__ = (
        UniqueConstraint("company_id", "branch_id", "requester_id", "idempotency_key", name="uq_refund_operations_idempotency"),
        UniqueConstraint("quote_id", name="uq_refund_operations_quote_id"),
        Index("ix_refund_operations_shift_status", "shift_id", "status", "created_at"),
        Index("ix_refund_operations_order_status", "order_id", "status", "created_at"),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    branch_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=False, index=True)
    order_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sale_orders.id"), nullable=False, index=True)
    quote_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("refund_quotes.id"), nullable=False)
    shift_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("cashier_shifts.id"), nullable=False, index=True)
    requester_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    approver_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    approval_grant_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, server_default=text("'requested'"))
    reason_code: Mapped[str] = mapped_column(String(50), nullable=False)
    reason_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, server_default=text("'THB'"))
    subtotal_amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    discount_amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    vat_amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    rounding_amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False, server_default=text("0"))
    total_amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    stock_disposition: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'none'"))
    provider_scenario: Mapped[str] = mapped_column(String(40), nullable=False, server_default=text("'succeeded'"))
    approval_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(100), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    row_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    failure_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    failure_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    finalized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    tax_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    items: Mapped[list["RefundOperationItem"]] = relationship("RefundOperationItem", back_populates="operation", cascade="all, delete-orphan")
    payment_legs: Mapped[list["RefundPaymentLeg"]] = relationship("RefundPaymentLeg", back_populates="operation", cascade="all, delete-orphan")


class RefundOperationItem(UUIDMixin, Base):
    __tablename__ = "refund_operation_items"
    __table_args__ = (UniqueConstraint("operation_id", "sale_order_item_id", name="uq_refund_operation_items_line"),)

    operation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("refund_operations.id"), nullable=False, index=True)
    sale_order_item_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sale_order_items.id"), nullable=False)
    product_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("products.id"), nullable=False)
    variant_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("product_variants.id"), nullable=True)
    product_name: Mapped[str] = mapped_column(String(500), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(15, 4), nullable=False)
    subtotal_amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    discount_amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    vat_amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    vat_type: Mapped[str] = mapped_column(String(20), nullable=False)
    vat_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    stock_disposition: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'none'"))
    stock_movement_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("stock_movements.id"), nullable=True)
    loyalty_reversal_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("points_transactions.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

    operation: Mapped[RefundOperation] = relationship("RefundOperation", back_populates="items")


class RefundPaymentLeg(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "refund_payment_legs"
    __table_args__ = (UniqueConstraint("operation_id", "original_payment_id", name="uq_refund_payment_legs_original"),)

    operation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("refund_operations.id"), nullable=False, index=True)
    original_payment_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("payments.id"), nullable=False, index=True)
    payment_method: Mapped[str] = mapped_column(String(30), nullable=False)
    leg_type: Mapped[str] = mapped_column(String(20), nullable=False)
    provider_name: Mapped[str | None] = mapped_column(String(40), nullable=True)
    provider_payment_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, server_default=text("'THB'"))
    status: Mapped[str] = mapped_column(String(30), nullable=False, server_default=text("'requested'"))
    provider_refund_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    last_event_sequence: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    last_error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    last_error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    succeeded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    operation: Mapped[RefundOperation] = relationship("RefundOperation", back_populates="payment_legs")


class ProviderRefundAttempt(UUIDMixin, Base):
    __tablename__ = "provider_refund_attempts"
    __table_args__ = (UniqueConstraint("payment_leg_id", "attempt_no", name="uq_provider_refund_attempt_no"),)

    payment_leg_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("refund_payment_legs.id"), nullable=False, index=True)
    attempt_no: Mapped[int] = mapped_column(Integer, nullable=False)
    operation_kind: Mapped[str] = mapped_column(String(20), nullable=False)
    request_id: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    request_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    response_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    result_state: Mapped[str] = mapped_column(String(30), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class ProviderRefundEvent(UUIDMixin, Base):
    __tablename__ = "provider_refund_events"
    __table_args__ = (UniqueConstraint("provider_name", "provider_event_id", name="uq_provider_refund_events_provider_event"),)

    payment_leg_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("refund_payment_legs.id"), nullable=False, index=True)
    provider_name: Mapped[str] = mapped_column(String(40), nullable=False)
    provider_event_id: Mapped[str] = mapped_column(String(160), nullable=False)
    event_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    signature_valid: Mapped[bool] = mapped_column(nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    payload_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    applied: Mapped[bool] = mapped_column(nullable=False, server_default=text("false"))
    ignored_reason: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class RefundTaxLink(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "refund_tax_links"
    __table_args__ = (UniqueConstraint("operation_id", name="uq_refund_tax_links_operation"),)

    operation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("refund_operations.id"), nullable=False, index=True)
    original_document_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("tax_documents.id"), nullable=True)
    credit_note_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("tax_documents.id"), nullable=True, unique=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, server_default=text("'pending'"))
    idempotency_key: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)


class RefundOperationAudit(UUIDMixin, Base):
    __tablename__ = "refund_operation_audits"
    __table_args__ = (UniqueConstraint("operation_id", "idempotency_key", name="uq_refund_operation_audit_idempotency"),)

    operation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("refund_operations.id"), nullable=False, index=True)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    branch_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=False, index=True)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(60), nullable=False)
    from_state: Mapped[str | None] = mapped_column(String(30), nullable=True)
    to_state: Mapped[str] = mapped_column(String(30), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(160), nullable=False)
    evidence: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
