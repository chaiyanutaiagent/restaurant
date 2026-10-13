from datetime import datetime
import uuid

from sqlalchemy import CheckConstraint, DateTime, JSON, String, Text, UniqueConstraint, Integer
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import UUIDMixin


class DocumentSnapshot(UUIDMixin, Base):
    """Append-only issuance evidence; database triggers prohibit modification."""
    __tablename__ = "document_snapshots"
    __table_args__ = (
        UniqueConstraint("company_id", "document_kind", "source_id", name="uq_document_snapshot_source"),
        CheckConstraint("document_kind IN ('purchase_order', 'goods_receipt', 'supplier_invoice', 'payment_voucher', 'wht_certificate', 'sales_tax_document', 'sales_quotation', 'sales_delivery', 'customer_invoice', 'billing_notice', 'customer_receipt')", name="document_snapshot_kind"),
    )
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    branch_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    document_kind: Mapped[str] = mapped_column(String(40), nullable=False)
    source_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    document_number: Mapped[str] = mapped_column(String(100), nullable=False)
    template_version: Mapped[str] = mapped_column(String(60), nullable=False)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    captured_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    rendered_html: Mapped[str] = mapped_column(Text, nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)


class DocumentEvent(UUIDMixin, Base):
    """Append-only revisions/actions; does not modify financial source records."""
    __tablename__ = "document_events"
    __table_args__ = (UniqueConstraint("company_id", "document_kind", "source_id", "sequence", name="uq_document_event_sequence"),)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    branch_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    document_kind: Mapped[str] = mapped_column(String(40), nullable=False)
    source_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    action: Mapped[str] = mapped_column(String(40), nullable=False)
    actor_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
