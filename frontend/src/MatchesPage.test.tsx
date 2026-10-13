// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { afterEach, expect, it, vi } from "vitest";
import { MatchesPage } from "./MatchesPage";
import { LangProvider } from "./i18n";
import type { Match } from "./api";

const match = (id: number, status: Match["status"]): Match => ({
  id, status, demo_file: `${status}.dem`, source: "upload", map_name: "de_mirage",
  team_a: "A", team_b: "B", tickrate: 64, imported_at: "2026-01-01T00:00:00Z",
  rounds: 24, ct_rounds: 13, t_rounds: 11, kills: 100, error_message: null,
  started_at: null, finished_at: null,
});

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

it("confirms deletion before requesting it, then removes the row", async () => {
  let rows = [match(1, "done"), match(2, "queued")];
  const fetchMock = vi.fn(async (_path: string, init?: RequestInit) => {
    if (init?.method === "DELETE") {
      rows = rows.filter((row) => row.id !== 1);
      return { ok: true, json: async () => ({ deleted: true, cleanup_failed: [] }) };
    }
    return { ok: true, json: async () => rows };
  });
  vi.stubGlobal("fetch", fetchMock);
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={client}><MemoryRouter><LangProvider><MatchesPage /></LangProvider></MemoryRouter></QueryClientProvider>);

  const deleteReady = await screen.findByRole("button", { name: "ลบเดโม done.dem" });
  expect((screen.getByRole("button", { name: "ลบเดโม queued.dem" }) as HTMLButtonElement).disabled).toBe(true);
  fireEvent.click(deleteReady);
  expect(fetchMock).not.toHaveBeenCalledWith("/api/matches/1", expect.anything());
  fireEvent.click(screen.getByRole("button", { name: "ยืนยันลบ" }));
  await waitFor(() => expect(fetchMock).toHaveBeenCalledWith("/api/matches/1", expect.objectContaining({ method: "DELETE" })));
  await waitFor(() => expect(screen.queryByRole("button", { name: "ลบเดโม done.dem" })).toBeNull());
});
