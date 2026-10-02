"""grenades: actual projectile positions from the demo entity stream

Revision ID: 0014
Revises: 0013
"""
from backend.db import execute_script

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    execute_script("ALTER TABLE grenades ADD COLUMN IF NOT EXISTS trajectory JSONB;")


def downgrade() -> None:
    execute_script("ALTER TABLE grenades DROP COLUMN IF EXISTS trajectory;")
