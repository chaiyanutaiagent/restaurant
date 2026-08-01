"""add Platform device registration and pairing credentials

Revision ID: p3platform0006
Revises: p2platform0005
Create Date: 2026-08-01 10:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "p3platform0006"
down_revision: Union[str, None] = "p2platform0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "device_registrations",
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("device_code", sa.String(length=24), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("device_type", sa.String(length=20), nullable=False),
        sa.Column("station_key", sa.String(length=100), nullable=True),
        sa.Column("pairing_pin_hash", sa.String(length=255), nullable=True),
        sa.Column("pairing_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "failed_pairing_attempts",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("pairing_locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "credential_version",
            sa.Integer(),
            server_default=sa.text("1"),
            nullable=False,
        ),
        sa.Column("paired_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("revoked_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revocation_reason", sa.String(length=500), nullable=True),
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
            "device_type IN ('counter', 'kitchen', 'pickup')",
            name=op.f("ck_device_registrations_supported_device_type"),
        ),
        sa.CheckConstraint(
            "(device_type = 'kitchen' AND station_key IS NOT NULL "
            "AND length(btrim(station_key)) > 0) OR "
            "(device_type IN ('counter', 'pickup') AND station_key IS NULL)",
            name=op.f("ck_device_registrations_device_station_shape"),
        ),
        sa.CheckConstraint(
            "credential_version > 0",
            name=op.f("ck_device_registrations_positive_credential_version"),
        ),
        sa.CheckConstraint(
            "failed_pairing_attempts >= 0",
            name=op.f("ck_device_registrations_failed_pairing_attempts_nonnegative"),
        ),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"]),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["revoked_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "company_id",
            "device_code",
            name="uq_device_registrations_company_device_code",
        ),
    )
    op.create_index(
        "ix_device_registrations_company_id",
        "device_registrations",
        ["company_id"],
    )
    op.create_index(
        "ix_device_registrations_branch_id",
        "device_registrations",
        ["branch_id"],
    )
    op.create_index(
        "ix_device_registrations_company_branch_active",
        "device_registrations",
        ["company_id", "branch_id"],
        postgresql_where=sa.text("revoked_at IS NULL"),
    )
    op.execute(
        "UPDATE database_boundary_metadata SET schema_contract_version = 4 "
        "WHERE boundary_name = 'platform_core'"
    )


def downgrade() -> None:
    op.execute(
        "UPDATE database_boundary_metadata SET schema_contract_version = 3 "
        "WHERE boundary_name = 'platform_core'"
    )
    op.drop_index(
        "ix_device_registrations_company_branch_active",
        table_name="device_registrations",
    )
    op.drop_index("ix_device_registrations_branch_id", table_name="device_registrations")
    op.drop_index("ix_device_registrations_company_id", table_name="device_registrations")
    op.drop_table("device_registrations")
