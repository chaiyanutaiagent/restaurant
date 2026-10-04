"""add provider refund and synthetic credit note orchestration

Revision ID: wp46refund0022
Revises: wp45cancel0021
Create Date: 2026-09-20 23:30:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "wp46refund0022"
down_revision: Union[str, None] = "wp45cancel0021"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _append_only(table_name: str) -> None:
    function_name = f"prevent_{table_name}_mutation"
    op.execute(f"""
        CREATE FUNCTION {function_name}() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN RAISE EXCEPTION '{table_name} is append-only' USING ERRCODE = '55000'; END; $$
    """)
    op.execute(f"""
        CREATE TRIGGER trg_{table_name}_append_only BEFORE UPDATE OR DELETE ON {table_name}
        FOR EACH ROW EXECUTE FUNCTION {function_name}()
    """)


def upgrade() -> None:
    op.create_table(
        "refund_quotes",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("order_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("requester_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("shift_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(20), server_default=sa.text("'active'"), nullable=False),
        sa.Column("currency", sa.String(3), server_default=sa.text("'THB'"), nullable=False),
        sa.Column("order_version", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.String(100), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("quote_hash", sa.String(64), nullable=False),
        sa.Column("items_snapshot", postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column("payment_snapshot", postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column("totals_snapshot", postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column("policy_snapshot", postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("status IN ('active','consumed','expired','cancelled')", name="ck_refund_quotes_status"),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"]),
        sa.ForeignKeyConstraint(["order_id"], ["sale_orders.id"]),
        sa.ForeignKeyConstraint(["requester_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["shift_id"], ["cashier_shifts.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id", "branch_id", "requester_id", "idempotency_key", name="uq_refund_quotes_idempotency"),
    )
    for name, cols in (
        ("ix_refund_quotes_company_id", ["company_id"]), ("ix_refund_quotes_branch_id", ["branch_id"]),
        ("ix_refund_quotes_order_id", ["order_id"]), ("ix_refund_quotes_requester_id", ["requester_id"]),
        ("ix_refund_quotes_shift_id", ["shift_id"]), ("ix_refund_quotes_order_status", ["order_id", "status", "expires_at"]),
    ):
        op.create_index(name, "refund_quotes", cols)

    op.create_table(
        "refund_operations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("order_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("quote_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("shift_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("requester_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("approver_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("approval_grant_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.String(30), server_default=sa.text("'requested'"), nullable=False),
        sa.Column("reason_code", sa.String(50), nullable=False),
        sa.Column("reason_note", sa.Text(), nullable=True),
        sa.Column("currency", sa.String(3), server_default=sa.text("'THB'"), nullable=False),
        sa.Column("subtotal_amount", sa.Numeric(15, 2), nullable=False),
        sa.Column("discount_amount", sa.Numeric(15, 2), nullable=False),
        sa.Column("vat_amount", sa.Numeric(15, 2), nullable=False),
        sa.Column("rounding_amount", sa.Numeric(15, 2), server_default=sa.text("0"), nullable=False),
        sa.Column("total_amount", sa.Numeric(15, 2), nullable=False),
        sa.Column("stock_disposition", sa.String(20), server_default=sa.text("'none'"), nullable=False),
        sa.Column("provider_scenario", sa.String(40), server_default=sa.text("'succeeded'"), nullable=False),
        sa.Column("approval_snapshot", postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column("idempotency_key", sa.String(100), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("row_version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("failure_code", sa.String(80), nullable=True),
        sa.Column("failure_message", sa.Text(), nullable=True),
        sa.Column("finalized_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("tax_completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("status IN ('requested','processing','cash_due','succeeded','failed','unknown','needs_reconciliation','tax_pending','completed')", name="ck_refund_operations_status"),
        sa.CheckConstraint("stock_disposition IN ('none','sellable')", name="ck_refund_operations_stock_disposition"),
        sa.CheckConstraint("total_amount > 0", name="ck_refund_operations_total_positive"),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]), sa.ForeignKeyConstraint(["branch_id"], ["branches.id"]),
        sa.ForeignKeyConstraint(["order_id"], ["sale_orders.id"]), sa.ForeignKeyConstraint(["quote_id"], ["refund_quotes.id"]),
        sa.ForeignKeyConstraint(["shift_id"], ["cashier_shifts.id"]), sa.ForeignKeyConstraint(["requester_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["approver_id"], ["users.id"]), sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("quote_id", name="uq_refund_operations_quote_id"),
        sa.UniqueConstraint("company_id", "branch_id", "requester_id", "idempotency_key", name="uq_refund_operations_idempotency"),
    )
    for name, cols in (
        ("ix_refund_operations_company_id", ["company_id"]), ("ix_refund_operations_branch_id", ["branch_id"]),
        ("ix_refund_operations_order_id", ["order_id"]), ("ix_refund_operations_shift_id", ["shift_id"]),
        ("ix_refund_operations_shift_status", ["shift_id", "status", "created_at"]),
        ("ix_refund_operations_order_status", ["order_id", "status", "created_at"]),
    ):
        op.create_index(name, "refund_operations", cols)

    op.create_table(
        "refund_operation_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("operation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sale_order_item_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("variant_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("product_name", sa.String(500), nullable=False),
        sa.Column("quantity", sa.Numeric(15, 4), nullable=False),
        sa.Column("subtotal_amount", sa.Numeric(15, 2), nullable=False),
        sa.Column("discount_amount", sa.Numeric(15, 2), nullable=False),
        sa.Column("vat_amount", sa.Numeric(15, 2), nullable=False),
        sa.Column("total_amount", sa.Numeric(15, 2), nullable=False),
        sa.Column("vat_type", sa.String(20), nullable=False), sa.Column("vat_rate", sa.Numeric(5, 2), nullable=False),
        sa.Column("stock_disposition", sa.String(20), server_default=sa.text("'none'"), nullable=False),
        sa.Column("stock_movement_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("loyalty_reversal_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("quantity > 0", name="ck_refund_operation_items_quantity"),
        sa.ForeignKeyConstraint(["operation_id"], ["refund_operations.id"]), sa.ForeignKeyConstraint(["sale_order_item_id"], ["sale_order_items.id"]),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"]), sa.ForeignKeyConstraint(["variant_id"], ["product_variants.id"]),
        sa.ForeignKeyConstraint(["stock_movement_id"], ["stock_movements.id"]), sa.ForeignKeyConstraint(["loyalty_reversal_id"], ["points_transactions.id"]),
        sa.PrimaryKeyConstraint("id"), sa.UniqueConstraint("operation_id", "sale_order_item_id", name="uq_refund_operation_items_line"),
    )
    op.create_index("ix_refund_operation_items_operation_id", "refund_operation_items", ["operation_id"])

    op.create_table(
        "refund_payment_legs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False), sa.Column("operation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("original_payment_id", postgresql.UUID(as_uuid=True), nullable=False), sa.Column("payment_method", sa.String(30), nullable=False),
        sa.Column("leg_type", sa.String(20), nullable=False), sa.Column("provider_name", sa.String(40), nullable=True),
        sa.Column("provider_payment_ref", sa.String(255), nullable=True), sa.Column("amount", sa.Numeric(15, 2), nullable=False),
        sa.Column("currency", sa.String(3), server_default=sa.text("'THB'"), nullable=False),
        sa.Column("status", sa.String(30), server_default=sa.text("'requested'"), nullable=False),
        sa.Column("provider_refund_ref", sa.String(255), nullable=True), sa.Column("attempt_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("last_event_sequence", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("last_error_code", sa.String(80), nullable=True), sa.Column("last_error_message", sa.Text(), nullable=True),
        sa.Column("succeeded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("leg_type IN ('cash','provider')", name="ck_refund_payment_legs_type"),
        sa.CheckConstraint("status IN ('requested','processing','cash_due','succeeded','failed','unknown')", name="ck_refund_payment_legs_status"),
        sa.CheckConstraint("amount > 0", name="ck_refund_payment_legs_amount"),
        sa.ForeignKeyConstraint(["operation_id"], ["refund_operations.id"]), sa.ForeignKeyConstraint(["original_payment_id"], ["payments.id"]),
        sa.PrimaryKeyConstraint("id"), sa.UniqueConstraint("operation_id", "original_payment_id", name="uq_refund_payment_legs_original"),
    )
    op.create_index("ix_refund_payment_legs_operation_id", "refund_payment_legs", ["operation_id"])
    op.create_index("ix_refund_payment_legs_original_payment_id", "refund_payment_legs", ["original_payment_id"])

    op.create_table(
        "provider_refund_attempts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False), sa.Column("payment_leg_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("attempt_no", sa.Integer(), nullable=False), sa.Column("operation_kind", sa.String(20), nullable=False),
        sa.Column("request_id", sa.String(120), nullable=False), sa.Column("request_snapshot", postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column("response_snapshot", postgresql.JSON(astext_type=sa.Text()), nullable=False), sa.Column("result_state", sa.String(30), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["payment_leg_id"], ["refund_payment_legs.id"]), sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("request_id"), sa.UniqueConstraint("payment_leg_id", "attempt_no", name="uq_provider_refund_attempt_no"),
    )
    op.create_index("ix_provider_refund_attempts_payment_leg_id", "provider_refund_attempts", ["payment_leg_id"])

    op.create_table(
        "provider_refund_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False), sa.Column("payment_leg_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider_name", sa.String(40), nullable=False), sa.Column("provider_event_id", sa.String(160), nullable=False),
        sa.Column("event_sequence", sa.Integer(), nullable=False), sa.Column("event_type", sa.String(80), nullable=False),
        sa.Column("signature_valid", sa.Boolean(), nullable=False), sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("payload_snapshot", postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column("applied", sa.Boolean(), server_default=sa.text("false"), nullable=False), sa.Column("ignored_reason", sa.String(120), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["payment_leg_id"], ["refund_payment_legs.id"]), sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider_name", "provider_event_id", name="uq_provider_refund_events_provider_event"),
    )
    op.create_index("ix_provider_refund_events_payment_leg_id", "provider_refund_events", ["payment_leg_id"])

    op.create_table(
        "refund_tax_links",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False), sa.Column("operation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("original_document_id", postgresql.UUID(as_uuid=True), nullable=True), sa.Column("credit_note_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.String(30), server_default=sa.text("'pending'"), nullable=False), sa.Column("idempotency_key", sa.String(120), nullable=False),
        sa.Column("retry_count", sa.Integer(), server_default=sa.text("0"), nullable=False), sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("status IN ('pending','not_required','issued','failed')", name="ck_refund_tax_links_status"),
        sa.ForeignKeyConstraint(["operation_id"], ["refund_operations.id"]),
        sa.ForeignKeyConstraint(["original_document_id"], ["tax_documents.id"]), sa.ForeignKeyConstraint(["credit_note_id"], ["tax_documents.id"]),
        sa.PrimaryKeyConstraint("id"), sa.UniqueConstraint("operation_id", name="uq_refund_tax_links_operation"),
        sa.UniqueConstraint("credit_note_id"), sa.UniqueConstraint("idempotency_key"),
    )
    op.create_index("ix_refund_tax_links_operation_id", "refund_tax_links", ["operation_id"])

    op.create_table(
        "refund_operation_audits",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False), sa.Column("operation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False), sa.Column("branch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=True), sa.Column("action", sa.String(60), nullable=False),
        sa.Column("from_state", sa.String(30), nullable=True), sa.Column("to_state", sa.String(30), nullable=False),
        sa.Column("idempotency_key", sa.String(160), nullable=False), sa.Column("evidence", postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["operation_id"], ["refund_operations.id"]), sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"]), sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"), sa.UniqueConstraint("operation_id", "idempotency_key", name="uq_refund_operation_audit_idempotency"),
    )
    op.create_index("ix_refund_operation_audits_operation_id", "refund_operation_audits", ["operation_id"])
    op.create_index("ix_refund_operation_audits_company_id", "refund_operation_audits", ["company_id"])
    op.create_index("ix_refund_operation_audits_branch_id", "refund_operation_audits", ["branch_id"])

    op.add_column("payments", sa.Column("currency", sa.String(3), server_default=sa.text("'THB'"), nullable=False))
    op.add_column("payments", sa.Column("provider_name", sa.String(40), nullable=True))
    op.add_column("payments", sa.Column("provider_payment_ref", sa.String(255), nullable=True))
    op.add_column("payments", sa.Column("settlement_state", sa.String(30), server_default=sa.text("'unknown'"), nullable=False))
    op.add_column("payments", sa.Column("refund_operation_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("payments", sa.Column("provider_refund_state", sa.String(30), nullable=True))
    op.create_foreign_key("fk_payments_refund_operation_id_refund_operations", "payments", "refund_operations", ["refund_operation_id"], ["id"])
    op.create_index("ix_payments_refund_operation_id", "payments", ["refund_operation_id"])
    op.create_unique_constraint("uq_payments_refund_operation_original", "payments", ["refund_operation_id", "original_payment_id"])
    op.execute("UPDATE payments SET settlement_state = CASE WHEN payment_method = 'cash' THEN 'settled' ELSE 'unknown' END WHERE amount > 0")
    op.create_index(
        "uq_points_transactions_refund_operation",
        "points_transactions",
        ["company_id", "reference_id"],
        unique=True,
        postgresql_where=sa.text("transaction_type = 'refund_earn' AND reference_type = 'RefundOperation'"),
    )

    op.add_column("tax_documents", sa.Column("source_refund_operation_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("tax_documents", sa.Column("is_synthetic", sa.Boolean(), server_default=sa.text("false"), nullable=False))
    op.add_column("tax_documents", sa.Column("watermark", sa.String(80), nullable=True))
    op.add_column("tax_documents", sa.Column("submission_status", sa.String(30), server_default=sa.text("'not_submitted'"), nullable=False))
    op.create_foreign_key("fk_tax_documents_source_refund_operation_id_refund_operations", "tax_documents", "refund_operations", ["source_refund_operation_id"], ["id"])
    op.create_unique_constraint("uq_tax_documents_source_refund_operation_id", "tax_documents", ["source_refund_operation_id"])

    for table_name in ("provider_refund_attempts", "provider_refund_events", "refund_operation_audits"):
        _append_only(table_name)
    op.execute("""
        CREATE FUNCTION protect_refund_tax_link_identity() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'refund_tax_links cannot be deleted' USING ERRCODE = '55000';
            END IF;
            IF NEW.operation_id IS DISTINCT FROM OLD.operation_id
               OR NEW.original_document_id IS DISTINCT FROM OLD.original_document_id
               OR (OLD.credit_note_id IS NOT NULL AND NEW.credit_note_id IS DISTINCT FROM OLD.credit_note_id)
               OR NEW.idempotency_key IS DISTINCT FROM OLD.idempotency_key THEN
                RAISE EXCEPTION 'refund_tax_links identity is immutable' USING ERRCODE = '55000';
            END IF;
            RETURN NEW;
        END; $$
    """)
    op.execute("""
        CREATE TRIGGER trg_refund_tax_links_identity
        BEFORE UPDATE OR DELETE ON refund_tax_links
        FOR EACH ROW EXECUTE FUNCTION protect_refund_tax_link_identity()
    """)
    op.execute("""
        CREATE FUNCTION protect_refund_credit_note() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF OLD.source_refund_operation_id IS NOT NULL THEN
                RAISE EXCEPTION 'refund Credit Note is immutable' USING ERRCODE = '55000';
            END IF;
            RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
        END; $$
    """)
    op.execute("""
        CREATE TRIGGER trg_refund_credit_note_immutable
        BEFORE UPDATE OR DELETE ON tax_documents
        FOR EACH ROW EXECUTE FUNCTION protect_refund_credit_note()
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_refund_credit_note_immutable ON tax_documents")
    op.execute("DROP FUNCTION IF EXISTS protect_refund_credit_note()")
    op.execute("DROP TRIGGER IF EXISTS trg_refund_tax_links_identity ON refund_tax_links")
    op.execute("DROP FUNCTION IF EXISTS protect_refund_tax_link_identity()")
    for table_name in ("refund_operation_audits", "provider_refund_events", "provider_refund_attempts"):
        op.execute(f"DROP TRIGGER IF EXISTS trg_{table_name}_append_only ON {table_name}")
        op.execute(f"DROP FUNCTION IF EXISTS prevent_{table_name}_mutation()")
    op.drop_index("uq_points_transactions_refund_operation", table_name="points_transactions")
    op.drop_constraint("uq_tax_documents_source_refund_operation_id", "tax_documents", type_="unique")
    op.drop_constraint("fk_tax_documents_source_refund_operation_id_refund_operations", "tax_documents", type_="foreignkey")
    for column in ("submission_status", "watermark", "is_synthetic", "source_refund_operation_id"):
        op.drop_column("tax_documents", column)
    op.drop_constraint("uq_payments_refund_operation_original", "payments", type_="unique")
    op.drop_index("ix_payments_refund_operation_id", table_name="payments")
    op.drop_constraint("fk_payments_refund_operation_id_refund_operations", "payments", type_="foreignkey")
    for column in ("provider_refund_state", "refund_operation_id", "settlement_state", "provider_payment_ref", "provider_name", "currency"):
        op.drop_column("payments", column)
    for table_name in (
        "refund_operation_audits", "refund_tax_links", "provider_refund_events", "provider_refund_attempts",
        "refund_payment_legs", "refund_operation_items", "refund_operations", "refund_quotes",
    ):
        op.drop_table(table_name)
