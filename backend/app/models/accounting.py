from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
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
    from app.models.user import User


class Account(SoftDeleteMixin, Base):
    __tablename__ = "accounts"
    __table_args__ = (
        UniqueConstraint("company_id", "code", name="uq_accounts_company_id_code"),
        Index("ix_accounts_parent_id", "parent_id"),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companies.id"),
        nullable=False,
        index=True,
    )
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("accounts.id"),
        nullable=True,
    )
    code: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    name_en: Mapped[str | None] = mapped_column(String(255), nullable=True)
    account_type: Mapped[str] = mapped_column(String(20), nullable=False)
    account_subtype: Mapped[str | None] = mapped_column(String(50), nullable=True)
    normal_balance: Mapped[str] = mapped_column(
        String(6),
        nullable=False,
        server_default=text("'debit'"),
    )
    is_header: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    is_system: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))

    company: Mapped["Company"] = relationship("Company")
    parent: Mapped["Account | None"] = relationship(
        "Account",
        remote_side="Account.id",
        back_populates="children",
    )
    children: Mapped[list["Account"]] = relationship(
        "Account",
        back_populates="parent",
        order_by="Account.code.asc()",
    )
    journal_lines: Mapped[list["JournalLine"]] = relationship("JournalLine", back_populates="account")
    balances: Mapped[list["AccountBalance"]] = relationship("AccountBalance", back_populates="account")


class JournalEntry(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "journal_entries"
    __table_args__ = (
        Index("ix_journal_entries_company_entry_number", "company_id", "entry_number"),
        Index("ix_journal_entries_period_year_period_month", "period_year", "period_month"),
        Index("ix_journal_entries_reference_type_reference_id", "reference_type", "reference_id"),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companies.id"),
        nullable=False,
        index=True,
    )
    branch_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("branches.id"),
        nullable=True,
        index=True,
    )
    entry_number: Mapped[str] = mapped_column(String(30), nullable=False, unique=True)
    entry_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    period_year: Mapped[int] = mapped_column(Integer, nullable=False)
    period_month: Mapped[int] = mapped_column(Integer, nullable=False)
    entry_type: Mapped[str] = mapped_column(String(30), nullable=False)
    reference_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    reference_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    is_posted: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    is_reversed: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    reversed_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("journal_entries.id"),
        nullable=True,
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=False,
    )
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    company: Mapped["Company"] = relationship("Company")
    branch: Mapped["Branch | None"] = relationship("Branch")
    creator: Mapped["User"] = relationship("User", foreign_keys=[created_by])
    reversal_entry: Mapped["JournalEntry | None"] = relationship(
        "JournalEntry",
        remote_side="JournalEntry.id",
        uselist=False,
    )
    lines: Mapped[list["JournalLine"]] = relationship(
        "JournalLine",
        back_populates="entry",
        cascade="all, delete-orphan",
        order_by="JournalLine.line_number.asc()",
    )


class JournalLine(UUIDMixin, Base):
    __tablename__ = "journal_lines"
    __table_args__ = (
        CheckConstraint(
            "NOT (debit_amount > 0 AND credit_amount > 0)",
            name="journal_lines_single_side",
        ),
        CheckConstraint(
            "debit_amount >= 0 AND credit_amount >= 0",
            name="journal_lines_non_negative",
        ),
    )

    entry_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("journal_entries.id"),
        nullable=False,
        index=True,
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companies.id"),
        nullable=False,
        index=True,
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("accounts.id"),
        nullable=False,
        index=True,
    )
    line_number: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    debit_amount: Mapped[Decimal] = mapped_column(
        Numeric(15, 2),
        nullable=False,
        server_default=text("0"),
    )
    credit_amount: Mapped[Decimal] = mapped_column(
        Numeric(15, 2),
        nullable=False,
        server_default=text("0"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )

    entry: Mapped["JournalEntry"] = relationship("JournalEntry", back_populates="lines")
    account: Mapped["Account"] = relationship("Account", back_populates="journal_lines")


class AccountBalance(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "account_balances"
    __table_args__ = (
        UniqueConstraint("account_id", "period_year", "period_month", name="uq_account_balances_account_period"),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companies.id"),
        nullable=False,
        index=True,
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("accounts.id"),
        nullable=False,
        index=True,
    )
    period_year: Mapped[int] = mapped_column(Integer, nullable=False)
    period_month: Mapped[int] = mapped_column(Integer, nullable=False)
    opening_balance: Mapped[Decimal] = mapped_column(
        Numeric(15, 2),
        nullable=False,
        server_default=text("0"),
    )
    debit_total: Mapped[Decimal] = mapped_column(
        Numeric(15, 2),
        nullable=False,
        server_default=text("0"),
    )
    credit_total: Mapped[Decimal] = mapped_column(
        Numeric(15, 2),
        nullable=False,
        server_default=text("0"),
    )
    closing_balance: Mapped[Decimal] = mapped_column(
        Numeric(15, 2),
        nullable=False,
        server_default=text("0"),
    )

    company: Mapped["Company"] = relationship("Company")
    account: Mapped["Account"] = relationship("Account", back_populates="balances")
