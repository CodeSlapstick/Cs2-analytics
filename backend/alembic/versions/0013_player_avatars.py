"""cache Steam avatars for demo players

Revision ID: 0013_avatars
Revises: 0012
"""
from alembic import op


revision = "0013_avatars"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The baseline schema already contains this column.  Keep this branch
    # migration safe for databases created both before and after that change.
    op.execute("ALTER TABLE players ADD COLUMN IF NOT EXISTS avatar TEXT")


def downgrade() -> None:
    op.execute("ALTER TABLE players DROP COLUMN IF EXISTS avatar")
