"""Repository DAG merge only. UAT pilot targets recipeflow0032, not this merge.

Do not use `upgrade head` to deploy the pilot: the other lineage includes Stripe
schema work not authorized by this rollout. No production flag is enabled here.
"""
revision = "reviewmerge0033"
down_revision = ("docmerge0029", "recipeflow0032")
branch_labels = None
depends_on = None

def upgrade():
    pass

def downgrade():
    pass
