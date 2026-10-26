import { request } from "../api";
import type { ReportData, ReportSide, ReportType } from "../types/report";

export const reportApi = {
  getReport(matchId: number, type: ReportType, side: ReportSide, playerId?: string, signal?: AbortSignal) {
    const path = type === "player"
      ? `/api/reports/player/${matchId}/${encodeURIComponent(playerId ?? "")}`
      : `/api/reports/coach/${matchId}`;
    return request<ReportData>(`${path}?side=${side}`, { signal });
  },
};
