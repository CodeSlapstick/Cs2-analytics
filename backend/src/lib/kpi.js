/**
 * Custom KPI — 5 มิติที่ระบบนี้เลือกวัด
 *
 *   computeKpi()  — แปลง "สถิติดิบจากไฟล์ .dem" เป็นคะแนน 5 มิติ
 *                   (aim, positioning, utility, clutch, opening)
 *                   สเกลประมาณ -10 ถึง +10 โดย 0 = ผู้เล่นระดับกลาง
 *
 * ทั้งหมดเป็นฟังก์ชันบริสุทธิ์ (ไม่แตะฐานข้อมูล ไม่แตะเน็ต) เพื่อให้เขียนเทสต์ได้ตรง ๆ
 */
export const KPI_DIMENSIONS = ['aim', 'positioning', 'utility', 'clutch', 'opening'];

// ---------------------------------------------------------------------------
// ค่าฐานอ้างอิง (baseline)
//
// แต่ละตัวชี้วัดมี center = ค่าของผู้เล่นระดับกลาง และ spread = ระยะที่ถือว่า "ห่าง 1 ช่วง"
// ตัวเลขชุดนี้อ้างอิงค่าเฉลี่ยที่ยอมรับกันในวงการ CS (ADR ~75, HS ~45%, K/D ~1.0)
// ไม่ได้ fit จากข้อมูลของเราเอง เพราะตอนนี้ยังมีแมตช์ไม่พอจะ fit ได้อย่างมีนัยสำคัญ
//
// วิธีอ่านคะแนน: metric ห่างจาก center ไป 1 spread = ได้ประมาณ 40% ของคะแนนเต็มมิตินั้น
// ตัดที่ ±2.5 spread เพื่อไม่ให้แมตช์เดียวที่โหดผิดปกติดึงคะแนนรวมจนเพี้ยน
//
// เปลี่ยนค่าพวกนี้ = คะแนนทุกคนขยับหมด ถ้าจะแก้ ให้แก้พร้อมกับอัปเดตเทสต์ใน
// backend/test/kpi.test.js เสมอ
// ---------------------------------------------------------------------------
export const KPI_BASELINES = {
  aim: [
    ['adr', 75, 18, 0.4],            // ดาเมจเฉลี่ยต่อรอบ
    ['hs_pct', 0.45, 0.12, 0.3],     // สัดส่วนคิลที่เป็นเฮดช็อต
    ['kpr', 0.72, 0.14, 0.3],        // คิลต่อรอบ
  ],
  positioning: [
    ['dpr_inv', 0.32, 0.1, 0.5],     // 1 - การตายต่อรอบ (ยิ่งตายน้อยยิ่งสูง)
    ['survival_rate', 0.32, 0.09, 0.3],
    ['traded_death_pct', 0.22, 0.09, 0.2], // ตายแล้วเพื่อนล้างแค้นให้ทัน = ตายในตำแหน่งที่มีคนคุม
  ],
  utility: [
    ['udr', 4.2, 2.2, 0.5],          // ดาเมจจากยูทิลิตี้ต่อรอบ
    ['flash_assist_rate', 0.06, 0.04, 0.3],
    ['nades_per_round', 1.6, 0.6, 0.2],
  ],
  clutch: [
    ['clutch_win_pct', 0.22, 0.13, 0.7],
    ['clutch_rate', 0.1, 0.05, 0.3], // ได้อยู่ในสถานการณ์ 1vX บ่อยแค่ไหน
  ],
  opening: [
    ['opening_win_pct', 0.5, 0.12, 0.6],
    ['opening_attempt_rate', 0.16, 0.07, 0.4], // กล้าเปิดไฟต์แค่ไหน
  ],
};

const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));
const ratio = (num, den) => (den > 0 ? num / den : null);

/**
 * แปลงตัวนับดิบ (จาก match_players) เป็นอัตราส่วนที่สูตร KPI ใช้
 * ใช้ได้ทั้งกับสถิติแมตช์เดียว และผลรวมหลายแมตช์ (โครงสร้างฟิลด์เหมือนกัน)
 */
export function metricsFromStats(s) {
  const rounds = Number(s?.rounds_played) || 0;
  const kills = Number(s?.kills) || 0;
  const deaths = Number(s?.deaths) || 0;
  const openings = (Number(s?.opening_kills) || 0) + (Number(s?.opening_deaths) || 0);
  const dpr = ratio(deaths, rounds);

  return {
    rounds,
    adr: ratio(Number(s?.damage) || 0, rounds),
    kpr: ratio(kills, rounds),
    dpr,
    dpr_inv: dpr === null ? null : 1 - dpr,
    hs_pct: ratio(Number(s?.headshot_kills) || 0, kills),
    kd: ratio(kills, deaths),
    survival_rate: ratio(Number(s?.rounds_survived) || 0, rounds),
    traded_death_pct: ratio(Number(s?.traded_deaths) || 0, deaths),
    udr: ratio(Number(s?.utility_damage) || 0, rounds),
    flash_assist_rate: ratio(Number(s?.flash_assists) || 0, rounds),
    nades_per_round: ratio(Number(s?.grenades_thrown) || 0, rounds),
    // สองมิตินี้วัดจาก "สถานการณ์ที่ต้องเจอก่อนถึงจะวัดได้" — ถ้าไม่เคยเจอเลย
    // ให้เป็น null (= ไม่มีข้อมูล) ไม่ใช่ 0 (= ทำได้แย่) เพราะการที่ทีมไม่เคยเหลือ
    // คนเดียวเลยทั้งแมตช์ ไม่ได้แปลว่าผู้เล่นคนนั้นคลัตช์ไม่เป็น
    opening_attempt_rate: openings > 0 ? ratio(openings, rounds) : null,
    opening_win_pct: ratio(Number(s?.opening_kills) || 0, openings),
    clutch_rate: (Number(s?.clutches_attempted) || 0) > 0 ? ratio(Number(s.clutches_attempted), rounds) : null,
    clutch_win_pct: ratio(Number(s?.clutches_won) || 0, Number(s?.clutches_attempted) || 0),
  };
}

/**
 * คิดคะแนน 5 มิติจาก metrics
 *
 * ตัวชี้วัดไหนคิดไม่ได้ (เช่นยังไม่เคยอยู่ในสถานการณ์คลัตช์เลย → หารศูนย์) จะถูก
 * ตัดออกแล้วเกลี่ยน้ำหนักที่เหลือใหม่ ไม่ใช่นับเป็น 0 — เพราะ "ไม่มีข้อมูล"
 * กับ "ทำได้แย่" เป็นคนละเรื่องกัน ถ้าไม่มีข้อมูลเลยทั้งมิติจะคืน null
 */
export function computeKpi(metrics) {
  const out = {};
  for (const dim of KPI_DIMENSIONS) {
    let score = 0;
    let usedWeight = 0;
    for (const [key, center, spread, weight] of KPI_BASELINES[dim]) {
      const v = metrics?.[key];
      if (v === null || v === undefined || !Number.isFinite(Number(v))) continue;
      const z = clamp((Number(v) - center) / spread, -2.5, 2.5) / 2.5; // -1 ถึง 1
      score += z * weight;
      usedWeight += weight;
    }
    out[dim] = usedWeight === 0 ? null : +((score / usedWeight) * 10).toFixed(2);
  }
  return out;
}
