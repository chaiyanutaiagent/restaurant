"""capture credentials on access request

Revision ID: f40a7c13e426
Revises: e28f6b02d315
Create Date: 2026-07-21 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f40a7c13e426"
down_revision: Union[str, None] = "e28f6b02d315"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "user_access_requests",
        sa.Column("requested_username", sa.String(length=100), nullable=True),
    )
    op.add_column(
        "user_access_requests",
        sa.Column("initial_password_hash", sa.String(length=255), nullable=True),
    )
    op.execute(
        sa.text(
            "CREATE UNIQUE INDEX ix_user_access_requests_username_pending_unique "
            "ON user_access_requests (company_id, lower(requested_username)) "
            "WHERE requested_username IS NOT NULL AND status = 'pending'"
        )
    )


def downgrade() -> None:
    op.drop_index(
        "ix_user_access_requests_username_pending_unique",
        table_name="user_access_requests",
    )
    op.drop_column("user_access_requests", "initial_password_hash")
    op.drop_column("user_access_requests", "requested_username")
