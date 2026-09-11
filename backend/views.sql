-- backend/views.sql — view ทั้งหมดของระบบ
--
-- ตารางไม่ได้อยู่ที่นี่แล้ว: ตารางเป็นหน้าที่ของ Alembic (backend/alembic/versions/)  ->  alembic upgrade head
-- ไฟล์นี้มีแต่ view ซึ่ง backend/app.py รันซ้ำทุกครั้งที่สตาร์ต (ปลอดภัย: CREATE OR REPLACE / DROP+CREATE ไม่แตะข้อมูล)
-- แก้สูตร KPI ที่นี่ที่เดียว แล้วรีสตาร์ตเซิร์ฟเวอร์ ไม่ต้องเขียน migration
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
       COUNT(k.id)                                            AS kills,
       m.status,                                              -- queued / parsing / done / error (Sprint 2)
       m.error_message,
       m.started_at,
       m.finished_at
FROM matches m
LEFT JOIN rounds r ON r.match_id = m.id
LEFT JOIN kills  k ON k.round_id = r.id
GROUP BY m.id;

-- ---------------------------------------------------------------------------
-- View ชั้นที่ 1: ข้อเท็จจริงรายคนรายรอบ — ฐานของ KAST / rating / opening / trade / ADR
-- ทุกคอลัมน์คือ "เกิดหรือไม่เกิดในรอบนั้น" ยังไม่รวมข้ามรอบ
-- DROP ก่อน CREATE เพราะ CREATE OR REPLACE VIEW ห้ามเปลี่ยนลำดับ/ชนิดคอลัมน์ของ view เดิม
-- ---------------------------------------------------------------------------
DROP VIEW IF EXISTS player_round_facts CASCADE;
CREATE VIEW player_round_facts AS
WITH duel AS (                          -- เฉพาะการดวลจริง: มีคนยิง และคนละฝั่ง (ตัด C4 / ตกที่สูง / ทีมคิล)
    SELECT k.*, m.tickrate
    FROM kills k JOIN rounds r ON r.id = k.round_id JOIN matches m ON m.id = r.match_id
    WHERE k.attacker_id IS NOT NULL AND k.attacker_side <> k.victim_side
), opening AS (                         -- คิลแรกของรอบ
    SELECT DISTINCT ON (round_id) round_id, attacker_id, victim_id
    FROM duel ORDER BY round_id, tick, id
), traded_death AS (                    -- ตายแล้วเพื่อนเก็บคนที่ฆ่าเราคืนภายใน 5 วินาที (เกณฑ์ HLTV)
    SELECT DISTINCT d.round_id, d.victim_id AS steam_id
    FROM duel d JOIN duel k2 ON k2.round_id = d.round_id AND k2.victim_id = d.attacker_id
                            AND k2.tick > d.tick AND k2.tick <= d.tick + 5 * d.tickrate
), trade_kill AS (                      -- ฆ่าคนที่เพิ่งฆ่าเพื่อนเราภายใน 5 วินาที
    SELECT k.round_id, k.attacker_id AS steam_id, COUNT(*) AS trade_kills
    FROM duel k JOIN duel d ON d.round_id = k.round_id AND d.attacker_id = k.victim_id
                            AND d.tick < k.tick AND d.tick >= k.tick - 5 * k.tickrate
                            AND d.victim_side = k.attacker_side
    GROUP BY k.round_id, k.attacker_id
), per_round AS (
    SELECT round_id, attacker_id AS steam_id, COUNT(*) AS kills, COUNT(*) FILTER (WHERE headshot) AS headshots
    FROM duel GROUP BY round_id, attacker_id
), died AS (
    SELECT DISTINCT round_id, victim_id AS steam_id FROM kills
), assists AS (
    SELECT round_id, assister_id AS steam_id, COUNT(*) AS assists
    FROM kills WHERE assister_id IS NOT NULL GROUP BY round_id, assister_id
), dmg AS (                             -- ดาเมจใส่ศัตรูเท่านั้น (ตัดยิงตัวเอง / ทีม)
    SELECT dm.round_id, dm.attacker_id AS steam_id, SUM(dm.damage) AS damage
    FROM damages dm
    JOIN player_rounds pa ON pa.round_id = dm.round_id AND pa.steam_id = dm.attacker_id
    JOIN player_rounds pv ON pv.round_id = dm.round_id AND pv.steam_id = dm.victim_id
    WHERE pa.side <> pv.side
    GROUP BY dm.round_id, dm.attacker_id
), util AS (
    SELECT round_id, thrower_id AS steam_id, COUNT(*) AS grenades
    FROM grenades WHERE thrower_id IS NOT NULL GROUP BY round_id, thrower_id
)
SELECT pr.round_id, r.match_id, r.round_num, pr.steam_id, pr.side, pr.equip_value, pr.survived,
       (r.winner_side = pr.side)                            AS won,
       COALESCE(k.kills, 0)                                 AS kills,
       COALESCE(k.headshots, 0)                             AS headshots,
       COALESCE(a.assists, 0)                               AS assists,
       (dd.steam_id IS NOT NULL)::int                       AS deaths,
       COALESCE(d.damage, 0)                                AS damage,
       COALESCE(u.grenades, 0)                              AS grenades,
       COALESCE(o.attacker_id = pr.steam_id, FALSE)         AS opening_kill,
       COALESCE(o.victim_id   = pr.steam_id, FALSE)         AS opening_death,
       (td.steam_id IS NOT NULL)                            AS was_traded,
       COALESCE(tk.trade_kills, 0)                          AS trade_kills,
       (COALESCE(k.kills, 0) > 0 OR COALESCE(a.assists, 0) > 0 OR pr.survived OR td.steam_id IS NOT NULL) AS kast
FROM player_rounds pr
JOIN rounds r ON r.id = pr.round_id
LEFT JOIN per_round k     ON k.round_id  = pr.round_id AND k.steam_id  = pr.steam_id
LEFT JOIN died dd         ON dd.round_id = pr.round_id AND dd.steam_id = pr.steam_id
LEFT JOIN assists a       ON a.round_id  = pr.round_id AND a.steam_id  = pr.steam_id
LEFT JOIN dmg d           ON d.round_id  = pr.round_id AND d.steam_id  = pr.steam_id
LEFT JOIN util u          ON u.round_id  = pr.round_id AND u.steam_id  = pr.steam_id
LEFT JOIN opening o       ON o.round_id  = pr.round_id
LEFT JOIN traded_death td ON td.round_id = pr.round_id AND td.steam_id = pr.steam_id
LEFT JOIN trade_kill tk   ON tk.round_id = pr.round_id AND tk.steam_id = pr.steam_id;

-- ---------------------------------------------------------------------------
-- View ชั้นที่ 1: clutch — จังหวะที่ฝั่งหนึ่งเหลือคนเดียวและอีกฝั่งยังมีคน ใครคือคนนั้น ชนะไหม
-- (1v1 นับเป็น clutch ของทั้งสองฝั่ง เหมือนเกณฑ์ HLTV)
-- ---------------------------------------------------------------------------
DROP VIEW IF EXISTS player_clutches CASCADE;
CREATE VIEW player_clutches AS
WITH ev AS (                            -- หลังคิลแต่ละครั้ง แต่ละฝั่งตายไปแล้วกี่คน
    SELECT k.round_id, k.tick,
           SUM((k.victim_side = 'ct')::int) OVER w AS dead_ct,
           SUM((k.victim_side = 't')::int)  OVER w AS dead_t
    FROM kills k
    WINDOW w AS (PARTITION BY k.round_id ORDER BY k.tick, k.id)
), start AS (                           -- จังหวะแรกที่ฝั่งหนึ่งเหลือ 1 คน
    SELECT round_id, side, MIN(tick) AS start_tick
    FROM (
        SELECT round_id, tick, 'ct' AS side FROM ev WHERE dead_ct = 4 AND dead_t < 5
        UNION ALL
        SELECT round_id, tick, 't'  AS side FROM ev WHERE dead_t = 4 AND dead_ct < 5
    ) s GROUP BY round_id, side
), enemies AS (                         -- ณ จังหวะนั้น ศัตรูเหลือกี่คน
    SELECT s.round_id, s.side, s.start_tick,
           5 - MAX(CASE WHEN s.side = 'ct' THEN e.dead_t ELSE e.dead_ct END) AS vs
    FROM start s JOIN ev e ON e.round_id = s.round_id AND e.tick <= s.start_tick
    GROUP BY s.round_id, s.side, s.start_tick
)
SELECT e.round_id, r.match_id, e.side, pr.steam_id, e.vs, (r.winner_side = e.side) AS won
FROM enemies e
JOIN rounds r ON r.id = e.round_id
JOIN player_rounds pr ON pr.round_id = e.round_id AND pr.side = e.side
WHERE e.vs >= 1
  AND NOT EXISTS (SELECT 1 FROM kills k WHERE k.round_id = e.round_id AND k.victim_id = pr.steam_id AND k.tick <= e.start_tick);

-- ---------------------------------------------------------------------------
-- View ชั้นที่ 2: สถิติรายนักแข่งรวมทุกแมตช์ — API /api/players อ่านตัวนี้
-- 9 คอลัมน์แรกคงเดิมเพื่อไม่ให้หน้าเว็บเก่าพัง คอลัมน์ใหม่ต่อท้าย
-- ---------------------------------------------------------------------------
DROP VIEW IF EXISTS player_stats CASCADE;
CREATE VIEW player_stats AS
WITH f AS (
    SELECT steam_id,
           COUNT(*)                                          AS rounds,
           COUNT(DISTINCT match_id)                          AS matches,
           SUM(kills) AS kills, SUM(deaths) AS deaths, SUM(assists) AS assists, SUM(headshots) AS headshots,
           SUM(damage) AS damage, SUM(grenades) AS grenades,
           COUNT(*) FILTER (WHERE kast)                      AS kast_rounds,
           COUNT(*) FILTER (WHERE won)                       AS rounds_won,
           COUNT(*) FILTER (WHERE survived)                  AS rounds_survived,
           COUNT(*) FILTER (WHERE opening_kill)              AS opening_kills,
           COUNT(*) FILTER (WHERE opening_death)             AS opening_deaths,
           SUM(trade_kills)                                  AS trade_kills,
           COUNT(*) FILTER (WHERE deaths > 0 AND was_traded) AS traded_deaths,
           COUNT(*) FILTER (WHERE kills = 1)  AS k1,
           COUNT(*) FILTER (WHERE kills = 2)  AS k2,
           COUNT(*) FILTER (WHERE kills = 3)  AS k3,
           COUNT(*) FILTER (WHERE kills = 4)  AS k4,
           COUNT(*) FILTER (WHERE kills >= 5) AS k5
    FROM player_round_facts GROUP BY steam_id
), c AS (
    SELECT steam_id, COUNT(*) AS clutch_attempts, COUNT(*) FILTER (WHERE won) AS clutch_wins
    FROM player_clutches GROUP BY steam_id
)
SELECT p.steam_id,
       p.name,
       COALESCE(f.matches, 0)    AS matches,
       COALESCE(f.kills, 0)      AS kills,
       COALESCE(f.deaths, 0)     AS deaths,
       COALESCE(f.assists, 0)    AS assists,
       COALESCE(f.headshots, 0)  AS headshots,
       ROUND(COALESCE(f.kills, 0)::numeric / GREATEST(COALESCE(f.deaths, 0), 1), 2)     AS kd,
       ROUND(100.0 * COALESCE(f.headshots, 0) / GREATEST(COALESCE(f.kills, 0), 1), 1)   AS hs_rate,
       -- ใหม่ (ต้องมี player_rounds ถึงจะไม่เป็นศูนย์)
       COALESCE(f.rounds, 0)                                                              AS rounds,
       ROUND(COALESCE(f.damage, 0)::numeric / GREATEST(COALESCE(f.rounds, 0), 1), 1)     AS adr,
       ROUND(100.0 * COALESCE(f.kast_rounds, 0) / GREATEST(COALESCE(f.rounds, 0), 1), 1) AS kast,
       ROUND(100.0 * COALESCE(f.rounds_won, 0) / GREATEST(COALESCE(f.rounds, 0), 1), 1)  AS win_rate,
       ROUND(100.0 * COALESCE(f.rounds_survived, 0) / GREATEST(COALESCE(f.rounds, 0), 1), 1) AS survival_rate,
       COALESCE(f.opening_kills, 0)                                                       AS opening_kills,
       COALESCE(f.opening_deaths, 0)                                                      AS opening_deaths,
       ROUND(100.0 * COALESCE(f.opening_kills, 0) / GREATEST(COALESCE(f.rounds, 0), 1), 1) AS opening_rate,
       COALESCE(f.trade_kills, 0)                                                         AS trade_kills,
       ROUND(100.0 * COALESCE(f.trade_kills, 0) / GREATEST(COALESCE(f.rounds, 0), 1), 1) AS trade_rate,
       ROUND(100.0 * COALESCE(f.traded_deaths, 0) / GREATEST(COALESCE(f.deaths, 0), 1), 1) AS traded_rate,
       ROUND(COALESCE(f.grenades, 0)::numeric / GREATEST(COALESCE(f.rounds, 0), 1), 2)   AS util_per_round,
       COALESCE(c.clutch_attempts, 0)                                                     AS clutch_attempts,
       COALESCE(c.clutch_wins, 0)                                                         AS clutch_wins,
       -- HLTV Rating 1.0 — สูตรที่ HLTV เปิดเผยสาธารณะ ไม่ใช่น้ำหนักที่เราตั้งเอง
       --   (KillRating + 0.7*SurvivalRating + MultiKillRating) / 2.7
       --   ค่าหาร 0.679 / 0.317 / 1.277 คือค่าเฉลี่ยของโปรที่ HLTV ใช้ทำให้ 1.00 = ผู้เล่นทั่วไป
       ROUND((
             (COALESCE(f.kills, 0)::numeric / GREATEST(COALESCE(f.rounds, 0), 1)) / 0.679
           + 0.7 * ((COALESCE(f.rounds, 0) - COALESCE(f.deaths, 0))::numeric / GREATEST(COALESCE(f.rounds, 0), 1)) / 0.317
           + ((COALESCE(f.k1, 0) + 4 * COALESCE(f.k2, 0) + 9 * COALESCE(f.k3, 0) + 16 * COALESCE(f.k4, 0) + 25 * COALESCE(f.k5, 0))::numeric
              / GREATEST(COALESCE(f.rounds, 0), 1)) / 1.277
       ) / 2.7, 2)                                                                        AS rating
FROM players p
LEFT JOIN f USING (steam_id)
LEFT JOIN c USING (steam_id);

-- ---------------------------------------------------------------------------
-- View ชั้นที่ 2: สกอร์บอร์ดรายแมตช์ — /api/matches/{id} อ่านตัวนี้
-- ---------------------------------------------------------------------------
DROP VIEW IF EXISTS match_scoreboard CASCADE;
CREATE VIEW match_scoreboard AS
SELECT f.match_id, f.steam_id, p.name,
       (array_agg(f.side ORDER BY f.round_num))[1]                   AS start_side,   -- ฝั่งที่เริ่มครึ่งแรก = ระบุทีม
       COUNT(*)                                                       AS rounds,
       SUM(f.kills) AS kills, SUM(f.deaths) AS deaths, SUM(f.assists) AS assists, SUM(f.headshots) AS headshots,
       ROUND(SUM(f.damage)::numeric / COUNT(*), 1)                    AS adr,
       ROUND(100.0 * COUNT(*) FILTER (WHERE f.kast) / COUNT(*), 1)    AS kast,
       ROUND(100.0 * SUM(f.headshots) / GREATEST(SUM(f.kills), 1), 1) AS hs_rate,
       ROUND((
             (SUM(f.kills)::numeric / COUNT(*)) / 0.679
           + 0.7 * ((COUNT(*) - SUM(f.deaths))::numeric / COUNT(*)) / 0.317
           + ((COUNT(*) FILTER (WHERE f.kills = 1) + 4 * COUNT(*) FILTER (WHERE f.kills = 2) + 9 * COUNT(*) FILTER (WHERE f.kills = 3)
               + 16 * COUNT(*) FILTER (WHERE f.kills = 4) + 25 * COUNT(*) FILTER (WHERE f.kills >= 5))::numeric / COUNT(*)) / 1.277
       ) / 2.7, 2)                                                    AS rating
FROM player_round_facts f
JOIN players p USING (steam_id)
GROUP BY f.match_id, f.steam_id, p.name;

-- ---------------------------------------------------------------------------
-- View ชั้นที่ 2: เศรษฐกิจรายรอบ — กราฟ equipment value ต่อรอบ + buy type
-- ขีดแบ่ง buy type ใช้ชุดเดียวกับ pipeline/features.py (มูลค่ารวมทั้งทีม 5 คน)
-- ---------------------------------------------------------------------------
DROP VIEW IF EXISTS round_economy CASCADE;
CREATE VIEW round_economy AS
WITH s AS (
    SELECT r.match_id, r.id AS round_id, r.round_num, r.winner_side, r.end_reason,
           SUM(pr.equip_value) FILTER (WHERE pr.side = 'ct') AS ct_equip,
           SUM(pr.equip_value) FILTER (WHERE pr.side = 't')  AS t_equip
    FROM rounds r JOIN player_rounds pr ON pr.round_id = r.id
    GROUP BY r.match_id, r.id
)
SELECT s.*,
       CASE WHEN round_num IN (1, 13) THEN 'pistol'
            WHEN ct_equip <= 5000  THEN 'eco'
            WHEN ct_equip <= 10000 THEN 'semi_eco'
            WHEN ct_equip <= 20000 THEN 'semi_buy'
            ELSE 'full' END AS ct_buy_type,
       CASE WHEN round_num IN (1, 13) THEN 'pistol'
            WHEN t_equip <= 5000  THEN 'eco'
            WHEN t_equip <= 10000 THEN 'semi_eco'
            WHEN t_equip <= 20000 THEN 'semi_buy'
            ELSE 'full' END AS t_buy_type
FROM s;
