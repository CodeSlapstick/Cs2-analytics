// ชั้นเดียวที่คุยกับ backend — ทุกหน้าเรียกผ่านที่นี่ จะได้ไม่มี fetch กระจายตามหน้า

export type MatchStatus = "queued" | "parsing" | "done" | "error";

export interface Match {
  id: number;
  demo_file: string;
  map_name: string | null;
  team_a: string | null;
  team_b: string | null;
  tickrate: number | null;
  imported_at: string;
  rounds: number;
  ct_rounds: number;
  t_rounds: number;
  kills: number;
  status: MatchStatus;
  error_message: string | null;
  started_at: string | null;
  finished_at: string | null;
  /** reference = เดโมชุดที่โมเดลเทรนจากมัน · upload = ผู้ใช้อัปโหลดเอง (ไม่เคยเข้าโมเดล) */
  source: MatchSource;
}

export type MatchSource = "reference" | "upload";

export interface RoundRow {
  round_num: number;
  winner_side: "ct" | "t" | null;
  end_reason: string | null;
  bomb_planted: boolean;
  kills: number;
  ct_equip: number | null;
  t_equip: number | null;
  ct_buy_type: string | null;
  t_buy_type: string | null;
}

export interface ScoreRow {
  steam_id: string;
  name: string;
  start_side: "ct" | "t" | null;
  rounds: number;
  kills: number;
  deaths: number;
  assists: number;
  headshots: number;
  hs_rate: number;
  adr: number;
  kast: number;
  rating: number;
}

/** ฟีเจอร์จาก backend/features (นิยามใน definitions.py) รวมทั้งแมตช์ต่อคน */
export interface PlayerFeatures {
  steam_id: string;
  opening_kills: number;
  opening_deaths: number;
  trade_kills: number;
  traded_deaths: number;
  clutch_attempts: number;
  clutch_wins: number;
  full_buys: number;
  force_buys: number;
  eco_buys: number;
  features_version: number;
}

export interface MatchDetail {
  match: Match;
  rounds: RoundRow[];
  scoreboard: ScoreRow[];
  features?: Record<string, PlayerFeatures>; // ว่างสำหรับแมตช์เก่าที่ยังไม่ได้ backfill
}

export interface StatusInfo {
  id: number;
  demo_file: string;
  status: MatchStatus;
  error_message: string | null;
  job: string | null;
  imported_at: string;
  started_at: string | null;
  finished_at: string | null;
}

export interface UploadResult {
  match_id: number;
  demo_file: string;
  size_mb: number;
  replaced: boolean;
  status: "queued";
  job_id: string;
  status_url: string;
}

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

/** event ที่ยิงเมื่อ API ตอบ 401 (token หมดอายุระหว่างใช้งาน) — ProtectedRoute ฟังแล้วพาไปหน้า login */
export const UNAUTHORIZED_EVENT = "cs2:unauthorized";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(path, { credentials: "same-origin", ...init });
  if (!r.ok) {
    if (r.status === 401 && !path.startsWith("/auth/")) window.dispatchEvent(new Event(UNAUTHORIZED_EVENT));
    let msg = `เซิร์ฟเวอร์ตอบ ${r.status}`;
    try {
      const body = await r.json();
      if (body?.detail) msg = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      /* ไม่ใช่ JSON เช่นหน้า error ของ proxy */
    }
    throw new ApiError(r.status, msg);
  }
  return r.json() as Promise<T>;
}

// ---------------------------------------------------------------------------
// Round Review — /api/review/*  (backend/review.py)
// ---------------------------------------------------------------------------
export type Side = "ct" | "t";
export type Px = [number, number];

export interface ReviewPerson {
  steamid: string;
  name: string;
  side: Side | null;
  team: string | null;
  color: string;
  /** หมายเลข 1-5 ในทีม คงที่ทั้งแมตช์ (backend/review.py player_slots) — null = ข้อมูลทีมและฝั่งขาดทั้งคู่ */
  slot: number | null;
}

export interface DeathCell {
  cx: number;
  cy: number;
  cluster_id: number;
  cluster_name: string;
  ct_win: number; // สัดส่วนที่ CT ชนะการดวลในกลุ่มนี้ (ทั้งดาต้าเซ็ต) — ไม่ใช่ผลของรอบ
  cell_ct_win: number;
  cell_duels: number;
}

export interface ReviewDeath {
  order: number;
  tick: number;
  t_round: number | null;
  victim: ReviewPerson;
  attacker: ReviewPerson | null;
  assister: string | null;
  is_duel: boolean;
  team_kill: boolean;
  weapon: string | null;
  headshot: boolean;
  attacker_blind: boolean;
  thru_smoke: boolean;
  noscope: boolean;
  penetrated: number;
  distance: number | null;
  victim_X: number | null;
  victim_Y: number | null;
  attacker_X: number | null;
  attacker_Y: number | null;
  victim_px: Px | null;
  attacker_px: Px | null;
  place: string | null;
  attacker_place: string | null;
  cell: DeathCell | null;
  hotspot: { id: number; place: string; share: number } | null;
  reason: null | "no_model" | "insufficient" | "no_position";
  disadvantaged: boolean | null;
  enemy_win: number | null;
}

export interface ReviewPlayer {
  name: string;
  steamid: string;
  color: string;
  slot: number | null;   // หมายเลขเดียวกับที่แสดงบนแผนที่ — ดู ReviewPerson.slot
  side: Side;
  survived: boolean;
  died_at_t: number | null;
  killed_by: string | null;
  weapon: string | null;
  death_order: number | null;
  kills: number;
}

export interface ReviewTeam {
  clan: string;
  side_this_round: Side;
  players: ReviewPlayer[];
}

export interface GridSource {
  matches: number;
  duels: number;
  map: string;
  label: string;
}

export type GrenadeType = "smoke" | "flash" | "he" | "molotov" | "decoy";

/** ระเบิดหนึ่งลูก — ใครขว้าง จากไหน ตกที่ไหน มีผลช่วงไหน (วินาทีนับจาก freeze จบ) */
export interface ReviewGrenade {
  type: GrenadeType;
  thrower: ReviewPerson | null;
  t_throw: number | null;
  t_land: number | null;
  t_end: number | null;
  throw_px: Px | null;
  land_px: Px | null;
  r_px: number; // รัศมีควัน/ไฟเป็นพิกเซล (0 = วาดเป็นจุด)
}

/**
 * โหมดเล่นย้อน: ตำแหน่งผู้เล่นรายวินาที เป็นพิกเซลบนภาพเรดาร์ (backend แปลงมาให้แล้ว)
 * คนที่ตายแล้วจะไม่มีในเฟรมถัด ๆ ไป · ช่วงระหว่างสองเฟรมหน้าเว็บวาดประมาณให้ต่อเนื่องเอง
 */
export interface RoundPositions {
  step: number; // วินาทีระหว่างสองเฟรม (1.0)
  t_end: number;
  note: string; // ข้อความกำกับว่าอะไรคือข้อมูลจริง — ต้องแสดงให้ผู้ใช้เห็น
  frames: { t: number; players: { steamid: string; px: Px; hp: number; side: Side | null; place: string | null }[] }[];
}

export interface RoundDetail {
  match: { id: number; demo_file: string; map_name: string; tickrate: number; team_a: string | null; team_b: string | null };
  round: {
    num: number;
    winner_side: Side | null;
    end_reason: string | null;
    bomb_planted_t: number | null;
    bomb: { x: number; y: number; px: Px | null; site: string | null } | null;
  };
  radar: { image: string; size: number; map: string } | null;
  grid: { source: GridSource; ct_win_overall: number; min_kills: number } | null;
  teams: ReviewTeam[];
  deaths: ReviewDeath[];
  grenades: ReviewGrenade[];
  summary: {
    first_death: { order: number; name: string; side: Side; place: string | null; t_round: number | null; by: string | null } | null;
    first_death_side_lost: boolean | null;
    disadvantaged_deaths: { ct: number; t: number };
    duel_deaths: number;
    deaths_with_context: number;
  };
}

export interface RoundListItem {
  round_num: number;
  winner_side: Side | null;
  end_reason: string | null;
  deaths_count: number;
  first_death_t: number | null;
}

export interface DeathCellCount {
  cx: number;
  cy: number;
  x: number;
  y: number;
  w: number;
  deaths: number;
  share: number; // สัดส่วนของจุดตายทั้งหมดในชุดนั้น — ใช้เทียบข้ามชุดที่จำนวนแมตช์ไม่เท่ากัน
  place: string | null; // ชื่อ callout ที่พบบ่อยสุดในช่องนั้น (เช่น BombsiteA) — null = เดโมไม่ได้บันทึกไว้
}

export interface DeathsOverlay {
  map: string;
  scope: MatchSource;
  side: "all" | "ct" | "t";
  demo: string | null;
  rounds: number[] | null; // เจาะจงบางรอบไหม — null = ทุกรอบ (เจาะจงได้เฉพาะตอนมี demo ด้วย)
  players: string[] | null; // เจาะจงบางคนไหม (SteamID64) — null = ทุกคน
  grid_n: number;
  matches: number;
  deaths: number;
  label: string;
  cells: DeathCellCount[];
  radar: { image: string; size: number; map: string };
}

/**
 * "อ่านทางออกง่ายแค่ไหน" — โมเดลทายไซต์ (research/site_ml.py) มาอ่านแมตช์ของทีมทีละรอบ
 * read_at = วินาทีแรกที่โมเดลมั่นใจ ≥ 80% ไปทางไซต์ที่เกิดขึ้นจริง · ยิ่งเร็ว = คู่แข่งยิ่งอ่านออกเร็ว
 */
export interface ReadRound {
  round_num: number;
  site: "A" | "B";
  plant_t: number | null;
  read_at: number | null; // null = โมเดลอ่านไม่ออกเลยจนถึงวินาทีที่วางบอมบ์
  lead: number | null; // อ่านออกก่อนบอมบ์ลงจริงกี่วินาที
  winner_side: Side | null;
}

export interface Readability {
  available: boolean;
  reason?: string;
  map?: string;
  demo?: string;
  rounds_detail?: ReadRound[];
  summary?: { rounds: number; read: number; avg_read_at: number | null; median_read_at: number | null; avg_lead: number | null };
  benchmark?: { threshold: number; rounds: number; read_share: number; avg_read_at: number | null; median_read_at: number | null };
  source?: { matches: number; rounds: number; label: string };
  note?: string;
}

const enc = encodeURIComponent;

export const api = {
  reviewRounds: (demo: string) => request<RoundListItem[]>(`/api/review/${enc(demo)}/rounds`),
  reviewRound: (demo: string, n: number) => request<RoundDetail>(`/api/review/${enc(demo)}/rounds/${n}`),
  reviewPositions: (demo: string, n: number) =>
    request<RoundPositions>(`/api/review/${enc(demo)}/rounds/${n}/positions`),
  // --- หน้าเครื่องมือวิเคราะห์ ---
  readability: (demo: string) => request<Readability>(`/api/analysis/readability?demo=${enc(demo)}`),
  analysisDeaths: (
    map: string, scope: MatchSource, side: string, demo?: string | null,
    rounds?: number[] | null, players?: string[] | null,
  ) =>
    request<DeathsOverlay>(
      `/api/analysis/deaths?map=${enc(map)}&scope=${scope}&side=${side}${demo ? `&demo=${enc(demo)}` : ""}` +
      (rounds?.length ? `&rounds=${rounds.join(",")}` : "") +
      (players?.length ? `&players=${players.join(",")}` : ""),
    ),
  matches: () => request<Match[]>("/api/matches"),
  match: (id: number | string) => request<MatchDetail>(`/api/matches/${id}`),
  status: (id: number | string) => request<StatusInfo>(`/api/matches/${id}/status`),
  upload: (file: File, force: boolean) => {
    const form = new FormData();
    form.append("file", file);
    form.append("force", force ? "1" : "0");
    return request<UploadResult>("/api/demos", { method: "POST", body: form });
  },
};

// ---------------------------------------------------------------------------
// ล็อกอิน — JWT อยู่ในคุกกี้ httpOnly ที่เซิร์ฟเวอร์ตั้งให้ JavaScript ไม่เคยเห็น token (ไม่ใช้ localStorage)
// ---------------------------------------------------------------------------
/**
 * ใครกำลังดูหน้านี้ — ฟิลด์เดียวกับที่ /auth/me ตอบมา
 *
 * type คือจุดเดียวที่หน้าเว็บใช้แยกว่าเป็นผู้ใช้ Steam หรือโหมดเยี่ยมชม
 * ตอนนี้สิทธิ์เท่ากันทุกอย่าง ฟิลด์นี้จึงใช้แค่แสดงสถานะบนแถบบน
 * วันไหนจะแยกสิทธิ์จริง ให้ดูจากฟิลด์นี้ อย่ากระจายเงื่อนไขไปทั่วหน้า
 */
export interface AuthUser {
  type: "steam" | "guest";
  id: number | null;         // guest ไม่มีบัญชี จึงเป็น null
  username: string | null;   // guest ไม่มีชื่อ จึงเป็น null
  guest_id: string | null;   // รหัส session ของโหมดเยี่ยมชม (ผู้ใช้ Steam เป็น null)
  avatar?: string | null;    // รูปโปรไฟล์จาก Steam — ไม่มีก็ใช้ตัวอักษรแรกของชื่อแทน
}

export const isGuest = (u: AuthUser | undefined | null) => u?.type === "guest";

/** สถิติรายคน (/api/players/...) — ตัวเลขทุกตัวมาจากเดโมที่โหลดเข้าระบบ */
export interface PlayerSummary {
  player: { steam_id: string; name: string; avatar: string | null; linked_account: string | null };
  totals: {
    matches: number; rounds: number; kills: number; deaths: number; assists: number; headshots: number;
    kd: number; hs_rate: number; adr: number; kast: number; win_rate: number; survival_rate: number; rating: number;
  };
  rating2_approx: number;
  entry: { both: EntrySide; t: EntrySide; ct: EntrySide };
  clutches: { vs: number; attempts: number; wins: number }[];
  source: { matches: number; label: string };
}
export interface EntrySide {
  kills: number;
  deaths: number;
}
export interface PlayerMatch {
  match_id: number; demo_file: string; map_name: string | null; team_a: string | null; team_b: string | null;
  imported_at: string; rounds: number; rounds_won: number; result: "win" | "loss" | "draw";
  kills: number; deaths: number; assists: number; adr: number; kast: number; rating: number;
}
export interface PlayerMap {
  map_name: string; matches: number; wins: number; losses: number; rounds: number; win_rate: number; rating: number; adr: number;
}
export interface PlayerWeapon {
  weapon: string;
  kills: number;
  headshots: number;
  hs_rate: number;
}

// เข้าระบบทางเดียวคือ Steam — ปุ่มบนหน้า /login ลิงก์ตรงไป /auth/steam/login
// ไม่ผ่าน fetch เพราะเป็น redirect ออกนอกเว็บ ที่นี่จึงเหลือแค่ "ฉันเป็นใคร" กับ "ออกจากระบบ"
export const auth = {
  me: () => request<{ user: AuthUser }>("/auth/me"),
  /** เข้าชมโดยไม่ล็อกอิน — เซิร์ฟเวอร์ออกคุกกี้ session ให้ (ไม่มีบัญชีในฐานข้อมูล) */
  guest: () => request<{ user: AuthUser }>("/auth/guest", { method: "POST" }),
  logout: () => request<{ ok: boolean }>("/auth/logout", { method: "POST" }),
};

/** who = "me" (บัญชีที่ล็อกอินด้วย Steam) หรือ SteamID64 */
export const playerApi = {
  summary: (who: string) => request<PlayerSummary>(`/api/players/${who}/summary`),
  matches: (who: string) => request<PlayerMatch[]>(`/api/players/${who}/matches`),
  maps: (who: string) => request<PlayerMap[]>(`/api/players/${who}/maps`),
  weapons: (who: string) => request<PlayerWeapon[]>(`/api/players/${who}/weapons`),
};

export const isBusy = (s: MatchStatus) => s === "queued" || s === "parsing";

/** รายการแมตช์ — ใช้ร่วมกันทั้ง sidebar และหน้าหลัก (key เดียวกัน = ยิงครั้งเดียว)
 *  poll ทุก 2 วินาทีเฉพาะตอนมีแมตช์ที่ยังแกะไม่เสร็จ เสร็จหมดแล้วหยุดถามเอง */
export const matchesQuery = {
  queryKey: ["matches"] as const,
  queryFn: () => api.matches(),
  refetchInterval: (query: { state: { data?: Match[] } }) =>
    query.state.data?.some((m) => isBusy(m.status)) ? 2000 : (false as const),
};
