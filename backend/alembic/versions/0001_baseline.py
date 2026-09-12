"""baseline: initial tables (users players matches rounds kills damages player_rounds grenades)

Revision ID: 0001
Revises:
Create Date: 2026-09-11

ยกมาจาก backend/schema.sql เดิมทั้งก้อน ทุกคำสั่งเป็น IF NOT EXISTS
จึงรันบนฐานข้อมูลที่มีตารางอยู่แล้ว (จาก Sprint 1) ได้โดยไม่พัง และไม่ต้อง alembic stamp ก่อน
ส่วน view ทั้งหมดอยู่ที่ backend/views.sql ซึ่ง backend/app.py รันซ้ำทุกครั้งที่สตาร์ต
"""
from backend.db import execute_script

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

TABLES_SQL = r"""
-- โครงฐานข้อมูล CS2 Analytics (PostgreSQL 16)
--
-- รันอัตโนมัติตอน docker compose สร้าง container ครั้งแรก (mount ไว้ใน docker-compose.yml)
-- หรือรันเองได้ทุกเมื่อ ปลอดภัยเพราะทุกคำสั่งเป็น IF NOT EXISTS:
--     docker compose exec -T db psql -U postgres -d cs2_analytics < backend/schema.sql
--
-- ความสัมพันธ์
--     matches 1 ─── n rounds 1 ─── n kills n ─── 1 players (attacker / victim / assister)
--     users                          (คนที่ล็อกอินเว็บ แยกจาก players ที่เป็นนักแข่งในเดโม)

-- ---------------------------------------------------------------------------
-- ผู้ใช้เว็บ — คนที่ล็อกอินผ่าน Steam เข้ามาดูข้อมูล
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
    steamid      VARCHAR(32) PRIMARY KEY,
    name         VARCHAR(255),
    avatar       TEXT,
    profile_url  TEXT,
    mode         VARCHAR(32),                 -- 'steam' = ล็อกอินจริง, 'dev' = โหมดทดสอบ
    last_login   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ---------------------------------------------------------------------------
-- นักแข่งที่โผล่ในเดโม — คีย์คือ SteamID64 ชื่อเก็บล่าสุดที่เห็น
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS players (
    steam_id  BIGINT PRIMARY KEY,
    name      TEXT NOT NULL
);

-- ---------------------------------------------------------------------------
-- แมตช์ = ไฟล์ .dem หนึ่งไฟล์
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS matches (
    id           SERIAL PRIMARY KEY,
    demo_file    TEXT UNIQUE NOT NULL,        -- ชื่อไฟล์ .dem ใช้กันโหลดซ้ำ
    map_name     TEXT NOT NULL,               -- de_mirage, de_dust2, ...
    tickrate     INT  NOT NULL,               -- 64 หรือ 128 tick/วินาที ไว้แปลง tick เป็นวินาที
    team_a       TEXT,                        -- แกะจากชื่อไฟล์ "A-vs-B-Map.dem" (อาจว่างถ้าชื่อไฟล์ไม่ตรงแบบ)
    team_b       TEXT,
    imported_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- รอบ — แต่ละแมตช์มี 16-30 รอบ
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS rounds (
    id               SERIAL PRIMARY KEY,
    match_id         INT NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
    round_num        INT NOT NULL,
    start_tick       INT,                     -- tick ที่ freeze time จบ
    bomb_plant_tick  INT,                     -- NULL = รอบนี้ไม่มีการวางระเบิด
    winner_side      TEXT CHECK (winner_side IN ('ct', 't')),
    end_reason       TEXT,                    -- t_killed / ct_killed / bomb_defused / bomb_exploded / time_ran_out
    UNIQUE (match_id, round_num)
);

-- ---------------------------------------------------------------------------
-- คิล — หนึ่งแถวต่อการฆ่าหนึ่งครั้ง ตารางหลักที่ทุกสถิติคำนวณจาก
-- พิกัด x/y อยู่ในระบบของเกม ต้องแปลงด้วย assets/radars.json ก่อนวาดทับภาพเรดาร์
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS kills (
    id              BIGSERIAL PRIMARY KEY,
    round_id        INT    NOT NULL REFERENCES rounds(id) ON DELETE CASCADE,
    tick            INT    NOT NULL,
    attacker_id     BIGINT REFERENCES players(steam_id),    -- NULL ได้ เช่นตายจากระเบิด/ตกที่สูง
    victim_id       BIGINT NOT NULL REFERENCES players(steam_id),
    assister_id     BIGINT REFERENCES players(steam_id),    -- NULL ถ้าไม่มีคนช่วย
    attacker_side   TEXT CHECK (attacker_side IN ('ct', 't')),
    victim_side     TEXT NOT NULL CHECK (victim_side IN ('ct', 't')),
    weapon          TEXT NOT NULL,
    headshot        BOOLEAN NOT NULL DEFAULT FALSE,
    hitgroup        TEXT,                     -- head / chest / stomach / left_arm / ... ('-1' = ไม่ทราบ)
    attacker_blind  BOOLEAN NOT NULL DEFAULT FALSE,
    thru_smoke      BOOLEAN NOT NULL DEFAULT FALSE,
    noscope         BOOLEAN NOT NULL DEFAULT FALSE,
    assisted_flash  BOOLEAN NOT NULL DEFAULT FALSE,
    penetrated      INT     NOT NULL DEFAULT 0,             -- ยิงทะลุกำแพงกี่ชั้น
    distance        REAL,                                   -- หน่วยของเกม (1 unit ≈ 1.9 ซม.)
    attacker_x      REAL, attacker_y REAL, attacker_z REAL,
    attacker_place  TEXT,                                   -- ชื่อ callout ที่คนยิงยืน เช่น Connector
    victim_x        REAL, victim_y REAL, victim_z REAL,
    victim_place    TEXT                                    -- ชื่อ callout ที่คนตายยืน
);

-- ดัชนีตามคำถามที่ API ถามบ่อย
CREATE INDEX IF NOT EXISTS kills_round_idx    ON kills (round_id);
CREATE INDEX IF NOT EXISTS kills_attacker_idx ON kills (attacker_id);
CREATE INDEX IF NOT EXISTS kills_victim_idx   ON kills (victim_id);
CREATE INDEX IF NOT EXISTS kills_weapon_idx   ON kills (weapon);
CREATE INDEX IF NOT EXISTS rounds_match_idx   ON rounds (match_id);

-- ---------------------------------------------------------------------------

-- ---------------------------------------------------------------------------
-- ดาเมจ — หนึ่งแถวต่อการสร้างความเสียหายหนึ่งครั้ง (สำหรับคำนวณ ADR / KAST)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS damages (
    id          BIGSERIAL PRIMARY KEY,
    round_id    INT NOT NULL REFERENCES rounds(id) ON DELETE CASCADE,
    tick        INT NOT NULL,
    attacker_id BIGINT REFERENCES players(steam_id),
    victim_id   BIGINT NOT NULL REFERENCES players(steam_id),
    weapon      TEXT,
    damage      INT NOT NULL,
    hitgroup    TEXT
);

CREATE INDEX IF NOT EXISTS damages_round_idx ON damages (round_id);
CREATE INDEX IF NOT EXISTS damages_attacker_idx ON damages (attacker_id);

-- ---------------------------------------------------------------------------
-- ผู้เล่นรายรอบ — หนึ่งแถวต่อคนต่อรอบ: อยู่ฝั่งไหน ถืออุปกรณ์มูลค่าเท่าไร รอดถึงจบรอบไหม
-- กุญแจของ KAST (S = survived), win rate (side = winner_side) และกราฟเศรษฐกิจ
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS player_rounds (
    id           BIGSERIAL PRIMARY KEY,
    round_id     INT     NOT NULL REFERENCES rounds(id) ON DELETE CASCADE,
    steam_id     BIGINT  NOT NULL REFERENCES players(steam_id),
    side         TEXT    NOT NULL CHECK (side IN ('ct', 't')),
    equip_value  INT,                        -- มูลค่าอุปกรณ์ตอน freeze time จบ (นิยาม HLTV)
    balance      INT,                        -- เงินในกระเป๋าตอนนั้น
    survived     BOOLEAN NOT NULL DEFAULT FALSE,
    UNIQUE (round_id, steam_id)
);
CREATE INDEX IF NOT EXISTS player_rounds_player_idx ON player_rounds (steam_id);

-- ระเบิด — หนึ่งแถวต่อลูกที่ขว้าง (utility per round)
CREATE TABLE IF NOT EXISTS grenades (
    id          BIGSERIAL PRIMARY KEY,
    round_id    INT    NOT NULL REFERENCES rounds(id) ON DELETE CASCADE,
    tick        INT    NOT NULL,
    thrower_id  BIGINT REFERENCES players(steam_id),
    side        TEXT   CHECK (side IN ('ct', 't')),
    type        TEXT   NOT NULL               -- flash / smoke / he / molotov / decoy
);
CREATE INDEX IF NOT EXISTS grenades_round_idx   ON grenades (round_id);
CREATE INDEX IF NOT EXISTS grenades_thrower_idx ON grenades (thrower_id);
"""


def upgrade() -> None:
    execute_script(TABLES_SQL)


def downgrade() -> None:
    execute_script("DROP TABLE IF EXISTS grenades, player_rounds, damages, kills, rounds, matches, players, users CASCADE;")
