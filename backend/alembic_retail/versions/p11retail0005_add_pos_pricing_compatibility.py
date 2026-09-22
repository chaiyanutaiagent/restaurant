"""add POS pricing compatibility to the Retail boundary

Revision ID: p11retail0005
Revises: p10retail0004
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "p11retail0005"
down_revision: Union[str, None] = "p10retail0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    for column in (
        sa.Column("brand_id", sa.UUID(), nullable=True),
        sa.Column("branch_id", sa.UUID(), nullable=True),
        sa.Column("customer_id", sa.UUID(), nullable=True),
        sa.Column("channel", sa.String(length=40), nullable=True),
        sa.Column("priority", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("price_kind", sa.String(length=20), nullable=False, server_default=sa.text("'standard'")),
        sa.Column("promotion_code", sa.String(length=80), nullable=True),
        sa.Column("valid_from_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("valid_until_at", sa.DateTime(timezone=True), nullable=True),
    ):
        op.add_column("price_lists", column)
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

    for column in (
        sa.Column("pos_price_override_auto_limit_pct", sa.Numeric(5, 2), nullable=False, server_default=sa.text("10")),
        sa.Column("pos_price_override_auto_limit_amount", sa.Numeric(15, 2), nullable=False, server_default=sa.text("100")),
        sa.Column("pos_price_override_max_deviation_pct", sa.Numeric(5, 2), nullable=False, server_default=sa.text("50")),
        sa.Column("pos_price_override_min_margin_pct", sa.Numeric(6, 2), nullable=False, server_default=sa.text("0")),
        sa.Column("pos_price_override_self_approval", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("pos_hold_draft_ttl_minutes", sa.Integer(), nullable=False, server_default=sa.text("120")),
    ):
        op.add_column("branch_settings", column)
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
    op.create_check_constraint(
        op.f("ck_branch_settings_pos_hold_draft_ttl_range"),
        "branch_settings",
        "pos_hold_draft_ttl_minutes >= 15 AND pos_hold_draft_ttl_minutes <= 1440",
    )

    for column in (
        sa.Column("pricing_quote_id", sa.UUID(), nullable=True),
        sa.Column("pricing_request_hash", sa.String(length=64), nullable=True),
        sa.Column("pricing_calculation_hash", sa.String(length=64), nullable=True),
        sa.Column("pricing_calculation_version", sa.String(length=30), nullable=True),
        sa.Column("pricing_context", sa.JSON(), nullable=True),
        sa.Column("pricing_snapshot", sa.JSON(), nullable=True),
        sa.Column("row_version", sa.Integer(), nullable=False, server_default=sa.text("1")),
    ):
        op.add_column("sale_orders", column)
    op.create_index("ix_sale_orders_pricing_quote_id", "sale_orders", ["pricing_quote_id"])

    for column in (
        sa.Column("price_source", sa.String(length=30), nullable=True),
        sa.Column("price_list_id", sa.UUID(), nullable=True),
        sa.Column("price_list_version", sa.Integer(), nullable=True),
        sa.Column("price_version", sa.String(length=128), nullable=True),
        sa.Column("price_snapshot", sa.JSON(), nullable=True),
        sa.Column("order_discount_share", sa.Numeric(15, 4), nullable=False, server_default=sa.text("0")),
        sa.Column("line_total", sa.Numeric(15, 4), nullable=False, server_default=sa.text("0")),
        sa.Column("price_override_applied", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("price_override_reason", sa.Text(), nullable=True),
    ):
        op.add_column("sale_order_items", column)

    for column in (
        sa.Column("currency", sa.String(length=3), nullable=False, server_default=sa.text("'THB'")),
        sa.Column("provider_name", sa.String(length=40), nullable=True),
        sa.Column("provider_payment_ref", sa.String(length=255), nullable=True),
        sa.Column("settlement_state", sa.String(length=30), nullable=False, server_default=sa.text("'unknown'")),
        sa.Column("refund_operation_id", sa.UUID(), nullable=True),
        sa.Column("provider_refund_state", sa.String(length=30), nullable=True),
    ):
        op.add_column("payments", column)
    op.create_index("ix_payments_refund_operation_id", "payments", ["refund_operation_id"])

    op.create_table(
        "price_override_audits",
        sa.Column("company_id", sa.UUID(), nullable=False),
        sa.Column("brand_id", sa.UUID(), nullable=True),
        sa.Column("branch_id", sa.UUID(), nullable=False),
        sa.Column("order_id", sa.UUID(), nullable=False),
        sa.Column("order_item_id", sa.UUID(), nullable=False),
        sa.Column("product_id", sa.UUID(), nullable=False),
        sa.Column("requester_id", sa.UUID(), nullable=False),
        sa.Column("approver_id", sa.UUID(), nullable=False),
        sa.Column("approval_grant_id", sa.UUID(), nullable=True),
        sa.Column("original_unit_price", sa.Numeric(15, 4), nullable=False),
        sa.Column("applied_unit_price", sa.Numeric(15, 4), nullable=False),
        sa.Column("deviation_pct", sa.Numeric(9, 4), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("reason_code", sa.String(length=40), nullable=False, server_default=sa.text("'other'")),
        sa.Column("approval_mode", sa.String(length=30), nullable=False),
        sa.Column("policy_snapshot", sa.JSON(), nullable=False),
        sa.Column("price_snapshot", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], name=op.f("fk_price_override_audits_company_id_companies")),
        sa.ForeignKeyConstraint(["brand_id"], ["brands.id"], name=op.f("fk_price_override_audits_brand_id_brands")),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"], name=op.f("fk_price_override_audits_branch_id_branches")),
        sa.ForeignKeyConstraint(["order_id"], ["sale_orders.id"], name=op.f("fk_price_override_audits_order_id_sale_orders")),
        sa.ForeignKeyConstraint(["order_item_id"], ["sale_order_items.id"], name=op.f("fk_price_override_audits_order_item_id_sale_order_items")),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], name=op.f("fk_price_override_audits_product_id_products")),
        sa.ForeignKeyConstraint(["requester_id"], ["users.id"], name=op.f("fk_price_override_audits_requester_id_users")),
        sa.ForeignKeyConstraint(["approver_id"], ["users.id"], name=op.f("fk_price_override_audits_approver_id_users")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_price_override_audits")),
    )
    op.create_index(
        "ix_price_override_audits_order",
        "price_override_audits",
        ["company_id", "order_id", "created_at"],
    )
    op.create_index(
        "ix_price_override_audits_product",
        "price_override_audits",
        ["company_id", "product_id", "created_at"],
    )
    op.execute(
        """
        CREATE FUNCTION prevent_retail_price_override_audit_mutation()
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
        CREATE TRIGGER trg_retail_price_override_audits_append_only
        BEFORE UPDATE OR DELETE ON price_override_audits
        FOR EACH ROW EXECUTE FUNCTION prevent_retail_price_override_audit_mutation()
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_retail_price_override_audits_append_only ON price_override_audits")
    op.execute("DROP FUNCTION IF EXISTS prevent_retail_price_override_audit_mutation()")
    op.drop_index("ix_price_override_audits_product", table_name="price_override_audits")
    op.drop_index("ix_price_override_audits_order", table_name="price_override_audits")
    op.drop_table("price_override_audits")

    op.drop_index("ix_payments_refund_operation_id", table_name="payments")
    for name in (
        "provider_refund_state",
        "refund_operation_id",
        "settlement_state",
        "provider_payment_ref",
        "provider_name",
        "currency",
    ):
        op.drop_column("payments", name)

    for name in (
        "price_override_reason",
        "price_override_applied",
        "line_total",
        "order_discount_share",
        "price_snapshot",
        "price_version",
        "price_list_version",
        "price_list_id",
        "price_source",
    ):
        op.drop_column("sale_order_items", name)

    op.drop_index("ix_sale_orders_pricing_quote_id", table_name="sale_orders")
    for name in (
        "row_version",
        "pricing_snapshot",
        "pricing_context",
        "pricing_calculation_version",
        "pricing_calculation_hash",
        "pricing_request_hash",
        "pricing_quote_id",
    ):
        op.drop_column("sale_orders", name)

    for constraint in (
        "ck_branch_settings_pos_hold_draft_ttl_range",
        "ck_branch_settings_pos_price_override_margin_range",
        "ck_branch_settings_pos_price_override_auto_amount_nonnegative",
        "ck_branch_settings_pos_price_override_max_range",
        "ck_branch_settings_pos_price_override_auto_within_max",
    ):
        op.drop_constraint(op.f(constraint), "branch_settings", type_="check")
    for name in (
        "pos_hold_draft_ttl_minutes",
        "pos_price_override_self_approval",
        "pos_price_override_min_margin_pct",
        "pos_price_override_max_deviation_pct",
        "pos_price_override_auto_limit_amount",
        "pos_price_override_auto_limit_pct",
    ):
        op.drop_column("branch_settings", name)

    op.drop_index("ix_price_lists_resolution", table_name="price_lists")
    op.drop_index("ix_price_lists_channel", table_name="price_lists")
    op.drop_index("ix_price_lists_customer_id", table_name="price_lists")
    op.drop_index("ix_price_lists_branch_id", table_name="price_lists")
    op.drop_index("ix_price_lists_brand_id", table_name="price_lists")
    op.drop_constraint("fk_price_lists_branch_id_branches", "price_lists", type_="foreignkey")
    op.drop_constraint("fk_price_lists_brand_id_brands", "price_lists", type_="foreignkey")
    op.drop_constraint(op.f("ck_price_lists_supported_price_kind"), "price_lists", type_="check")
    for name in (
        "valid_until_at",
        "valid_from_at",
        "promotion_code",
        "price_kind",
        "version",
        "priority",
        "channel",
        "customer_id",
        "branch_id",
        "brand_id",
    ):
        op.drop_column("price_lists", name)
