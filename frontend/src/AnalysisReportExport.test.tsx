// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AnalysisReportExport } from "./AnalysisReportExport";
import { api, type Match } from "./api";
import { LangProvider } from "./i18n";
import { reportApi } from "./services/reportApi";
import type { ReportData } from "./types/report";

const match: Match = { id: 1, demo_file: "team.dem", map_name: "de_mirage", team_a: "Alpha", team_b: "Bravo", tickrate: 64, imported_at: "2026-10-16", rounds: 24, ct_rounds: 12, t_rounds: 12, kills: 86, status: "done", error_message: null, started_at: null, finished_at: null, source: "upload" };
const report: ReportData = {
  header: { match_id: 1, demo_file: "team.dem", report_type: "coach", player_id: null, player_name: null, team_a: "Alpha", team_b: "Bravo", map_name: "de_mirage", score_ct: 13, score_t: 11, rounds: 24, match_date: "2026-10-16", generated_at: "2026-10-25T00:00:00Z", dataset_version: "report-v1" },
  side: "all", executive_summary: ["วิเคราะห์ 24 รอบ"], insights: [{ key: "opening", title: "เสียผู้เล่นคนแรก", observation: "เสีย 5 ครั้ง", impact: "ต้องเล่น 4v5", evidence: [], possible_causes: ["อาจไม่มี flash support"], confidence: "medium", recommendation: "ซ้อมเป็นคู่", next_target: "ไม่เกิน 2 ครั้ง", sample_size: 24 }],
  kpis: [{ key: "adr", label: "ADR", value: 84.2, comparison: 78, sample_size: 24, status: "good", explanation: "damage ต่อรอบ" }],
  turning_points: [{ round_num: 4, winner_side: "ct", buy_type: "full", event: "เสียชีวิต 5 คน", turning_point: "first death", improvement: "ตรวจ utility", watch_time_seconds: 38, viewer_url: "/matches/team.dem/rounds/4" }],
  side_analysis: [{ side: "ct", rounds: 24, wins: 13, strengths: ["ชนะ 13 รอบ"], problems: ["เสียคนแรก"], evidence: ["รอบ 4"], actions: ["ซ้อม trade"] }], economy: [],
  players: [{ steam_id: "1", name: "Player One", rounds: 24, kills: 20, deaths: 14, assists: 5, adr: 84.2, kast: 74, rating: 1.18, opening_kills: 4, opening_deaths: 3, trade_kills: 2, traded_deaths: 5 }],
  training_plan: [{ title: "Trade", problem: "ห่างกัน", evidence: "รอบ 4", method: "ซ้อมเป็นคู่", owner: "Coach", duration: "15 นาที", target: "ไม่เกิน 2 ครั้ง", review_after: "5 แมตช์" }], next_match_goals: ["opening death ไม่เกิน 2"], data_quality: { demos: 1, rounds: 24, dataset_version: "report-v1", missing: ["Utility damage"], estimated: ["Rating"], warnings: [] },
};

afterEach(() => { cleanup(); localStorage.clear(); vi.restoreAllMocks(); });

describe("report downloads", () => {
  it("shows separate match, coach and per-player PDF downloads", async () => {
    vi.spyOn(reportApi, "getReport").mockImplementation(async (_id, type) => type === "player" ? { ...report, header: { ...report.header, report_type: "player", player_id: "1", player_name: "Player One" } } : report);
    vi.spyOn(api, "economy").mockResolvedValue({ demo: "team.dem", map: "de_mirage", teams: ["Alpha", "Bravo"], buy_types: [], rounds: [] });
    vi.spyOn(api, "playerBehavior").mockResolvedValue({ available: false, reason: "insufficient_data" });
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(<QueryClientProvider client={client}><LangProvider><AnalysisReportExport match={match} /></LangProvider></QueryClientProvider>);
    expect(await screen.findByRole("heading", { name: "ดาวน์โหลดรายงาน" })).toBeTruthy();
    expect(await screen.findByRole("heading", { name: "รายงานแมตช์ฉบับเต็ม" })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "รายงานสำหรับโค้ช" })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "รายงานผู้เล่นรายคน" })).toBeTruthy();
    expect(screen.getByRole("button", { name: /Player One.*ดาวน์โหลด PDF/ })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "7. มูลค่าอุปกรณ์รายรอบ" })).toBeTruthy();
  });

  it("opens coach settings, keeps Match Overview mandatory and clears optional sections", async () => {
    vi.spyOn(reportApi, "getReport").mockResolvedValue(report);
    vi.spyOn(api, "economy").mockResolvedValue({ demo: "team.dem", map: "de_mirage", teams: ["Alpha", "Bravo"], buy_types: [], rounds: [] });
    vi.spyOn(api, "playerBehavior").mockResolvedValue({ available: false, reason: "insufficient_data" });
    vi.spyOn(api, "heatmap").mockResolvedValue({ event: "kills", demo: "team.dem", map: "de_mirage", points: [[20,20]], count: 1, rounds: 24, roster: [], radar: { image: "/map.png", size: 1024, map: "de_mirage" } });
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(<QueryClientProvider client={client}><LangProvider><AnalysisReportExport match={match} /></LangProvider></QueryClientProvider>);
    fireEvent.click(await screen.findByRole("button", { name: /ตั้งค่ารายงานสำหรับ Alpha/ }));
    expect(screen.getByRole("dialog", { name: "ตั้งค่ารายงานสำหรับโค้ช" })).toBeTruthy();
    const overview = screen.getByRole("checkbox", { name: "Match Overview" }) as HTMLInputElement;
    expect(overview.checked).toBe(true); expect(overview.disabled).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: "ล้างตัวเลือก" }));
    expect((screen.getByRole("checkbox", { name: "Match Overview" }) as HTMLInputElement).checked).toBe(true);
    expect(screen.getByText("1 หัวข้อ")).toBeTruthy();
  });
});
