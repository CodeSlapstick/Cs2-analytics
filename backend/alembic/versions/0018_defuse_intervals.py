"""Store real C4 defuse intervals for replay.

Revision ID: 0018_defuses
Revises: 0017_round_end
"""
from backend.db import execute_script

revision = "0018_defuses"
down_revision = "0017_round_end"
branch_labels = None
depends_on = None


def upgrade() -> None:
    execute_script("ALTER TABLE rounds ADD COLUMN IF NOT EXISTS defuse_intervals JSONB;")


def downgrade() -> None:
    execute_script("ALTER TABLE rounds DROP COLUMN IF EXISTS defuse_intervals;")
