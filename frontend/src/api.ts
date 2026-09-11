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
}

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

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(path, { credentials: "same-origin", ...init });
  if (!r.ok) {
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

export interface GridOverlay {
  available: boolean;
  reason?: string;
  source?: GridSource;
  ct_win_overall?: number;
  min_kills?: number;
  clusters?: { id: number; name: string; ct_win: number; n_cells: number; duels: number }[];
  cells?: { cx: number; cy: number; cluster_id: number; x: number; y: number; w: number }[];
  hotspots?: { id: number; place: string; share: number; duels: number; ct_win: number; px: number; py: number; r: number }[];
}

const enc = encodeURIComponent;

export const api = {
  reviewRounds: (demo: string) => request<RoundListItem[]>(`/api/review/${enc(demo)}/rounds`),
  reviewRound: (demo: string, n: number) => request<RoundDetail>(`/api/review/${enc(demo)}/rounds/${n}`),
  reviewGrid: (map: string) => request<GridOverlay>(`/api/review/grid?map=${enc(map)}`),
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

// Sprint 2 ไม่มีระบบผู้ใช้ — ใช้ SteamID ตัวเดียวล็อกอินโหมดทดสอบ (backend ต้องเปิด ALLOW_DEV_LOGIN=1)
const DEV_STEAMID = import.meta.env.VITE_DEV_STEAMID ?? "76561198000000001";

export async function ensureLogin(): Promise<void> {
  try {
    await request("/api/me");
    return; // มีคุกกี้อยู่แล้ว
  } catch (e) {
    if (!(e instanceof ApiError) || e.status !== 401) throw e;
  }
  await request("/auth/dev-login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ steamid: DEV_STEAMID }),
  });
}

export const isBusy = (s: MatchStatus) => s === "queued" || s === "parsing";
