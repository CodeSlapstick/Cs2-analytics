/**
 * เทสต์ ETL แบบยิงลงฐานข้อมูลจริง
 *
 * ใช้ PGlite แบบ in-memory (PGLITE_DIR=memory://) จึงไม่แตะข้อมูลใน data/pgdata
 * ที่ใช้ dev อยู่ และไม่ต้องมี PostgreSQL server ตอนรันเทสต์
 */
import './setup-env.js'; // ต้องมาก่อน import อื่นทั้งหมด — อ่านเหตุผลในไฟล์นั้น
import { test, describe, before, after } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { query, exec, closeDb } from '../src/db.js';
import { loadMatch } from '../src/etl/load.js';

const here = dirname(fileURLToPath(import.meta.url));

const A = '76561198000000001';
const B = '76561198000000002';
const C = '76561198000000003';
const D = '76561198000000004';

function sampleDoc(overrides = {}) {
  return {
    schema_version: 1,
    match: {
      external_id: 'etl-test-1',
      map_name: 'de_nuke',
      finished_at: '2025-08-01T12:00:00.000Z',
      tickrate: 64,
      source: 'sample',
      ...overrides,
    },
    players: [
      { steam64_id: A, name: 'A', team_number: 2 },
      { steam64_id: B, name: 'B', team_number: 2 },
      { steam64_id: C, name: 'C', team_number: 3 },
      { steam64_id: D, name: 'D', team_number: 3 },
    ],
    rounds: [
      { round_number: 1, winner_team_number: 2, winner_side: 't', end_reason: 't_win', bomb_planted: true },
      { round_number: 2, winner_team_number: 3, winner_side: 'ct', end_reason: 'ct_win' },
    ],
    events: [
      { type: 'kill', round_number: 1, tick: 100, actor_steam64: A, victim_steam64: C, weapon: 'ak47', headshot: true,
        actor_x: 1, actor_y: 2, actor_z: 3, victim_x: 4, victim_y: 5, victim_z: 6 },
      { type: 'kill', round_number: 1, tick: 200, actor_steam64: A, victim_steam64: D, weapon: 'ak47' },
      { type: 'kill', round_number: 2, tick: 300, actor_steam64: C, victim_steam64: A, weapon: 'awp' },
      { type: 'kill', round_number: 2, tick: 400, actor_steam64: D, victim_steam64: B, weapon: 'awp' },
      { type: 'damage', round_number: 1, tick: 90, actor_steam64: A, victim_steam64: C, weapon: 'hegrenade', damage: 40 },
    ],
  };
}

before(async () => {
  const sql = readFileSync(resolve(here, '../db/migrations/001_init.sql'), 'utf8');
  await exec(sql);
});

after(async () => {
  await closeDb();
});

describe('loadMatch', () => {
  test('โหลดครั้งแรก เขียนครบทุกตาราง', async () => {
    const r = await loadMatch(sampleDoc());
    assert.equal(r.replaced, false);
    assert.equal(r.inserted.rounds, 2);
    assert.equal(r.inserted.players, 4);

    const [m] = await query('SELECT * FROM matches WHERE external_id = $1', ['etl-test-1']);
    assert.equal(m.map_name, 'de_nuke');
    assert.equal(m.score_team2, 1);
    assert.equal(m.score_team3, 1);
    assert.equal(m.rounds_played, 2);

    const players = await query('SELECT * FROM players ORDER BY steam64_id');
    assert.equal(players.length, 4);

    const [{ count: eventCount }] = await query('SELECT COUNT(*)::int AS count FROM events WHERE match_id = $1', [m.id]);
    assert.equal(eventCount, 5);
  });

  test('event ผูกกับ round ที่ถูกต้อง (มี round_id ไม่ใช่แค่เลขรอบ)', async () => {
    const rows = await query(
      `SELECT e.round_number, r.round_number AS joined_round
         FROM events e JOIN rounds r ON r.id = e.round_id
        ORDER BY e.tick`
    );
    assert.ok(rows.length > 0);
    for (const row of rows) assert.equal(row.round_number, row.joined_round);
  });

  test('เก็บพิกัดคิลไว้ครบ (ใช้ทำ heatmap ต่อ)', async () => {
    const [kill] = await query(
      "SELECT actor_x, actor_y, victim_x FROM events WHERE event_type = 'kill' AND tick = 100"
    );
    assert.deepEqual([kill.actor_x, kill.actor_y, kill.victim_x], [1, 2, 4]);
  });

  test('คำนวณสถิติและ KPI เก็บลงตารางให้เลย', async () => {
    const [a] = await query(
      `SELECT mp.kills, mp.deaths, mp.headshot_kills, mp.utility_damage, mp.won,
              k.aim, k.metrics
         FROM match_players mp
         JOIN player_match_kpi k ON k.match_id = mp.match_id AND k.steam64_id = mp.steam64_id
        WHERE mp.steam64_id = $1`,
      [A]
    );
    assert.equal(a.kills, 2);
    assert.equal(a.deaths, 1);
    assert.equal(a.headshot_kills, 1);
    assert.equal(a.utility_damage, 40);
    assert.equal(a.won, null, 'สกอร์ 1–1 = เสมอ');
    assert.ok(Number.isFinite(a.aim));
    assert.ok(a.metrics.kpr > 0, 'เก็บ metrics ดิบไว้ตรวจย้อนหลังได้');
  });

  test('โหลดไฟล์เดิมซ้ำ = อัปเดตทับ ไม่ใช่ข้อมูลซ้อน', async () => {
    const r = await loadMatch(sampleDoc());
    assert.equal(r.replaced, true);

    const [{ count: matches }] = await query('SELECT COUNT(*)::int AS count FROM matches');
    assert.equal(matches, 1);
    const [{ count: rounds }] = await query('SELECT COUNT(*)::int AS count FROM rounds');
    assert.equal(rounds, 2, 'รอบต้องไม่ซ้อนเป็น 4');
    const [{ count: stats }] = await query('SELECT COUNT(*)::int AS count FROM match_players');
    assert.equal(stats, 4);
  });

  test('โหลดทับแล้วโน้ตของโค้ชต้องยังอยู่ (ไม่ใช่ผลจากการ parse)', async () => {
    const [m] = await query('SELECT id FROM matches WHERE external_id = $1', ['etl-test-1']);
    const [u] = await query(
      "INSERT INTO users (steam64_id, display_name) VALUES ('76561198000009999','โค้ช') RETURNING id"
    );
    await query('INSERT INTO coach_notes (author_id, match_id, body) VALUES ($1, $2, $3)', [
      u.id, m.id, 'ต้องซ้อม retake ไซต์ B',
    ]);

    await loadMatch(sampleDoc());
    const notes = await query('SELECT body FROM coach_notes WHERE match_id = $1', [m.id]);
    assert.equal(notes.length, 1);
    assert.equal(notes[0].body, 'ต้องซ้อม retake ไซต์ B');
  });

  test('ไฟล์ที่ไม่ผ่าน validate ต้องโยน error และไม่เขียนอะไรเลย', async () => {
    const before = (await query('SELECT COUNT(*)::int AS count FROM matches'))[0].count;
    const broken = sampleDoc({ external_id: 'etl-test-broken' });
    broken.players[0].team_number = 5; // ต้องเป็น 2 หรือ 3 เท่านั้น

    await assert.rejects(() => loadMatch(broken), /team_number/);
    const after = (await query('SELECT COUNT(*)::int AS count FROM matches'))[0].count;
    assert.equal(after, before, 'ต้องไม่มีแมตช์ใหม่ถูกสร้าง');
  });

  test('ลบแมตช์แล้ว event/รอบ/สถิติของแมตช์นั้นหายตามไปด้วย (ON DELETE CASCADE)', async () => {
    const doc = sampleDoc({ external_id: 'etl-test-cascade' });
    const r = await loadMatch(doc);
    await query('DELETE FROM matches WHERE id = $1', [r.match_id]);

    for (const table of ['rounds', 'events', 'match_players', 'player_match_kpi']) {
      const [{ count }] = await query(`SELECT COUNT(*)::int AS count FROM ${table} WHERE match_id = $1`, [r.match_id]);
      assert.equal(count, 0, `${table} ต้องไม่มีแถวค้าง`);
    }
  });
});
