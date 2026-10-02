// @vitest-environment jsdom
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { placeLivePlayerLabels, PlaybackDeathMarker, truncatePlayerName } from "./RoundView";
import type { LivePlayer } from "./playback";

describe("playback death marker", () => {
  it("uses a 40% smaller visual X while preserving a 24px interactive target", async () => {
    const onActivate = vi.fn();
    const user = userEvent.setup();
    render(<svg><PlaybackDeathMarker visualRadius={7.2} hitRadius={12} line={1.2} color="#2563c9"
      slot={2} selected={false} highlighted={false} name="Player One"
      label={{ x: 0, y: 20, anchor: "middle" }} onActivate={onActivate} /></svg>);

    const marker = screen.getByRole("button", { name: "Player One" });
    expect(Number(marker.getAttribute("data-visual-diameter"))).toBeCloseTo(14.4);
    expect(Number(marker.getAttribute("data-hit-diameter"))).toBeGreaterThanOrEqual(24);
    expect(screen.queryByText("Player One")).toBeNull();
    await user.click(marker);
    marker.focus();
    await user.keyboard("{Enter}");
    expect(onActivate).toHaveBeenCalledTimes(2);
  });

  it("shows the player name only for selected or highlighted deaths", () => {
    const common = { visualRadius: 7.2, hitRadius: 12, line: 1.2, color: "#f0891c", slot: 4,
      highlighted: false, name: "Player Two", label: { x: 0, y: 20, anchor: "middle" as const }, onActivate: vi.fn() };
    const { rerender } = render(<svg><PlaybackDeathMarker {...common} selected /></svg>);
    expect(screen.getByText("Player Two")).toBeTruthy();
    rerender(<svg><PlaybackDeathMarker {...common} selected={false} highlighted /></svg>);
    expect(screen.getByText("Player Two")).toBeTruthy();
  });
});

describe("live player labels", () => {
  const player = (steamid: string, name: string, x: number, y: number): LivePlayer => ({
    steamid, name, px: [x, y], hp: 100, side: "ct", slot: 1, place: null, color: "#2563c9",
    activeWeapon: null, armor: null, hasHelmet: null, hasDefuser: null,
  });

  it("is deterministic, prioritizes the highlighted player and avoids marker centers", () => {
    const players = [player("2", "ชื่อผู้เล่นภาษาไทยที่ยาวมาก", 50, 50), player("1", "玩家一", 54, 50)];
    const bounds = { left: 0, top: 0, right: 120, bottom: 120 };
    const a = placeLivePlayerLabels(players, bounds, 8, 10, "2", 10);
    const b = placeLivePlayerLabels([...players].reverse(), bounds, 8, 10, "2", 10);
    expect([...a]).toEqual([...b]);
    expect(a.get("2")?.text.endsWith("…")).toBe(true);
    expect(Array.from(a.get("2")!.text)).toHaveLength(10);
    for (const p of players) {
      const label = a.get(p.steamid)!;
      expect(Math.hypot(label.x - p.px[0], label.y - p.px[1])).toBeGreaterThan(8);
    }
  });

  it("truncates Unicode by code point and preserves short multilingual names", () => {
    expect(truncatePlayerName("玩家一", 4)).toBe("玩家一");
    expect(truncatePlayerName("abcdefgh", 5)).toBe("abcd…");
  });
});
