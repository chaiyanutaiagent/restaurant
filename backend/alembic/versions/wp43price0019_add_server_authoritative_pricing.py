"""add server-authoritative pricing and override audit

Revision ID: wp43price0019
Revises: p16taxops0018
Create Date: 2026-09-20 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "wp43price0019"
down_revision: Union[str, None] = "p16taxops0018"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint(
        op.f("ck_approval_grant_usages_supported_action"),
        "approval_grant_usages",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_approval_grant_usages_supported_action"),
        "approval_grant_usages",
        "action IN ('pos.discount.override', 'pos.price.override', 'pos.sale.void', 'pos.refund.create', 'inventory.stock.adjust')",
    )
    op.add_column("price_lists", sa.Column("brand_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("price_lists", sa.Column("branch_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("price_lists", sa.Column("customer_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("price_lists", sa.Column("channel", sa.String(length=40), nullable=True))
    op.add_column("price_lists", sa.Column("priority", sa.Integer(), server_default=sa.text("0"), nullable=False))
    op.add_column("price_lists", sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False))
    op.add_column("price_lists", sa.Column("price_kind", sa.String(length=20), server_default=sa.text("'standard'"), nullable=False))
    op.add_column("price_lists", sa.Column("promotion_code", sa.String(length=80), nullable=True))
    op.add_column("price_lists", sa.Column("valid_from_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("price_lists", sa.Column("valid_until_at", sa.DateTime(timezone=True), nullable=True))
    op.create_check_constraint(
        op.f("ck_price_lists_supported_price_kind"),
        "price_lists",
        "price_kind IN ('standard', 'promotion')",
    )
    op.create_foreign_key("fk_price_lists_brand_id_brands", "price_lists", "brands", ["brand_id"], ["id"])
    op.create_foreign_key("fk_price_lists_branch_id_branches", "price_lists", "branches", ["branch_id"], ["id"])
    op.create_index("ix_price_lists_brand_id", "price_lists", ["brand_id"])
    op.create_index("ix_price_lists_branch_id", "price_lists", ["branch_id"])
    op.create_index("ix_price_lists_customer_id", "price_lists", ["customer_id"])
    op.create_index("ix_price_lists_channel", "price_lists", ["channel"])
    op.create_index(
        "ix_price_lists_resolution",
        "price_lists",
        ["company_id", "branch_id", "brand_id", "channel", "currency", "is_active"],
    )

    op.add_column("branch_settings", sa.Column("pos_price_override_auto_limit_pct", sa.Numeric(5, 2), server_default=sa.text("10"), nullable=False))
    op.add_column("branch_settings", sa.Column("pos_price_override_auto_limit_amount", sa.Numeric(15, 2), server_default=sa.text("100"), nullable=False))
    op.add_column("branch_settings", sa.Column("pos_price_override_max_deviation_pct", sa.Numeric(5, 2), server_default=sa.text("50"), nullable=False))
    op.add_column("branch_settings", sa.Column("pos_price_override_min_margin_pct", sa.Numeric(6, 2), server_default=sa.text("0"), nullable=False))
    op.add_column("branch_settings", sa.Column("pos_price_override_self_approval", sa.Boolean(), server_default=sa.text("false"), nullable=False))
    op.create_check_constraint(
        op.f("ck_branch_settings_pos_price_override_auto_within_max"),
        "branch_settings",
        "pos_price_override_auto_limit_pct >= 0 AND pos_price_override_auto_limit_pct <= pos_price_override_max_deviation_pct",
    )
    op.create_check_constraint(
        op.f("ck_branch_settings_pos_price_override_max_range"),
        "branch_settings",
        "pos_price_override_max_deviation_pct >= 0 AND pos_price_override_max_deviation_pct <= 100",
    )
    op.create_check_constraint(
        op.f("ck_branch_settings_pos_price_override_auto_amount_nonnegative"),
        "branch_settings",
        "pos_price_override_auto_limit_amount >= 0",
    )
    op.create_check_constraint(
        op.f("ck_branch_settings_pos_price_override_margin_range"),
        "branch_settings",
        "pos_price_override_min_margin_pct >= -100 AND pos_price_override_min_margin_pct <= 100",
    )

    for name, column in (
        ("pricing_quote_id", sa.Column("pricing_quote_id", postgresql.UUID(as_uuid=True), nullable=True)),
        ("pricing_request_hash", sa.Column("pricing_request_hash", sa.String(length=64), nullable=True)),
        ("pricing_calculation_hash", sa.Column("pricing_calculation_hash", sa.String(length=64), nullable=True)),
        ("pricing_calculation_version", sa.Column("pricing_calculation_version", sa.String(length=30), nullable=True)),
        ("pricing_context", sa.Column("pricing_context", postgresql.JSON(astext_type=sa.Text()), nullable=True)),
        ("pricing_snapshot", sa.Column("pricing_snapshot", postgresql.JSON(astext_type=sa.Text()), nullable=True)),
        ("row_version", sa.Column("row_version", sa.Integer(), server_default=sa.text("1"), nullable=False)),
    ):
        op.add_column("sale_orders", column)
    op.create_index("ix_sale_orders_pricing_quote_id", "sale_orders", ["pricing_quote_id"])

    for column in (
        sa.Column("price_source", sa.String(length=30), nullable=True),
        sa.Column("price_list_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("price_list_version", sa.Integer(), nullable=True),
        sa.Column("price_version", sa.String(length=128), nullable=True),
        sa.Column("price_snapshot", postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column("order_discount_share", sa.Numeric(15, 4), server_default=sa.text("0"), nullable=False),
        sa.Column("line_total", sa.Numeric(15, 4), server_default=sa.text("0"), nullable=False),
        sa.Column("price_override_applied", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("price_override_reason", sa.Text(), nullable=True),
    ):
        op.add_column("sale_order_items", column)

    for column in (
        sa.Column("idempotency_key", sa.String(length=100), nullable=True),
        sa.Column("request_hash", sa.String(length=64), nullable=True),
        sa.Column("pricing_calculation_hash", sa.String(length=64), nullable=True),
        sa.Column("pricing_calculation_version", sa.String(length=30), nullable=True),
        sa.Column("pricing_context", postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column("row_version", sa.Integer(), server_default=sa.text("1"), nullable=False),
    ):
        op.add_column("dining_orders", column)
    op.create_unique_constraint(
        "uq_dining_orders_idempotency",
        "dining_orders",
        ["company_id", "branch_id", "idempotency_key"],
    )

    for column in (
        sa.Column("original_price", sa.Numeric(15, 4), server_default=sa.text("0"), nullable=False),
        sa.Column("vat_type", sa.String(length=20), server_default=sa.text("'included'"), nullable=False),
        sa.Column("vat_rate", sa.Numeric(5, 2), server_default=sa.text("7"), nullable=False),
        sa.Column("vat_amount", sa.Numeric(15, 4), server_default=sa.text("0"), nullable=False),
        sa.Column("line_total", sa.Numeric(15, 4), server_default=sa.text("0"), nullable=False),
        sa.Column("price_source", sa.String(length=30), nullable=True),
        sa.Column("price_list_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("price_list_version", sa.Integer(), nullable=True),
        sa.Column("price_version", sa.String(length=128), nullable=True),
        sa.Column("price_snapshot", postgresql.JSON(astext_type=sa.Text()), nullable=True),
    ):
        op.add_column("dining_order_items", column)

    op.create_table(
        "price_calculations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("brand_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("operation", sa.String(length=30), server_default=sa.text("'calculate'"), nullable=False),
        sa.Column("channel", sa.String(length=40), nullable=False),
        sa.Column("currency", sa.String(length=3), server_default=sa.text("'THB'"), nullable=False),
        sa.Column("idempotency_key", sa.String(length=100), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("calculation_hash", sa.String(length=64), nullable=False),
        sa.Column("calculation_version", sa.String(length=30), nullable=False),
        sa.Column("cart_version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("price_list_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("price_list_version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("context_json", postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column("result_json", postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.String(length=20), server_default=sa.text("'quoted'"), nullable=False),
        sa.Column("consumed_order_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["brand_id"], ["brands.id"]),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"]),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.ForeignKeyConstraint(["price_list_id"], ["price_lists.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id", "branch_id", "operation", "idempotency_key", name="uq_price_calculations_idempotency"),
    )
    op.create_index("ix_price_calculations_context", "price_calculations", ["company_id", "branch_id", "created_at"])

    op.create_table(
        "price_override_audits",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("brand_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("order_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("order_item_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("requester_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("approver_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("approval_grant_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("original_unit_price", sa.Numeric(15, 4), nullable=False),
        sa.Column("applied_unit_price", sa.Numeric(15, 4), nullable=False),
        sa.Column("deviation_pct", sa.Numeric(9, 4), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("reason_code", sa.String(length=40), server_default=sa.text("'other'"), nullable=False),
        sa.Column("approval_mode", sa.String(length=30), nullable=False),
        sa.Column("policy_snapshot", postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column("price_snapshot", postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["brand_id"], ["brands.id"]),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"]),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.ForeignKeyConstraint(["order_id"], ["sale_orders.id"]),
        sa.ForeignKeyConstraint(["order_item_id"], ["sale_order_items.id"]),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
        sa.ForeignKeyConstraint(["requester_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["approver_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_price_override_audits_order", "price_override_audits", ["company_id", "order_id", "created_at"])
    op.create_index("ix_price_override_audits_product", "price_override_audits", ["company_id", "product_id", "created_at"])
    op.execute(
        """
        CREATE FUNCTION prevent_price_override_audit_mutation()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            RAISE EXCEPTION 'price_override_audits is append-only' USING ERRCODE = '55000';
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_price_override_audits_append_only
        BEFORE UPDATE OR DELETE ON price_override_audits
        FOR EACH ROW EXECUTE FUNCTION prevent_price_override_audit_mutation()
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_price_override_audits_append_only ON price_override_audits")
    op.execute("DROP FUNCTION IF EXISTS prevent_price_override_audit_mutation()")
    op.drop_index("ix_price_override_audits_product", table_name="price_override_audits")
    op.drop_index("ix_price_override_audits_order", table_name="price_override_audits")
    op.drop_table("price_override_audits")
    op.drop_index("ix_price_calculations_context", table_name="price_calculations")
    op.drop_table("price_calculations")

    for name in ("price_snapshot", "price_version", "price_list_version", "price_list_id", "price_source", "line_total", "vat_amount", "vat_rate", "vat_type", "original_price"):
        op.drop_column("dining_order_items", name)
    op.drop_constraint("uq_dining_orders_idempotency", "dining_orders", type_="unique")
    for name in ("row_version", "pricing_context", "pricing_calculation_version", "pricing_calculation_hash", "request_hash", "idempotency_key"):
        op.drop_column("dining_orders", name)
    for name in ("price_override_reason", "price_override_applied", "line_total", "order_discount_share", "price_snapshot", "price_version", "price_list_version", "price_list_id", "price_source"):
        op.drop_column("sale_order_items", name)
    op.drop_index("ix_sale_orders_pricing_quote_id", table_name="sale_orders")
    for name in ("row_version", "pricing_snapshot", "pricing_context", "pricing_calculation_version", "pricing_calculation_hash", "pricing_request_hash", "pricing_quote_id"):
        op.drop_column("sale_orders", name)

    op.drop_constraint(op.f("ck_branch_settings_pos_price_override_margin_range"), "branch_settings", type_="check")
    op.drop_constraint(op.f("ck_branch_settings_pos_price_override_auto_amount_nonnegative"), "branch_settings", type_="check")
    op.drop_constraint(op.f("ck_branch_settings_pos_price_override_max_range"), "branch_settings", type_="check")
    op.drop_constraint(op.f("ck_branch_settings_pos_price_override_auto_within_max"), "branch_settings", type_="check")
    for name in ("pos_price_override_self_approval", "pos_price_override_min_margin_pct", "pos_price_override_max_deviation_pct", "pos_price_override_auto_limit_amount", "pos_price_override_auto_limit_pct"):
        op.drop_column("branch_settings", name)

    op.drop_index("ix_price_lists_resolution", table_name="price_lists")
    op.drop_index("ix_price_lists_channel", table_name="price_lists")
    op.drop_index("ix_price_lists_customer_id", table_name="price_lists")
    op.drop_index("ix_price_lists_branch_id", table_name="price_lists")
    op.drop_index("ix_price_lists_brand_id", table_name="price_lists")
    op.drop_constraint("fk_price_lists_branch_id_branches", "price_lists", type_="foreignkey")
    op.drop_constraint("fk_price_lists_brand_id_brands", "price_lists", type_="foreignkey")
    op.drop_constraint(op.f("ck_price_lists_supported_price_kind"), "price_lists", type_="check")
    for name in ("valid_until_at", "valid_from_at", "promotion_code", "price_kind", "version", "priority", "channel", "customer_id", "branch_id", "brand_id"):
        op.drop_column("price_lists", name)
    op.drop_constraint(
        op.f("ck_approval_grant_usages_supported_action"),
        "approval_grant_usages",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_approval_grant_usages_supported_action"),
        "approval_grant_usages",
        "action IN ('pos.discount.override', 'pos.sale.void', 'pos.refund.create', 'inventory.stock.adjust')",
    )
