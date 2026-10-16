// @vitest-environment jsdom
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AnalysisPage } from "./AnalysisPage";
import { api, type OpeningRoutes } from "./api";
import { LangProvider } from "./i18n";

const openingRoutes: OpeningRoutes = {
  radar: { image: "/assets/maps/de_mirage.png", size: 1024, map: "de_mirage" },
  matches: 1,
  undated_matches: 0,
  window_seconds: 30,
  clock_source: "stored_start_tick_unverified",
  rounds: [],
};

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("analysis tools navigation", () => {
  it("hosts Opening Route and removes the professional comparison and readability pages", async () => {
    vi.spyOn(api, "matches").mockResolvedValue([]);
    vi.spyOn(api, "referenceMaps").mockResolvedValue([]);
    vi.spyOn(api, "openingCatalog").mockResolvedValue([
      { id: 1, demo_file: "match.dem", map_name: "de_mirage", steamid: "1", name: "Player", match_date: "2026-10-01" },
    ]);
    vi.spyOn(api, "openingRoutes").mockResolvedValue(openingRoutes);

    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={["/analysis?tool=opening-route"]}>
          <LangProvider><AnalysisPage /></LangProvider>
        </MemoryRouter>
      </QueryClientProvider>,
    );

    expect(screen.getByRole("tab", { name: "ทีมเราตายตรงไหน" })).toBeTruthy();
    expect(screen.getByRole("tab", { name: "Opening Route" }).getAttribute("aria-selected")).toBe("true");
    expect(screen.queryByRole("tab", { name: "เทียบกับทีมอาชีพ" })).toBeNull();
    expect(screen.queryByRole("tab", { name: "อ่านทางเราออกไหม" })).toBeNull();
    await waitFor(() => expect(screen.getByRole("combobox", { name: /ผู้เล่น/ })).toBeTruthy());
    expect(screen.queryByRole("heading", { name: "Opening Route" })).toBeNull();
  });
});
