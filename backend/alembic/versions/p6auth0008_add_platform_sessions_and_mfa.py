"""add Platform sessions and MFA controls

Revision ID: p6auth0008
Revises: p5tenant0007
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "p6auth0008"
down_revision: Union[str, None] = "p5tenant0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "platform_operators",
        sa.Column("mfa_secret_ciphertext", sa.Text(), nullable=True),
    )
    op.add_column(
        "platform_operators",
        sa.Column("mfa_enabled_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "platform_operators",
        sa.Column("mfa_last_verified_step", sa.BigInteger(), nullable=True),
    )
    op.add_column(
        "platform_operators",
        sa.Column(
            "mfa_recovery_code_hashes",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )
    op.create_table(
        "platform_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("operator_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("credential_version", sa.Integer(), nullable=False),
        sa.Column("refresh_token_hash", sa.String(length=64), nullable=False),
        sa.Column("csrf_token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("mfa_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revocation_reason", sa.String(length=100), nullable=True),
        sa.Column("ip_address", sa.String(length=45), nullable=True),
        sa.Column("user_agent", sa.String(length=500), nullable=True),
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
            "credential_version > 0",
            name="ck_platform_sessions_credential_version_positive",
        ),
        sa.ForeignKeyConstraint(
            ["operator_id"],
            ["platform_operators.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "refresh_token_hash",
            name="uq_platform_sessions_refresh_token_hash",
        ),
    )
    op.create_index(
        "ix_platform_sessions_operator_active",
        "platform_sessions",
        ["operator_id", "revoked_at"],
    )
    op.create_index(
        "ix_platform_sessions_expires_at",
        "platform_sessions",
        ["expires_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_platform_sessions_expires_at", table_name="platform_sessions")
    op.drop_index("ix_platform_sessions_operator_active", table_name="platform_sessions")
    op.drop_table("platform_sessions")
    op.drop_column("platform_operators", "mfa_recovery_code_hashes")
    op.drop_column("platform_operators", "mfa_enabled_at")
    op.drop_column("platform_operators", "mfa_last_verified_step")
    op.drop_column("platform_operators", "mfa_secret_ciphertext")
