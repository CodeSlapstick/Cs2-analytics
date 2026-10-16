// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";
import { toPng } from "html-to-image";
import { AnalysisReportExport } from "./AnalysisReportExport";
import { api, type DeathsOverlay, type Match, type PlayerBehavior, type ScoreRow } from "./api";
import { LangProvider } from "./i18n";

vi.mock("html-to-image", () => ({ toPng: vi.fn().mockResolvedValue("data:image/png;base64,report") }));

const match: Match = {
  id: 1, demo_file: "team.dem", map_name: "de_mirage", team_a: "Alpha", team_b: "Bravo", tickrate: 64,
  imported_at: "2026-10-16", rounds: 24, ct_rounds: 12, t_rounds: 12, kills: 86, status: "done",
  error_message: null, started_at: null, finished_at: null, source: "upload",
};
const heatmap: DeathsOverlay = {
  map: "de_mirage", scope: "upload", side: "all", demo: "team.dem", rounds: null, players: null,
  grid_n: 32, matches: 1, deaths: 10, label: "team.dem", radar: { image: "/map.png", size: 1024, map: "de_mirage" },
  cells: [{ cx: 1, cy: 2, x: 32, y: 64, w: 32, deaths: 4, share: .4, place: "Mid" }],
};
const scoreboard: ScoreRow[] = [{
  steam_id: "1", name: "Player One", start_side: "ct", rounds: 24, kills: 20, deaths: 14, assists: 5,
  headshots: 10, hs_rate: 50, adr: 84.2, kast: 74, rating: 1.18,
}];
const behavior: PlayerBehavior = {
  available: true, demo: "team.dem", map: "de_mirage", players: [{
    steamid: "1", name: "Player One", side: "ct", rounds: 12, available: true, role: "Site Anchor",
    signals: [{ feature: "site_engagement_rate", direction: "higher", z: 1.2, value: .6 }],
  }],
};

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("full analysis report export", () => {
  it("builds the four report sections and exports one long PNG", async () => {
    vi.spyOn(api, "economy").mockResolvedValue({ demo: "team.dem", map: "de_mirage", teams: ["Alpha", "Bravo"], buy_types: ["full"], rounds: [] });
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(<QueryClientProvider client={client}><LangProvider><AnalysisReportExport
      match={match} heatmap={heatmap} behavior={behavior} scoreboard={scoreboard} side="all"
      selectedRounds={null} selectedPlayers={null}
    /></LangProvider></QueryClientProvider>);

    expect(screen.getByRole("heading", { name: "Export รายงานการเล่นฉบับเต็ม" })).toBeTruthy();
    expect(screen.getByText("พื้นที่ที่ทีมเสียผู้เล่น")).toBeTruthy();
    expect(screen.getByText("รูปแบบการซื้อและความพร้อมของทีม")).toBeTruthy();
    expect(screen.getByText("รูปแบบการเล่นและสถิติผู้เล่น")).toBeTruthy();
    expect(screen.getAllByText("Player One").length).toBeGreaterThan(0);

    const button = screen.getByRole("button", { name: /Export Full Report PNG/ });
    await waitFor(() => expect((button as HTMLButtonElement).disabled).toBe(false));
    fireEvent.click(button);
    await waitFor(() => expect(toPng).toHaveBeenCalled());
  });
});
