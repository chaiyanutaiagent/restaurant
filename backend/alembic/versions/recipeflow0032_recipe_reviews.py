"""Add review workspace only; no operational recipe/stock writes or data migration."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "recipeflow0032"
down_revision = "creditsale0031"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table("recipe_reviews",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", UUID(as_uuid=True), nullable=False),
        sa.Column("brand_id", UUID(as_uuid=True), nullable=False),
        sa.Column("branch_id", UUID(as_uuid=True)),
        sa.Column("system", sa.String(20), nullable=False),
        sa.Column("source_id", UUID(as_uuid=True)),
        sa.Column("request_key", UUID(as_uuid=True), nullable=False),
        sa.Column("created_by", UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("baseline", JSONB(), nullable=False),
        sa.Column("proposal", JSONB(), nullable=False),
        sa.Column("history", JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("company_id", "request_key", name="uq_recipe_reviews_request"),
        sa.CheckConstraint("system IN ('restaurant','takeaway')", name="recipe_review_system"),
        sa.CheckConstraint("status IN ('draft','submitted','returned','rejected','approved_hold')", name="recipe_review_status"))
    for col in ("company_id", "brand_id", "branch_id"):
        op.create_index(f"ix_recipe_reviews_{col}", "recipe_reviews", [col])

def downgrade():
    raise RuntimeError("Preserve review history. Roll back images, not approval evidence.")
