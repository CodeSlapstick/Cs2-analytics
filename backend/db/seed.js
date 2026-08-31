#!/usr/bin/env node
/**
 * Seed — สร้างข้อมูลตัวอย่างให้ระบบมีอะไรให้ดูตั้งแต่รันครั้งแรก
 *
 * สำคัญ: สคริปต์นี้ **ไม่ได้เขียนลงตารางเอง** แต่สร้าง "normalized JSON" หน้าตา
 * เดียวกับที่ parser ฝั่ง Python ปล่อยออกมา (ดู docs/normalized-match.md) แล้วส่ง
 * เข้า ETL ตัวเดียวกับข้อมูลจริง (src/etl/load.js)
 *
 * ทำแบบนี้เพราะสองเหตุผล
 *   1) ทุกครั้งที่ seed = ได้ทดสอบ ETL ทั้งเส้นทางจริง ๆ ไม่ใช่ทางลัดที่ใช้ได้แค่ตอน demo
 *   2) วันที่ได้ไฟล์ .dem จริงมา เราจะรู้ทันทีว่า pipeline ฝั่งหลัง parser ใช้งานได้อยู่
 *      เพราะมันคือโค้ดเส้นเดียวกันที่รันมาตลอด
 *
 * ข้อมูลที่ได้เป็นการ "จำลองการยิงกันรายรอบ" (ใครฆ่าใคร ตอน tick ไหน ตรงพิกัดไหน)
 * ไม่ใช่การสุ่มตัวเลขสถิติตรง ๆ — สถิติทุกตัวถูกคำนวณจาก event เหล่านั้นด้วยสูตร
 * เดียวกับข้อมูลจริง (src/etl/derive.js) ตัวเลขจึงสอดคล้องกันเองเสมอ
 * (K + D ของทั้งสองฝั่งเท่ากัน, ADR สมเหตุสมผลกับจำนวนรอบ ฯลฯ)
 *
 * ใช้: npm run db:seed        (ล้างของเดิมที่ source='sample' แล้วสร้างใหม่)
 */
import { query, tx, closeDb } from '../src/db.js';
import { loadMatch } from '../src/etl/load.js';

// ---------------------------------------------------------------------------
// สุ่มแบบมีเมล็ด — รันกี่ครั้งก็ได้ข้อมูลชุดเดิม (จะได้เทียบผลก่อน/หลังแก้โค้ดได้)
// ---------------------------------------------------------------------------
function rng(seed) {
  let s = seed >>> 0 || 1;
  return () => {
    s = (s * 1664525 + 1013904223) >>> 0;
    return s / 4294967296;
  };
}

const MAPS = ['de_mirage', 'de_inferno', 'de_nuke', 'de_ancient', 'de_dust2', 'de_anubis'];
const RIFLES = ['ak47', 'm4a1_silencer', 'm4a1', 'awp', 'deagle', 'galilar', 'famas', 'usp_silencer', 'glock'];
const NADES = ['flashbang', 'smokegrenade', 'hegrenade', 'molotov', 'incgrenade'];
const UTIL_DMG_WEAPONS = ['hegrenade', 'inferno'];

// ทีมเรา — คนแรกใช้ Steam64 เดียวกับที่กรอกไว้ในหน้า "โหมดทดสอบ" ของหน้า login
// เข้าระบบด้วย ID นี้แล้วหน้าแดชบอร์ดจะมีข้อมูลทันที
const OUR_TEAM = [
  { steam64_id: '76561198283431555', name: 'Nine', role: 'IGL', skill: 0.62 },
  { steam64_id: '76561198111000021', name: 'Bank', role: 'AWPer', skill: 0.74 },
  { steam64_id: '76561198111000022', name: 'Ohm', role: 'Entry', skill: 0.58 },
  { steam64_id: '76561198111000023', name: 'Guide', role: 'Support', skill: 0.45 },
  { steam64_id: '76561198111000024', name: 'Pete', role: 'Lurker', skill: 0.55 },
];

const OPPONENTS = [
  { steam64_id: '76561198222000031', name: 'Zeta', skill: 0.6 },
  { steam64_id: '76561198222000032', name: 'Krit', skill: 0.52 },
  { steam64_id: '76561198222000033', name: 'Ryu', skill: 0.66 },
  { steam64_id: '76561198222000034', name: 'Mos', skill: 0.48 },
  { steam64_id: '76561198222000035', name: 'Ton', skill: 0.57 },
];

const TICKRATE = 64;

/** สุ่มพิกัดบนแผนที่แบบหยาบ ๆ (หน่วยเดียวกับพิกัดในเกม) ไว้ทำ heatmap ใน sprint ถัดไป */
const coord = (r) => ({
  x: +(-2200 + r() * 4400).toFixed(1),
  y: +(-1400 + r() * 3600).toFixed(1),
  z: +(-180 + r() * 360).toFixed(1),
});

function pickWeighted(list, r) {
  const total = list.reduce((a, p) => a + p.skill, 0);
  let t = r() * total;
  for (const p of list) {
    t -= p.skill;
    if (t <= 0) return p;
  }
  return list[list.length - 1];
}

/**
 * จำลองหนึ่งรอบ: ตัดสินผู้ชนะก่อน แล้วค่อยจำลองว่าใครฆ่าใครจนได้ผลนั้น
 * คืน event ของรอบนั้นทั้งหมด (kill / damage / grenade)
 */
function simulateRound(roundNumber, teams, winnerTeam, startTick, r) {
  const events = [];
  const alive = { 2: [...teams[2]], 3: [...teams[3]] };
  const loser = winnerTeam === 2 ? 3 : 2;
  let tick = startTick + 1000;

  // ยูทิลิตี้ช่วงต้นรอบ — ผู้เล่นจริงขว้างกันราว 1.5–2 ลูกต่อคนต่อรอบ
  const nadeCount = 12 + Math.floor(r() * 9);
  for (let i = 0; i < nadeCount; i++) {
    const side = r() < 0.5 ? 2 : 3;
    const actor = pickWeighted(teams[side], r);
    const weapon = NADES[Math.floor(r() * NADES.length)];
    const c = coord(r);
    tick += Math.floor(20 + r() * 90);
    events.push({
      type: 'grenade', round_number: roundNumber, tick,
      actor_steam64: actor.steam64_id, victim_steam64: null, assister_steam64: null,
      weapon, headshot: false, damage: null,
      actor_x: c.x, actor_y: c.y, actor_z: c.z,
      victim_x: null, victim_y: null, victim_z: null,
      meta: { thrown: true },
    });
    // ยูทิลิตี้บางลูกโดนคน
    if (UTIL_DMG_WEAPONS.includes(weapon) && r() < 0.55) {
      const victim = alive[side === 2 ? 3 : 2][Math.floor(r() * alive[side === 2 ? 3 : 2].length)];
      if (victim) {
        events.push({
          type: 'damage', round_number: roundNumber, tick: tick + 30,
          actor_steam64: actor.steam64_id, victim_steam64: victim.steam64_id, assister_steam64: null,
          weapon: weapon === 'molotov' || weapon === 'incgrenade' ? 'inferno' : weapon,
          headshot: false, damage: Math.floor(8 + r() * 45),
          actor_x: c.x, actor_y: c.y, actor_z: c.z,
          victim_x: c.x + 120, victim_y: c.y - 90, victim_z: c.z,
          meta: { utility: true },
        });
      }
    }
  }

  // ฝ่ายแพ้ต้องเสียคนเกือบหมด ฝ่ายชนะเสียได้บ้าง
  // ราว 12% ของรอบ ฝ่ายชนะเหลือคนเดียว = รอบคลัตช์ (1vX) ให้ข้อมูลมิติ clutch มีน้ำหนัก
  const loserDeaths = r() < 0.75 ? 5 : 3 + Math.floor(r() * 2);
  const winnerDeaths = r() < 0.12 ? 4 : Math.floor(r() * 4);
  const plan = [];
  for (let i = 0; i < loserDeaths; i++) plan.push(loser);
  for (let i = 0; i < winnerDeaths; i++) plan.push(winnerTeam);
  // สลับลำดับการตายแบบมีเมล็ด (Fisher–Yates)
  for (let i = plan.length - 1; i > 0; i--) {
    const j = Math.floor(r() * (i + 1));
    [plan[i], plan[j]] = [plan[j], plan[i]];
  }
  // รอบคลัตช์: ให้ฝ่ายชนะตายไปก่อนจนเหลือคนเดียว แล้วค่อยเก็บฝ่ายตรงข้ามทีละคน
  // ถ้าปล่อยให้สลับมั่ว คนสุดท้ายของฝ่ายชนะจะไม่เคยอยู่ในสถานการณ์ 1vX เลย
  // แล้วมิติ clutch จะติดลบกันทั้งกระดานเพราะไม่มีใครชนะคลัตช์ได้เลยสักคน
  if (winnerDeaths === 4) plan.sort((a, b) => (a === winnerTeam ? -1 : 0) - (b === winnerTeam ? -1 : 0));

  for (const dyingTeam of plan) {
    const killerTeam = dyingTeam === 2 ? 3 : 2;
    if (alive[dyingTeam].length === 0 || alive[killerTeam].length === 0) continue;

    const victim = pickWeighted(
      alive[dyingTeam].map((p) => ({ ...p, skill: 1.2 - p.skill })), // คนสกิลต่ำมักตายก่อน
      r
    );
    const killer = pickWeighted(alive[killerTeam], r);
    const weapon = RIFLES[Math.floor(r() * RIFLES.length)];
    const a = coord(r);
    const v = coord(r);
    tick += Math.floor(120 + r() * 700);

    // ดาเมจนำก่อนตาย (คนอื่นอาจช่วยยิง)
    const chip = Math.floor(r() * 60);
    if (chip > 12) {
      const helper = alive[killerTeam][Math.floor(r() * alive[killerTeam].length)];
      events.push({
        type: 'damage', round_number: roundNumber, tick: tick - 40,
        actor_steam64: helper.steam64_id, victim_steam64: victim.steam64_id, assister_steam64: null,
        weapon: RIFLES[Math.floor(r() * RIFLES.length)], headshot: false, damage: chip,
        actor_x: a.x, actor_y: a.y, actor_z: a.z, victim_x: v.x, victim_y: v.y, victim_z: v.z,
        meta: null,
      });
    }

    const killDamage = 100 - chip;
    events.push({
      type: 'damage', round_number: roundNumber, tick: tick - 1,
      actor_steam64: killer.steam64_id, victim_steam64: victim.steam64_id, assister_steam64: null,
      weapon, headshot: false, damage: killDamage,
      actor_x: a.x, actor_y: a.y, actor_z: a.z, victim_x: v.x, victim_y: v.y, victim_z: v.z,
      meta: null,
    });

    const assistPool = alive[killerTeam].filter((p) => p.steam64_id !== killer.steam64_id);
    const assister = r() < 0.28 && assistPool.length ? assistPool[Math.floor(r() * assistPool.length)] : null;
    events.push({
      type: 'kill', round_number: roundNumber, tick,
      actor_steam64: killer.steam64_id, victim_steam64: victim.steam64_id,
      assister_steam64: assister ? assister.steam64_id : null,
      weapon, headshot: r() < 0.2 + killer.skill * 0.4, damage: killDamage,
      actor_x: a.x, actor_y: a.y, actor_z: a.z, victim_x: v.x, victim_y: v.y, victim_z: v.z,
      meta: { assistedflash: Boolean(assister) && r() < 0.35, noscope: weapon === 'awp' && r() < 0.05 },
    });

    alive[dyingTeam] = alive[dyingTeam].filter((p) => p.steam64_id !== victim.steam64_id);
  }

  return { events, endTick: tick + 400 };
}

/** สร้างหนึ่งแมตช์เป็น normalized JSON (schema เดียวกับ parser) */
function buildMatch(index, seed) {
  const r = rng(seed);
  const map = MAPS[index % MAPS.length];
  const ourSide = index % 2 === 0 ? 2 : 3; // สลับฝั่งเริ่มต้นไปมา
  const oppSide = ourSide === 2 ? 3 : 2;

  const players = [
    ...OUR_TEAM.map((p) => ({ ...p, team_number: ourSide })),
    ...OPPONENTS.map((p) => ({ ...p, team_number: oppSide })),
  ];
  const teams = {
    2: players.filter((p) => p.team_number === 2),
    3: players.filter((p) => p.team_number === 3),
  };

  const ourStrength = OUR_TEAM.reduce((a, p) => a + p.skill, 0);
  const oppStrength = OPPONENTS.reduce((a, p) => a + p.skill, 0);
  const ourWinChance = 0.5 + (ourStrength - oppStrength) * 0.12 + (r() - 0.5) * 0.22;

  const rounds = [];
  const events = [];
  let score = { 2: 0, 3: 0 };
  let tick = 12000;

  for (let n = 1; n <= 24; n++) {
    if (score[2] === 13 || score[3] === 13) break;
    const winnerTeam = r() < ourWinChance ? ourSide : oppSide;
    const sim = simulateRound(n, teams, winnerTeam, tick, r);
    events.push(...sim.events);
    score[winnerTeam] += 1;

    // ฝั่งของแต่ละทีมสลับหลังจบครึ่งแรก (รอบที่ 12) — MR12 ตามกติกา CS2 ปัจจุบัน
    const swapped = n > 12;
    const winnerStartedT = winnerTeam === 2;
    const winnerSide = swapped ? (winnerStartedT ? 'ct' : 't') : winnerStartedT ? 't' : 'ct';

    rounds.push({
      round_number: n,
      winner_team_number: winnerTeam,
      winner_side: winnerSide,
      end_reason: winnerSide === 't' ? (r() < 0.35 ? 'bomb_exploded' : 't_win') : r() < 0.3 ? 'bomb_defused' : 'ct_win',
      bomb_planted: r() < 0.55,
      start_tick: tick,
      freeze_end_tick: tick + 900,
      end_tick: sim.endTick,
      official_end_tick: sim.endTick + 320,
    });
    tick = sim.endTick + 700;
  }

  const finishedAt = new Date(Date.now() - index * 2.5 * 86400000);
  const startedAt = new Date(finishedAt.getTime() - (30 + rounds.length * 100000) * 60);

  return {
    schema_version: 1,
    match: {
      external_id: `sample-${map}-${String(index + 1).padStart(2, '0')}`,
      map_name: map,
      started_at: startedAt.toISOString(),
      finished_at: finishedAt.toISOString(),
      tickrate: TICKRATE,
      source: 'sample',
      demo_file: null,
      server_name: 'Seed (ข้อมูลจำลอง)',
    },
    players: players.map((p) => ({
      steam64_id: p.steam64_id,
      name: p.name,
      team_number: p.team_number,
      rounds_played: rounds.length,
    })),
    rounds,
    events,
  };
}

// ---------------------------------------------------------------------------

async function seedUserAndTeams() {
  const owner = OUR_TEAM[0];
  const user = await tx(async (t) => {
    const res = await t.query(
      `INSERT INTO users (steam64_id, display_name)
       VALUES ($1, $2)
       ON CONFLICT (steam64_id) DO UPDATE SET display_name = EXCLUDED.display_name
       RETURNING id`,
      [owner.steam64_id, `${owner.name} (โค้ช)`]
    );
    return Number(res.rows[0].id);
  });

  await query('DELETE FROM teams WHERE owner_id = $1', [user]);

  const mkTeam = async (name, isOpponent, roster) => {
    const t = await query(
      'INSERT INTO teams (name, owner_id, is_opponent) VALUES ($1, $2, $3) RETURNING id',
      [name, user, isOpponent]
    );
    const teamId = Number(t[0].id);
    for (const p of roster) {
      await query(
        'INSERT INTO team_members (team_id, steam64_id, nickname, role) VALUES ($1, $2, $3, $4)',
        [teamId, p.steam64_id, p.name, p.role || null]
      );
    }
    return teamId;
  };

  await mkTeam('UTCC eSports', false, OUR_TEAM);
  await mkTeam('คู่แข่ง — Zeta Five', true, OPPONENTS);
  return user;
}

async function main() {
  const matchCount = Number(process.argv[2]) || 12;

  console.log('[seed] ล้างข้อมูลแมตช์ที่ source = sample ของเดิมทิ้งก่อน');
  await query("DELETE FROM matches WHERE source = 'sample'");

  console.log(`[seed] สร้าง ${matchCount} แมตช์จำลอง แล้วส่งเข้า ETL ตัวเดียวกับข้อมูลจริง`);
  let events = 0;
  for (let i = 0; i < matchCount; i++) {
    const doc = buildMatch(i, 20250801 + i * 7919);
    const r = await loadMatch(doc);
    events += r.inserted.events;
    console.log(`  ✓ ${r.external_id} — ${r.inserted.rounds} รอบ, ${r.inserted.events} events`);
  }

  const userId = await seedUserAndTeams();
  console.log(`[seed] สร้างผู้ใช้ตัวอย่าง (id=${userId}) + ทีม UTCC eSports และทีมคู่แข่ง`);

  const [{ count: playerCount }] = await query('SELECT COUNT(*)::int AS count FROM players');
  console.log(
    `\nเสร็จแล้ว: ${matchCount} แมตช์, ${playerCount} ผู้เล่น, ${events} events\n` +
      `เข้าระบบที่หน้า login ด้วยโหมดทดสอบ Steam64 = ${OUR_TEAM[0].steam64_id} เพื่อดูข้อมูลชุดนี้`
  );
}

main()
  .catch((e) => {
    console.error('[seed] ล้มเหลว:', e);
    process.exitCode = 1;
  })
  .finally(() => closeDb());
