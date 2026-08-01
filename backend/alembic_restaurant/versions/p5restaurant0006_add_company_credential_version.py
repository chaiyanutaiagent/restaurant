"""add Phase 5 Company credential generation

Revision ID: p5restaurant0006
Revises: p4restaurant0005
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "p5restaurant0006"
down_revision: Union[str, None] = "p4restaurant0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "companies",
        sa.Column("credential_version", sa.Integer(), server_default=sa.text("1"), nullable=False),
    )
    op.create_check_constraint(
        "ck_companies_company_credential_version_positive",
        "companies",
        "credential_version > 0",
    )


def downgrade() -> None:
    op.drop_constraint("ck_companies_company_credential_version_positive", "companies", type_="check")
    op.drop_column("companies", "credential_version")
