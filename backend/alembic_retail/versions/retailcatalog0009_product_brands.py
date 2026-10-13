"""Retail product brands; additive, no changes to existing products or balances."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "retailcatalog0009"
down_revision = "wp84retail0008"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("retail_product_brands",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", UUID(as_uuid=True), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("name", sa.String(150), nullable=False),
        sa.Column("name_key", sa.String(300), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("company_id", "name_key", name="uq_retail_product_brand_name"))
    op.create_table("retail_product_brand_links",
        sa.Column("product_id", UUID(as_uuid=True), sa.ForeignKey("products.id"), primary_key=True),
        sa.Column("company_id", UUID(as_uuid=True), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("product_brand_id", UUID(as_uuid=True), sa.ForeignKey("retail_product_brands.id"), nullable=False))


def downgrade():
    op.drop_table("retail_product_brand_links")
    op.drop_table("retail_product_brands")
