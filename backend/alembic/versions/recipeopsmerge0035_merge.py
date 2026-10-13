"""Repository-only merge; UAT explicitly upgrades recipeops0034, not head."""
revision = "recipeopsmerge0035"
down_revision = ("reviewmerge0033", "recipeops0034")
branch_labels = None
depends_on = None

def upgrade():
    pass

def downgrade():
    pass
