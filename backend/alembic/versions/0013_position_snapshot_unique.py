"""player_positions: prevent duplicate player snapshots

Revision ID: 0013
Revises: 0012
"""
from backend.db import execute_script

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    execute_script("""
        DELETE FROM player_positions a
        USING player_positions b
        WHERE a.id > b.id
          AND a.match_id = b.match_id
          AND a.round_num = b.round_num
          AND a.tick = b.tick
          AND a.steam_id = b.steam_id;
        ALTER TABLE player_positions
        ADD CONSTRAINT player_positions_snapshot_unique
        UNIQUE (match_id, round_num, tick, steam_id);
    """)


def downgrade() -> None:
    execute_script("ALTER TABLE player_positions DROP CONSTRAINT IF EXISTS player_positions_snapshot_unique;")
