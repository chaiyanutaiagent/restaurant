from __future__ import annotations

from datetime import datetime
from decimal import Decimal
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import SoftDeleteMixin, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.branch import Branch
    from app.models.company import Company
    from app.models.product import Product, ProductVariant
    from app.models.user import User


class StockLocation(SoftDeleteMixin, Base):
    __tablename__ = "stock_locations"
    __table_args__ = (UniqueConstraint("branch_id", "code", name="uq_stock_locations_branch_id_code"),)

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
    code: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))

    company: Mapped["Company"] = relationship("Company")
    branch: Mapped["Branch"] = relationship("Branch")


class StockBalance(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "stock_balances"
    __table_args__ = (
        UniqueConstraint(
            "location_id",
            "product_id",
            "variant_id",
            name="uq_stock_balances_location_product_variant",
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
    qty_on_hand: Mapped[Decimal] = mapped_column(
        Numeric(15, 4),
        nullable=False,
        server_default=text("0"),
    )
    qty_reserved: Mapped[Decimal] = mapped_column(
        Numeric(15, 4),
        nullable=False,
        server_default=text("0"),
    )
    cost_per_unit: Mapped[Decimal] = mapped_column(
        Numeric(15, 4),
        nullable=False,
        server_default=text("0"),
    )
    last_movement_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    company: Mapped["Company"] = relationship("Company")
    branch: Mapped["Branch"] = relationship("Branch")
    location: Mapped["StockLocation"] = relationship("StockLocation")
    product: Mapped["Product"] = relationship("Product")
    variant: Mapped["ProductVariant | None"] = relationship("ProductVariant")

    @hybrid_property
    def qty_available(self) -> Decimal:
        return (self.qty_on_hand or Decimal("0")) - (self.qty_reserved or Decimal("0"))


class StockMovement(UUIDMixin, Base):
    __tablename__ = "stock_movements"

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
    movement_type: Mapped[str] = mapped_column(String(30), nullable=False)
    qty: Mapped[Decimal] = mapped_column(Numeric(15, 4), nullable=False)
    qty_before: Mapped[Decimal] = mapped_column(Numeric(15, 4), nullable=False)
    qty_after: Mapped[Decimal] = mapped_column(Numeric(15, 4), nullable=False)
    cost_per_unit: Mapped[Decimal] = mapped_column(
        Numeric(15, 4),
        nullable=False,
        server_default=text("0"),
    )
    reference_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    reference_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=False,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
        index=True,
    )

    company: Mapped["Company"] = relationship("Company")
    branch: Mapped["Branch"] = relationship("Branch")
    location: Mapped["StockLocation"] = relationship("StockLocation")
    product: Mapped["Product"] = relationship("Product")
    variant: Mapped["ProductVariant | None"] = relationship("ProductVariant")
    user: Mapped["User"] = relationship("User")
