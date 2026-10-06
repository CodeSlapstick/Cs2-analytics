"""Store real C4 defuse intervals for replay.

Revision ID: 0017
Revises: 0016
"""
from backend.db import execute_script

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    execute_script("ALTER TABLE rounds ADD COLUMN IF NOT EXISTS defuse_intervals JSONB;")


def downgrade() -> None:
    execute_script("ALTER TABLE rounds DROP COLUMN IF EXISTS defuse_intervals;")
