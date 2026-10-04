from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import SoftDeleteMixin, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.branch import Branch
    from app.models.company import Company


class Unit(SoftDeleteMixin, Base):
    __tablename__ = "units"
    __table_args__ = (UniqueConstraint("company_id", "code", name="uq_units_company_id_code"),)

    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companies.id"),
        nullable=False,
        index=True,
    )
    code: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    name_en: Mapped[str | None] = mapped_column(String(100), nullable=True)
    decimal_places: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))

    company: Mapped["Company"] = relationship("Company")


class Category(SoftDeleteMixin, Base):
    __tablename__ = "categories"
    __table_args__ = (
        CheckConstraint("price_kind IN ('standard', 'promotion')", name="supported_price_kind"),
        Index(
            "ix_categories_company_code_not_null_unique",
            "company_id",
            "code",
            unique=True,
            postgresql_where=text("code IS NOT NULL"),
        ),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companies.id"),
        nullable=False,
        index=True,
    )
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("categories.id"),
        nullable=True,
    )
    code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    name_en: Mapped[str | None] = mapped_column(String(255), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    image_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))

    parent: Mapped["Category | None"] = relationship(
        "Category",
        remote_side="Category.id",
        back_populates="children",
    )
    children: Mapped[list["Category"]] = relationship(
        "Category",
        back_populates="parent",
        cascade="save-update",
    )
    products: Mapped[list["Product"]] = relationship("Product", back_populates="category")
    company: Mapped["Company"] = relationship("Company")


class Product(SoftDeleteMixin, Base):
    __tablename__ = "products"
    __table_args__ = (UniqueConstraint("company_id", "sku", name="uq_products_company_id_sku"),)

    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companies.id"),
        nullable=False,
        index=True,
    )
    category_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("categories.id"),
        nullable=True,
        index=True,
    )
    brand_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("brands.id"),
        nullable=True,
        index=True,
    )
    unit_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("units.id"),
        nullable=True,
        index=True,
    )
    sku: Mapped[str] = mapped_column(String(100), nullable=False)
    barcode: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    name_en: Mapped[str | None] = mapped_column(String(500), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    description_en: Mapped[str | None] = mapped_column(Text, nullable=True)
    product_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        server_default=text("'simple'"),
    )
    inventory_role: Mapped[str | None] = mapped_column(
        String(30),
        nullable=True,
        index=True,
        comment="central_raw, central_ready, store_local, or not_stocked",
    )
    cost_price: Mapped[Decimal] = mapped_column(
        Numeric(15, 4),
        nullable=False,
        server_default=text("0"),
    )
    selling_price: Mapped[Decimal] = mapped_column(
        Numeric(15, 4),
        nullable=False,
        server_default=text("0"),
    )
    vat_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        server_default=text("'included'"),
    )
    vat_rate: Mapped[Decimal] = mapped_column(
        Numeric(5, 2),
        nullable=False,
        server_default=text("7.00"),
    )
    weight_grams: Mapped[int | None] = mapped_column(Integer, nullable=True)
    image_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    is_for_sale: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    is_for_purchase: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    min_stock_qty: Mapped[Decimal] = mapped_column(
        Numeric(15, 4),
        nullable=False,
        server_default=text("0"),
    )

    category: Mapped["Category | None"] = relationship("Category", back_populates="products")
    brand: Mapped["Brand | None"] = relationship("Brand")  # type: ignore[name-defined]
    unit: Mapped["Unit | None"] = relationship("Unit")
    variants: Mapped[list["ProductVariant"]] = relationship("ProductVariant", back_populates="product")
    images: Mapped[list["ProductImage"]] = relationship(
        "ProductImage",
        back_populates="product",
        order_by="ProductImage.sort_order.asc()",
    )
    price_items: Mapped[list["PriceListItem"]] = relationship("PriceListItem", back_populates="product")
    replacement_sources: Mapped[list["BranchProductReplacementRule"]] = relationship(
        "BranchProductReplacementRule",
        back_populates="source_product",
        foreign_keys="BranchProductReplacementRule.source_product_id",
    )
    replacement_targets: Mapped[list["BranchProductReplacementRule"]] = relationship(
        "BranchProductReplacementRule",
        back_populates="replacement_product",
        foreign_keys="BranchProductReplacementRule.replacement_product_id",
    )
    company: Mapped["Company"] = relationship("Company")


class ProductVariant(SoftDeleteMixin, Base):
    __tablename__ = "product_variants"
    __table_args__ = (UniqueConstraint("company_id", "sku", name="uq_product_variants_company_id_sku"),)

    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("products.id"),
        nullable=False,
        index=True,
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companies.id"),
        nullable=False,
        index=True,
    )
    sku: Mapped[str] = mapped_column(String(100), nullable=False)
    barcode: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    attributes: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    cost_price: Mapped[Decimal | None] = mapped_column(Numeric(15, 4), nullable=True)
    selling_price: Mapped[Decimal | None] = mapped_column(Numeric(15, 4), nullable=True)
    image_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))

    product: Mapped["Product"] = relationship("Product", back_populates="variants")
    company: Mapped["Company"] = relationship("Company")


class ProductImage(UUIDMixin, Base):
    __tablename__ = "product_images"

    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("products.id"),
        nullable=False,
        index=True,
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companies.id"),
        nullable=False,
        index=True,
    )
    url: Mapped[str] = mapped_column(String(500), nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )

    product: Mapped["Product"] = relationship("Product", back_populates="images")
    company: Mapped["Company"] = relationship("Company")


class BranchProductReplacementRule(UUIDMixin, Base):
    __tablename__ = "branch_product_replacement_rules"
    __table_args__ = (
        UniqueConstraint(
            "branch_id",
            "source_product_id",
            name="uq_branch_product_replacement_rules_branch_source",
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
    source_product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("products.id"),
        nullable=False,
        index=True,
    )
    replacement_product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("products.id"),
        nullable=False,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )

    company: Mapped["Company"] = relationship("Company")
    branch: Mapped["Branch"] = relationship("Branch")
    source_product: Mapped["Product"] = relationship(
        "Product",
        back_populates="replacement_sources",
        foreign_keys=[source_product_id],
    )
    replacement_product: Mapped["Product"] = relationship(
        "Product",
        back_populates="replacement_targets",
        foreign_keys=[replacement_product_id],
    )


class PriceList(SoftDeleteMixin, Base):
    __tablename__ = "price_lists"

    __table_args__ = (
        Index(
            "ix_price_lists_resolution",
            "company_id",
            "branch_id",
            "brand_id",
            "channel",
            "currency",
            "is_active",
        ),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companies.id"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, server_default=text("'THB'"))
    brand_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("brands.id"), nullable=True, index=True
    )
    branch_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("branches.id"), nullable=True, index=True
    )
    customer_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    channel: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    price_kind: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'standard'"))
    promotion_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    valid_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    valid_until: Mapped[date | None] = mapped_column(Date, nullable=True)
    valid_from_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    valid_until_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))

    company: Mapped["Company"] = relationship("Company")
    brand: Mapped["Brand | None"] = relationship("Brand")  # type: ignore[name-defined]
    branch: Mapped["Branch | None"] = relationship("Branch")  # type: ignore[name-defined]
    items: Mapped[list["PriceListItem"]] = relationship("PriceListItem", back_populates="price_list")


class PriceListItem(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "price_list_items"
    __table_args__ = (
        UniqueConstraint(
            "price_list_id",
            "product_id",
            "variant_id",
            name="uq_price_list_items_price_list_product_variant",
        ),
    )

    price_list_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("price_lists.id"),
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
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companies.id"),
        nullable=False,
        index=True,
    )
    price: Mapped[Decimal] = mapped_column(Numeric(15, 4), nullable=False)
    min_qty: Mapped[Decimal] = mapped_column(
        Numeric(15, 4),
        nullable=False,
        server_default=text("1"),
    )

    price_list: Mapped["PriceList"] = relationship("PriceList", back_populates="items")
    product: Mapped["Product"] = relationship("Product", back_populates="price_items")
    variant: Mapped["ProductVariant | None"] = relationship("ProductVariant")
    company: Mapped["Company"] = relationship("Company")
