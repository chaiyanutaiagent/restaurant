"""Retail-only merchandising data, separate from operational restaurant brands."""
import uuid

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import SoftDeleteMixin


class RetailProductBrand(SoftDeleteMixin, Base):
    __tablename__ = "retail_product_brands"
    __table_args__ = (UniqueConstraint("company_id", "name_key", name="uq_retail_product_brand_name"),)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    name_key: Mapped[str] = mapped_column(String(300), nullable=False)


class RetailProductBrandLink(Base):
    __tablename__ = "retail_product_brand_links"
    product_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("products.id"), primary_key=True)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False)
    product_brand_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("retail_product_brands.id"), nullable=False)
