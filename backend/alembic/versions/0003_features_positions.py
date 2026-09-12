"""player_rounds: feature columns (opening/trade/buy_type/clutch/kast) + tables match_players, player_positions

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-11

ฟีเจอร์ต่อคนต่อรอบคำนวณด้วย backend/features.py ตอน worker โหลดแมตช์ แล้วเก็บลง player_rounds
(= player_round_stats ในเอกสารดีไซน์) features_version บอกว่าแถวนั้นใช้นิยามรุ่นไหน (0 = ยังไม่เคยคำนวณ)
player_positions เก็บตำแหน่งผู้เล่นที่ 1 Hz เท่านั้น — ห้ามเก็บทุก tick (ดู backend/parser/positions.py)
"""
from backend.db import execute_script

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    execute_script("""
        ALTER TABLE player_rounds ADD COLUMN IF NOT EXISTS buy_type         TEXT;
        ALTER TABLE player_rounds ADD COLUMN IF NOT EXISTS kills            INT     NOT NULL DEFAULT 0;
        ALTER TABLE player_rounds ADD COLUMN IF NOT EXISTS deaths           INT     NOT NULL DEFAULT 0;
        ALTER TABLE player_rounds ADD COLUMN IF NOT EXISTS assists          INT     NOT NULL DEFAULT 0;
        ALTER TABLE player_rounds ADD COLUMN IF NOT EXISTS headshots        INT     NOT NULL DEFAULT 0;
        ALTER TABLE player_rounds ADD COLUMN IF NOT EXISTS damage           INT     NOT NULL DEFAULT 0;
        ALTER TABLE player_rounds ADD COLUMN IF NOT EXISTS opening_kill     BOOLEAN NOT NULL DEFAULT FALSE;
        ALTER TABLE player_rounds ADD COLUMN IF NOT EXISTS opening_death    BOOLEAN NOT NULL DEFAULT FALSE;
        ALTER TABLE player_rounds ADD COLUMN IF NOT EXISTS trade_kills      INT     NOT NULL DEFAULT 0;
        ALTER TABLE player_rounds ADD COLUMN IF NOT EXISTS was_traded       BOOLEAN NOT NULL DEFAULT FALSE;
        ALTER TABLE player_rounds ADD COLUMN IF NOT EXISTS clutch_vs        INT     NOT NULL DEFAULT 0;
        ALTER TABLE player_rounds ADD COLUMN IF NOT EXISTS clutch_won       BOOLEAN;
        ALTER TABLE player_rounds ADD COLUMN IF NOT EXISTS kast             BOOLEAN NOT NULL DEFAULT FALSE;
        ALTER TABLE player_rounds ADD COLUMN IF NOT EXISTS features_version INT     NOT NULL DEFAULT 0;
        ALTER TABLE player_rounds DROP CONSTRAINT IF EXISTS player_rounds_buy_type_check;
        ALTER TABLE player_rounds ADD CONSTRAINT player_rounds_buy_type_check
            CHECK (buy_type IS NULL OR buy_type IN ('pistol', 'full', 'force', 'eco'));

        -- ใครเล่นในแมตช์ไหน (สรุปจาก player_rounds ตอนโหลด) — เร็วกว่าไล่นับรายรอบทุกครั้ง
        CREATE TABLE IF NOT EXISTS match_players (
            match_id   INT    NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
            steam_id   BIGINT NOT NULL REFERENCES players(steam_id),
            start_side TEXT   CHECK (start_side IN ('ct', 't')),   -- ฝั่งในรอบแรกที่เล่น = ระบุทีม
            rounds     INT    NOT NULL DEFAULT 0,
            PRIMARY KEY (match_id, steam_id)
        );
        CREATE INDEX IF NOT EXISTS match_players_player_idx ON match_players (steam_id);

        -- ตำแหน่งผู้เล่น 1 Hz — หนึ่งแถวต่อคนต่อวินาที (~21,000 แถวต่อแมตช์)
        CREATE TABLE IF NOT EXISTS player_positions (
            id        BIGSERIAL PRIMARY KEY,
            match_id  INT    NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
            round_num INT    NOT NULL,
            tick      INT    NOT NULL,
            steam_id  BIGINT NOT NULL REFERENCES players(steam_id),
            side      TEXT   CHECK (side IN ('ct', 't')),
            x         REAL   NOT NULL,
            y         REAL   NOT NULL,
            z         REAL,
            health    SMALLINT,
            place     TEXT                                          -- ชื่อ callout ที่ยืน (ถ้ามี)
        );
        CREATE INDEX IF NOT EXISTS player_positions_match_round_idx ON player_positions (match_id, round_num);
        CREATE INDEX IF NOT EXISTS player_positions_player_idx      ON player_positions (steam_id);
    """)


def downgrade() -> None:
    execute_script("""
        DROP TABLE IF EXISTS player_positions;
        DROP TABLE IF EXISTS match_players;
        ALTER TABLE player_rounds DROP CONSTRAINT IF EXISTS player_rounds_buy_type_check;
        ALTER TABLE player_rounds DROP COLUMN IF EXISTS features_version;
        ALTER TABLE player_rounds DROP COLUMN IF EXISTS kast;
        ALTER TABLE player_rounds DROP COLUMN IF EXISTS clutch_won;
        ALTER TABLE player_rounds DROP COLUMN IF EXISTS clutch_vs;
        ALTER TABLE player_rounds DROP COLUMN IF EXISTS was_traded;
        ALTER TABLE player_rounds DROP COLUMN IF EXISTS trade_kills;
        ALTER TABLE player_rounds DROP COLUMN IF EXISTS opening_death;
        ALTER TABLE player_rounds DROP COLUMN IF EXISTS opening_kill;
        ALTER TABLE player_rounds DROP COLUMN IF EXISTS damage;
        ALTER TABLE player_rounds DROP COLUMN IF EXISTS headshots;
        ALTER TABLE player_rounds DROP COLUMN IF EXISTS assists;
        ALTER TABLE player_rounds DROP COLUMN IF EXISTS deaths;
        ALTER TABLE player_rounds DROP COLUMN IF EXISTS kills;
        ALTER TABLE player_rounds DROP COLUMN IF EXISTS buy_type;
    """)
