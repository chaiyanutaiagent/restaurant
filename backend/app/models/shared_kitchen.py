from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
import uuid

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
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


class CompanyKitchen(UUIDMixin, TimestampMixin, Base):
    """One Company-owned kitchen and raw-material pool for the WP5 MVP."""

    __tablename__ = "company_kitchens"
    __table_args__ = (
        UniqueConstraint("company_id", name="uq_company_kitchens_company_id"),
        UniqueConstraint("raw_location_id", name="uq_company_kitchens_raw_location_id"),
        CheckConstraint(
            "costing_method IN ('fifo')",
            name="ck_company_kitchens_costing_method",
        ),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True
    )
    branch_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("branches.id"), nullable=False, index=True
    )
    raw_location_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stock_locations.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    timezone: Mapped[str] = mapped_column(
        String(50), nullable=False, server_default=text("'Asia/Bangkok'")
    )
    costing_method: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'fifo'")
    )
    allow_negative_stock: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )


class CompanyIngredient(UUIDMixin, TimestampMixin, Base):
    """Canonical Company identity for one physical raw material."""

    __tablename__ = "company_ingredients"
    __table_args__ = (
        UniqueConstraint("company_id", "code", name="uq_company_ingredients_company_code"),
        UniqueConstraint("company_id", "canonical_product_id", name="uq_company_ingredients_company_product"),
        CheckConstraint(
            "unit_dimension IN ('mass', 'volume', 'count')",
            name="ck_company_ingredients_unit_dimension",
        ),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True
    )
    canonical_product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("products.id"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(80), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    base_unit_code: Mapped[str] = mapped_column(String(30), nullable=False)
    unit_dimension: Mapped[str] = mapped_column(String(20), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))

    canonical_product: Mapped["Product"] = relationship("Product")  # type: ignore[name-defined]


class CompanyIngredientAlias(UUIDMixin, TimestampMixin, Base):
    """Maps a Brand recipe Product/SKU onto a canonical Company ingredient."""

    __tablename__ = "company_ingredient_aliases"
    __table_args__ = (
        UniqueConstraint(
            "company_id",
            "brand_id",
            "source_product_id",
            name="uq_company_ingredient_aliases_brand_product",
        ),
        Index("ix_company_ingredient_aliases_company_ingredient", "company_id", "ingredient_id"),
        CheckConstraint(
            "conversion_factor > 0",
            name="ck_company_ingredient_aliases_conversion_positive",
        ),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True
    )
    ingredient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company_ingredients.id", ondelete="CASCADE"), nullable=False
    )
    brand_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("brands.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("products.id"), nullable=False, index=True
    )
    source_unit_code: Mapped[str] = mapped_column(String(30), nullable=False)
    conversion_factor: Mapped[Decimal] = mapped_column(
        Numeric(18, 8), nullable=False, server_default=text("1")
    )
    supplier_sku: Mapped[str | None] = mapped_column(String(100), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))

    ingredient: Mapped["CompanyIngredient"] = relationship("CompanyIngredient")
    brand: Mapped["Brand"] = relationship("Brand")  # type: ignore[name-defined]
    source_product: Mapped["Product"] = relationship("Product")  # type: ignore[name-defined]


class CompanyIngredientLot(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "company_ingredient_lots"
    __table_args__ = (
        UniqueConstraint(
            "kitchen_id", "ingredient_id", "lot_code", name="uq_company_ingredient_lots_identity"
        ),
        Index(
            "ix_company_ingredient_lots_fifo",
            "company_id",
            "kitchen_id",
            "ingredient_id",
            "expires_on",
            "received_at",
        ),
        CheckConstraint("qty_on_hand >= 0", name="ck_company_ingredient_lots_qty_nonnegative"),
        CheckConstraint("unit_cost >= 0", name="ck_company_ingredient_lots_cost_nonnegative"),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True
    )
    kitchen_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company_kitchens.id", ondelete="CASCADE"), nullable=False
    )
    ingredient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company_ingredients.id"), nullable=False, index=True
    )
    lot_code: Mapped[str] = mapped_column(String(100), nullable=False)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    expires_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    qty_on_hand: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, server_default=text("0")
    )
    unit_cost: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, server_default=text("0")
    )

    kitchen: Mapped["CompanyKitchen"] = relationship("CompanyKitchen")
    ingredient: Mapped["CompanyIngredient"] = relationship("CompanyIngredient")


class CompanyProductionDemand(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "company_production_demands"
    __table_args__ = (
        UniqueConstraint("company_id", "idempotency_key", name="uq_company_production_demands_idempotency"),
        Index(
            "ix_company_production_demands_plan",
            "company_id",
            "needed_on",
            "status",
            "brand_id",
        ),
        CheckConstraint(
            "status IN ('submitted', 'converted', 'cancelled')",
            name="ck_company_production_demands_status",
        ),
        CheckConstraint("requested_qty > 0", name="ck_company_production_demands_qty_positive"),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True
    )
    brand_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("brands.id"), nullable=False, index=True
    )
    branch_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("branches.id"), nullable=False, index=True
    )
    output_product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("products.id"), nullable=False, index=True
    )
    needed_on: Mapped[date] = mapped_column(Date, nullable=False)
    requested_qty: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    unit_code: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'submitted'")
    )
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)
    source_id: Mapped[str] = mapped_column(String(120), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(120), nullable=False)
    requested_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    brand: Mapped["Brand"] = relationship("Brand")  # type: ignore[name-defined]
    branch: Mapped["Branch"] = relationship("Branch")  # type: ignore[name-defined]
    output_product: Mapped["Product"] = relationship("Product")  # type: ignore[name-defined]


class CompanyProductionOrder(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "company_production_orders"
    __table_args__ = (
        UniqueConstraint("company_id", "order_number", name="uq_company_production_orders_number"),
        UniqueConstraint("company_id", "idempotency_key", name="uq_company_production_orders_idempotency"),
        UniqueConstraint("company_id", "completion_key", name="uq_company_production_orders_completion"),
        UniqueConstraint("company_id", "reversal_key", name="uq_company_production_orders_reversal"),
        Index(
            "ix_company_production_orders_company_brand_status",
            "company_id",
            "brand_id",
            "status",
        ),
        CheckConstraint(
            "status IN ('planned', 'in_progress', 'completed', 'reversed', 'cancelled')",
            name="ck_company_production_orders_status",
        ),
        CheckConstraint("planned_qty > 0", name="ck_company_production_orders_planned_positive"),
        CheckConstraint(
            "actual_output_qty IS NULL OR actual_output_qty > 0",
            name="ck_company_production_orders_output_positive",
        ),
        CheckConstraint("waste_qty >= 0", name="ck_company_production_orders_waste_nonnegative"),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True
    )
    kitchen_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company_kitchens.id"), nullable=False
    )
    brand_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("brands.id"), nullable=False, index=True
    )
    demand_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company_production_demands.id"), nullable=True, index=True
    )
    recipe_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("recipes.id"), nullable=False
    )
    output_product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("products.id"), nullable=False, index=True
    )
    ready_location_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stock_locations.id"), nullable=False
    )
    order_number: Mapped[str] = mapped_column(String(50), nullable=False)
    planned_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'planned'")
    )
    planned_qty: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    actual_output_qty: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    waste_qty: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, server_default=text("0")
    )
    output_unit_code: Mapped[str] = mapped_column(String(30), nullable=False)
    total_input_cost: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, server_default=text("0")
    )
    output_cost_per_unit: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, server_default=text("0")
    )
    idempotency_key: Mapped[str] = mapped_column(String(120), nullable=False)
    completion_key: Mapped[str | None] = mapped_column(String(120), nullable=True)
    reversal_key: Mapped[str | None] = mapped_column(String(120), nullable=True)
    planned_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    started_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    completed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    reversed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reversed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    kitchen: Mapped["CompanyKitchen"] = relationship("CompanyKitchen")
    brand: Mapped["Brand"] = relationship("Brand")  # type: ignore[name-defined]
    demand: Mapped["CompanyProductionDemand | None"] = relationship("CompanyProductionDemand")
    recipe: Mapped["Recipe"] = relationship("Recipe")  # type: ignore[name-defined]
    output_product: Mapped["Product"] = relationship("Product")  # type: ignore[name-defined]
    inputs: Mapped[list["CompanyProductionInput"]] = relationship(
        "CompanyProductionInput",
        back_populates="order",
        cascade="all, delete-orphan",
        order_by="CompanyProductionInput.created_at.asc()",
    )


class CompanyProductionInput(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "company_production_inputs"
    __table_args__ = (
        UniqueConstraint("order_id", "ingredient_id", name="uq_company_production_inputs_order_ingredient"),
        CheckConstraint("planned_qty > 0", name="ck_company_production_inputs_planned_positive"),
        CheckConstraint(
            "actual_qty IS NULL OR actual_qty >= 0",
            name="ck_company_production_inputs_actual_nonnegative",
        ),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True
    )
    order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company_production_orders.id", ondelete="CASCADE"), nullable=False
    )
    ingredient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company_ingredients.id"), nullable=False, index=True
    )
    planned_qty: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    actual_qty: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    base_unit_code: Mapped[str] = mapped_column(String(30), nullable=False)
    actual_cost: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, server_default=text("0")
    )

    order: Mapped["CompanyProductionOrder"] = relationship(
        "CompanyProductionOrder", back_populates="inputs"
    )
    ingredient: Mapped["CompanyIngredient"] = relationship("CompanyIngredient")


class CompanyKitchenMovement(UUIDMixin, Base):
    """Append-only shared raw-material ledger. Every quantity is in the canonical base unit."""

    __tablename__ = "company_kitchen_movements"
    __table_args__ = (
        UniqueConstraint("company_id", "idempotency_key", name="uq_company_kitchen_movements_idempotency"),
        UniqueConstraint("reversal_of_id", name="uq_company_kitchen_movements_reversal"),
        Index(
            "ix_company_kitchen_movements_report",
            "company_id",
            "created_at",
            "brand_id",
            "ingredient_id",
        ),
        CheckConstraint(
            "movement_type IN ('receipt', 'production_issue', 'production_reversal', 'waste', 'adjustment')",
            name="ck_company_kitchen_movements_type",
        ),
        CheckConstraint("qty <> 0", name="ck_company_kitchen_movements_qty_nonzero"),
        CheckConstraint("qty_after >= 0", name="ck_company_kitchen_movements_after_nonnegative"),
        CheckConstraint("unit_cost >= 0", name="ck_company_kitchen_movements_cost_nonnegative"),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True
    )
    kitchen_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company_kitchens.id"), nullable=False
    )
    ingredient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company_ingredients.id"), nullable=False, index=True
    )
    lot_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company_ingredient_lots.id"), nullable=False, index=True
    )
    location_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stock_locations.id"), nullable=False, index=True
    )
    brand_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("brands.id"), nullable=True, index=True
    )
    production_order_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company_production_orders.id"), nullable=True, index=True
    )
    reversal_of_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company_kitchen_movements.id"), nullable=True
    )
    movement_type: Mapped[str] = mapped_column(String(30), nullable=False)
    qty: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    qty_before: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    qty_after: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(160), nullable=False)
    reference_type: Mapped[str] = mapped_column(String(50), nullable=False)
    reference_id: Mapped[str] = mapped_column(String(120), nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    actor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()"), index=True
    )

    ingredient: Mapped["CompanyIngredient"] = relationship("CompanyIngredient")
    lot: Mapped["CompanyIngredientLot"] = relationship("CompanyIngredientLot")
    location: Mapped["StockLocation"] = relationship("StockLocation")  # type: ignore[name-defined]
    brand: Mapped["Brand | None"] = relationship("Brand")  # type: ignore[name-defined]
    production_order: Mapped["CompanyProductionOrder | None"] = relationship("CompanyProductionOrder")
