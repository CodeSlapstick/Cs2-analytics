/**
 * ชั้นอ่านข้อมูลวิเคราะห์จากฐานข้อมูล — มาแทน services/sampleData.js ของ Sprint 0
 *
 * ทุกตัวเลขในไฟล์นี้มาจากตาราง match_players / player_match_kpi ที่ ETL เขียนไว้
 * ไม่มีการสุ่มค่าใด ๆ อีกแล้ว ถ้าฐานข้อมูลว่าง API ก็ตอบว่าไม่มีข้อมูล (แทนที่จะ
 * แต่งตัวเลขมาให้) — ตั้งใจให้หน้าเว็บแยกออกชัด ๆ ว่า "ยังไม่ได้โหลดแมตช์"
 * ต่างจาก "โหลดแล้วแต่ผู้เล่นคนนี้เล่นได้แย่"
 *
 * KPI ระดับ "ตลอดกาล" ของผู้เล่น คิดจากผลรวมตัวนับทุกแมตช์แล้วเข้าสูตรครั้งเดียว
 * (ไม่ใช่เอา KPI รายแมตช์มาเฉลี่ย) เพราะแมตช์ที่เล่น 8 รอบกับ 24 รอบ ไม่ควรมี
 * น้ำหนักเท่ากันในภาพรวม
 */
import { query, one } from '../db.js';
import { computeKpi, metricsFromStats } from '../lib/kpi.js';

const round2 = (v) => (v === null || v === undefined || !Number.isFinite(Number(v)) ? null : +Number(v).toFixed(2));

/** เฉลี่ย KPI 5 มิติเป็นคะแนนเดียว ใช้เป็น "performance rating" ของแมตช์นั้น */
function flatRating(k) {
  const vals = ['aim', 'positioning', 'utility', 'clutch', 'opening']
    .map((d) => Number(k?.[d]))
    .filter(Number.isFinite);
  return vals.length ? +(vals.reduce((a, b) => a + b, 0) / vals.length).toFixed(2) : null;
}

const SUM_COLUMNS = `
  COUNT(*)::int                          AS total_matches,
  COALESCE(SUM(mp.rounds_played),0)::int AS rounds_played,
  COALESCE(SUM(mp.kills),0)::int         AS kills,
  COALESCE(SUM(mp.deaths),0)::int        AS deaths,
  COALESCE(SUM(mp.assists),0)::int       AS assists,
  COALESCE(SUM(mp.headshot_kills),0)::int AS headshot_kills,
  COALESCE(SUM(mp.damage),0)::int        AS damage,
  COALESCE(SUM(mp.utility_damage),0)::int AS utility_damage,
  COALESCE(SUM(mp.grenades_thrown),0)::int AS grenades_thrown,
  COALESCE(SUM(mp.flash_assists),0)::int AS flash_assists,
  COALESCE(SUM(mp.opening_kills),0)::int AS opening_kills,
  COALESCE(SUM(mp.opening_deaths),0)::int AS opening_deaths,
  COALESCE(SUM(mp.trade_kills),0)::int   AS trade_kills,
  COALESCE(SUM(mp.traded_deaths),0)::int AS traded_deaths,
  COALESCE(SUM(mp.rounds_survived),0)::int AS rounds_survived,
  COALESCE(SUM(mp.clutches_won),0)::int  AS clutches_won,
  COALESCE(SUM(mp.clutches_attempted),0)::int AS clutches_attempted,
  COALESCE(SUM(CASE WHEN mp.won IS TRUE THEN 1 ELSE 0 END),0)::int AS wins,
  COALESCE(SUM(CASE WHEN mp.won IS FALSE THEN 1 ELSE 0 END),0)::int AS losses
`;

/** แมตช์ล่าสุดของผู้เล่นหนึ่งคน (รวมคะแนน KPI ของแมตช์นั้น ๆ) */
export async function getPlayerMatches(steam64Id, limit = 20) {
  const rows = await query(
    `SELECT m.id, m.external_id, m.map_name, m.finished_at, m.rounds_played AS match_rounds,
            m.score_team2, m.score_team3, m.source,
            mp.team_number, mp.won, mp.rounds_played, mp.kills, mp.deaths, mp.assists,
            mp.headshot_kills, mp.damage, mp.opening_kills, mp.opening_deaths,
            mp.clutches_won, mp.clutches_attempted,
            k.aim, k.positioning, k.utility, k.clutch, k.opening
       FROM match_players mp
       JOIN matches m ON m.id = mp.match_id
       LEFT JOIN player_match_kpi k ON k.match_id = mp.match_id AND k.steam64_id = mp.steam64_id
      WHERE mp.steam64_id = $1
      ORDER BY m.finished_at DESC NULLS LAST, m.id DESC
      LIMIT $2`,
    [String(steam64Id), Number(limit) || 20]
  );

  return rows.map((r) => {
    const mine = r.team_number === 2 ? r.score_team2 : r.score_team3;
    const theirs = r.team_number === 2 ? r.score_team3 : r.score_team2;
    const rating = { aim: r.aim, positioning: r.positioning, utility: r.utility, clutch: r.clutch, opening: r.opening };
    return {
      id: Number(r.id),
      external_id: r.external_id,
      map_name: r.map_name,
      finished_at: r.finished_at,
      source: r.source,
      outcome: mine === theirs ? 'tie' : mine > theirs ? 'win' : 'loss',
      score: [mine, theirs],
      rounds_played: r.rounds_played,
      kills: r.kills,
      deaths: r.deaths,
      assists: r.assists,
      adr: round2(r.rounds_played ? r.damage / r.rounds_played : null),
      hs_pct: round2(r.kills ? r.headshot_kills / r.kills : null),
      opening_kills: r.opening_kills,
      opening_deaths: r.opening_deaths,
      clutches_won: r.clutches_won,
      clutches_attempted: r.clutches_attempted,
      rating,
      performance_rating: flatRating(rating),
    };
  });
}

/**
 * โปรไฟล์ผู้เล่นหนึ่งคน — คืน null ถ้าไม่เคยมีแมตช์ของคนนี้ในฐานข้อมูล
 * (ให้ route ตอบ 404 ไป ดีกว่าคืนโปรไฟล์เปล่าที่ดูเหมือนผู้เล่นห่วย)
 */
export async function getPlayerProfile(steam64Id, matchLimit = 20) {
  const id = String(steam64Id);
  const totals = await one(
    `SELECT ${SUM_COLUMNS},
            MIN(m.finished_at) AS first_match_date,
            MAX(m.finished_at) AS last_match_date
       FROM match_players mp JOIN matches m ON m.id = mp.match_id
      WHERE mp.steam64_id = $1`,
    [id]
  );
  if (!totals || totals.total_matches === 0) return null;

  const player = await one('SELECT name FROM players WHERE steam64_id = $1', [id]);
  const metrics = metricsFromStats(totals);
  const rating = computeKpi(metrics);
  const decided = totals.wins + totals.losses;

  return {
    steam64_id: id,
    name: player?.name || `Player_${id.slice(-4)}`,
    total_matches: totals.total_matches,
    rounds_played: totals.rounds_played,
    wins: totals.wins,
    losses: totals.losses,
    winrate: decided ? +(totals.wins / decided).toFixed(3) : null,
    first_match_date: totals.first_match_date,
    last_match_date: totals.last_match_date,
    rating,
    kpi_score: flatRating(rating),
    totals: {
      kills: totals.kills,
      deaths: totals.deaths,
      assists: totals.assists,
      headshot_kills: totals.headshot_kills,
      damage: totals.damage,
      opening_kills: totals.opening_kills,
      opening_deaths: totals.opening_deaths,
      clutches_won: totals.clutches_won,
      clutches_attempted: totals.clutches_attempted,
      trade_kills: totals.trade_kills,
      traded_deaths: totals.traded_deaths,
    },
    // อัตราส่วนที่สูตร KPI ใช้จริง — ส่งไปให้ frontend โชว์ได้ว่าคะแนนมาจากตัวเลขอะไร
    stats: {
      adr: round2(metrics.adr),
      kpr: round2(metrics.kpr),
      dpr: round2(metrics.dpr),
      kd: round2(metrics.kd),
      hs_pct: round2(metrics.hs_pct),
      survival_rate: round2(metrics.survival_rate),
      traded_death_pct: round2(metrics.traded_death_pct),
      utility_damage_per_round: round2(metrics.udr),
      nades_per_round: round2(metrics.nades_per_round),
      flash_assist_rate: round2(metrics.flash_assist_rate),
      opening_attempt_rate: round2(metrics.opening_attempt_rate),
      opening_win_pct: round2(metrics.opening_win_pct),
      clutch_rate: round2(metrics.clutch_rate),
      clutch_win_pct: round2(metrics.clutch_win_pct),
    },
    recent_matches: await getPlayerMatches(id, matchLimit),
  };
}

/** รายชื่อแมตช์ทั้งหมดในระบบ (หน้า "แมตช์") */
export async function listMatches({ limit = 30, offset = 0, steam64Id = null } = {}) {
  const rows = await query(
    `SELECT m.id, m.external_id, m.map_name, m.finished_at, m.rounds_played,
            m.score_team2, m.score_team3, m.source, m.demo_file,
            (SELECT COUNT(*)::int FROM match_players mp WHERE mp.match_id = m.id) AS player_count,
            (SELECT COUNT(*)::int FROM coach_notes n WHERE n.match_id = m.id) AS note_count
       FROM matches m
      WHERE $3::text IS NULL
         OR EXISTS (SELECT 1 FROM match_players mp WHERE mp.match_id = m.id AND mp.steam64_id = $3)
      ORDER BY m.finished_at DESC NULLS LAST, m.id DESC
      LIMIT $1 OFFSET $2`,
    [Number(limit) || 30, Number(offset) || 0, steam64Id ? String(steam64Id) : null]
  );
  return rows.map((r) => ({
    ...r,
    id: Number(r.id),
    team_scores: [
      { team_number: 2, score: r.score_team2 },
      { team_number: 3, score: r.score_team3 },
    ],
  }));
}

/** รายละเอียดแมตช์ + สกอร์บอร์ดผู้เล่นทั้งสองฝั่ง */
export async function getMatchDetails(matchId) {
  const id = Number(matchId);
  if (!Number.isFinite(id)) return null;

  const match = await one('SELECT * FROM matches WHERE id = $1', [id]);
  if (!match) return null;

  const rows = await query(
    `SELECT mp.*, k.aim, k.positioning, k.utility, k.clutch, k.opening
       FROM match_players mp
       LEFT JOIN player_match_kpi k ON k.match_id = mp.match_id AND k.steam64_id = mp.steam64_id
      WHERE mp.match_id = $1
      ORDER BY mp.team_number, mp.kills DESC`,
    [id]
  );

  const scoreboard = rows.map((r) => {
    const rating = { aim: r.aim, positioning: r.positioning, utility: r.utility, clutch: r.clutch, opening: r.opening };
    return {
      steam64_id: r.steam64_id,
      name: r.name,
      team_number: r.team_number,
      rounds_played: r.rounds_played,
      kills: r.kills,
      deaths: r.deaths,
      assists: r.assists,
      headshot_kills: r.headshot_kills,
      hs_pct: round2(r.kills ? r.headshot_kills / r.kills : null),
      kd: round2(r.deaths ? r.kills / r.deaths : r.kills),
      adr: round2(r.rounds_played ? r.damage / r.rounds_played : null),
      utility_damage: r.utility_damage,
      opening_kills: r.opening_kills,
      opening_deaths: r.opening_deaths,
      trade_kills: r.trade_kills,
      clutches_won: r.clutches_won,
      clutches_attempted: r.clutches_attempted,
      rating,
      performance_rating: flatRating(rating),
    };
  });

  const rounds = await query(
    `SELECT round_number, winner_team_number, winner_side, end_reason, bomb_planted
       FROM rounds WHERE match_id = $1 ORDER BY round_number`,
    [id]
  );

  return {
    id: Number(match.id),
    external_id: match.external_id,
    map_name: match.map_name,
    started_at: match.started_at,
    finished_at: match.finished_at,
    rounds_played: match.rounds_played,
    source: match.source,
    demo_file: match.demo_file,
    team_scores: [
      { team_number: 2, score: match.score_team2 },
      { team_number: 3, score: match.score_team3 },
    ],
    stats: scoreboard,
    rounds,
  };
}

/** พิกัดคิลของแมตช์ — เตรียมไว้ให้ heatmap ใน sprint ถัดไปเรียกใช้ได้เลย */
export async function getMatchKillPositions(matchId) {
  return query(
    `SELECT round_number, tick, actor_steam64, victim_steam64, weapon, headshot,
            actor_x, actor_y, actor_z, victim_x, victim_y, victim_z
       FROM events
      WHERE match_id = $1 AND event_type = 'kill'
      ORDER BY round_number, tick`,
    [Number(matchId)]
  );
}
