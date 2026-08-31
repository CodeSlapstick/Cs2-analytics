/**
 * ชั้นคำนวณของ ETL — normalized JSON (ข้อเท็จจริงดิบ) → สถิติรายคนต่อแมตช์ + KPI
 *
 * ตั้งใจแยกไฟล์นี้ออกจากการเขียนฐานข้อมูล (load.js) ด้วยเหตุผลเดียว:
 * ตรงนี้คือ "สูตร" ทั้งหมดของโปรเจกต์ (opening duel, trade, clutch, ADR) ซึ่งเป็น
 * ส่วนที่ต้องพิสูจน์ให้กรรมการดูได้ว่าคิดยังไง — เป็นฟังก์ชันบริสุทธิ์ล้วน
 * ไม่แตะ DB ไม่แตะไฟล์ จึงเขียนเทสต์ยิงตรงได้ (backend/test/derive.test.js)
 *
 * และเป็นเหตุผลเดียวกับที่ parser ฝั่ง Python ไม่คิดสถิติพวกนี้เอง — ถ้าคิดสองที่
 * (Python ตอน parse + Node ตอน seed) สูตรจะเพี้ยนกันแน่นอนเมื่อแก้ข้างเดียว
 */
import { computeKpi, metricsFromStats } from '../lib/kpi.js';

/** ช่วงเวลาที่ถือว่า "ล้างแค้นให้เพื่อนทัน" = 5 วินาที (แปลงเป็น tick ตาม tickrate) */
export const TRADE_WINDOW_SECONDS = 5;

/**
 * จับคู่ "คิลล้างแค้น" กับ "ศพที่ถูกล้างแค้นให้" แบบหนึ่งต่อหนึ่ง
 *
 * อยู่แยกเป็นฟังก์ชันเพราะมีสองที่ที่ต้องใช้: ตัวนับ trade_kills/traded_deaths
 * ข้างล่างนี้ กับการวิเคราะห์ "ตายตรงไหนแล้วไม่มีใครล้างแค้นให้" ใน
 * services/mapInsights.js ถ้าต่างคนต่างเขียน ตัวเลขสองหน้าจะขัดกันเองโดยไม่มีใครรู้
 * (เคยเกิดจริง: นับได้ 13 กับ 10 จากข้อมูลชุดเดียวกัน)
 *
 * หนึ่งต่อหนึ่งสำคัญ: ถ้าศัตรูคนเดียวฆ่าเพื่อนเราสองคนแล้วเราฆ่ามันคืน
 * นับเป็นการล้างแค้นให้ศพเดียว ไม่ใช่สองศพ
 *
 * @param {Array<{victim:string, actor:string|null, victimTeam:number|null,
 *                actorTeam:number|null, tick:number}>} kills คิลของหนึ่งรอบ เรียงตาม tick แล้ว
 * @param {number} tickrate
 * @returns {number[]} ยาวเท่า kills — ค่าคือ index ของศพที่คิลนั้นล้างแค้นให้ (−1 = ไม่ได้ล้างแค้น)
 */
export function matchTrades(kills, tickrate) {
  const window = TRADE_WINDOW_SECONDS * (Number(tickrate) || 64);
  const enemies = (a, b) => a !== null && b !== null && a !== b;
  const deathLog = [];
  const tradedBy = new Array(kills.length).fill(-1);

  kills.forEach((e, i) => {
    const enemyKill = e.actor && enemies(e.actorTeam, e.victimTeam);
    if (enemyKill) {
      for (const d of deathLog) {
        if (d.traded) continue;
        if (d.killer !== e.victim) continue;              // ต้องเป็นคนที่ฆ่าเพื่อนเรา
        if (!enemies(d.victimTeam, e.victimTeam)) continue;
        if (d.victimTeam !== e.actorTeam) continue;       // เพื่อนร่วมทีมของคนล้างแค้น
        if (e.tick - d.tick > window) continue;
        d.traded = true;
        tradedBy[i] = d.index;
        break;
      }
    }
    deathLog.push({
      index: i,
      victim: e.victim,
      victimTeam: e.victimTeam,
      killer: enemyKill ? e.actor : null,
      tick: e.tick,
      traded: false,
    });
  });

  return tradedBy;
}

const UTILITY_WEAPONS = new Set(['hegrenade', 'inferno', 'molotov', 'incgrenade', 'firebomb']);
const EVENT_TYPES = new Set(['kill', 'damage', 'grenade', 'bomb']);
const isSteam64 = (v) => /^\d{17}$/.test(String(v ?? ''));

/**
 * ตรวจว่า normalized JSON ใช้ได้ไหม ก่อนแตะฐานข้อมูล
 * errors = โหลดต่อไม่ได้ / warnings = โหลดได้แต่มีข้อมูลบางส่วนถูกตัดทิ้ง
 */
export function validateMatch(doc) {
  const errors = [];
  const warnings = [];

  if (!doc || typeof doc !== 'object') return { errors: ['ไฟล์ไม่ใช่ JSON object'], warnings };
  if (Number(doc.schema_version) !== 1) {
    errors.push(`รองรับ schema_version 1 เท่านั้น (ไฟล์นี้เป็น ${doc.schema_version})`);
  }

  const m = doc.match;
  if (!m?.external_id) errors.push('match.external_id ว่างไม่ได้ (ใช้กันโหลดซ้ำ)');
  if (!m?.map_name) errors.push('match.map_name ว่างไม่ได้');

  const players = Array.isArray(doc.players) ? doc.players : [];
  if (players.length === 0) errors.push('ไม่มีผู้เล่นในไฟล์');
  for (const p of players) {
    if (!isSteam64(p?.steam64_id)) errors.push(`steam64_id ไม่ถูกต้อง: ${p?.steam64_id}`);
    if (p?.team_number !== 2 && p?.team_number !== 3) {
      errors.push(`team_number ต้องเป็น 2 หรือ 3 (${p?.steam64_id} = ${p?.team_number})`);
    }
  }

  const rounds = Array.isArray(doc.rounds) ? doc.rounds : [];
  if (rounds.length === 0) errors.push('ไม่มีข้อมูลรอบ (rounds) — แมตช์ที่ parse ไม่สำเร็จมักหน้าตาแบบนี้');
  rounds.forEach((r, i) => {
    if (Number(r?.round_number) !== i + 1) {
      errors.push(`rounds ต้องเรียง 1..N ไม่ข้าม (ตำแหน่งที่ ${i + 1} เป็นรอบ ${r?.round_number})`);
    }
  });

  const events = Array.isArray(doc.events) ? doc.events : [];
  const known = new Set(players.map((p) => String(p.steam64_id)));
  const roundNums = new Set(rounds.map((r) => Number(r.round_number)));
  let dropped = 0;
  let unknownActor = 0;
  for (const e of events) {
    if (!EVENT_TYPES.has(e?.type) || !roundNums.has(Number(e?.round_number))) {
      dropped += 1;
      continue;
    }
    for (const k of ['actor_steam64', 'victim_steam64', 'assister_steam64']) {
      if (e[k] && !known.has(String(e[k]))) unknownActor += 1;
    }
  }
  if (dropped) warnings.push(`ตัด event ที่อยู่นอกรอบหรือชนิดไม่รู้จักทิ้ง ${dropped} รายการ`);
  if (unknownActor) warnings.push(`พบ steam64 ที่ไม่อยู่ในรายชื่อผู้เล่น ${unknownActor} ครั้ง (บอท/ผู้ชม/คนออกกลางแมตช์) — ข้ามช่องนั้น`);

  return { errors, warnings };
}

function blankStats(player, roundsPlayed) {
  return {
    steam64_id: String(player.steam64_id),
    name: player.name || `Player_${String(player.steam64_id).slice(-4)}`,
    team_number: player.team_number,
    rounds_played: roundsPlayed,
    won: null,
    kills: 0, deaths: 0, assists: 0, headshot_kills: 0,
    damage: 0, utility_damage: 0, grenades_thrown: 0, flash_assists: 0,
    opening_kills: 0, opening_deaths: 0, trade_kills: 0, traded_deaths: 0,
    rounds_survived: 0, clutches_won: 0, clutches_attempted: 0,
  };
}

/**
 * คิดสถิติรายคน + KPI ของทั้งแมตช์
 * คืน { match, players, rounds, events, stats, kpi } พร้อมเขียนลง DB
 */
export function deriveMatch(doc) {
  const rounds = doc.rounds.map((r) => ({ ...r, round_number: Number(r.round_number) }));
  const players = doc.players.map((p) => ({ ...p, steam64_id: String(p.steam64_id) }));
  const byId = new Map(players.map((p) => [p.steam64_id, p]));
  const tickrate = Number(doc.match?.tickrate) || 64;

  const stats = new Map(players.map((p) => [p.steam64_id, blankStats(p, Number(p.rounds_played) || rounds.length)]));
  const roundNums = new Set(rounds.map((r) => r.round_number));

  // เก็บ event ที่ผ่านการตรวจแล้ว แยกตามรอบ เรียงตาม tick
  const events = (doc.events || []).filter(
    (e) => EVENT_TYPES.has(e?.type) && roundNums.has(Number(e?.round_number))
  );
  const perRound = new Map(rounds.map((r) => [r.round_number, []]));
  for (const e of events) perRound.get(Number(e.round_number)).push(e);
  for (const list of perRound.values()) list.sort((a, b) => (a.tick ?? 0) - (b.tick ?? 0));

  const teamOf = (id) => byId.get(String(id ?? ''))?.team_number ?? null;
  const isEnemy = (a, b) => {
    const ta = teamOf(a);
    const tb = teamOf(b);
    return ta !== null && tb !== null && ta !== tb;
  };
  const bump = (id, field, by = 1) => {
    const s = stats.get(String(id ?? ''));
    if (s) s[field] += by;
  };

  for (const round of rounds) {
    const list = perRound.get(round.round_number) || [];
    const alive = new Set(players.map((p) => p.steam64_id));
    const clutchClaimed = new Set(); // กันนับคลัตช์ซ้ำในรอบเดียว

    // จับคู่ trade ของทั้งรอบไว้ก่อนด้วยฟังก์ชันกลาง (ตัวเดียวกับที่ mapInsights ใช้)
    const roundKills = list.filter(
      (e) => e.type === 'kill' && stats.has(String(e.victim_steam64 ?? ''))
    );
    const tradedBy = matchTrades(
      roundKills.map((e) => ({
        victim: String(e.victim_steam64 ?? ''),
        actor: e.actor_steam64 ? String(e.actor_steam64) : null,
        victimTeam: teamOf(e.victim_steam64),
        actorTeam: teamOf(e.actor_steam64),
        tick: Number(e.tick) || 0,
      })),
      tickrate
    );
    // event ที่เป็นคิลล้างแค้น -> event ของศพที่มันล้างแค้นให้
    const tradeFor = new Map();
    tradedBy.forEach((j, i) => {
      if (j >= 0) tradeFor.set(roundKills[i], roundKills[j]);
    });
    let firstBlood = true;

    for (const e of list) {
      if (e.type === 'grenade') {
        bump(e.actor_steam64, 'grenades_thrown');
        continue;
      }

      if (e.type === 'damage') {
        if (!isEnemy(e.actor_steam64, e.victim_steam64)) continue; // ตัดดาเมจใส่เพื่อน
        const dmg = Math.max(0, Number(e.damage) || 0);
        bump(e.actor_steam64, 'damage', dmg);
        if (UTILITY_WEAPONS.has(String(e.weapon || '').toLowerCase())) {
          bump(e.actor_steam64, 'utility_damage', dmg);
        }
        continue;
      }

      if (e.type !== 'kill') continue;

      const victim = String(e.victim_steam64 ?? '');
      const actor = e.actor_steam64 ? String(e.actor_steam64) : null;
      if (!stats.has(victim)) continue;

      bump(victim, 'deaths');
      alive.delete(victim);

      const enemyKill = actor && isEnemy(actor, victim);
      if (enemyKill) {
        bump(actor, 'kills');
        if (e.headshot) bump(actor, 'headshot_kills');

        // trade — คิลนี้ล้างแค้นให้เพื่อนที่เพิ่งตายจากมือคนเดียวกันภายใน 5 วินาที
        // (จับคู่ไว้แล้วที่หัวรอบด้วย matchTrades)
        const avenged = tradeFor.get(e);
        if (avenged) {
          bump(actor, 'trade_kills');
          bump(String(avenged.victim_steam64 ?? ''), 'traded_deaths');
        }

        const assister = e.assister_steam64 ? String(e.assister_steam64) : null;
        if (assister && isEnemy(assister, victim)) {
          bump(assister, 'assists');
          if (e.meta?.assistedflash) bump(assister, 'flash_assists');
        }
      }

      if (firstBlood) {
        firstBlood = false;
        bump(victim, 'opening_deaths');
        if (enemyKill) bump(actor, 'opening_kills');
      }

      // ตรวจสถานการณ์คลัตช์: เหลือคนเดียวของฝั่งหนึ่ง เจอศัตรูอย่างน้อยหนึ่งคน
      for (const teamNumber of [2, 3]) {
        const mine = [...alive].filter((id) => teamOf(id) === teamNumber);
        const theirs = [...alive].filter((id) => teamOf(id) !== teamNumber);
        if (mine.length === 1 && theirs.length >= 1 && !clutchClaimed.has(mine[0])) {
          clutchClaimed.add(mine[0]);
          bump(mine[0], 'clutches_attempted');
          if (round.winner_team_number === teamNumber) bump(mine[0], 'clutches_won');
        }
      }
    }

    for (const id of alive) bump(id, 'rounds_survived');
  }

  // ผลแพ้ชนะของแมตช์
  const score2 = rounds.filter((r) => Number(r.winner_team_number) === 2).length;
  const score3 = rounds.filter((r) => Number(r.winner_team_number) === 3).length;
  for (const s of stats.values()) {
    const mine = s.team_number === 2 ? score2 : score3;
    const theirs = s.team_number === 2 ? score3 : score2;
    s.won = mine === theirs ? null : mine > theirs;
  }

  const statsList = [...stats.values()];
  const kpi = statsList.map((s) => {
    const metrics = metricsFromStats(s);
    return { steam64_id: s.steam64_id, ...computeKpi(metrics), metrics };
  });

  return {
    match: {
      external_id: String(doc.match.external_id),
      map_name: String(doc.match.map_name),
      started_at: doc.match.started_at || null,
      finished_at: doc.match.finished_at || null,
      rounds_played: rounds.length,
      score_team2: score2,
      score_team3: score3,
      tickrate,
      source: doc.match.source || 'demo',
      demo_file: doc.match.demo_file || null,
      server_name: doc.match.server_name || null,
    },
    players,
    rounds,
    events,
    stats: statsList,
    kpi,
  };
}
