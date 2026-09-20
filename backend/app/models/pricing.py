from __future__ import annotations

from datetime import datetime
from decimal import Decimal
import uuid

from sqlalchemy import DateTime, ForeignKey, Index, Integer, JSON, Numeric, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import UUIDMixin


class PriceCalculation(UUIDMixin, Base):
    __tablename__ = "price_calculations"
    __table_args__ = (
        UniqueConstraint(
            "company_id",
            "branch_id",
            "operation",
            "idempotency_key",
            name="uq_price_calculations_idempotency",
        ),
        Index("ix_price_calculations_context", "company_id", "branch_id", "created_at"),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False)
    brand_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("brands.id"), nullable=True)
    branch_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    customer_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    operation: Mapped[str] = mapped_column(String(30), nullable=False, server_default=text("'calculate'"))
    channel: Mapped[str] = mapped_column(String(40), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, server_default=text("'THB'"))
    idempotency_key: Mapped[str] = mapped_column(String(100), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    calculation_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    calculation_version: Mapped[str] = mapped_column(String(30), nullable=False)
    cart_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    price_list_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("price_lists.id"), nullable=True)
    price_list_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    context_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    result_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'quoted'"))
    consumed_order_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PriceOverrideAudit(UUIDMixin, Base):
    __tablename__ = "price_override_audits"
    __table_args__ = (
        Index("ix_price_override_audits_order", "company_id", "order_id", "created_at"),
        Index("ix_price_override_audits_product", "company_id", "product_id", "created_at"),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False)
    brand_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("brands.id"), nullable=True)
    branch_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=False)
    order_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sale_orders.id"), nullable=False)
    order_item_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sale_order_items.id"), nullable=False)
    product_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("products.id"), nullable=False)
    requester_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    approver_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    approval_grant_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    original_unit_price: Mapped[Decimal] = mapped_column(Numeric(15, 4), nullable=False)
    applied_unit_price: Mapped[Decimal] = mapped_column(Numeric(15, 4), nullable=False)
    deviation_pct: Mapped[Decimal] = mapped_column(Numeric(9, 4), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    reason_code: Mapped[str] = mapped_column(String(40), nullable=False, server_default=text("'other'"))
    approval_mode: Mapped[str] = mapped_column(String(30), nullable=False)
    policy_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    price_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
