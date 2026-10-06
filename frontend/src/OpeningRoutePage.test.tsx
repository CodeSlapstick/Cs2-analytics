// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { OpeningRouteStage } from "./OpeningRoutePage";
import { LangProvider } from "./i18n";
import type { OpeningRoutes } from "./api";

const data: OpeningRoutes = {
  radar: { image: "/assets/maps/de_mirage.png", size: 1024, map: "de_mirage" },
  matches: 1, undated_matches: 1, window_seconds: 30, clock_source: "stored_start_tick_unverified",
  rounds: [{ key: "1:1", demo_file: "real.dem", match_name: "A vs B", match_date: null, round_num: 1,
    side: "t", clock_available: true, max_gap: 1.5, death_t: null,
    segments: [[{ t: 0, px: [0, 0] }, { t: 1, px: [100, 100] }]],
    utility: [{ type: "flash", thrower: null, t_throw: 2, t_land: 3, t_end: null, throw_px: [100, 100], land_px: [200, 200], r_px: 0 }],
  }],
};

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });
function mount(key = "initial") {
  return <MemoryRouter><LangProvider><OpeningRouteStage key={key} data={data} playerName="Player" map="de_mirage" side="t" /></LangProvider></MemoryRouter>;
}

describe("Opening Route controls", () => {
  it("seeks immediately, toggles round overlays, resets and links to evidence", () => {
    const { container } = render(mount());
    fireEvent.change(screen.getByRole("slider", { name: "เวลา Playback" }), { target: { value: "0.5" } });
    expect(container.querySelector(".opening-marker")?.getAttribute("cx")).toBe("50");
    fireEvent.change(screen.getByRole("slider", { name: "เวลา Playback" }), { target: { value: "3" } });
    expect(container.querySelector("rect.opening-utility-flash")).toBeNull();
    expect(container.querySelector("g.opening-utility-flash rect")).not.toBeNull();
    const toggle = screen.getByRole("button", { name: /R1 · A vs B/ });
    fireEvent.click(toggle);
    expect(toggle.getAttribute("aria-pressed")).toBe("false");
    expect(container.querySelector("g.opening-utility-flash")).toBeNull();
    fireEvent.click(toggle);
    fireEvent.click(screen.getByRole("button", { name: "กลับ 0 วินาที" }));
    expect(screen.getByRole("slider", { name: "เวลา Playback" }).getAttribute("value")).toBe("0");
    expect(screen.getByRole("link", { name: "เปิดหลักฐานรอบ 1" }).getAttribute("href")).toBe("/matches/real.dem/rounds/1");
  });

  it("advances with elapsed time, stops at 30, and cancels animation on filter reset/unmount", () => {
    let callback: FrameRequestCallback = () => undefined;
    vi.stubGlobal("requestAnimationFrame", vi.fn((fn: FrameRequestCallback) => { callback = fn; return 1; }));
    const cancel = vi.fn(); vi.stubGlobal("cancelAnimationFrame", cancel);
    const { rerender, unmount } = render(mount());
    fireEvent.change(screen.getByRole("combobox", { name: "ความเร็ว Playback" }), { target: { value: "4" } });
    fireEvent.click(screen.getByRole("button", { name: "เล่น" }));
    act(() => callback(0)); act(() => callback(1000));
    expect(screen.getByRole("slider", { name: "เวลา Playback" }).getAttribute("value")).toBe("4");
    act(() => callback(9000));
    expect(screen.getByRole("slider", { name: "เวลา Playback" }).getAttribute("value")).toBe("30");
    expect(screen.getByRole("button", { name: "เล่น" })).not.toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "เล่น" }));
    rerender(mount("new-filter"));
    expect(screen.getByRole("slider", { name: "เวลา Playback" }).getAttribute("value")).toBe("0");
    expect(cancel).toHaveBeenCalled();
    unmount();
  });
});
