// ตัวช่วยที่ทุกหน้าใช้ร่วมกัน: จัดรูปแบบข้อความ · state บน URL · หน้า 404
import { useCallback } from "react";
import { Link, useSearchParams } from "react-router-dom";
import type { ReviewGrenade } from "./api";

// ================================================================================================
// จัดรูปแบบข้อความ (เวลา / % / ชื่ออาวุธ / สาเหตุจบรอบ / สีประเภทช่อง)
// ================================================================================================
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

const NADE_LABEL: Record<string, string> = { smoke: "สโมค", flash: "แฟลช", he: "HE", molotov: "โมโลตอฟ", decoy: "ดีคอย" };
export const NADE_COLOR: Record<string, string> = {
  smoke: "#cbd5e1", flash: "#fde047", he: "#f87171", molotov: "#fb923c", decoy: "#a78bfa",
};
export const nadeLabel = (t: string) => NADE_LABEL[t] ?? t;
/** ชนิดที่วาดบนแผนที่ได้จริง — decoy ไม่มีในนี้เพราะเดโมไม่บันทึกว่ามันไปตกที่ไหน */
export const NADE_TYPES = ["smoke", "flash", "he", "molotov"] as const;
export type NadeType = (typeof NADE_TYPES)[number];

/** ระเบิดลูกนี้มีผลอยู่ ณ วินาที t ไหม — ควัน/ไฟ: ตั้งแต่ตกจนหมด · แฟลช/HE: แตกภายใน 3 วินาทีก่อนหน้า */
export function nadeActiveAt(n: ReviewGrenade, t: number): boolean {
  if (n.t_land == null) return false;
  if (n.type === "smoke" || n.type === "molotov") return n.t_land <= t && t <= (n.t_end ?? n.t_land);
  return n.t_land <= t && t - n.t_land <= 3;
}

// ================================================================================================
// state ของหน้าบน URL
// ================================================================================================
/**
 * state ของหน้าที่เก็บบน query string — refresh แล้วอยู่ที่เดิม และแชร์ลิงก์ให้คนอื่นเห็นแบบเดียวกันได้
 * แมตช์กับรอบอยู่ใน path (/matches/{demo_file}/rounds/{n}) ส่วนที่เหลืออยู่ที่นี่
 */
export interface ViewState {
  sidebar: boolean; // sb=0      ย่อ sidebar
  board: boolean; // board=1   เปิดแผงสกอร์บอร์ดทั้งแมตช์
  cells: boolean; // cells=1   ซ้อนประเภทช่องจาก grid_ml1
  hotspots: boolean; // hs=1      ซ้อนวง hotspot
  nades: NadeType[]; // g=smoke,flash  ชนิดระเบิดที่แสดง (ไม่มี g = แสดงครบ, g=none = ไม่แสดงเลย)
  zoom: number; // z=2.5     ซูมแผนที่ (1 = เต็มแมพ)
  center: [number, number] | null; // c=x,y  จุดกึ่งกลางที่มองอยู่ (หน่วยพิกเซลของภาพเรดาร์)
  playback: boolean; // pb=1     โหมดเล่นย้อน (ดูตัวผู้เล่นเดินตามเวลา)
  time: number | null; // t=12.5   วินาทีในรอบที่ดูค้างไว้
  player: string | null; // p=<steamid> ไฮไลต์ผู้เล่น
  death: number | null; // d=<ลำดับ>  การตายที่เลือก
}

export const MAX_ZOOM = 6;

/** g=smoke,flash | g=none | ไม่มี g = ครบทุกชนิด (g=0 ของรุ่นก่อน = ไม่แสดงเลย) */
function parseNades(raw: string | null): NadeType[] {
  if (raw === null) return [...NADE_TYPES];
  if (raw === "none" || raw === "0") return [];
  const picked = raw.split(",").filter((t): t is NadeType => (NADE_TYPES as readonly string[]).includes(t));
  return picked.length ? picked : [...NADE_TYPES];
}

export const clampZoom = (z: number) => Math.min(MAX_ZOOM, Math.max(1, Number.isFinite(z) ? z : 1));

function parseCenter(raw: string | null): [number, number] | null {
  const [x, y] = (raw ?? "").split(",").map(Number);
  return Number.isFinite(x) && Number.isFinite(y) ? [x, y] : null;
}

export function useViewState() {
  const [params, setParams] = useSearchParams();
  const d = Number(params.get("d"));
  const state: ViewState = {
    sidebar: params.get("sb") !== "0",
    board: params.get("board") === "1",
    cells: params.get("cells") === "1",
    hotspots: params.get("hs") === "1",
    nades: parseNades(params.get("g")),
    zoom: clampZoom(Number(params.get("z")) || 1),
    center: parseCenter(params.get("c")),
    playback: params.get("pb") === "1",
    time: params.get("t") !== null && Number.isFinite(Number(params.get("t"))) ? Number(params.get("t")) : null,
    player: params.get("p"),
    death: params.get("d") && Number.isInteger(d) && d > 0 ? d : null,
  };

  // toggle บนหน้าเดียวกันใช้ replace — ปุ่ม Back ของเบราว์เซอร์จะย้อนไปรอบ/แมตช์ก่อน ไม่ใช่ย้อนทีละคลิก
  const update = useCallback(
    (patch: Partial<ViewState>) => {
      setParams(
        (prev) => {
          const next = new URLSearchParams(prev);
          const put = (key: string, value: string | null) => (value === null ? next.delete(key) : next.set(key, value));
          if ("sidebar" in patch) put("sb", patch.sidebar ? null : "0");
          if ("board" in patch) put("board", patch.board ? "1" : null);
          if ("cells" in patch) put("cells", patch.cells ? "1" : null);
          if ("hotspots" in patch) put("hs", patch.hotspots ? "1" : null);
          if ("nades" in patch) {
            const list = patch.nades ?? [];
            put("g", list.length === NADE_TYPES.length ? null : list.length === 0 ? "none" : list.join(","));
          }
          if ("zoom" in patch) put("z", !patch.zoom || patch.zoom <= 1.01 ? null : patch.zoom.toFixed(2));
          if ("center" in patch) put("c", patch.center ? patch.center.map(Math.round).join(",") : null);
          if ("playback" in patch) put("pb", patch.playback ? "1" : null);
          if ("time" in patch) put("t", patch.time == null ? null : patch.time.toFixed(1));
          if ("player" in patch) put("p", patch.player ?? null);
          if ("death" in patch) put("d", patch.death == null ? null : String(patch.death));
          return next;
        },
        { replace: true },
      );
    },
    [setParams],
  );

  return [state, update, params] as const;
}

/**
 * URL ของรอบหนึ่ง — ชื่อไฟล์เดโมถูก encode (มีจุดและขีด และอาจมีวงเล็บ)
 * drop = query ที่ไม่ควรติดไปด้วย เช่น เปลี่ยนรอบทิ้ง d, เปลี่ยนแมตช์ทิ้ง d กับ p (คนละชุดผู้เล่น)
 */
export function roundUrl(demo: string, round: number, params?: URLSearchParams, drop: string[] = []): string {
  const q = new URLSearchParams(params);
  drop.forEach((k) => q.delete(k));
  const s = q.toString();
  return `/matches/${encodeURIComponent(demo)}/rounds/${round}${s ? `?${s}` : ""}`;
}

// ================================================================================================
// หน้า 404
// ================================================================================================
/** 404 ที่มีปุ่มกลับ — ใช้ทั้ง path ที่ไม่มีจริง แมตช์ที่ไม่มีในระบบ และเลขรอบที่เกินจำนวนรอบ */
export function NotFound({ title = "ไม่พบหน้านี้", detail }: { title?: string; detail?: string }) {
  return (
    <div className="notfound" data-testid="not-found">
      <p className="eyebrow">404</p>
      <h1>{title}</h1>
      {detail && <p className="muted">{detail}</p>}
      <Link className="btn-primary" to="/matches">
        กลับไปหน้าแมตช์
      </Link>
    </div>
  );
}
