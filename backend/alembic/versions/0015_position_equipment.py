"""player_positions: real active weapon and equipment snapshots

Revision ID: 0015
Revises: 0014
"""
from backend.db import execute_script

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    execute_script("""
        ALTER TABLE player_positions ADD COLUMN IF NOT EXISTS active_weapon TEXT;
        ALTER TABLE player_positions ADD COLUMN IF NOT EXISTS armor SMALLINT;
        ALTER TABLE player_positions ADD COLUMN IF NOT EXISTS has_helmet BOOLEAN;
        ALTER TABLE player_positions ADD COLUMN IF NOT EXISTS has_defuser BOOLEAN;
    """)


def downgrade() -> None:
    execute_script("""
        ALTER TABLE player_positions DROP COLUMN IF EXISTS has_defuser;
        ALTER TABLE player_positions DROP COLUMN IF EXISTS has_helmet;
        ALTER TABLE player_positions DROP COLUMN IF EXISTS armor;
        ALTER TABLE player_positions DROP COLUMN IF EXISTS active_weapon;
    """)
