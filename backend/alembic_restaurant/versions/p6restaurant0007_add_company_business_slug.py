"""add canonical Company business slug reference

Revision ID: p6restaurant0007
Revises: p5restaurant0006
"""

from typing import Sequence, Union
import re
import unicodedata

from alembic import op
import sqlalchemy as sa


revision: str = "p6restaurant0007"
down_revision: Union[str, None] = "p5restaurant0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

RESERVED = {"403", "accounting", "admin", "api", "billing", "branches", "central", "counter", "crm", "dashboard", "device", "devices", "erp", "etax", "forgot-password", "hr", "integrations", "kitchen", "logistics", "login", "menu", "order", "payable", "pickup", "platform", "pos", "privacy-support", "products", "purchase", "reports", "reset-password", "restaurant", "roles", "settings", "shift-history", "signup", "stock", "stock-count", "store", "transfer", "units", "uploads", "users", "verify-email"}


def _base_slug(name: str, company_id: str) -> str:
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    candidate = re.sub(r"[^a-z0-9]+", "-", ascii_name.lower()).strip("-")[:63].rstrip("-")
    if len(candidate) < 3 or candidate in RESERVED:
        candidate = f"business-{company_id.replace('-', '')[:12]}"
    return candidate


def _unique_slug(candidate: str, company_id: str, used: set[str]) -> str:
    if candidate not in used:
        return candidate
    compact_id = company_id.replace("-", "")[:8]
    counter = 1
    while True:
        suffix = compact_id if counter == 1 else f"{compact_id}-{counter}"
        prefix = candidate[: 62 - len(suffix)].rstrip("-")
        generated = f"{prefix}-{suffix}"
        if generated not in used:
            return generated
        counter += 1


def upgrade() -> None:
    op.add_column("companies", sa.Column("business_slug", sa.String(length=63), nullable=True))
    connection = op.get_bind()
    rows = connection.execute(
        sa.text("SELECT id, name, name_en FROM companies ORDER BY created_at, id")
    ).mappings()
    used: set[str] = set()
    for row in rows:
        company_id = str(row["id"])
        candidate = _unique_slug(
            _base_slug(str(row["name_en"] or row["name"] or ""), company_id),
            company_id,
            used,
        )
        used.add(candidate)
        connection.execute(
            sa.text("UPDATE companies SET business_slug = :business_slug WHERE id = :company_id"),
            {"business_slug": candidate, "company_id": row["id"]},
        )
    op.alter_column("companies", "business_slug", existing_type=sa.String(length=63), nullable=False)
    op.create_index("ux_companies_business_slug", "companies", ["business_slug"], unique=True)


def downgrade() -> None:
    op.drop_index("ux_companies_business_slug", table_name="companies")
    op.drop_column("companies", "business_slug")
