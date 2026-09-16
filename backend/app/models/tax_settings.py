from __future__ import annotations

from datetime import date
from decimal import Decimal
import uuid

from sqlalchemy import Boolean, CheckConstraint, Date, ForeignKey, Index, Numeric, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import TimestampMixin, UUIDMixin


class CompanyTaxProfile(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "company_tax_profiles"
    __table_args__ = (
        CheckConstraint(
            "default_price_vat_type IN ('included', 'excluded', 'exempt')",
            name="default_vat_type",
        ),
        CheckConstraint(
            "vat_filing_mode IN ('separate', 'consolidated')",
            name="filing_mode",
        ),
        CheckConstraint(
            "default_vat_rate >= 0 AND default_vat_rate <= 100",
            name="default_rate",
        ),
        CheckConstraint(
            "tax_id IS NULL OR tax_id ~ '^[0-9]{13}$'",
            name="tax_id_format",
        ),
        UniqueConstraint("company_id", name="uq_company_tax_profiles_company_id"),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True
    )
    legal_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    tax_id: Mapped[str | None] = mapped_column(String(13), nullable=True)
    vat_registered: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    vat_registration_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    registered_address: Mapped[str | None] = mapped_column(Text, nullable=True)
    default_price_vat_type: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'included'")
    )
    default_vat_rate: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), nullable=False, server_default=text("7.00")
    )
    vat_filing_mode: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'separate'")
    )
    consolidated_filing_approved: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )


class BranchTaxProfile(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "branch_tax_profiles"
    __table_args__ = (
        CheckConstraint(
            "tax_branch_code ~ '^[0-9]{5}$'",
            name="code_format",
        ),
        CheckConstraint(
            "effective_to IS NULL OR effective_to >= effective_from",
            name="effective_period",
        ),
        UniqueConstraint("branch_id", name="uq_branch_tax_profiles_branch_id"),
        UniqueConstraint(
            "company_id",
            "tax_branch_code",
            name="uq_branch_tax_profiles_company_tax_code",
        ),
        Index("ix_branch_tax_profiles_company_branch", "company_id", "branch_id"),
        Index(
            "uq_branch_tax_profiles_head_office",
            "company_id",
            unique=True,
            postgresql_where=text("is_head_office"),
        ),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True
    )
    branch_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("branches.id"), nullable=False, index=True
    )
    tax_branch_code: Mapped[str] = mapped_column(String(5), nullable=False)
    is_head_office: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    legal_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    registered_address: Mapped[str | None] = mapped_column(Text, nullable=True)
    vat_registration_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    filing_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)


class TaxRateRule(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "tax_rate_rules"
    __table_args__ = (
        CheckConstraint(
            "tax_category IN ('standard', 'zero', 'exempt')",
            name="category",
        ),
        CheckConstraint(
            "price_vat_type IN ('included', 'excluded', 'exempt')",
            name="price_vat_type",
        ),
        CheckConstraint("rate >= 0 AND rate <= 100", name="rate"),
        CheckConstraint(
            "effective_to IS NULL OR effective_to >= effective_from",
            name="effective_period",
        ),
        UniqueConstraint(
            "company_id", "code", "effective_from", name="uq_tax_rate_rules_company_code_start"
        ),
        Index("ix_tax_rate_rules_company_period", "company_id", "effective_from", "effective_to"),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(30), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    tax_category: Mapped[str] = mapped_column(String(20), nullable=False)
    rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    price_vat_type: Mapped[str] = mapped_column(String(20), nullable=False)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
