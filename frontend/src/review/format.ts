// ตัวช่วยแสดงผลของหน้า Round Review — ข้อความทุกตัวต้องเป็นข้อเท็จจริง ไม่ตัดสินผู้เล่น

/** 23.4 -> "0:23" */
export function fmtT(t: number | null | undefined): string {
  if (t == null) return "—";
  const s = Math.max(0, Math.floor(t));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

export const pct = (x: number | null | undefined) => (x == null ? "—" : `${Math.round(x * 100)}%`);

export const sideLabel = (s: string | null | undefined) => (s === "ct" ? "CT" : s === "t" ? "T" : "?");

const WEAPONS: Record<string, string> = {
  ak47: "AK-47", m4a1: "M4A4", m4a1_silencer: "M4A1-S", awp: "AWP", ssg08: "SSG 08", deagle: "Desert Eagle",
  usp_silencer: "USP-S", glock: "Glock-18", hkp2000: "P2000", p250: "P250", tec9: "Tec-9", fiveseven: "Five-SeveN",
  cz75a: "CZ75-Auto", galilar: "Galil AR", famas: "FAMAS", mp9: "MP9", mac10: "MAC-10", mp7: "MP7", ump45: "UMP-45",
  p90: "P90", sg556: "SG 553", aug: "AUG", hegrenade: "HE", inferno: "Molotov", knife: "มีด", world: "ตกที่สูง",
  planted_c4: "C4",
};
export const weaponLabel = (w: string | null | undefined) => (w ? WEAPONS[w] ?? w : "—");

export const END_REASON: Record<string, string> = {
  ct_killed: "ฆ่า CT หมดทีม",
  t_killed: "ฆ่า T หมดทีม",
  bomb_exploded: "ระเบิดลง",
  bomb_defused: "กู้ระเบิดสำเร็จ",
  time_ran_out: "หมดเวลา",
  ct_win: "CT ชนะ",
  t_win: "T ชนะ",
};
export const endReasonLabel = (r: string | null | undefined) => (r ? END_REASON[r] ?? r : "—");

// สีของประเภทช่อง — ตรงกับรูป output/grid_ml1_map.png (matplotlib tab10 เรียงตามเบอร์กลุ่ม 1, 2, 3, …)
const TAB10 = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd", "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf"];
export const clusterColor = (id: number) => TAB10[(id - 1) % TAB10.length];
