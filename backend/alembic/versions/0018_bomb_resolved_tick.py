"""Store the C4 defuse or explosion tick for replay.

Revision ID: 0018
Revises: 0017
"""
from backend.db import execute_script

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    execute_script("ALTER TABLE rounds ADD COLUMN IF NOT EXISTS bomb_resolved_tick INTEGER;")


def downgrade() -> None:
    execute_script("ALTER TABLE rounds DROP COLUMN IF EXISTS bomb_resolved_tick;")
