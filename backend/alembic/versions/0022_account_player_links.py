"""Allow an account to explicitly confirm its demo-player identity.

Revision ID: 0022
Revises: 0021
"""
from backend.db import execute_script

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    execute_script("""
        CREATE TABLE IF NOT EXISTS account_player_links (
            account_id BIGINT PRIMARY KEY REFERENCES accounts(id) ON DELETE CASCADE,
            steam_id BIGINT NOT NULL REFERENCES players(steam_id),
            confirmed_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        CREATE INDEX IF NOT EXISTS account_player_links_player_idx
            ON account_player_links (steam_id);
    """)


def downgrade() -> None:
    execute_script("DROP TABLE IF EXISTS account_player_links;")
