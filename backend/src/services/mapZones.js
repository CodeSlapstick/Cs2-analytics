/**
 * Map analytics — ให้คะแนนโซนของแมพ
 *
 * แบ่งงานกับ parser/map_zones.py แบบเดียวกับที่ parse_demo.py แบ่งกับ derive.js:
 *
 *   parser/map_zones.py  ออกแบบโซน (unsupervised: KMeans + DBSCAN) -> data/zones/<map>.json
 *   ไฟล์นี้              ให้คะแนนโซนจากเหตุการณ์จริงในฐานข้อมูล
 *
 * ทำไมต้องแยก: ขอบเขตโซนควรนิ่ง ถ้าคำนวณใหม่ทุกครั้งที่เปิดหน้าเว็บ โค้ชจะเทียบ
 * ตัวเลขข้ามสัปดาห์ไม่ได้เลยเพราะโซนขยับตลอด การ fit หนึ่งครั้งแล้วเก็บเป็นไฟล์
 * ทำให้ "โซน Long A" สัปดาห์นี้กับสัปดาห์หน้าเป็นพื้นที่เดียวกันจริง ๆ
 *
 * โซนถูกกำหนดด้วย centroid ล้วน ๆ การจับ event เข้าโซนจึงใช้ nearest centroid
 * ซึ่งเป็นนิยามเดียวกับที่ KMeans ใช้ตอน fit — ไม่ใช่การประมาณคนละแบบ
 */
import { readFileSync, existsSync, readdirSync } from 'node:fs';
import { resolve } from 'node:path';
import { query } from '../db.js';

const ZONES_DIR = resolve(process.cwd(), process.env.ZONES_DIR || 'data/zones');
const RADARS_PATH = resolve(process.cwd(), process.env.RADARS_PATH || 'data/radars.json');

/** โซนจะถูกทำเครื่องหมายว่า "ข้อมูลน้อย" เมื่อมีการปะทะน้อยกว่านี้ */
const LOW_SAMPLE_DUELS = 10;

const round2 = (v) => (Number.isFinite(Number(v)) ? +Number(v).toFixed(2) : null);

/** อ่านไฟล์โซนของแมพหนึ่ง — คืน null ถ้ายังไม่เคย fit แมพนี้ */
export function loadZoneModel(mapName) {
  const path = resolve(ZONES_DIR, `${String(mapName).replace(/[^a-z0-9_]/gi, '')}.json`);
  if (!existsSync(path)) return null;
  return JSON.parse(readFileSync(path, 'utf8'));
}

/**
 * ค่าปรับเทียบภาพเรดาร์ของแมพหนึ่ง (พิกัดเกม -> พิกเซลบนภาพ)
 *
 * อ่านสด ๆ ทุกครั้งแทนที่จะ cache เพราะไฟล์นี้ถูกแก้ด้วยมือตอนปรับเทียบแมพใหม่
 * ถ้า cache ไว้ ต้องรีสตาร์ต backend ทุกครั้งที่ขยับเลข ซึ่งทำให้ปรับจูนช้ามาก
 */
export function loadRadar(mapName) {
  if (!existsSync(RADARS_PATH)) return null;
  const all = JSON.parse(readFileSync(RADARS_PATH, 'utf8'));
  const r = all[mapName];
  if (!r) return null;
  const { fitted_note: _note, ...rest } = r;
  return rest;
}

/** แมพที่ fit โซนไว้แล้ว ใช้ให้หน้าเว็บรู้ว่ามีอะไรให้ดูบ้าง */
export function listFittedMaps() {
  if (!existsSync(ZONES_DIR)) return [];
  return readdirSync(ZONES_DIR)
    .filter((f) => f.endsWith('.json'))
    .map((f) => f.slice(0, -5))
    .sort();
}

/**
 * จับพิกัดเข้าโซนที่ centroid ใกล้ที่สุด
 * เทียบระยะกำลังสอง ไม่ต้องถอดรากเพราะเราสนแค่ว่าอันไหนใกล้กว่า
 */
export function nearestZone(zones, x, y) {
  if (x === null || x === undefined || y === null || y === undefined) return null;
  let best = null;
  let bestDist = Infinity;
  for (const z of zones) {
    const dx = x - z.centroid[0];
    const dy = y - z.centroid[1];
    const d = dx * dx + dy * dy;
    if (d < bestDist) {
      bestDist = d;
      best = z;
    }
  }
  return best;
}

/**
 * คะแนนของโซนหนึ่งสำหรับทีมหนึ่ง — ช่วง −10..+10 สเกลเดียวกับ KPI 5 มิติ
 * เพื่อให้โค้ชอ่านด้วยความรู้สึกเดียวกัน (0 = สูสี, บวก = ทีมนี้ได้เปรียบ)
 *
 * ใช้สัดส่วนคิล ไม่ใช่ผลต่างคิล เพราะโซนที่ปะทะกัน 40 ครั้งกับ 8 ครั้ง ผลต่าง +4
 * เท่ากันแต่ความหมายต่างกันมาก สัดส่วนหารความถี่ออกไปแล้ว เทียบข้ามโซนได้ตรง ๆ
 *
 * ตัวหาร +4 คือ pseudo-count (Laplace smoothing) กันโซนที่ปะทะครั้งเดียวแล้วชนะ
 * ไม่ให้เด้งไป +10 ทันที — ยิ่งข้อมูลน้อย คะแนนยิ่งถูกดึงกลับเข้าใกล้ 0
 */
export function zoneScore(kills, deaths) {
  const total = kills + deaths;
  if (total === 0) return null;
  const share = (kills + 2) / (total + 4);
  return round2((share - 0.5) * 20);
}

/** A, B, … Z, AA, AB — ป้ายคอลัมน์ของกริด แบบเดียวกับหัวคอลัมน์ในสเปรดชีต */
function columnLabel(i) {
  let n = i;
  let out = '';
  do {
    out = String.fromCharCode(65 + (n % 26)) + out;
    n = Math.floor(n / 26) - 1;
  } while (n >= 0);
  return out;
}

/**
 * รวมคิลเป็นช่องกริดสี่เหลี่ยม
 *
 * กริดยึดมุมบนซ้ายของภาพเรดาร์เป็นจุดตั้งต้น เส้นกริดจึงตรงกับขอบพิกเซลของภาพเสมอ
 * ไม่ว่าจะซูมเท่าไร และช่อง "K4" บนจอกับในไฟล์เป็นช่องเดียวกันแน่นอน
 *
 * กริดกับโซนตอบคนละคำถาม จึงมีทั้งคู่:
 *   กริด = "ตรงพิกัดนี้เกิดอะไรขึ้น" ละเอียด สม่ำเสมอ ชี้ตำแหน่งได้แม่น
 *   โซน  = "พื้นที่นี้เรียกว่าอะไร ใครคุมอยู่" หยาบกว่า แต่มีความหมายเชิงยุทธวิธี
 */
function buildGrid(kills, radar) {
  if (!radar?.grid) return null;
  const size = radar.grid;
  const cells = new Map();

  for (const k of kills) {
    if (k.victim_x === null || k.victim_y === null) continue;
    // แกน y ในเกมเพิ่มขึ้นไปทางเหนือ แต่แถวของกริดนับลงล่างตามภาพ
    const cx = Math.floor((k.victim_x - radar.pos_x) / size);
    const cy = Math.floor((radar.pos_y - k.victim_y) / size);
    const key = `${cx},${cy}`;
    let c = cells.get(key);
    if (!c) {
      c = { col: cx, row: cy, label: `${columnLabel(cx)}${cy + 1}`, team2: 0, team3: 0, deaths: 0 };
      cells.set(key, c);
    }
    c.deaths += 1;
    if (k.actor_team === 2) c.team2 += 1;
    else if (k.actor_team === 3) c.team3 += 1;
  }

  const out = [...cells.values()].map((c) => ({
    ...c,
    // ขอบช่องเป็นหน่วยเกม ให้หน้าเว็บฉายผ่านสูตรเดียวกับจุดอื่น ๆ ไม่ต้องคิดเอง
    x0: radar.pos_x + c.col * size,
    y0: radar.pos_y - c.row * size,
    score: zoneScore(c.team2, c.team3),
  }));

  return {
    cell_size: size,
    max_deaths: Math.max(0, ...out.map((c) => c.deaths)),
    cells: out.sort((a, b) => b.deaths - a.deaths),
  };
}

/**
 * สรุปการปะทะรายโซนของหนึ่งแมตช์ หรือทุกแมตช์ของแมพนั้น
 *
 * @param {string} mapName ชื่อแมพ เช่น de_dust2
 * @param {{matchId?: number}} opts ระบุ matchId เพื่อดูเฉพาะแมตช์เดียว
 */
export async function getZoneAnalytics(mapName, { matchId = null } = {}) {
  const model = loadZoneModel(mapName);
  if (!model) return null;

  const params = [mapName];
  let matchFilter = '';
  if (matchId) {
    params.push(Number(matchId));
    matchFilter = `AND m.id = $${params.length}`;
  }

  // นับเฉพาะแมตช์ที่มาจากไฟล์ .dem จริง
  //
  // db:seed สุ่มพิกัดแบบ uniform ในสี่เหลี่ยมกว้าง ๆ (ดู coord() ใน db/seed.js) ซึ่งพอ
  // ปนเข้ามาแล้วทุกโซนจะถูกดึงเข้าหา 50/50 จนอ่านอะไรไม่ได้ — สถิติจะดูเหมือนว่า
  // "ทุกพื้นที่สูสีหมด" ทั้งที่จริงคือเรากำลังวัดตัวสุ่ม ไม่ใช่วัดการเล่น
  //
  // ตัวโซนเองไม่มีปัญหานี้อยู่แล้วเพราะ map_zones.py fit จากไฟล์ normalized JSON
  // ซึ่งมีเฉพาะแมตช์ที่ผ่าน parser จริง ๆ แมตช์ seed ไม่เคยมีไฟล์ JSON
  const sourceFilter = "AND m.source = 'demo'";

  // ดึงคิลพร้อม "ทีมของคนยิง/คนตาย" มาในคิวรีเดียว — ทีมมาจาก match_players
  // ซึ่งยึดฝั่งในรอบแรกไว้แล้ว จึงไม่เพี้ยนตอนสลับฝั่งครึ่งหลัง
  const kills = await query(
    `SELECT e.match_id, e.round_number, e.weapon, e.headshot,
            e.actor_x, e.actor_y, e.victim_x, e.victim_y,
            ap.team_number AS actor_team, ap.name AS actor_name,
            vp.team_number AS victim_team, vp.name AS victim_name
       FROM events e
       JOIN matches m ON m.id = e.match_id
       LEFT JOIN match_players ap ON ap.match_id = e.match_id AND ap.steam64_id = e.actor_steam64
       LEFT JOIN match_players vp ON vp.match_id = e.match_id AND vp.steam64_id = e.victim_steam64
      WHERE m.map_name = $1 AND e.event_type = 'kill'
            AND e.victim_x IS NOT NULL ${sourceFilter} ${matchFilter}
      ORDER BY e.match_id, e.round_number, e.tick`,
    params
  );

  const matches = await query(
    `SELECT COUNT(*)::int AS n FROM matches m WHERE m.map_name = $1 ${sourceFilter} ${matchFilter}`,
    params
  );

  const zones = model.zones;
  const byId = new Map(
    zones.map((z) => [
      z.zone_id,
      {
        zone_id: z.zone_id,
        name: z.name,
        centroid: z.centroid,
        bbox: z.bbox,
        radius: z.radius,
        hotspots: z.hotspots,
        deaths_at_fit: z.deaths,
        // ทีม 2 = ทีมที่เริ่มฝั่ง T, ทีม 3 = ทีมที่เริ่มฝั่ง CT (นิยามเดียวกันทั้งระบบ)
        team2: { kills: 0, deaths: 0 },
        team3: { kills: 0, deaths: 0 },
        opening: { team2: 0, team3: 0 },
        weapons: new Map(),
      },
    ])
  );

  // ลูกศรทิศทางการปะทะ: จากโซนของคนยิง -> โซนของคนตาย (ตามภาพร่างบนบอร์ด)
  const flows = new Map();
  let firstKillOfRound = new Set();

  for (const k of kills) {
    const dz = nearestZone(zones, k.victim_x, k.victim_y);
    if (!dz) continue;
    const bucket = byId.get(dz.zone_id);
    if (!bucket) continue;

    const victimKey = k.victim_team === 2 ? 'team2' : k.victim_team === 3 ? 'team3' : null;
    const actorKey = k.actor_team === 2 ? 'team2' : k.actor_team === 3 ? 'team3' : null;
    if (victimKey) bucket[victimKey].deaths += 1;
    if (actorKey) bucket[actorKey].kills += 1;

    if (k.weapon) bucket.weapons.set(k.weapon, (bucket.weapons.get(k.weapon) || 0) + 1);

    // คิลแรกของรอบ = opening duel ของโซนนั้น ใช้ตอบว่า "รอบมักเริ่มแตกที่ไหน"
    // ต้องมี match_id ในคีย์ด้วย ไม่งั้นรอบ 1 ของทุกแมตช์จะถูกนับเป็นรอบเดียวกัน
    const roundKey = `${k.match_id}:${k.round_number}`;
    if (!firstKillOfRound.has(roundKey)) {
      firstKillOfRound.add(roundKey);
      if (actorKey) bucket.opening[actorKey] += 1;
    }

    const sz = nearestZone(zones, k.actor_x, k.actor_y);
    if (sz && sz.zone_id !== dz.zone_id) {
      const fk = `${sz.zone_id}->${dz.zone_id}`;
      const cur = flows.get(fk) || { from: sz.zone_id, to: dz.zone_id, kills: 0 };
      cur.kills += 1;
      flows.set(fk, cur);
    }
  }

  const out = [...byId.values()].map((z) => {
    const duels = z.team2.kills + z.team3.kills;
    const topWeapons = [...z.weapons.entries()]
      .sort((a, b) => b[1] - a[1])
      .slice(0, 3)
      .map(([weapon, n]) => ({ weapon, kills: n }));
    return {
      zone_id: z.zone_id,
      name: z.name,
      centroid: z.centroid,
      bbox: z.bbox,
      radius: z.radius,
      hotspots: z.hotspots,
      duels,
      // ข้อมูลน้อยเกินกว่าจะสรุป — หน้าเว็บใช้ธงนี้เพื่อไม่ให้โค้ชอ่านคะแนนเกินจริง
      low_sample: duels < LOW_SAMPLE_DUELS,
      team2: { ...z.team2, score: zoneScore(z.team2.kills, z.team2.deaths) },
      team3: { ...z.team3, score: zoneScore(z.team3.kills, z.team3.deaths) },
      opening: z.opening,
      top_weapons: topWeapons,
    };
  });

  const radar = loadRadar(mapName);

  return {
    map_name: mapName,
    radar,
    model: model.model,
    fit_from: model.fit_from,
    fitted_at: model.fitted_at,
    scored_from: { matches: matches[0]?.n ?? 0, kills: kills.length, source: 'demo' },
    zones: out.sort((a, b) => b.duels - a.duels),
    grid: buildGrid(kills, radar),
    flows: [...flows.values()].sort((a, b) => b.kills - a.kills).slice(0, 12),
  };
}

/** แมพที่มีทั้งข้อมูลแมตช์และไฟล์โซน — ใช้เติมตัวเลือกในหน้า Map analytics */
export async function getAvailableMaps() {
  const fitted = new Set(listFittedMaps());
  const rows = await query(
    `SELECT map_name, COUNT(*)::int AS matches, SUM(rounds_played)::int AS rounds
       FROM matches GROUP BY map_name ORDER BY COUNT(*) DESC`
  );
  return rows.map((r) => ({ ...r, has_zones: fitted.has(r.map_name) }));
}
