"""add phase 4 operational handoff

Revision ID: p4handoff0005
Revises: p3device0004
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "p4handoff0005"
down_revision: Union[str, None] = "p3device0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    duplicate_count = op.get_bind().execute(sa.text("""
        SELECT count(*)
        FROM (
            SELECT company_id, entry_type, reference_type, reference_id
            FROM journal_entries
            WHERE reference_type IS NOT NULL AND reference_id IS NOT NULL
            GROUP BY company_id, entry_type, reference_type, reference_id
            HAVING count(*) > 1
        ) duplicate_sources
    """)).scalar_one()
    if duplicate_count:
        raise RuntimeError("Duplicate journal source postings must be reconciled before Phase 4 migration")

    op.create_unique_constraint(
        "uq_journal_entries_source_posting",
        "journal_entries",
        ["company_id", "entry_type", "reference_type", "reference_id"],
    )
    op.create_table(
        "operational_outbox_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("brand_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("contract_version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("aggregate_type", sa.String(length=50), nullable=False),
        sa.Column("aggregate_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("idempotency_key", sa.String(length=200), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.String(length=20), server_default=sa.text("'pending'"), nullable=False),
        sa.Column("attempts", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key", name="uq_operational_outbox_events_idempotency_key"),
    )
    for column in ("company_id", "brand_id", "branch_id", "event_type", "aggregate_id", "status", "created_at"):
        op.create_index(f"ix_operational_outbox_events_{column}", "operational_outbox_events", [column])


def downgrade() -> None:
    op.drop_table("operational_outbox_events")
    op.drop_constraint("uq_journal_entries_source_posting", "journal_entries", type_="unique")
