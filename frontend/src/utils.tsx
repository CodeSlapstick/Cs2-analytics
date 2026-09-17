// ตัวช่วยที่ทุกหน้าใช้ร่วมกัน: จัดรูปแบบข้อความ · state บน URL · หน้า 404
import { useCallback } from "react";
import { Link, useSearchParams } from "react-router-dom";
import type { ReviewGrenade, ReviewTeam, Side } from "./api";

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

// ================================================================================================
// สีฝั่ง + เลขผู้เล่น — สีสดในหน้ารอบมีแค่สองสี (CT ฟ้า / T ส้ม) แต่ละคนแยกกันด้วยเลข 1–5 ไม่ใช่สีรายคน
// ================================================================================================
/** เลขประจำตัว 1–5 ในทีม ตามลำดับรายชื่อจาก backend (เรียงตาม steam_id จึงคงที่ทุกรอบของแมตช์) */
export function playerNumbers(teams: ReviewTeam[]): Map<string, number> {
  const m = new Map<string, number>();
  teams.forEach((t) => t.players.forEach((p, i) => m.set(p.steamid, i + 1)));
  return m;
}

// ================================================================================================
// หน้า Analysis: จุดที่ตาย
// (ผลโมเดลไม่ถูกระบายลงหน้าจอที่ไหนอีกแล้ว — โมเดลอยู่หลังบ้านอย่างเดียว ตัดสินใจ 2026-09-18)
// ================================================================================================
/**
 * ไล่เฉดของ "จำนวนครั้งที่ตาย" — สีบอกว่าดูฝั่งไหนอยู่ ความเข้มบอกว่าตายบ่อยแค่ไหน
 *   ct  ฟ้า   ตอนเป็น CT     t  ส้ม  ตอนเป็น T     all  แดง  รวมทั้งสองฝั่ง
 * แต่ละชุดเป็นเฉดเดียวไล่ อ่อน -> เข้ม: ตายน้อยจาง ตายเยอะเข้ม
 * ลำดับอยู่ที่ความสว่าง ไม่ใช่ที่สี คนตาบอดสีจึงยังอ่านลำดับได้
 * (ตรวจด้วย scripts/validate_palette.js: ΔE ของคู่ที่ติดกันน้อยสุด 13.9 แบบ protan)
 */
export const DEATH_RAMP: Record<"all" | Side, readonly string[]> = {
  ct: ["#DBEAFE", "#93C5FD", "#3B82F6", "#1D4ED8", "#1E3A8A"],
  t: ["#FFEDD5", "#FDBA74", "#F97316", "#C2410C", "#7C2D12"],
  all: ["#FFE4E6", "#FCA5A5", "#EF4444", "#B91C3C", "#7F1D1D"],
};

// ---- หน้า Analysis: เทียบสองชุดข้อมูล ----------------------------------------------------------
/**
 * ค่าที่มีสองขั้วรอบจุดกลาง (ตายบ่อยกว่า / พอ ๆ กัน / น้อยกว่าชุดอ้างอิง) ใช้สีสองขั้ว + กลางไม่ระบาย
 * แต่ละขั้วไล่จากเข้ม (ต่างเล็กน้อย) ไปสว่าง (ต่างมาก) — ความสว่างบอก "ต่างแค่ไหน" สีบอก "ต่างทางไหน"
 */
export const DIFF_FILL = {
  "-2": "#2DD4BF", // ตายน้อยกว่าชุดอ้างอิงมาก
  "-1": "#0D9488",
  "1": "#B91C3C",
  "2": "#FB7185", // ตายบ่อยกว่าชุดอ้างอิงมาก
} as const;
export type DiffLevel = -2 | -1 | 0 | 1 | 2;
/** ต่ำกว่านี้ถือว่าพอ ๆ กัน — ไม่ระบาย เพราะความต่างเล็กน้อยจากข้อมูลไม่กี่แมตช์คือความบังเอิญ */
export const DIFF_STEPS = { near: 1.3, far: 2 } as const;
/**
 * heatmap "ทีมเราตายบ่อยกว่ากี่เท่า" ต่อโซน — ไล่เหลือง -> ส้ม -> แดง ทางเดียว (ไม่มีขั้วตรงข้าม
 * แบบ DIFF_FILL) เพราะแผนที่นี้ต้องการเน้นเฉพาะโซนที่แย่กว่าจริง ๆ ให้เด่น ส่วนโซนที่ตายน้อยกว่าหรือ
 * พอ ๆ กันไม่ต้องมีสีแยก (ตารางข้าง ๆ ก็แสดงเฉพาะโซนที่แย่กว่าอยู่แล้ว)
 */
export const RATIO_RAMP = ["#FDE047", "#FB923C", "#DC2626"] as const;
/** ช่องที่ฝั่งเราตายน้อยกว่านี้ไม่ระบายเลย — 1-2 ครั้งบอกอะไรไม่ได้ */
export const DIFF_MIN_DEATHS = 3;

/** เทียบสัดส่วนต่อช่องของสองชุด — คืนระดับความต่าง (0 = พอ ๆ กัน หรือข้อมูลไม่พอ) */
export function diffLevel(shareMine: number, shareRef: number, deathsMine: number): DiffLevel {
  if (deathsMine < DIFF_MIN_DEATHS) return 0;
  const ratio = shareRef > 0 ? shareMine / shareRef : Infinity;
  if (ratio >= DIFF_STEPS.far) return 2;
  if (ratio >= DIFF_STEPS.near) return 1;
  if (ratio <= 1 / DIFF_STEPS.far) return -2;
  if (ratio <= 1 / DIFF_STEPS.near) return -1;
  return 0;
}

// ---- สีของ "ตัวผู้เล่น" บนแผนที่หน้ารอบ (วง + เลข 1–5) — คนละเฉดกับ SIDE_FILL ที่ใช้ระบายพื้นที่ -----------
// ทั้งทีมใช้สีเดียวกันตามฝั่ง แยกตัวบุคคลด้วยหมายเลข ไม่ใช่ด้วยสี
// ฟ้าเข้มกว่า SIDE_FILL เพราะเลขสีขาวต้องอ่านออกบนวง (#4f8cff ได้ contrast 3:1 · ตัวนี้ 6:1)
const PLAYER_FILL: Record<string, string> = { ct: "#2563c9", t: "#f0891c" };
/** สีตัวเลขบนวง — ส้มเป็นสีอ่อน เลขสีขาวบนส้มอ่านไม่ออก ต้องใช้ตัวเข้ม ส่วนบนฟ้าเข้มใช้ตัวขาว */
const PLAYER_INK: Record<string, string> = { ct: "#ffffff", t: "#20160a" };
export const playerFill = (side: string | null | undefined) => PLAYER_FILL[side ?? ""] ?? "#94a3b8";
export const playerInk = (side: string | null | undefined) => PLAYER_INK[side ?? ""] ?? "#20160a";

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

/** ชื่อแมตช์ที่คนอ่านรู้เรื่อง — ไม่มีชื่อทีมในเดโมก็ใช้ชื่อไฟล์ */
export const matchTitle = (m: { team_a: string | null; team_b: string | null; demo_file: string }) =>
  m.team_a && m.team_b ? `${m.team_a} vs ${m.team_b}` : m.demo_file;

/** 12345 -> "12,345" — ตัวเลขทุกตัวในเว็บใช้ตัวคั่นหลักพันแบบเดียวกัน */
export const num = (n: number) => n.toLocaleString("th-TH");

export const mb = (n: number) => `${(n / 1024 / 1024).toFixed(1)} MB`;

// ================================================================================================
// state ของหน้าบน URL
// ================================================================================================
/**
 * state ของหน้าที่เก็บบน query string — refresh แล้วอยู่ที่เดิม และแชร์ลิงก์ให้คนอื่นเห็นแบบเดียวกันได้
 * แมตช์กับรอบอยู่ใน path (/matches/{demo_file}/rounds/{n}) ส่วนที่เหลืออยู่ที่นี่
 */
export interface ViewState {
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
// เส้นทางย้อนกลับ (breadcrumb)
// ================================================================================================
export interface Crumb {
  label: string;
  to?: string; // ไม่มี to = ระดับที่กำลังอยู่ (ไม่ใช่ลิงก์)
}

/**
 * แมตช์ › ชื่อแมตช์ › รอบ 7 — กดย้อนได้ทุกระดับที่มี to
 *
 * ระดับสุดท้ายเป็นข้อความเปล่าและใส่ aria-current ไว้ เพราะการทำลิงก์ชี้หน้าตัวเอง
 * ทำให้ screen reader อ่านว่ายังไปที่อื่นได้ ซึ่งไม่จริง
 */
export function Breadcrumb({ items }: { items: Crumb[] }) {
  return (
    <nav className="crumbs" aria-label="เส้นทางหน้า" data-testid="breadcrumb">
      {items.map((c, i) => (
        <span key={`${c.label}-${i}`}>
          {i > 0 && <span className="crumb-sep" aria-hidden="true">›</span>}
          {c.to ? <Link to={c.to}>{c.label}</Link> : <b aria-current="page">{c.label}</b>}
        </span>
      ))}
    </nav>
  );
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
