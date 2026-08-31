-- =====================================================================
-- 001_init — โครงสร้างฐานข้อมูล PostgreSQL ของ CS2 Team Analytics
--
-- แทนที่ SQLite เดิม (4 ตาราง: users/teams/team_members/coach_notes)
-- ด้วย 10 ตารางตาม ER diagram ใน proposal เพื่อรองรับข้อมูลจริงจากไฟล์ .dem
--
-- แบ่งเป็น 3 กลุ่ม
--   1) ผู้ใช้/ทีม   — users, teams, team_members, coach_notes   (ของเดิม ย้ายมา)
--   2) ข้อมูลแมตช์  — players, matches, rounds, match_players, events
--   3) ผลวิเคราะห์  — player_match_kpi (KPI 5 มิติ คิดตอน ETL เก็บผลไว้เลย)
--
-- ห้ามเพิ่มตารางเก็บผลลัพธ์จาก API ภายนอก (บทเรียนจาก Leetify: ToS ห้าม cache)
-- ข้อมูลทุกแถวในนี้ต้องมาจากไฟล์ .dem ที่เรา parse เอง หรือจาก seed ของเราเอง
-- =====================================================================

-- ---------- 1) ผู้ใช้ / ทีม ----------

CREATE TABLE IF NOT EXISTS users (
  id            BIGSERIAL PRIMARY KEY,
  steam64_id    TEXT        NOT NULL UNIQUE,
  display_name  TEXT        NOT NULL,
  avatar_url    TEXT,
  profile_url   TEXT,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  last_login_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS teams (
  id          BIGSERIAL PRIMARY KEY,
  name        TEXT        NOT NULL,
  owner_id    BIGINT      NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  is_opponent BOOLEAN     NOT NULL DEFAULT FALSE,
  -- น้ำหนัก KPI ที่โค้ชตั้งเอง เก็บเป็น jsonb เพราะจำนวนมิติอาจเพิ่มทีหลัง
  kpi_weights JSONB       NOT NULL DEFAULT '{"aim":1,"positioning":1,"utility":1,"clutch":1,"opening":1}'::jsonb,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_teams_owner ON teams(owner_id);

CREATE TABLE IF NOT EXISTS team_members (
  id         BIGSERIAL PRIMARY KEY,
  team_id    BIGINT      NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
  steam64_id TEXT        NOT NULL,
  nickname   TEXT,
  role       TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (team_id, steam64_id)
);

-- ---------- 2) ข้อมูลแมตช์ (มาจาก pipeline parse .dem) ----------

-- ทะเบียนผู้เล่นทุกคนที่เคยโผล่ในไฟล์ .dem ที่โหลดเข้ามา
-- แยกจาก users เพราะคนที่เราวิเคราะห์ ส่วนใหญ่ไม่เคยล็อกอินเว็บเรา (เช่น ทีมคู่แข่ง)
CREATE TABLE IF NOT EXISTS players (
  steam64_id    TEXT PRIMARY KEY,
  name          TEXT        NOT NULL,
  first_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  last_seen_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS matches (
  id            BIGSERIAL PRIMARY KEY,
  -- คีย์จากไฟล์ต้นทาง ใช้กันโหลดซ้ำ: โหลด .dem ไฟล์เดิมอีกรอบ = อัปเดตทับ ไม่ใช่เพิ่มแถวใหม่
  external_id   TEXT        NOT NULL UNIQUE,
  map_name      TEXT        NOT NULL,
  started_at    TIMESTAMPTZ,
  finished_at   TIMESTAMPTZ,
  rounds_played INTEGER     NOT NULL DEFAULT 0,
  -- สกอร์แยกตาม "ทีมที่เริ่มฝั่งไหน": team2 = เริ่มเป็น T, team3 = เริ่มเป็น CT
  score_team2   INTEGER     NOT NULL DEFAULT 0,
  score_team3   INTEGER     NOT NULL DEFAULT 0,
  tickrate      INTEGER,
  source        TEXT        NOT NULL DEFAULT 'demo',   -- 'demo' | 'sample'
  demo_file     TEXT,
  server_name   TEXT,
  parsed_at     TIMESTAMPTZ,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_matches_finished ON matches(finished_at DESC);

CREATE TABLE IF NOT EXISTS rounds (
  id                 BIGSERIAL PRIMARY KEY,
  match_id           BIGINT  NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
  round_number       INTEGER NOT NULL,
  winner_team_number SMALLINT,          -- 2 | 3
  winner_side        TEXT,              -- 't' | 'ct'
  end_reason         TEXT,
  bomb_planted       BOOLEAN NOT NULL DEFAULT FALSE,
  start_tick         INTEGER,
  freeze_end_tick    INTEGER,
  end_tick           INTEGER,
  official_end_tick  INTEGER,
  UNIQUE (match_id, round_number)
);

-- สถิติรายคนต่อแมตช์ — คำนวณตอน ETL (ดู backend/src/etl/derive.js)
-- เก็บผลไว้เลยแทนที่จะคิดสดจากตาราง events ทุกครั้ง เพราะ events โตเร็วมาก
-- (1 แมตช์ ประมาณ 150-250 kill + 600+ damage สะสม 50 แมตช์ก็หลักหมื่นแถว)
CREATE TABLE IF NOT EXISTS match_players (
  id              BIGSERIAL PRIMARY KEY,
  match_id        BIGINT   NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
  steam64_id      TEXT     NOT NULL REFERENCES players(steam64_id) ON DELETE CASCADE,
  name            TEXT     NOT NULL,
  team_number     SMALLINT NOT NULL,        -- 2 = เริ่มฝั่ง T, 3 = เริ่มฝั่ง CT
  rounds_played   INTEGER  NOT NULL DEFAULT 0,
  won             BOOLEAN,                  -- ทีมของคนนี้ชนะแมตช์ไหม (null = เสมอ)

  kills           INTEGER NOT NULL DEFAULT 0,
  deaths          INTEGER NOT NULL DEFAULT 0,
  assists         INTEGER NOT NULL DEFAULT 0,
  headshot_kills  INTEGER NOT NULL DEFAULT 0,
  damage          INTEGER NOT NULL DEFAULT 0,   -- ดาเมจรวมที่ทำใส่ศัตรู
  utility_damage  INTEGER NOT NULL DEFAULT 0,   -- ดาเมจจาก he/molotov เท่านั้น
  grenades_thrown INTEGER NOT NULL DEFAULT 0,
  flash_assists   INTEGER NOT NULL DEFAULT 0,

  opening_kills   INTEGER NOT NULL DEFAULT 0,   -- ฆ่าคนแรกของรอบ
  opening_deaths  INTEGER NOT NULL DEFAULT 0,   -- ตายเป็นคนแรกของรอบ
  trade_kills     INTEGER NOT NULL DEFAULT 0,   -- ฆ่าล้างแค้นให้เพื่อนภายใน 5 วินาที
  traded_deaths   INTEGER NOT NULL DEFAULT 0,   -- ตายแล้วเพื่อนล้างแค้นให้ทัน
  rounds_survived INTEGER NOT NULL DEFAULT 0,

  clutches_won       INTEGER NOT NULL DEFAULT 0,
  clutches_attempted INTEGER NOT NULL DEFAULT 0,

  UNIQUE (match_id, steam64_id)
);
CREATE INDEX IF NOT EXISTS idx_match_players_player ON match_players(steam64_id);

-- เหตุการณ์ดิบรายรอบ พร้อมพิกัด X/Y/Z — เก็บไว้ทำ heatmap และตรวจย้อนหลังได้ว่า
-- ตัวเลขใน match_players มาจากไหน (ถ้าไม่เก็บ จะพิสูจน์สูตร KPI กับกรรมการไม่ได้)
CREATE TABLE IF NOT EXISTS events (
  id               BIGSERIAL PRIMARY KEY,
  match_id         BIGINT  NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
  round_id         BIGINT  REFERENCES rounds(id) ON DELETE CASCADE,
  round_number     INTEGER NOT NULL,
  tick             INTEGER,
  event_type       TEXT    NOT NULL,     -- kill | damage | grenade | bomb
  actor_steam64    TEXT,
  victim_steam64   TEXT,
  assister_steam64 TEXT,
  weapon           TEXT,
  headshot         BOOLEAN NOT NULL DEFAULT FALSE,
  damage           INTEGER,
  actor_x  DOUBLE PRECISION, actor_y  DOUBLE PRECISION, actor_z  DOUBLE PRECISION,
  victim_x DOUBLE PRECISION, victim_y DOUBLE PRECISION, victim_z DOUBLE PRECISION,
  meta             JSONB
);
CREATE INDEX IF NOT EXISTS idx_events_match_round ON events(match_id, round_number);
CREATE INDEX IF NOT EXISTS idx_events_actor ON events(actor_steam64, event_type);

-- ---------- 3) ผลวิเคราะห์ ----------

-- KPI 5 มิติ ของผู้เล่นหนึ่งคนในแมตช์หนึ่งนัด (สเกลประมาณ -10 ถึง +10, 0 = ค่ากลาง)
-- สูตรและค่าฐานอยู่ใน backend/src/lib/kpi.js — เก็บ metrics ดิบไว้ใน jsonb ด้วย
-- เพื่อให้ย้อนดูได้ว่าคะแนนแต่ละมิติมาจากตัวเลขอะไร (ตอนนำเสนอจะถูกถามแน่)
CREATE TABLE IF NOT EXISTS player_match_kpi (
  match_id    BIGINT NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
  steam64_id  TEXT   NOT NULL REFERENCES players(steam64_id) ON DELETE CASCADE,
  aim         REAL,
  positioning REAL,
  utility     REAL,
  clutch      REAL,
  opening     REAL,
  metrics     JSONB  NOT NULL DEFAULT '{}'::jsonb,
  computed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (match_id, steam64_id)
);

-- ---------- โน้ตของโค้ช (ผูกกับ matches จริงแล้ว ไม่ใช่ text id ลอย ๆ) ----------

CREATE TABLE IF NOT EXISTS coach_notes (
  id         BIGSERIAL PRIMARY KEY,
  author_id  BIGINT      NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  match_id   BIGINT      NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
  team_id    BIGINT      REFERENCES teams(id) ON DELETE SET NULL,
  body       TEXT        NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_notes_match ON coach_notes(match_id);
