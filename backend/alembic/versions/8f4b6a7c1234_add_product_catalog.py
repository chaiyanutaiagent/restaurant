"""add_product_catalog

Revision ID: 8f4b6a7c1234
Revises: dfd147ecd9ce
Create Date: 2026-05-13 17:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "8f4b6a7c1234"
down_revision: Union[str, None] = "dfd147ecd9ce"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "units",
        sa.Column("company_id", sa.UUID(), nullable=False),
        sa.Column("code", sa.String(length=20), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("name_en", sa.String(length=100), nullable=True),
        sa.Column("decimal_places", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], name=op.f("fk_units_company_id_companies")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_units")),
        sa.UniqueConstraint("company_id", "code", name="uq_units_company_id_code"),
    )
    op.create_index(op.f("ix_units_company_id"), "units", ["company_id"], unique=False)

    op.create_table(
        "categories",
        sa.Column("company_id", sa.UUID(), nullable=False),
        sa.Column("parent_id", sa.UUID(), nullable=True),
        sa.Column("code", sa.String(length=50), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("name_en", sa.String(length=255), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("image_url", sa.String(length=500), nullable=True),
        sa.Column("sort_order", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], name=op.f("fk_categories_company_id_companies")),
        sa.ForeignKeyConstraint(["parent_id"], ["categories.id"], name=op.f("fk_categories_parent_id_categories")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_categories")),
    )
    op.create_index(op.f("ix_categories_company_id"), "categories", ["company_id"], unique=False)
    op.create_index(
        "ix_categories_company_code_not_null_unique",
        "categories",
        ["company_id", "code"],
        unique=True,
        postgresql_where=sa.text("code IS NOT NULL"),
    )

    op.create_table(
        "price_lists",
        sa.Column("company_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("currency", sa.String(length=3), server_default=sa.text("'THB'"), nullable=False),
        sa.Column("is_default", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("valid_from", sa.Date(), nullable=True),
        sa.Column("valid_until", sa.Date(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], name=op.f("fk_price_lists_company_id_companies")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_price_lists")),
    )
    op.create_index(op.f("ix_price_lists_company_id"), "price_lists", ["company_id"], unique=False)

    op.create_table(
        "products",
        sa.Column("company_id", sa.UUID(), nullable=False),
        sa.Column("category_id", sa.UUID(), nullable=True),
        sa.Column("unit_id", sa.UUID(), nullable=True),
        sa.Column("sku", sa.String(length=100), nullable=False),
        sa.Column("barcode", sa.String(length=100), nullable=True),
        sa.Column("name", sa.String(length=500), nullable=False),
        sa.Column("name_en", sa.String(length=500), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("description_en", sa.Text(), nullable=True),
        sa.Column("product_type", sa.String(length=20), server_default=sa.text("'simple'"), nullable=False),
        sa.Column("cost_price", sa.Numeric(15, 4), server_default=sa.text("0"), nullable=False),
        sa.Column("selling_price", sa.Numeric(15, 4), server_default=sa.text("0"), nullable=False),
        sa.Column("vat_type", sa.String(length=20), server_default=sa.text("'included'"), nullable=False),
        sa.Column("vat_rate", sa.Numeric(5, 2), server_default=sa.text("7.00"), nullable=False),
        sa.Column("weight_grams", sa.Integer(), nullable=True),
        sa.Column("image_url", sa.String(length=500), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("is_for_sale", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("is_for_purchase", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("min_stock_qty", sa.Numeric(15, 4), server_default=sa.text("0"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["category_id"], ["categories.id"], name=op.f("fk_products_category_id_categories")),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], name=op.f("fk_products_company_id_companies")),
        sa.ForeignKeyConstraint(["unit_id"], ["units.id"], name=op.f("fk_products_unit_id_units")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_products")),
        sa.UniqueConstraint("company_id", "sku", name="uq_products_company_id_sku"),
    )
    op.create_index(op.f("ix_products_barcode"), "products", ["barcode"], unique=False)
    op.create_index(op.f("ix_products_category_id"), "products", ["category_id"], unique=False)
    op.create_index(op.f("ix_products_company_id"), "products", ["company_id"], unique=False)
    op.create_index(op.f("ix_products_unit_id"), "products", ["unit_id"], unique=False)

    op.create_table(
        "product_variants",
        sa.Column("product_id", sa.UUID(), nullable=False),
        sa.Column("company_id", sa.UUID(), nullable=False),
        sa.Column("sku", sa.String(length=100), nullable=False),
        sa.Column("barcode", sa.String(length=100), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("attributes", sa.JSON(), nullable=True),
        sa.Column("cost_price", sa.Numeric(15, 4), nullable=True),
        sa.Column("selling_price", sa.Numeric(15, 4), nullable=True),
        sa.Column("image_url", sa.String(length=500), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], name=op.f("fk_product_variants_company_id_companies")),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], name=op.f("fk_product_variants_product_id_products")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_product_variants")),
        sa.UniqueConstraint("company_id", "sku", name="uq_product_variants_company_id_sku"),
    )
    op.create_index(op.f("ix_product_variants_barcode"), "product_variants", ["barcode"], unique=False)
    op.create_index(op.f("ix_product_variants_company_id"), "product_variants", ["company_id"], unique=False)
    op.create_index(op.f("ix_product_variants_product_id"), "product_variants", ["product_id"], unique=False)

    op.create_table(
        "product_images",
        sa.Column("product_id", sa.UUID(), nullable=False),
        sa.Column("company_id", sa.UUID(), nullable=False),
        sa.Column("url", sa.String(length=500), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("is_primary", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], name=op.f("fk_product_images_company_id_companies")),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], name=op.f("fk_product_images_product_id_products")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_product_images")),
    )
    op.create_index(op.f("ix_product_images_company_id"), "product_images", ["company_id"], unique=False)
    op.create_index(op.f("ix_product_images_product_id"), "product_images", ["product_id"], unique=False)

    op.create_table(
        "price_list_items",
        sa.Column("price_list_id", sa.UUID(), nullable=False),
        sa.Column("product_id", sa.UUID(), nullable=False),
        sa.Column("variant_id", sa.UUID(), nullable=True),
        sa.Column("company_id", sa.UUID(), nullable=False),
        sa.Column("price", sa.Numeric(15, 4), nullable=False),
        sa.Column("min_qty", sa.Numeric(15, 4), server_default=sa.text("1"), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], name=op.f("fk_price_list_items_company_id_companies")),
        sa.ForeignKeyConstraint(["price_list_id"], ["price_lists.id"], name=op.f("fk_price_list_items_price_list_id_price_lists")),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], name=op.f("fk_price_list_items_product_id_products")),
        sa.ForeignKeyConstraint(["variant_id"], ["product_variants.id"], name=op.f("fk_price_list_items_variant_id_product_variants")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_price_list_items")),
        sa.UniqueConstraint("price_list_id", "product_id", "variant_id", name="uq_price_list_items_price_list_product_variant"),
    )
    op.create_index(op.f("ix_price_list_items_company_id"), "price_list_items", ["company_id"], unique=False)
    op.create_index(op.f("ix_price_list_items_price_list_id"), "price_list_items", ["price_list_id"], unique=False)
    op.create_index(op.f("ix_price_list_items_product_id"), "price_list_items", ["product_id"], unique=False)
    op.create_index(op.f("ix_price_list_items_variant_id"), "price_list_items", ["variant_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_price_list_items_variant_id"), table_name="price_list_items")
    op.drop_index(op.f("ix_price_list_items_product_id"), table_name="price_list_items")
    op.drop_index(op.f("ix_price_list_items_price_list_id"), table_name="price_list_items")
    op.drop_index(op.f("ix_price_list_items_company_id"), table_name="price_list_items")
    op.drop_table("price_list_items")
    op.drop_index(op.f("ix_product_images_product_id"), table_name="product_images")
    op.drop_index(op.f("ix_product_images_company_id"), table_name="product_images")
    op.drop_table("product_images")
    op.drop_index(op.f("ix_product_variants_product_id"), table_name="product_variants")
    op.drop_index(op.f("ix_product_variants_company_id"), table_name="product_variants")
    op.drop_index(op.f("ix_product_variants_barcode"), table_name="product_variants")
    op.drop_table("product_variants")
    op.drop_index(op.f("ix_products_unit_id"), table_name="products")
    op.drop_index(op.f("ix_products_company_id"), table_name="products")
    op.drop_index(op.f("ix_products_category_id"), table_name="products")
    op.drop_index(op.f("ix_products_barcode"), table_name="products")
    op.drop_table("products")
    op.drop_index(op.f("ix_price_lists_company_id"), table_name="price_lists")
    op.drop_table("price_lists")
    op.drop_index("ix_categories_company_code_not_null_unique", table_name="categories", postgresql_where=sa.text("code IS NOT NULL"))
    op.drop_index(op.f("ix_categories_company_id"), table_name="categories")
    op.drop_table("categories")
    op.drop_index(op.f("ix_units_company_id"), table_name="units")
    op.drop_table("units")
