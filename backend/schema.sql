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
-- View สรุป — เขียน SQL ยาก ๆ ไว้ที่เดียว API แค่ SELECT * FROM view
-- ---------------------------------------------------------------------------

-- สรุปรายแมตช์: กี่รอบ ฝั่งไหนชนะกี่รอบ คิลรวม
CREATE OR REPLACE VIEW match_summary AS
SELECT m.id,
       m.demo_file,
       m.map_name,
       m.team_a,
       m.team_b,
       m.tickrate,
       m.imported_at,
       COUNT(DISTINCT r.id)                                   AS rounds,
       COUNT(DISTINCT r.id) FILTER (WHERE r.winner_side = 'ct') AS ct_rounds,
       COUNT(DISTINCT r.id) FILTER (WHERE r.winner_side = 't')  AS t_rounds,
       COUNT(k.id)                                            AS kills
FROM matches m
LEFT JOIN rounds r ON r.match_id = m.id
LEFT JOIN kills  k ON k.round_id = r.id
GROUP BY m.id;

-- สถิติรายนักแข่งรวมทุกแมตช์: คิล ตาย ยิงหัว K/D
CREATE OR REPLACE VIEW player_stats AS
WITH k AS (
    SELECT attacker_id AS steam_id,
           COUNT(*)                          AS kills,
           COUNT(*) FILTER (WHERE headshot)  AS headshots
    FROM kills WHERE attacker_id IS NOT NULL
    GROUP BY attacker_id
), d AS (
    SELECT victim_id AS steam_id, COUNT(*) AS deaths
    FROM kills GROUP BY victim_id
), a AS (
    SELECT assister_id AS steam_id, COUNT(*) AS assists
    FROM kills WHERE assister_id IS NOT NULL
    GROUP BY assister_id
), mp AS (
    -- นับว่าเล่นกี่แมตช์ = แมตช์ที่โผล่เป็นคนยิงหรือคนตายอย่างน้อยหนึ่งครั้ง
    SELECT steam_id, COUNT(DISTINCT match_id) AS matches
    FROM (
        SELECT k.attacker_id AS steam_id, r.match_id FROM kills k JOIN rounds r ON r.id = k.round_id
        UNION
        SELECT k.victim_id,               r.match_id FROM kills k JOIN rounds r ON r.id = k.round_id
    ) x WHERE steam_id IS NOT NULL
    GROUP BY steam_id
)
SELECT p.steam_id,
       p.name,
       COALESCE(mp.matches, 0)   AS matches,
       COALESCE(k.kills, 0)      AS kills,
       COALESCE(d.deaths, 0)     AS deaths,
       COALESCE(a.assists, 0)    AS assists,
       COALESCE(k.headshots, 0)  AS headshots,
       ROUND(COALESCE(k.kills, 0)::numeric / GREATEST(COALESCE(d.deaths, 0), 1), 2) AS kd,
       ROUND(100.0 * COALESCE(k.headshots, 0) / GREATEST(COALESCE(k.kills, 0), 1), 1) AS hs_rate
FROM players p
LEFT JOIN k  USING (steam_id)
LEFT JOIN d  USING (steam_id)
LEFT JOIN a  USING (steam_id)
LEFT JOIN mp USING (steam_id);
