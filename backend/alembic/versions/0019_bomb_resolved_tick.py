"""Store the C4 defuse or explosion tick for replay.

Revision ID: 0019_bomb_resolved
Revises: 0018_defuses
"""
from backend.db import execute_script

revision = "0019_bomb_resolved"
down_revision = "0018_defuses"
branch_labels = None
depends_on = None


def upgrade() -> None:
    execute_script("ALTER TABLE rounds ADD COLUMN IF NOT EXISTS bomb_resolved_tick INTEGER;")


def downgrade() -> None:
    execute_script("ALTER TABLE rounds DROP COLUMN IF EXISTS bomb_resolved_tick;")
