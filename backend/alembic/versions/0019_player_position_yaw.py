"""Store player eye yaw in replay position snapshots.

Revision ID: 0019
Revises: 0018
"""
from backend.db import execute_script

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    execute_script("ALTER TABLE player_positions ADD COLUMN IF NOT EXISTS yaw REAL;")


def downgrade() -> None:
    execute_script("ALTER TABLE player_positions DROP COLUMN IF EXISTS yaw;")
