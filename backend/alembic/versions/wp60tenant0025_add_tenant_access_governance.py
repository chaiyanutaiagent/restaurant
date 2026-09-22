"""add tenant access governance

Revision ID: wp60tenant0025
Revises: wp50shift0024
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "wp60tenant0025"
down_revision: Union[str, None] = "wp50shift0024"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("platform_sessions", sa.Column("qa_persona", sa.String(length=80), nullable=True))
    op.add_column("users", sa.Column("credential_version", sa.Integer(), server_default=sa.text("1"), nullable=False))
    op.add_column("users", sa.Column("mfa_enabled", sa.Boolean(), server_default=sa.text("false"), nullable=False))
    op.add_column("users", sa.Column("access_reviewed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("access_review_due_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("access_reviewed_by", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("users", sa.Column("access_review_outcome", sa.String(length=20), nullable=True))
    op.add_column("users", sa.Column("deactivated_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("deactivated_by", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("users", sa.Column("deactivation_reason", sa.Text(), nullable=True))
    op.create_check_constraint("ck_users_credential_version_positive", "users", "credential_version > 0")
    op.create_index("ix_users_company_access_review_due", "users", ["company_id", "access_review_due_at"])


def downgrade() -> None:
    op.drop_index("ix_users_company_access_review_due", table_name="users")
    op.drop_constraint("ck_users_credential_version_positive", "users", type_="check")
    op.drop_column("users", "deactivation_reason")
    op.drop_column("users", "deactivated_by")
    op.drop_column("users", "deactivated_at")
    op.drop_column("users", "access_review_outcome")
    op.drop_column("users", "access_reviewed_by")
    op.drop_column("users", "access_review_due_at")
    op.drop_column("users", "access_reviewed_at")
    op.drop_column("users", "mfa_enabled")
    op.drop_column("users", "credential_version")
    op.drop_column("platform_sessions", "qa_persona")
