from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
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
    from app.models.pos import SaleOrder
    from app.models.product import ProductVariant, Product
    from app.models.stock import StockLocation
    from app.models.user import User


class Supplier(SoftDeleteMixin, Base):
    __tablename__ = "suppliers"
    __table_args__ = (UniqueConstraint("company_id", "code", name="uq_suppliers_company_id_code"),)

    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companies.id"),
        nullable=False,
        index=True,
    )
    code: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    name_en: Mapped[str | None] = mapped_column(String(255), nullable=True)
    tax_id: Mapped[str | None] = mapped_column(String(20), nullable=True)
    branch_code: Mapped[str | None] = mapped_column(String(10), nullable=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    address_en: Mapped[str | None] = mapped_column(Text, nullable=True)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    contact_person: Mapped[str | None] = mapped_column(String(255), nullable=True)
    payment_term_days: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("30"))
    wht_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, server_default=text("3.00"))
    wht_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    credit_limit: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False, server_default=text("0"))
    bank_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    bank_account: Mapped[str | None] = mapped_column(String(30), nullable=True)
    bank_account_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))

    company: Mapped["Company"] = relationship("Company")
    purchase_orders: Mapped[list["PurchaseOrder"]] = relationship("PurchaseOrder", back_populates="supplier")


class PurchaseOrder(SoftDeleteMixin, Base):
    __tablename__ = "purchase_orders"
    __table_args__ = (
        Index("ix_purchase_orders_company_id_po_number", "company_id", "po_number"),
        Index("ix_purchase_orders_status", "status"),
        Index("ix_purchase_orders_order_date", "order_date"),
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
    supplier_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("suppliers.id"),
        nullable=False,
        index=True,
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=False,
    )
    approved_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=True,
    )
    po_number: Mapped[str] = mapped_column(String(30), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'draft'"))
    order_date: Mapped[date] = mapped_column(Date, nullable=False, server_default=text("CURRENT_DATE"))
    expected_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancel_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    subtotal: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False, server_default=text("0"))
    discount_amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False, server_default=text("0"))
    vat_amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False, server_default=text("0"))
    wht_amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False, server_default=text("0"))
    total_amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False, server_default=text("0"))
    paid_amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False, server_default=text("0"))
    remaining_amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False, server_default=text("0"))
    vat_type: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'excluded'"))
    vat_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, server_default=text("7.00"))
    wht_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, server_default=text("3.00"))
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    internal_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    company: Mapped["Company"] = relationship("Company")
    branch: Mapped["Branch"] = relationship("Branch")
    supplier: Mapped["Supplier"] = relationship("Supplier", back_populates="purchase_orders")
    creator: Mapped["User"] = relationship("User", foreign_keys=[created_by])
    approver: Mapped["User | None"] = relationship("User", foreign_keys=[approved_by])
    items: Mapped[list["PurchaseOrderItem"]] = relationship(
        "PurchaseOrderItem",
        back_populates="purchase_order",
        cascade="all, delete-orphan",
        order_by="PurchaseOrderItem.created_at.asc()",
    )
    receipts: Mapped[list["GoodsReceipt"]] = relationship(
        "GoodsReceipt",
        back_populates="purchase_order",
        order_by="GoodsReceipt.created_at.asc()",
    )


class PurchaseOrderItem(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "purchase_order_items"

    po_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("purchase_orders.id"),
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
    sku: Mapped[str] = mapped_column(String(100), nullable=False)
    unit_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    qty_ordered: Mapped[Decimal] = mapped_column(Numeric(15, 4), nullable=False)
    qty_received: Mapped[Decimal] = mapped_column(Numeric(15, 4), nullable=False, server_default=text("0"))
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(15, 4), nullable=False)
    discount_amount: Mapped[Decimal] = mapped_column(Numeric(15, 4), nullable=False, server_default=text("0"))
    vat_type: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'excluded'"))
    vat_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, server_default=text("7.00"))
    vat_amount: Mapped[Decimal] = mapped_column(Numeric(15, 4), nullable=False, server_default=text("0"))
    subtotal: Mapped[Decimal] = mapped_column(Numeric(15, 4), nullable=False)

    purchase_order: Mapped["PurchaseOrder"] = relationship("PurchaseOrder", back_populates="items")
    product: Mapped["Product"] = relationship("Product")
    variant: Mapped["ProductVariant | None"] = relationship("ProductVariant")
    company: Mapped["Company"] = relationship("Company")
    receipt_items: Mapped[list["GoodsReceiptItem"]] = relationship("GoodsReceiptItem", back_populates="po_item")


class GoodsReceipt(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "goods_receipts"
    __table_args__ = (
        Index("ix_goods_receipts_company_id_gr_number", "company_id", "gr_number"),
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
    po_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("purchase_orders.id"),
        nullable=False,
        index=True,
    )
    location_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("stock_locations.id"),
        nullable=False,
        index=True,
    )
    received_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=False,
    )
    gr_number: Mapped[str] = mapped_column(String(30), nullable=False, unique=True)
    received_date: Mapped[date] = mapped_column(Date, nullable=False, server_default=text("CURRENT_DATE"))
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    company: Mapped["Company"] = relationship("Company")
    branch: Mapped["Branch"] = relationship("Branch")
    purchase_order: Mapped["PurchaseOrder"] = relationship("PurchaseOrder", back_populates="receipts")
    location: Mapped["StockLocation"] = relationship("StockLocation")
    receiver: Mapped["User"] = relationship("User")
    items: Mapped[list["GoodsReceiptItem"]] = relationship(
        "GoodsReceiptItem",
        back_populates="goods_receipt",
        cascade="all, delete-orphan",
        order_by="GoodsReceiptItem.created_at.asc()",
    )


class GoodsReceiptItem(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "goods_receipt_items"

    gr_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("goods_receipts.id"),
        nullable=False,
        index=True,
    )
    po_item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("purchase_order_items.id"),
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
    )
    qty_received: Mapped[Decimal] = mapped_column(Numeric(15, 4), nullable=False)
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(15, 4), nullable=False)
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)

    goods_receipt: Mapped["GoodsReceipt"] = relationship("GoodsReceipt", back_populates="items")
    po_item: Mapped["PurchaseOrderItem"] = relationship("PurchaseOrderItem", back_populates="receipt_items")
    product: Mapped["Product"] = relationship("Product")
    variant: Mapped["ProductVariant | None"] = relationship("ProductVariant")
