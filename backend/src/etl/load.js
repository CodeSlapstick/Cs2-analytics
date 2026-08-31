/**
 * ETL loader — normalized JSON → PostgreSQL
 *
 * คุณสมบัติที่ต้องมี (และเทสต์ไว้ใน backend/test/etl.test.js)
 *   1) โหลดซ้ำได้ (idempotent) — ไฟล์เดิม external_id เดิม โหลดกี่รอบก็ได้ผลเท่าเดิม
 *      ไม่ใช่ข้อมูลซ้อนกันเป็นสองแมตช์
 *   2) ทั้งหมดอยู่ใน transaction เดียว — พังกลางทางแล้ว rollback หมด ไม่เหลือแมตช์ครึ่งใบ
 *   3) ไม่คิดสถิติเอง — เรียก deriveMatch() ที่เดียว (ดูเหตุผลใน derive.js)
 */
import { tx } from '../db.js';
import { deriveMatch, validateMatch } from './derive.js';

/** แบ่ง insert เป็นก้อน กัน parameter เกินลิมิตของ Postgres (65535 ตัวต่อคำสั่ง) */
async function insertMany(t, table, columns, rows, chunkSize = 400) {
  if (rows.length === 0) return;
  const cols = columns.join(', ');
  for (let i = 0; i < rows.length; i += chunkSize) {
    const chunk = rows.slice(i, i + chunkSize);
    const params = [];
    const tuples = chunk.map((row) => {
      const slots = row.map((v) => {
        params.push(v);
        return `$${params.length}`;
      });
      return `(${slots.join(', ')})`;
    });
    await t.query(`INSERT INTO ${table} (${cols}) VALUES ${tuples.join(', ')}`, params);
  }
}

/**
 * โหลดหนึ่งแมตช์เข้าฐานข้อมูล
 * @returns {{match_id:number, external_id:string, inserted:{rounds:number,events:number,players:number}, warnings:string[], replaced:boolean}}
 */
export async function loadMatch(doc) {
  const { errors, warnings } = validateMatch(doc);
  if (errors.length) {
    const err = new Error(`normalized JSON ไม่ผ่านการตรวจ:\n - ${errors.join('\n - ')}`);
    err.validationErrors = errors;
    throw err;
  }

  const d = deriveMatch(doc);

  return tx(async (t) => {
    // ---- ทะเบียนผู้เล่น (ไม่ผูกกับแมตช์ ค้างไว้ข้ามแมตช์ได้) ----
    for (const p of d.players) {
      await t.query(
        `INSERT INTO players (steam64_id, name)
         VALUES ($1, $2)
         ON CONFLICT (steam64_id) DO UPDATE SET name = EXCLUDED.name, last_seen_at = now()`,
        [p.steam64_id, p.name || `Player_${p.steam64_id.slice(-4)}`]
      );
    }

    // ---- ตัวแมตช์ ----
    const m = d.match;
    const existing = await t.query('SELECT id FROM matches WHERE external_id = $1', [m.external_id]);
    const replaced = existing.rows.length > 0;

    const inserted = await t.query(
      `INSERT INTO matches (external_id, map_name, started_at, finished_at, rounds_played,
                            score_team2, score_team3, tickrate, source, demo_file, server_name, parsed_at)
       VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11, now())
       ON CONFLICT (external_id) DO UPDATE SET
         map_name = EXCLUDED.map_name, started_at = EXCLUDED.started_at,
         finished_at = EXCLUDED.finished_at, rounds_played = EXCLUDED.rounds_played,
         score_team2 = EXCLUDED.score_team2, score_team3 = EXCLUDED.score_team3,
         tickrate = EXCLUDED.tickrate, source = EXCLUDED.source,
         demo_file = EXCLUDED.demo_file, server_name = EXCLUDED.server_name,
         parsed_at = now()
       RETURNING id`,
      [m.external_id, m.map_name, m.started_at, m.finished_at, m.rounds_played,
       m.score_team2, m.score_team3, m.tickrate, m.source, m.demo_file, m.server_name]
    );
    const matchId = Number(inserted.rows[0].id);

    // โหลดทับของเดิม: ลบลูกทั้งหมดของแมตช์นี้ก่อน แล้วเขียนใหม่ทั้งชุด
    // (coach_notes ไม่โดนลบ เพราะเป็นของโค้ช ไม่ใช่ผลจากการ parse)
    if (replaced) {
      await t.query('DELETE FROM events WHERE match_id = $1', [matchId]);
      await t.query('DELETE FROM rounds WHERE match_id = $1', [matchId]);
      await t.query('DELETE FROM match_players WHERE match_id = $1', [matchId]);
      await t.query('DELETE FROM player_match_kpi WHERE match_id = $1', [matchId]);
    }

    // ---- รอบ ----
    await insertMany(
      t,
      'rounds',
      ['match_id', 'round_number', 'winner_team_number', 'winner_side', 'end_reason',
       'bomb_planted', 'start_tick', 'freeze_end_tick', 'end_tick', 'official_end_tick'],
      d.rounds.map((r) => [
        matchId, r.round_number, r.winner_team_number ?? null, r.winner_side ?? null,
        r.end_reason ?? null, Boolean(r.bomb_planted), r.start_tick ?? null,
        r.freeze_end_tick ?? null, r.end_tick ?? null, r.official_end_tick ?? null,
      ])
    );

    const roundIds = new Map(
      (await t.query('SELECT id, round_number FROM rounds WHERE match_id = $1', [matchId])).rows.map(
        (r) => [Number(r.round_number), Number(r.id)]
      )
    );

    // ---- สถิติรายคน ----
    await insertMany(
      t,
      'match_players',
      ['match_id', 'steam64_id', 'name', 'team_number', 'rounds_played', 'won',
       'kills', 'deaths', 'assists', 'headshot_kills', 'damage', 'utility_damage',
       'grenades_thrown', 'flash_assists', 'opening_kills', 'opening_deaths',
       'trade_kills', 'traded_deaths', 'rounds_survived', 'clutches_won', 'clutches_attempted'],
      d.stats.map((s) => [
        matchId, s.steam64_id, s.name, s.team_number, s.rounds_played, s.won,
        s.kills, s.deaths, s.assists, s.headshot_kills, s.damage, s.utility_damage,
        s.grenades_thrown, s.flash_assists, s.opening_kills, s.opening_deaths,
        s.trade_kills, s.traded_deaths, s.rounds_survived, s.clutches_won, s.clutches_attempted,
      ])
    );

    // ---- KPI 5 มิติ (คิดจากสถิติข้างบน เก็บ metrics ดิบไว้ตรวจย้อนหลัง) ----
    await insertMany(
      t,
      'player_match_kpi',
      ['match_id', 'steam64_id', 'aim', 'positioning', 'utility', 'clutch', 'opening', 'metrics'],
      d.kpi.map((k) => [
        matchId, k.steam64_id, k.aim, k.positioning, k.utility, k.clutch, k.opening,
        JSON.stringify(k.metrics),
      ])
    );

    // ---- event ดิบ (ก้อนใหญ่สุด — 1 แมตช์ราว 800-1500 แถว) ----
    await insertMany(
      t,
      'events',
      ['match_id', 'round_id', 'round_number', 'tick', 'event_type', 'actor_steam64',
       'victim_steam64', 'assister_steam64', 'weapon', 'headshot', 'damage',
       'actor_x', 'actor_y', 'actor_z', 'victim_x', 'victim_y', 'victim_z', 'meta'],
      d.events.map((e) => [
        matchId, roundIds.get(Number(e.round_number)) ?? null, Number(e.round_number),
        e.tick ?? null, e.type, e.actor_steam64 ?? null, e.victim_steam64 ?? null,
        e.assister_steam64 ?? null, e.weapon ?? null, Boolean(e.headshot),
        e.damage ?? null, e.actor_x ?? null, e.actor_y ?? null, e.actor_z ?? null,
        e.victim_x ?? null, e.victim_y ?? null, e.victim_z ?? null,
        e.meta ? JSON.stringify(e.meta) : null,
      ])
    );

    return {
      match_id: matchId,
      external_id: m.external_id,
      replaced,
      inserted: { rounds: d.rounds.length, events: d.events.length, players: d.stats.length },
      warnings,
    };
  });
}
