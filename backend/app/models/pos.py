from __future__ import annotations

from datetime import datetime
from decimal import Decimal
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.branch import Branch
    from app.models.company import Company
    from app.models.stock import StockLocation
    from app.models.user import User


class CashierShift(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "cashier_shifts"
    __table_args__ = (
        Index(
            "ix_cashier_shifts_user_branch_open_unique",
            "user_id",
            "branch_id",
            unique=True,
            postgresql_where=text("status = 'open'"),
        ),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companies.id"),
        nullable=False,
        index=True,
    )
    branch_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("branches.id"),
        nullable=False,
        index=True,
    )
    location_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("stock_locations.id"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=False,
        index=True,
    )
    shift_number: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'open'"))
    opened_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    opening_cash: Mapped[Decimal] = mapped_column(
        Numeric(15, 2),
        nullable=False,
        server_default=text("0"),
    )
    closing_cash: Mapped[Decimal | None] = mapped_column(Numeric(15, 2), nullable=True)
    expected_cash: Mapped[Decimal | None] = mapped_column(Numeric(15, 2), nullable=True)
    cash_difference: Mapped[Decimal | None] = mapped_column(Numeric(15, 2), nullable=True)
    total_sales: Mapped[Decimal] = mapped_column(
        Numeric(15, 2),
        nullable=False,
        server_default=text("0"),
    )
    total_orders: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    total_voids: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    company: Mapped["Company"] = relationship("Company")
    branch: Mapped["Branch"] = relationship("Branch")
    location: Mapped["StockLocation"] = relationship("StockLocation")
    user: Mapped["User"] = relationship("User")
    orders: Mapped[list["SaleOrder"]] = relationship("SaleOrder", back_populates="shift")


class SaleOrder(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "sale_orders"
    __table_args__ = (
        Index("ix_sale_orders_company_id_order_number", "company_id", "order_number"),
        Index("ix_sale_orders_status", "status"),
        Index("ix_sale_orders_created_at", "created_at"),
        UniqueConstraint("company_id", "client_order_id", name="uq_sale_orders_client_order_id"),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companies.id"),
        nullable=False,
        index=True,
    )
    branch_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("branches.id"),
        nullable=False,
        index=True,
    )
    location_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("stock_locations.id"),
        nullable=False,
        index=True,
    )
    shift_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("cashier_shifts.id"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=False,
        index=True,
    )
    order_number: Mapped[str] = mapped_column(String(30), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'completed'"))
    customer_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    customer_phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    customer_tax_id: Mapped[str | None] = mapped_column(String(20), nullable=True)
    subtotal: Mapped[Decimal] = mapped_column(
        Numeric(15, 2),
        nullable=False,
        server_default=text("0"),
    )
    discount_amount: Mapped[Decimal] = mapped_column(
        Numeric(15, 2),
        nullable=False,
        server_default=text("0"),
    )
    discount_type: Mapped[str] = mapped_column(String(10), nullable=False, server_default=text("'amount'"))
    vat_amount: Mapped[Decimal] = mapped_column(
        Numeric(15, 2),
        nullable=False,
        server_default=text("0"),
    )
    vat_rate: Mapped[Decimal] = mapped_column(
        Numeric(5, 2),
        nullable=False,
        server_default=text("7.00"),
    )
    total_amount: Mapped[Decimal] = mapped_column(
        Numeric(15, 2),
        nullable=False,
        server_default=text("0"),
    )
    refund_amount: Mapped[Decimal] = mapped_column(
        Numeric(15, 2),
        nullable=False,
        server_default=text("0"),
    )
    paid_amount: Mapped[Decimal] = mapped_column(
        Numeric(15, 2),
        nullable=False,
        server_default=text("0"),
    )
    change_amount: Mapped[Decimal] = mapped_column(
        Numeric(15, 2),
        nullable=False,
        server_default=text("0"),
    )
    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    voided_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=True,
    )
    void_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    refunded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_offline: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    client_order_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    recipe_stock_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    recipe_stock_warnings: Mapped[str | None] = mapped_column(Text, nullable=True)
    recipe_stock_posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    recipe_stock_reversed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    pricing_quote_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    pricing_request_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    pricing_calculation_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    pricing_calculation_version: Mapped[str | None] = mapped_column(String(30), nullable=True)
    pricing_context: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    pricing_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    row_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))

    company: Mapped["Company"] = relationship("Company")
    branch: Mapped["Branch"] = relationship("Branch")
    location: Mapped["StockLocation"] = relationship("StockLocation")
    shift: Mapped["CashierShift"] = relationship("CashierShift", back_populates="orders")
    user: Mapped["User"] = relationship("User", foreign_keys=[user_id])
    void_user: Mapped["User | None"] = relationship("User", foreign_keys=[voided_by])
    items: Mapped[list["SaleOrderItem"]] = relationship(
        "SaleOrderItem",
        back_populates="order",
        cascade="all, delete-orphan",
        order_by="SaleOrderItem.created_at.asc()",
    )
    payments: Mapped[list["Payment"]] = relationship(
        "Payment",
        back_populates="order",
        cascade="all, delete-orphan",
        order_by="Payment.paid_at.asc()",
    )


class SaleOrderItem(UUIDMixin, Base):
    __tablename__ = "sale_order_items"

    order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sale_orders.id"),
        nullable=False,
        index=True,
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companies.id"),
        nullable=False,
        index=True,
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("products.id"),
        nullable=False,
        index=True,
    )
    variant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("product_variants.id"),
        nullable=True,
        index=True,
    )
    product_name: Mapped[str] = mapped_column(String(500), nullable=False)
    variant_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sku: Mapped[str] = mapped_column(String(100), nullable=False)
    unit_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    qty: Mapped[Decimal] = mapped_column(Numeric(15, 4), nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(15, 4), nullable=False)
    original_price: Mapped[Decimal] = mapped_column(Numeric(15, 4), nullable=False)
    discount_amount: Mapped[Decimal] = mapped_column(
        Numeric(15, 4),
        nullable=False,
        server_default=text("0"),
    )
    discount_type: Mapped[str] = mapped_column(String(10), nullable=False, server_default=text("'amount'"))
    vat_type: Mapped[str] = mapped_column(String(20), nullable=False)
    vat_rate: Mapped[Decimal] = mapped_column(
        Numeric(5, 2),
        nullable=False,
        server_default=text("7.00"),
    )
    vat_amount: Mapped[Decimal] = mapped_column(
        Numeric(15, 4),
        nullable=False,
        server_default=text("0"),
    )
    subtotal: Mapped[Decimal] = mapped_column(Numeric(15, 4), nullable=False)
    refunded_qty: Mapped[Decimal] = mapped_column(
        Numeric(15, 4),
        nullable=False,
        server_default=text("0"),
    )
    refunded_amount: Mapped[Decimal] = mapped_column(
        Numeric(15, 2),
        nullable=False,
        server_default=text("0"),
    )
    price_source: Mapped[str | None] = mapped_column(String(30), nullable=True)
    price_list_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    price_list_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    price_version: Mapped[str | None] = mapped_column(String(128), nullable=True)
    price_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    order_discount_share: Mapped[Decimal] = mapped_column(
        Numeric(15, 4), nullable=False, server_default=text("0")
    )
    line_total: Mapped[Decimal] = mapped_column(Numeric(15, 4), nullable=False, server_default=text("0"))
    price_override_applied: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    price_override_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )

    order: Mapped["SaleOrder"] = relationship("SaleOrder", back_populates="items")


class Payment(UUIDMixin, Base):
    __tablename__ = "payments"

    order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sale_orders.id"),
        nullable=False,
        index=True,
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companies.id"),
        nullable=False,
        index=True,
    )
    payment_method: Mapped[str] = mapped_column(String(30), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    reference_no: Mapped[str | None] = mapped_column(String(100), nullable=True)
    original_payment_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("payments.id"),
        nullable=True,
        index=True,
    )
    paid_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )

    order: Mapped["SaleOrder"] = relationship("SaleOrder", back_populates="payments")


class PosHoldDraft(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "pos_hold_drafts"
    __table_args__ = (
        UniqueConstraint("company_id", "draft_no", name="uq_pos_hold_drafts_number"),
        UniqueConstraint(
            "company_id",
            "branch_id",
            "idempotency_key",
            name="uq_pos_hold_drafts_idempotency",
        ),
        CheckConstraint(
            "status IN ('active', 'claimed', 'resumed', 'expired', 'converted', 'cancelled')",
            name="ck_pos_hold_drafts_status",
        ),
        CheckConstraint("version >= 1", name="ck_pos_hold_drafts_version"),
        Index(
            "ix_pos_hold_drafts_branch_status_updated",
            "company_id",
            "branch_id",
            "status",
            "updated_at",
        ),
        Index("ix_pos_hold_drafts_owner", "company_id", "branch_id", "owner_user_id"),
        Index("ix_pos_hold_drafts_expiry", "status", "expires_at"),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True
    )
    brand_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("brands.id"), nullable=True, index=True
    )
    branch_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("branches.id"), nullable=False, index=True
    )
    location_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stock_locations.id"), nullable=False, index=True
    )
    origin_shift_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cashier_shifts.id"), nullable=False, index=True
    )
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    assignee_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True
    )
    origin_device_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    origin_device_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    parent_draft_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("pos_hold_drafts.id"), nullable=True, index=True
    )
    converted_order_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sale_orders.id"), nullable=True, index=True
    )
    draft_no: Mapped[str] = mapped_column(String(40), nullable=False)
    label: Mapped[str] = mapped_column(String(160), nullable=False)
    source_type: Mapped[str] = mapped_column(String(40), nullable=False, server_default=text("'walk_in'"))
    table_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    queue_label: Mapped[str | None] = mapped_column(String(80), nullable=True)
    customer_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    customer_display: Mapped[str | None] = mapped_column(String(160), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    pricing_context: Mapped[dict] = mapped_column(JSON, nullable=False)
    pricing_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    last_revalidation: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'active'"))
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    idempotency_key: Mapped[str] = mapped_column(String(100), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    claim_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    claimed_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    claimed_device_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    claim_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    resumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resumed_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    resumed_device_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    expired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    cancel_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    converted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PosHoldDraftAudit(UUIDMixin, Base):
    __tablename__ = "pos_hold_draft_audits"
    __table_args__ = (
        UniqueConstraint(
            "company_id",
            "branch_id",
            "action",
            "idempotency_key",
            name="uq_pos_hold_draft_audits_idempotency",
        ),
        Index("ix_pos_hold_draft_audits_draft", "draft_id", "created_at"),
        Index("ix_pos_hold_draft_audits_scope", "company_id", "branch_id", "created_at"),
    )

    draft_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("pos_hold_drafts.id"), nullable=False, index=True
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True
    )
    branch_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("branches.id"), nullable=False, index=True
    )
    actor_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    device_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    shift_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    action: Mapped[str] = mapped_column(String(40), nullable=False)
    from_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    to_status: Mapped[str] = mapped_column(String(20), nullable=False)
    from_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    to_version: Mapped[int] = mapped_column(Integer, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(100), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, server_default=text("'{}'::json"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
