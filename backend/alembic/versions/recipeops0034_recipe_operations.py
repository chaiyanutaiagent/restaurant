"""Add immutable publication evidence and recoverable shared-ledger production."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "recipeops0034"
down_revision = "recipeflow0032"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_constraint("recipe_review_status", "recipe_reviews", type_="check")
    op.create_check_constraint("recipe_review_status", "recipe_reviews",
        "status IN ('draft','submitted','returned','rejected','approved_hold','published')")
    op.add_column("recipe_reviews", sa.Column("publication", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")))
    def common():
        return [sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column("company_id", UUID(as_uuid=True), nullable=False),
            sa.Column("brand_id", UUID(as_uuid=True), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()"))]
    op.create_table("recipe_legacy_registrations", *common(),
        sa.Column("system", sa.String(20), nullable=False),
        sa.Column("source_id", UUID(as_uuid=True), nullable=False),
        sa.Column("snapshot", JSONB(), nullable=False),
        sa.Column("registered_by", UUID(as_uuid=True), nullable=False),
        sa.UniqueConstraint("company_id", "system", "source_id", name="uq_recipe_legacy_source"))
    op.create_table("recipe_production_runs", *common(),
        sa.Column("review_id", UUID(as_uuid=True), nullable=False),
        sa.Column("request_key", UUID(as_uuid=True), nullable=False),
        sa.Column("created_by", UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("snapshot", JSONB(), nullable=False),
        sa.UniqueConstraint("company_id", "request_key", name="uq_recipe_run_request"),
        sa.CheckConstraint("status IN ('output_pending','completed')", name="recipe_run_status"))
    for table in ("recipe_legacy_registrations", "recipe_production_runs"):
        op.create_index(f"ix_{table}_company_id", table, ["company_id"])


def downgrade():
    raise RuntimeError("Preserve recipe and stock evidence; roll back application images only.")
