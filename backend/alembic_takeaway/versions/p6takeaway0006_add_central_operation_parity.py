"""add Takeaway central operation parity

Revision ID: p6takeaway0006
Revises: p6takeaway0005
Create Date: 2026-09-17 10:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "p6takeaway0006"
down_revision: Union[str, None] = "p6takeaway0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("takeaway_central_orders", sa.Column("discrepancy_status", sa.String(30), nullable=False, server_default="none"))
    op.add_column("takeaway_central_orders", sa.Column("receipt_note", sa.Text(), nullable=True))
    for name in ("approved_qty", "packed_qty", "shipped_qty", "received_qty"):
        op.add_column("takeaway_central_order_items", sa.Column(name, sa.Numeric(15, 4), nullable=True))
    op.add_column("takeaway_central_order_items", sa.Column("discrepancy_qty", sa.Numeric(15, 4), nullable=False, server_default="0"))
    op.add_column("takeaway_central_order_items", sa.Column("resolution_note", sa.Text(), nullable=True))

    op.add_column("takeaway_production_batches", sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("takeaway_production_batches", sa.Column("note", sa.Text(), nullable=True))
    op.add_column("takeaway_production_lines", sa.Column("waste_qty", sa.Numeric(15, 4), nullable=False, server_default="0"))
    op.add_column("takeaway_production_lines", sa.Column("unit_cost", sa.Numeric(15, 4), nullable=False, server_default="0"))

    op.add_column("takeaway_transfers", sa.Column("discrepancy_status", sa.String(30), nullable=False, server_default="none"))
    op.add_column("takeaway_transfers", sa.Column("note", sa.Text(), nullable=True))
    op.add_column("takeaway_transfer_items", sa.Column("discrepancy_qty", sa.Numeric(15, 4), nullable=False, server_default="0"))
    op.add_column("takeaway_transfer_items", sa.Column("resolution_note", sa.Text(), nullable=True))

    op.create_table(
        "takeaway_credit_topup_requests",
        sa.Column("company_id", sa.UUID(), nullable=False),
        sa.Column("brand_id", sa.UUID(), nullable=False),
        sa.Column("branch_id", sa.UUID(), nullable=False),
        sa.Column("account_id", sa.UUID(), nullable=False),
        sa.Column("amount", sa.Numeric(15, 2), nullable=False),
        sa.Column("payment_method", sa.String(30), nullable=False),
        sa.Column("payment_reference", sa.String(200), nullable=True),
        sa.Column("evidence_url", sa.String(500), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("idempotency_key", sa.String(180), nullable=False),
        sa.Column("requested_by", sa.UUID(), nullable=False),
        sa.Column("reviewed_by", sa.UUID(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("review_note", sa.Text(), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("amount > 0", name="ck_takeaway_credit_topup_amount"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("account_id", "idempotency_key", name="uq_takeaway_credit_topup_idempotency"),
    )
    op.create_index("ix_takeaway_credit_topup_requests_account_id", "takeaway_credit_topup_requests", ["account_id"])
    op.create_table(
        "takeaway_credit_payment_configs",
        sa.Column("company_id", sa.UUID(), nullable=False),
        sa.Column("brand_id", sa.UUID(), nullable=False),
        sa.Column("promptpay_label", sa.String(200), nullable=True),
        sa.Column("promptpay_payload", sa.Text(), nullable=True),
        sa.Column("bank_name", sa.String(120), nullable=True),
        sa.Column("bank_account_name", sa.String(200), nullable=True),
        sa.Column("bank_account_number", sa.String(80), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id", "brand_id", name="uq_takeaway_credit_payment_config"),
    )


def downgrade() -> None:
    op.drop_table("takeaway_credit_payment_configs")
    op.drop_index("ix_takeaway_credit_topup_requests_account_id", table_name="takeaway_credit_topup_requests")
    op.drop_table("takeaway_credit_topup_requests")
    op.drop_column("takeaway_transfer_items", "resolution_note")
    op.drop_column("takeaway_transfer_items", "discrepancy_qty")
    op.drop_column("takeaway_transfers", "note")
    op.drop_column("takeaway_transfers", "discrepancy_status")
    op.drop_column("takeaway_production_lines", "unit_cost")
    op.drop_column("takeaway_production_lines", "waste_qty")
    op.drop_column("takeaway_production_batches", "note")
    op.drop_column("takeaway_production_batches", "cancelled_at")
    op.drop_column("takeaway_central_order_items", "resolution_note")
    op.drop_column("takeaway_central_order_items", "discrepancy_qty")
    for name in ("received_qty", "shipped_qty", "packed_qty", "approved_qty"):
        op.drop_column("takeaway_central_order_items", name)
    op.drop_column("takeaway_central_orders", "receipt_note")
    op.drop_column("takeaway_central_orders", "discrepancy_status")
