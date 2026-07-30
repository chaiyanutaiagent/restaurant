"""add_api_integration

Revision ID: 20f2b8ef1375
Revises: 4bb56123b795
Create Date: 2026-05-15 14:33:12.781959

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20f2b8ef1375"
down_revision: Union[str, None] = "4bb56123b795"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "webhook_endpoints",
        sa.Column("company_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("url", sa.String(length=500), nullable=False),
        sa.Column("events", sa.JSON(), server_default=sa.text("'[]'::json"), nullable=False),
        sa.Column("secret", sa.String(length=255), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("last_triggered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], name=op.f("fk_webhook_endpoints_company_id_companies")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_webhook_endpoints")),
    )
    op.create_index(op.f("ix_webhook_endpoints_company_id"), "webhook_endpoints", ["company_id"], unique=False)

    op.create_table(
        "api_keys",
        sa.Column("company_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("key_prefix", sa.String(length=8), nullable=False),
        sa.Column("key_hash", sa.String(length=255), nullable=False),
        sa.Column("scopes", sa.JSON(), server_default=sa.text("'[]'::json"), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.UUID(), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_by", sa.UUID(), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], name=op.f("fk_api_keys_company_id_companies")),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], name=op.f("fk_api_keys_created_by_users")),
        sa.ForeignKeyConstraint(["revoked_by"], ["users.id"], name=op.f("fk_api_keys_revoked_by_users")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_api_keys")),
    )
    op.create_index(op.f("ix_api_keys_company_id"), "api_keys", ["company_id"], unique=False)
    op.create_index("ix_api_keys_company_id_key_prefix", "api_keys", ["company_id", "key_prefix"], unique=False)

    op.create_table(
        "webhook_deliveries",
        sa.Column("webhook_id", sa.UUID(), nullable=False),
        sa.Column("company_id", sa.UUID(), nullable=False),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("response_status", sa.Integer(), nullable=True),
        sa.Column("response_body", sa.Text(), nullable=True),
        sa.Column("attempt_count", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], name=op.f("fk_webhook_deliveries_company_id_companies")),
        sa.ForeignKeyConstraint(["webhook_id"], ["webhook_endpoints.id"], name=op.f("fk_webhook_deliveries_webhook_id_webhook_endpoints")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_webhook_deliveries")),
    )
    op.create_index(op.f("ix_webhook_deliveries_company_id"), "webhook_deliveries", ["company_id"], unique=False)
    op.create_index("ix_webhook_deliveries_event_type", "webhook_deliveries", ["event_type"], unique=False)
    op.create_index(op.f("ix_webhook_deliveries_webhook_id"), "webhook_deliveries", ["webhook_id"], unique=False)
    op.create_index("ix_webhook_deliveries_webhook_id_created_at", "webhook_deliveries", ["webhook_id", "created_at"], unique=False)

    op.create_table(
        "external_orders",
        sa.Column("company_id", sa.UUID(), nullable=False),
        sa.Column("source", sa.String(length=50), server_default=sa.text("'blifehealthy'"), nullable=False),
        sa.Column("external_order_id", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=20), server_default=sa.text("'pending'"), nullable=False),
        sa.Column("customer_name", sa.String(length=255), nullable=True),
        sa.Column("customer_phone", sa.String(length=20), nullable=True),
        sa.Column("customer_email", sa.String(length=255), nullable=True),
        sa.Column("customer_address", sa.Text(), nullable=True),
        sa.Column("items_json", sa.JSON(), nullable=False),
        sa.Column("total_amount", sa.Numeric(precision=15, scale=2), nullable=False),
        sa.Column("payment_method", sa.String(length=50), nullable=True),
        sa.Column("payment_status", sa.String(length=20), nullable=True),
        sa.Column("sale_order_id", sa.UUID(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("raw_payload", sa.JSON(), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], name=op.f("fk_external_orders_company_id_companies")),
        sa.ForeignKeyConstraint(["sale_order_id"], ["sale_orders.id"], name=op.f("fk_external_orders_sale_order_id_sale_orders")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_external_orders")),
        sa.UniqueConstraint("company_id", "source", "external_order_id", name="uq_external_orders_company_source_external_order_id"),
    )
    op.create_index(op.f("ix_external_orders_company_id"), "external_orders", ["company_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_external_orders_company_id"), table_name="external_orders")
    op.drop_table("external_orders")
    op.drop_index("ix_webhook_deliveries_webhook_id_created_at", table_name="webhook_deliveries")
    op.drop_index(op.f("ix_webhook_deliveries_webhook_id"), table_name="webhook_deliveries")
    op.drop_index("ix_webhook_deliveries_event_type", table_name="webhook_deliveries")
    op.drop_index(op.f("ix_webhook_deliveries_company_id"), table_name="webhook_deliveries")
    op.drop_table("webhook_deliveries")
    op.drop_index("ix_api_keys_company_id_key_prefix", table_name="api_keys")
    op.drop_index(op.f("ix_api_keys_company_id"), table_name="api_keys")
    op.drop_table("api_keys")
    op.drop_index(op.f("ix_webhook_endpoints_company_id"), table_name="webhook_endpoints")
    op.drop_table("webhook_endpoints")
