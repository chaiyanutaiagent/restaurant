"""add Platform manager PIN credentials

Revision ID: p2platform0005
Revises: p2platform0004
Create Date: 2026-08-01 09:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "p2platform0005"
down_revision: Union[str, None] = "p2platform0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "manager_pin_credentials",
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("pin_hash", sa.String(length=255), nullable=False),
        sa.Column("failed_attempts", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("pin_set_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "failed_attempts >= 0",
            name=op.f("ck_manager_pin_credentials_failed_attempts_nonnegative"),
        ),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", name="uq_manager_pin_credentials_user_id"),
    )
    op.create_index(
        "ix_manager_pin_credentials_company_id",
        "manager_pin_credentials",
        ["company_id"],
    )
    op.execute(
        "UPDATE database_boundary_metadata SET schema_contract_version = 3 "
        "WHERE boundary_name = 'platform_core'"
    )


def downgrade() -> None:
    op.execute(
        "UPDATE database_boundary_metadata SET schema_contract_version = 2 "
        "WHERE boundary_name = 'platform_core'"
    )
    op.drop_index(
        "ix_manager_pin_credentials_company_id",
        table_name="manager_pin_credentials",
    )
    op.drop_table("manager_pin_credentials")
