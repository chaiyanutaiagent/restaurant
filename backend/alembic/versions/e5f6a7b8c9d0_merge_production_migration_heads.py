"""merge production migration heads

Revision ID: e5f6a7b8c9d0
Revises: a1b2c3d4e5f6, d4e5f6a7b8c9
Create Date: 2026-06-05 00:00:00.000000
"""

from typing import Sequence, Union


revision: str = "e5f6a7b8c9d0"
down_revision: Union[str, tuple[str, str]] = ("a1b2c3d4e5f6", "d4e5f6a7b8c9")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
