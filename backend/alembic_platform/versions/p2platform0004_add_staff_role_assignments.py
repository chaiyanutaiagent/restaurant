"""add Platform staff role assignments

Revision ID: p2platform0004
Revises: p1platform0003
Create Date: 2026-08-01 07:50:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "p2platform0004"
down_revision: Union[str, None] = "p1platform0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "roles",
        sa.Column(
            "allowed_scope_types",
            sa.JSON(),
            server_default=sa.text("'[\"branch\"]'::json"),
            nullable=False,
        ),
    )
    op.create_table(
        "staff_role_assignments",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("scope_type", sa.String(length=20), nullable=False),
        sa.Column("scope_key", sa.String(length=255), nullable=False),
        sa.Column("brand_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("station_key", sa.String(length=100), nullable=True),
        sa.Column("assignment_reason", sa.String(length=500), nullable=False),
        sa.Column("assigned_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "assigned_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("revoked_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revocation_reason", sa.String(length=500), nullable=True),
        sa.CheckConstraint(
            "scope_type IN ('company', 'brand', 'branch', 'station')",
            name="ck_staff_role_assignments_scope_type",
        ),
        sa.CheckConstraint(
            "(scope_type = 'company' AND brand_id IS NULL AND branch_id IS NULL "
            "AND station_key IS NULL) OR "
            "(scope_type = 'brand' AND brand_id IS NOT NULL AND branch_id IS NULL "
            "AND station_key IS NULL) OR "
            "(scope_type = 'branch' AND brand_id IS NOT NULL AND branch_id IS NOT NULL "
            "AND station_key IS NULL) OR "
            "(scope_type = 'station' AND brand_id IS NOT NULL AND branch_id IS NOT NULL "
            "AND station_key IS NOT NULL AND length(btrim(station_key)) > 0)",
            name="ck_staff_role_assignments_scope_shape",
        ),
        sa.ForeignKeyConstraint(["assigned_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"]),
        sa.ForeignKeyConstraint(["brand_id"], ["brands.id"]),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.ForeignKeyConstraint(["revoked_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["role_id"], ["roles.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("company_id", "user_id", "role_id", "brand_id", "branch_id"):
        op.create_index(
            f"ix_staff_role_assignments_{column}",
            "staff_role_assignments",
            [column],
        )
    op.create_index(
        "ix_staff_role_assignments_user_active",
        "staff_role_assignments",
        ["company_id", "user_id"],
        postgresql_where=sa.text("revoked_at IS NULL"),
    )
    op.create_index(
        "uq_staff_role_assignments_active_scope",
        "staff_role_assignments",
        ["user_id", "role_id", "scope_type", "scope_key"],
        unique=True,
        postgresql_where=sa.text("revoked_at IS NULL"),
    )
    op.execute(
        "UPDATE database_boundary_metadata SET schema_contract_version = 2 "
        "WHERE boundary_name = 'platform_core'"
    )


def downgrade() -> None:
    op.execute(
        "UPDATE database_boundary_metadata SET schema_contract_version = 1 "
        "WHERE boundary_name = 'platform_core'"
    )
    op.drop_index("uq_staff_role_assignments_active_scope", table_name="staff_role_assignments")
    op.drop_index("ix_staff_role_assignments_user_active", table_name="staff_role_assignments")
    for column in ("branch_id", "brand_id", "role_id", "user_id", "company_id"):
        op.drop_index(f"ix_staff_role_assignments_{column}", table_name="staff_role_assignments")
    op.drop_table("staff_role_assignments")
    op.drop_column("roles", "allowed_scope_types")
