from __future__ import annotations

from datetime import datetime
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, JSON, Numeric, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.user_access import UserAccessRequest


class BranchSettings(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "branch_settings"
    __table_args__ = (
        CheckConstraint(
            "pos_max_discount_pct >= 0 AND pos_max_discount_pct <= 100",
            name="pos_max_discount_range",
        ),
        CheckConstraint(
            "pos_cashier_discount_limit_pct >= 0 "
            "AND pos_cashier_discount_limit_pct <= pos_max_discount_pct",
            name="pos_cashier_discount_limit_within_max",
        ),
        CheckConstraint(
            "stock_adjust_approval_threshold_qty >= 0",
            name="stock_adjust_approval_threshold_nonnegative",
        ),
        CheckConstraint(
            "pos_price_override_auto_limit_pct >= 0 "
            "AND pos_price_override_auto_limit_pct <= pos_price_override_max_deviation_pct",
            name="pos_price_override_auto_within_max",
        ),
        CheckConstraint(
            "pos_price_override_max_deviation_pct >= 0 "
            "AND pos_price_override_max_deviation_pct <= 100",
            name="pos_price_override_max_range",
        ),
        CheckConstraint(
            "pos_price_override_auto_limit_amount >= 0",
            name="pos_price_override_auto_amount_nonnegative",
        ),
        CheckConstraint(
            "pos_price_override_min_margin_pct >= -100 "
            "AND pos_price_override_min_margin_pct <= 100",
            name="pos_price_override_margin_range",
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
        unique=True,
    )
    pos_receipt_header: Mapped[str | None] = mapped_column(Text, nullable=True)
    pos_receipt_footer: Mapped[str | None] = mapped_column(Text, nullable=True)
    pos_require_customer: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("false"),
    )
    pos_allow_discount: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("true"),
    )
    pos_max_discount_pct: Mapped[float] = mapped_column(
        Numeric(5, 2),
        nullable=False,
        server_default=text("100"),
    )
    pos_cashier_discount_limit_pct: Mapped[float] = mapped_column(
        Numeric(5, 2),
        nullable=False,
        server_default=text("10"),
    )
    pos_price_override_auto_limit_pct: Mapped[float] = mapped_column(
        Numeric(5, 2), nullable=False, server_default=text("10")
    )
    pos_price_override_auto_limit_amount: Mapped[float] = mapped_column(
        Numeric(15, 2), nullable=False, server_default=text("100")
    )
    pos_price_override_max_deviation_pct: Mapped[float] = mapped_column(
        Numeric(5, 2), nullable=False, server_default=text("50")
    )
    pos_price_override_min_margin_pct: Mapped[float] = mapped_column(
        Numeric(6, 2), nullable=False, server_default=text("0")
    )
    pos_price_override_self_approval: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    stock_adjust_approval_threshold_qty: Mapped[float] = mapped_column(
        Numeric(12, 4),
        nullable=False,
        server_default=text("10"),
    )
    pos_default_price_list_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
    )
    promptpay_target: Mapped[str | None] = mapped_column(String(20), nullable=True)
    promptpay_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    promptpay_qr_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    working_hours: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    public_storefront_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("true"),
    )
    allow_negative_stock: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("false"),
    )
    low_stock_alert_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("true"),
    )
    receipt_show_tax_id: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("true"),
    )
    receipt_show_logo: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("false"),
    )
    receipt_logo_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    receipt_copies: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("1"),
    )
    notify_low_stock_email: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # F&B Module
    fb_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("false"),
    )
    fb_service_mode: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        server_default=text("'quick_service'"),
    )
    fb_table_qr_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("false"),
    )
    fb_bill_at_table: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("false"),
    )
    fb_queue_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("true"),
    )
    fb_queue_reset: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        server_default=text("'daily'"),
    )
    fb_queue_prefix: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        server_default=text("''"),
    )
    fb_pickup_display_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("true"),
    )
    fb_line_notify_token: Mapped[str | None] = mapped_column(String(255), nullable=True)
    fb_line_mode: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        server_default=text("'group'"),
    )
    fb_kitchen_stations: Mapped[list | None] = mapped_column(JSON, nullable=True)
    fb_setup_completed: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("false"),
    )
    fb_qs_qr_token: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        unique=True,
        comment="QR token สำหรับ Quick Service (shop-level)",
    )

    branch = relationship("Branch")


class UserInvitation(UUIDMixin, Base):
    __tablename__ = "user_invitations"
    __table_args__ = (
        Index("ix_user_invitations_company_id_otp_hash", "company_id", "otp_hash"),
        Index("ix_user_invitations_expires_at", "expires_at"),
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
    )
    role_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("roles.id"),
        nullable=False,
    )
    invited_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=False,
    )
    access_request_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("user_access_requests.id"),
        nullable=True,
        index=True,
    )
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    otp_code: Mapped[str | None] = mapped_column(String(8), nullable=True)
    otp_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    first_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )

    branch = relationship("Branch", foreign_keys=[branch_id])
    role = relationship("Role", foreign_keys=[role_id])
    inviter = relationship("User", foreign_keys=[invited_by])
    created_user = relationship("User", foreign_keys=[created_user_id])
    access_request: Mapped["UserAccessRequest | None"] = relationship(
        "UserAccessRequest",
        back_populates="invitations",
    )
