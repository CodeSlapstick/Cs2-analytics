"""Store live player money and C4 carrier state in replay snapshots.

Revision ID: 0021
Revises: 0020
"""
from backend.db import execute_script

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    execute_script("""
        ALTER TABLE player_positions ADD COLUMN IF NOT EXISTS money INTEGER;
        ALTER TABLE player_positions ADD COLUMN IF NOT EXISTS has_bomb BOOLEAN;
    """)


def downgrade() -> None:
    execute_script("""
        ALTER TABLE player_positions DROP COLUMN IF EXISTS has_bomb;
        ALTER TABLE player_positions DROP COLUMN IF EXISTS money;
    """)
