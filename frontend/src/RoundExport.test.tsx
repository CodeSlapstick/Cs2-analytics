// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { RoundDetail } from "./api";
import { LangProvider } from "./i18n";
import { RoundExportButton, RoundReport } from "./RoundExport";

const { toPngMock } = vi.hoisted(() => ({
  toPngMock: vi.fn((_node: HTMLElement, _options?: Record<string, unknown>) => Promise.resolve("data:image/png;base64,abc")),
}));
vi.mock("html-to-image", () => ({ toPng: toPngMock }));

const person = (steamid: string, name: string, side: "ct" | "t", slot: number) =>
  ({ steamid, name, side, team: side === "ct" ? "Blue" : "Orange", color: side === "ct" ? "#4f8cff" : "#ff8a1e", slot });

const data: RoundDetail = {
  match: { id: 1, demo_file: "team-a-vs-team-b.dem", map_name: "de_mirage", tickrate: 128, team_a: "Team A", team_b: "Team B" },
  round: { num: 9, winner_side: "ct", end_reason: "bomb_defused", start_tick: 100, bomb_planted_t: 31.2,
    bomb_resolved_t: 37, duration: 38, latest_event_t: 37, defuses: [],
    bomb: { x: 0, y: 0, px: [520, 360], site: "A" } },
  radar: { image: "/assets/maps/de_mirage.png", size: 1024, map: "de_mirage" },
  grid: null,
  teams: [
    { clan: "Team A", side_this_round: "ct", players: [{ name: "Alpha", steamid: "1", color: "#4f8cff", slot: 1,
      side: "ct", survived: true, died_at_t: null, killed_by: null, weapon: null, death_order: null, kills: 1 }] },
    { clan: "Team B", side_this_round: "t", players: [{ name: "Bravo", steamid: "2", color: "#ff8a1e", slot: 1,
      side: "t", survived: false, died_at_t: 12.4, killed_by: "Alpha", weapon: "ak47", death_order: 1, kills: 0 }] },
  ],
  deaths: [{ order: 1, tick: 200, t_round: 12.4, victim: person("2", "Bravo", "t", 1), attacker: person("1", "Alpha", "ct", 1),
    assister: null, is_duel: true, team_kill: false, weapon: "ak47", headshot: true, attacker_blind: false, thru_smoke: false,
    noscope: false, penetrated: 0, distance: 450, victim_X: 0, victim_Y: 0, attacker_X: 1, attacker_Y: 1,
    victim_px: [400, 420], attacker_px: [300, 300], place: "BombsiteA", attacker_place: "Connector", cell: null,
    hotspot: null, reason: null, disadvantaged: false, enemy_win: null }],
  damages: [],
  grenades: [{ type: "smoke", thrower: person("2", "Bravo", "t", 1), t_throw: 8, t_land: 9, t_end: 27,
    throw_px: [200, 200], land_px: [450, 440], r_px: 40 }],
  summary: { first_death: { order: 1, name: "Bravo", side: "t", place: "BombsiteA", t_round: 12.4, by: "Alpha" },
    first_death_side_lost: true, disadvantaged_deaths: { ct: 0, t: 1 }, duel_deaths: 1, deaths_with_context: 1 },
};

afterEach(() => { cleanup(); vi.clearAllMocks(); });

describe("round PNG report", () => {
  it("contains the match identity, key facts, map evidence and death timeline", () => {
    const { container } = render(<LangProvider><RoundReport data={data} /></LangProvider>);
    expect(screen.getByText("Team A vs Team B")).toBeTruthy();
    expect(screen.getByText("CT ชนะ")).toBeTruthy();
    expect(screen.getByText(/คนแรกที่ตาย: Bravo/)).toBeTruthy();
    expect(screen.getByText("AK-47")).toBeTruthy();
    expect(container.querySelector(".round-report-death")).toBeTruthy();
    expect(container.querySelector(".round-report-bomb")).toBeTruthy();
  });

  it("renders the fixed report and passes it to the PNG encoder", async () => {
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);
    render(<LangProvider><RoundExportButton data={data} /></LangProvider>);
    fireEvent.click(screen.getByRole("button", { name: /Export สรุปรอบ PNG/ }));
    await waitFor(() => expect(toPngMock).toHaveBeenCalledTimes(1));
    expect(toPngMock.mock.calls[0][1]).toMatchObject({ width: 1200, pixelRatio: 1.5 });
  });
});
