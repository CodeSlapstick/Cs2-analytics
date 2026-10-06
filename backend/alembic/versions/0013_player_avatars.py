"""cache Steam avatars for demo players

Revision ID: 0013_avatars
Revises: 0012
"""
from alembic import op
import sqlalchemy as sa


revision = "0013_avatars"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("players", sa.Column("avatar", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("players", "avatar")
