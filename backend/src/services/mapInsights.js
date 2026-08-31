/**
 * Map insights — แปลงตัวเลขพื้นที่เป็นข้อสรุปที่โค้ชเอาไปสั่งได้
 *
 * ชั้น mapZones.js ตอบว่า "พื้นที่ไหนใครได้เปรียบ" ซึ่งยังเป็นแค่ตัวเลข
 * ไฟล์นี้ตอบคำถามถัดไปที่โค้ชถามจริง ๆ ว่า **"แล้วต้องแก้อะไร"**
 *
 * สามคำถามที่ตอบ
 *
 *   1. แยกฝั่ง T/CT     แผนของโค้ชคนละแผนกันสองฝั่ง ตัวเลขที่รวมสองฝั่งไว้ด้วยกัน
 *                       เอาไปวางแผนไม่ได้ ต้องแยกก่อนถึงจะใช้งานได้จริง
 *   2. พื้นที่ไหนชี้ผลรอบ  ตายเยอะไม่เท่ากับสำคัญ วัดจาก "รอบที่เปิดไฟต์แรกตรงนี้
 *                       จบลงยังไง" เทียบกับอัตราชนะปกติของทีม
 *   3. ตายแล้วไม่มีใครล้างแค้น  ตายเดี่ยวคือปัญหาการยืนตำแหน่ง ไม่ใช่ปัญหาการเล็ง
 *                       เป็นสิ่งที่แก้ได้ด้วยการซ้อม ต่างจาก "ยิงไม่แม่น"
 *
 * ทุกตัวเลขติดขนาดกลุ่มตัวอย่างไปด้วยเสมอ และข้อสรุปที่กลุ่มตัวอย่างเล็กเกินไป
 * จะไม่ถูกสร้างขึ้นมาเลย ดีกว่าปล่อยให้โค้ชอ่านตัวเลขจาก 2 รอบแล้วเปลี่ยนแผนทั้งทีม
 */
import { query } from '../db.js';
import { matchTrades } from '../etl/derive.js';
import { loadZoneModel, nearestZone } from './mapZones.js';

/** ต่ำกว่านี้ไม่สร้างข้อสรุป — จาก 19 รอบต่อแมตช์ 6 รอบคือราวหนึ่งในสาม */
const MIN_ROUNDS_FOR_CLAIM = 6;

/** ต่ำกว่านี้ไม่สรุปเรื่องพื้นที่ */
const MIN_DUELS_FOR_CLAIM = 8;

const pct = (a, b) => (b > 0 ? Math.round((a / b) * 100) : null);

/**
 * ฝั่งที่แต่ละทีมยืนในแต่ละรอบ
 *
 * ตาราง rounds เก็บทั้ง "ทีมไหนชนะ" และ "ฝั่งไหนชนะ" ของรอบนั้น พอมีสองอย่างนี้
 * ก็อนุมานได้ว่าทีมไหนอยู่ฝั่งไหน โดยไม่ต้องพึ่งกติกาสลับฝั่ง — ซึ่งสำคัญเพราะ
 * overtime สลับฝั่งคนละแบบ และ demo ที่ restart กลางแมตช์จะทำให้การนับรอบเพี้ยน
 */
function sidesByRound(rounds) {
  const map = new Map();
  for (const r of rounds) {
    if (!r.winner_side || !r.winner_team_number) continue;
    const other = r.winner_side === 't' ? 'ct' : 't';
    map.set(`${r.match_id}:${r.round_number}`, {
      team2: r.winner_team_number === 2 ? r.winner_side : other,
      team3: r.winner_team_number === 3 ? r.winner_side : other,
    });
  }
  return map;
}

/**
 * รวบรวมสถิติเชิงลึกของแมพหนึ่ง
 *
 * @param {string} mapName
 * @param {{matchId?: number, side?: 't'|'ct'|null}} opts
 *   side = ดูเฉพาะรอบที่ "ทีมที่เริ่มฝั่ง T" ยืนฝั่งนั้น (null = ทุกรอบ)
 */
export async function getMapInsights(mapName, { matchId = null, side = null } = {}) {
  const model = loadZoneModel(mapName);
  if (!model) return null;

  const params = [mapName];
  let matchFilter = '';
  if (matchId) {
    params.push(Number(matchId));
    matchFilter = `AND m.id = $${params.length}`;
  }
  // เหตุผลเดียวกับใน mapZones.js — พิกัดของข้อมูล seed เป็นการสุ่ม ใช้วิเคราะห์ไม่ได้
  const src = "AND m.source = 'demo'";

  const rounds = await query(
    `SELECT r.match_id, r.round_number, r.winner_team_number, r.winner_side, r.end_reason,
            m.tickrate
       FROM rounds r JOIN matches m ON m.id = r.match_id
      WHERE m.map_name = $1 ${src} ${matchFilter}
      ORDER BY r.match_id, r.round_number`,
    params
  );
  if (rounds.length === 0) return null;

  const kills = await query(
    `SELECT e.match_id, e.round_number, e.tick, e.victim_x, e.victim_y,
            e.actor_steam64, e.victim_steam64,
            ap.team_number AS actor_team, ap.name AS actor_name,
            vp.team_number AS victim_team, vp.name AS victim_name
       FROM events e
       JOIN matches m ON m.id = e.match_id
       LEFT JOIN match_players ap ON ap.match_id = e.match_id AND ap.steam64_id = e.actor_steam64
       LEFT JOIN match_players vp ON vp.match_id = e.match_id AND vp.steam64_id = e.victim_steam64
      WHERE m.map_name = $1 AND e.event_type = 'kill' AND e.victim_x IS NOT NULL
            ${src} ${matchFilter}
      ORDER BY e.match_id, e.round_number, e.tick`,
    params
  );

  const sides = sidesByRound(rounds);
  const inScope = (matchId2, roundNo) => {
    if (!side) return true;
    return sides.get(`${matchId2}:${roundNo}`)?.team2 === side;
  };

  const scopedRounds = rounds.filter((r) => inScope(r.match_id, r.round_number));
  const scopedKills = kills.filter((k) => inScope(k.match_id, k.round_number));
  if (scopedRounds.length === 0) return null;

  const wins2 = scopedRounds.filter((r) => r.winner_team_number === 2).length;
  const baseline = pct(wins2, scopedRounds.length);

  // ---------- จัดคิลเข้ารอบ ----------
  const byRound = new Map();
  for (const k of scopedKills) {
    const key = `${k.match_id}:${k.round_number}`;
    if (!byRound.has(key)) byRound.set(key, []);
    byRound.get(key).push(k);
  }

  // ---------- 1) พื้นที่ไหนชี้ผลรอบ ----------
  // นับจาก "คิลแรกของรอบ" เพราะเป็นเหตุการณ์เดียวที่เกิดก่อนทุกอย่าง จึงตีความได้ว่า
  // เป็นต้นเหตุ ไม่ใช่ผลพลอยได้ของการที่ทีมกำลังจะชนะรอบอยู่แล้ว
  const leverage = new Map();
  for (const z of model.zones) leverage.set(z.zone_id, { zone_id: z.zone_id, name: z.name, rounds: 0, wins: 0 });

  for (const [key, list] of byRound) {
    const first = list[0];
    if (!first || first.actor_team !== 2) continue; // นับเฉพาะรอบที่ทีม 2 เป็นฝ่ายเปิด
    const z = nearestZone(model.zones, first.victim_x, first.victim_y);
    if (!z) continue;
    const bucket = leverage.get(z.zone_id);
    const [mid, rno] = key.split(':');
    const round = scopedRounds.find((r) => String(r.match_id) === mid && String(r.round_number) === rno);
    if (!round) continue;
    bucket.rounds += 1;
    if (round.winner_team_number === 2) bucket.wins += 1;
  }

  const zoneImpact = [...leverage.values()]
    .map((z) => ({
      ...z,
      win_pct: pct(z.wins, z.rounds),
      // ต่างจากอัตราชนะปกติกี่จุด — บวกมากแปลว่าเปิดไฟต์ชนะตรงนี้แล้วมักได้รอบ
      lift: z.rounds > 0 && baseline !== null ? pct(z.wins, z.rounds) - baseline : null,
      enough: z.rounds >= MIN_ROUNDS_FOR_CLAIM,
    }))
    .sort((a, b) => b.rounds - a.rounds);

  // ---------- 2) ตายแล้วไม่มีใครล้างแค้น ----------
  // ใช้นิยาม trade เดียวกับ derive.js เป๊ะ ๆ (นำเข้าค่าคงที่มาใช้ ไม่ได้พิมพ์เลขซ้ำ)
  // ถ้าสองที่นิยามไม่ตรงกัน ตัวเลขหน้านี้จะขัดกับสกอร์บอร์ดโดยไม่มีใครรู้
  const untraded = new Map();
  for (const z of model.zones) untraded.set(z.zone_id, { zone_id: z.zone_id, name: z.name, deaths: 0, untraded: 0 });

  const roster = new Map();
  const playerRow = (steam64, name, team) => {
    const id = String(steam64);
    if (!roster.has(id)) {
      roster.set(id, {
        steam64_id: id, name: name || id.slice(-4), team_number: team ?? null,
        kills: 0, deaths: 0, untraded_deaths: 0,
        kill_zones: {}, death_zones: {},
      });
    }
    const row = roster.get(id);
    // ชื่อกับทีมอาจมาเป็น null จากฝั่ง actor ถ้าคิลนั้นไม่มีคนยิง เติมเมื่อรู้แล้วเท่านั้น
    if (name && !row.name) row.name = name;
    if (row.team_number === null && team !== null && team !== undefined) row.team_number = team;
    return row;
  };

  for (const list of byRound.values()) {
    const tickrate = rounds[0]?.tickrate || 64;
    // ศพไหนถูกล้างแค้นให้บ้าง ตัดสินด้วยฟังก์ชันกลางจาก derive.js ตัวเดียวกับที่
    // ETL ใช้คิด traded_deaths ในสกอร์บอร์ด ตัวเลขสองหน้าจึงตรงกันเสมอ
    const tradedBy = matchTrades(
      list.map((k) => ({
        victim: String(k.victim_steam64 ?? ''),
        actor: k.actor_steam64 ? String(k.actor_steam64) : null,
        victimTeam: k.victim_team ?? null,
        actorTeam: k.actor_team ?? null,
        tick: Number(k.tick) || 0,
      })),
      tickrate
    );
    const avengedDeaths = new Set(tradedBy.filter((j) => j >= 0));

    list.forEach((k, i) => {
      const z = nearestZone(model.zones, k.victim_x, k.victim_y);
      if (!z) return;

      // สถิติรายคน — เก็บทั้งสองทีม โค้ชต้องส่องคู่แข่งด้วย ไม่ใช่แค่ทีมตัวเอง
      if (k.victim_steam64) {
        const v = playerRow(k.victim_steam64, k.victim_name, k.victim_team);
        v.deaths += 1;
        v.death_zones[z.zone_id] = (v.death_zones[z.zone_id] || 0) + 1;
        if (!avengedDeaths.has(i)) v.untraded_deaths += 1;
      }
      if (k.actor_steam64 && k.actor_team !== k.victim_team) {
        const a = playerRow(k.actor_steam64, k.actor_name, k.actor_team);
        a.kills += 1;
        a.kill_zones[z.zone_id] = (a.kill_zones[z.zone_id] || 0) + 1;
      }

      if (k.victim_team !== 2) return; // ส่วนสรุปพื้นที่สนใจเฉพาะการตายของทีมที่เริ่มฝั่ง T
      const b = untraded.get(z.zone_id);
      b.deaths += 1;
      if (!avengedDeaths.has(i)) b.untraded += 1;
    });
  }

  const exposure = [...untraded.values()]
    .filter((z) => z.deaths > 0)
    .map((z) => ({ ...z, untraded_pct: pct(z.untraded, z.deaths), enough: z.deaths >= MIN_DUELS_FOR_CLAIM }))
    .sort((a, b) => b.untraded - a.untraded);

  // ---------- 3) ได้คิลแรกแล้วชนะรอบไหม ----------
  let fbRounds = 0;
  let fbWins = 0;
  for (const [key, list] of byRound) {
    const first = list[0];
    if (!first || first.actor_team !== 2) continue;
    const [mid, rno] = key.split(':');
    const round = scopedRounds.find((r) => String(r.match_id) === mid && String(r.round_number) === rno);
    if (!round) continue;
    fbRounds += 1;
    if (round.winner_team_number === 2) fbWins += 1;
  }

  return {
    side,
    scope: {
      rounds: scopedRounds.length,
      kills: scopedKills.length,
      round_win_pct: baseline,
      wins: wins2,
    },
    first_blood: {
      rounds: fbRounds,
      wins: fbWins,
      win_pct: pct(fbWins, fbRounds),
      lift: fbRounds > 0 && baseline !== null ? pct(fbWins, fbRounds) - baseline : null,
      enough: fbRounds >= MIN_ROUNDS_FOR_CLAIM,
    },
    zone_impact: zoneImpact,
    exposure,
    players: buildPlayers(roster, model.zones),
    findings: buildFindings({ baseline, scopedRounds, zoneImpact, exposure, fbRounds, fbWins, side }),
    thresholds: { min_rounds: MIN_ROUNDS_FOR_CLAIM, min_duels: MIN_DUELS_FOR_CLAIM },
  };
}

/**
 * สรุปรายผู้เล่น: ทำคิลได้มากสุดตรงไหน ตายบ่อยสุดตรงไหน และตายเดี่ยวกี่ครั้ง
 *
 * "ตายบ่อยสุดตรงไหน" คือสิ่งที่โค้ชเอาไปคุยกับคนคนนั้นได้ตรง ๆ ต่างจาก K/D
 * ที่บอกแค่ว่าเล่นดีหรือไม่ดี แต่ไม่บอกว่าต้องแก้ตรงไหน
 */
function buildPlayers(roster, zones) {
  const zoneName = (id) => zones.find((z) => z.zone_id === Number(id))?.name ?? `โซน ${id}`;
  const top = (counts) => {
    const entries = Object.entries(counts);
    if (entries.length === 0) return null;
    const [id, n] = entries.sort((a, b) => b[1] - a[1])[0];
    return { zone_id: Number(id), name: zoneName(id), count: n };
  };

  return [...roster.values()]
    .map((p) => ({
      steam64_id: p.steam64_id,
      name: p.name,
      team_number: p.team_number,
      kills: p.kills,
      deaths: p.deaths,
      kd: p.deaths > 0 ? +(p.kills / p.deaths).toFixed(2) : null,
      untraded_deaths: p.untraded_deaths,
      untraded_pct: pct(p.untraded_deaths, p.deaths),
      top_kill_zone: top(p.kill_zones),
      top_death_zone: top(p.death_zones),
    }))
    .sort((a, b) => (a.team_number ?? 9) - (b.team_number ?? 9) || b.kills - a.kills);
}

/**
 * เขียนข้อสรุปเป็นประโยคจากตัวเลขที่ผ่านเกณฑ์ขนาดกลุ่มตัวอย่างแล้วเท่านั้น
 *
 * ตั้งใจให้ "ไม่มีข้อสรุป" เป็นผลลัพธ์ที่ยอมรับได้ ระบบที่พยายามพูดอะไรสักอย่าง
 * ทุกครั้งจะกลายเป็นระบบที่พูดมั่วเมื่อข้อมูลน้อย ซึ่งอันตรายกว่าการเงียบ
 */
function buildFindings({ baseline, scopedRounds, zoneImpact, exposure, fbRounds, fbWins, side }) {
  const out = [];
  const sideWord = side === 't' ? 'ตอนเล่นฝั่ง T' : side === 'ct' ? 'ตอนเล่นฝั่ง CT' : 'ทั้งแมตช์';

  if (scopedRounds.length < MIN_ROUNDS_FOR_CLAIM) {
    return [{
      kind: 'warn',
      text: `${sideWord} มีแค่ ${scopedRounds.length} รอบ น้อยเกินกว่าจะสรุปอะไรได้ — ต้องเก็บแมตช์เพิ่ม`,
    }];
  }

  const fbPct = pct(fbWins, fbRounds);
  if (fbRounds >= MIN_ROUNDS_FOR_CLAIM && fbPct !== null && baseline !== null) {
    const d = fbPct - baseline;
    out.push({
      kind: Math.abs(d) >= 15 ? 'strong' : 'info',
      text: `${sideWord} รอบที่ได้คิลแรก ชนะ ${fbPct}% (${fbWins}/${fbRounds} รอบ) `
        + `เทียบกับอัตราชนะปกติ ${baseline}% — ต่างกัน ${d > 0 ? '+' : ''}${d} จุด`,
    });
  }

  const bestZone = zoneImpact.filter((z) => z.enough).sort((a, b) => (b.lift ?? -99) - (a.lift ?? -99))[0];
  if (bestZone && bestZone.lift !== null && bestZone.lift >= 10) {
    out.push({
      kind: 'strong',
      text: `เปิดไฟต์แรกที่ ${bestZone.name} แล้วชนะรอบ ${bestZone.win_pct}% `
        + `(${bestZone.wins}/${bestZone.rounds} รอบ) สูงกว่าปกติ ${bestZone.lift} จุด — พื้นที่นี้คุ้มที่จะทุ่มยูทิลิตี้`,
    });
  }

  const weak = exposure.filter((z) => z.enough).sort((a, b) => b.untraded_pct - a.untraded_pct)[0];
  if (weak && weak.untraded_pct >= 60) {
    out.push({
      kind: 'warn',
      text: `ที่ ${weak.name} ตาย ${weak.deaths} ครั้ง แต่ ${weak.untraded} ครั้งไม่มีเพื่อนล้างแค้นให้ทัน `
        + `(${weak.untraded_pct}%) — เป็นปัญหาการยืนตำแหน่งและระยะห่าง ไม่ใช่ปัญหาการเล็ง`,
    });
  }

  const noisy = zoneImpact.filter((z) => z.rounds > 0 && !z.enough);
  if (noisy.length) {
    out.push({
      kind: 'info',
      text: `อีก ${noisy.length} พื้นที่ยังมีรอบน้อยกว่า ${MIN_ROUNDS_FOR_CLAIM} รอบ `
        + 'จึงยังไม่สรุป — ตัวเลขมีให้ดูในตารางแต่อย่าเพิ่งเอาไปวางแผน',
    });
  }

  return out;
}
