"""harden integration governance

Revision ID: wp65govern0026
Revises: wp60tenant0025
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "wp65govern0026"
down_revision: Union[str, None] = "wp60tenant0025"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("api_keys", sa.Column("purpose", sa.String(length=255), server_default="integration", nullable=False))
    op.add_column("api_keys", sa.Column("owner_contact", sa.String(length=255), server_default="unassigned", nullable=False))
    op.add_column("api_keys", sa.Column("rotated_from_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key("fk_api_keys_rotated_from_id", "api_keys", "api_keys", ["rotated_from_id"], ["id"])
    op.create_index("ix_api_keys_rotated_from_id", "api_keys", ["rotated_from_id"])

    op.alter_column("webhook_endpoints", "secret", new_column_name="secret_ciphertext", existing_type=sa.String(length=255))
    op.alter_column("webhook_endpoints", "secret_ciphertext", type_=sa.String(length=512), existing_type=sa.String(length=255))
    op.add_column("webhook_endpoints", sa.Column("secret_rotated_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("webhook_endpoints", sa.Column("incoming_source", sa.String(length=50), nullable=True))
    op.create_index(
        "uq_webhook_endpoints_incoming_source",
        "webhook_endpoints",
        ["incoming_source"],
        unique=True,
        postgresql_where=sa.text("incoming_source IS NOT NULL"),
    )

    op.add_column("webhook_deliveries", sa.Column("status", sa.String(length=30), server_default="pending", nullable=False))
    op.add_column("webhook_deliveries", sa.Column("last_error_code", sa.String(length=120), nullable=True))
    op.execute("UPDATE webhook_deliveries SET status = CASE WHEN delivered_at IS NOT NULL THEN 'delivered' WHEN failed_at IS NOT NULL THEN 'retry_scheduled' ELSE 'pending' END")
    op.alter_column("webhook_deliveries", "attempt_count", server_default="0", existing_type=sa.Integer(), nullable=False)
    op.create_index("ix_webhook_deliveries_status", "webhook_deliveries", ["status"])
    op.create_check_constraint(
        "ck_webhook_deliveries_status",
        "webhook_deliveries",
        "status IN ('pending','delivered','retry_scheduled','dead_letter')",
    )

    op.add_column("external_orders", sa.Column("server_total_amount", sa.Numeric(15, 2), nullable=True))
    op.add_column("external_orders", sa.Column("review_reasons", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False))
    op.add_column("external_orders", sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("external_orders", sa.Column("reviewed_by", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key("fk_external_orders_reviewed_by", "external_orders", "users", ["reviewed_by"], ["id"])
    op.create_index("ix_external_orders_reviewed_by", "external_orders", ["reviewed_by"])


def downgrade() -> None:
    op.drop_index("ix_external_orders_reviewed_by", table_name="external_orders")
    op.drop_constraint("fk_external_orders_reviewed_by", "external_orders", type_="foreignkey")
    op.drop_column("external_orders", "reviewed_by")
    op.drop_column("external_orders", "reviewed_at")
    op.drop_column("external_orders", "review_reasons")
    op.drop_column("external_orders", "server_total_amount")

    op.drop_constraint("ck_webhook_deliveries_status", "webhook_deliveries", type_="check")
    op.drop_index("ix_webhook_deliveries_status", table_name="webhook_deliveries")
    op.drop_column("webhook_deliveries", "last_error_code")
    op.drop_column("webhook_deliveries", "status")

    op.drop_index("uq_webhook_endpoints_incoming_source", table_name="webhook_endpoints")
    op.drop_column("webhook_endpoints", "incoming_source")
    op.drop_column("webhook_endpoints", "secret_rotated_at")
    op.alter_column("webhook_endpoints", "secret_ciphertext", type_=sa.String(length=255), existing_type=sa.String(length=512))
    op.alter_column("webhook_endpoints", "secret_ciphertext", new_column_name="secret", existing_type=sa.String(length=255))

    op.drop_index("ix_api_keys_rotated_from_id", table_name="api_keys")
    op.drop_constraint("fk_api_keys_rotated_from_id", "api_keys", type_="foreignkey")
    op.drop_column("api_keys", "rotated_from_id")
    op.drop_column("api_keys", "owner_contact")
    op.drop_column("api_keys", "purpose")
