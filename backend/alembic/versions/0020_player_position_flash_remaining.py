"""Store remaining flash blindness in replay position snapshots.

Revision ID: 0020
Revises: 0019
"""
from backend.db import execute_script

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    execute_script("ALTER TABLE player_positions ADD COLUMN IF NOT EXISTS flash_remaining REAL;")


def downgrade() -> None:
    execute_script("ALTER TABLE player_positions DROP COLUMN IF EXISTS flash_remaining;")
