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

export interface MatchDetail {
  match: Match;
  rounds: RoundRow[];
  scoreboard: ScoreRow[];
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

export const api = {
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
