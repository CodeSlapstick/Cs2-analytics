"""Keep the official round end tick for replay duration.

Revision ID: 0017_round_end
Revises: 0016
"""
from backend.db import execute_script

revision = "0017_round_end"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    execute_script("ALTER TABLE rounds ADD COLUMN IF NOT EXISTS end_tick INTEGER;")


def downgrade() -> None:
    execute_script("ALTER TABLE rounds DROP COLUMN IF EXISTS end_tick;")
