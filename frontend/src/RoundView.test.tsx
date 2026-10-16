// @vitest-environment jsdom
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { DefuseHud, MapView, PlantedBomb, placeLivePlayerLabels, PlaybackDeathMarker, truncatePlayerName } from "./RoundView";
import type { ReviewDeath } from "./api";
import type { LivePlayer } from "./playback";
import { LangProvider } from "./i18n";

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

  it("keeps every label centered below its marker regardless of slot or player order", () => {
    const players = [1, 2, 3, 4, 5].map((slot) => ({
      ...player(String(slot), slot === 3 ? "ชื่อผู้เล่นภาษาไทยที่ยาวมาก" : `Player ${slot}`, 50, 50), slot,
    }));
    const a = placeLivePlayerLabels(players, 8, 15, 10);
    const moved = placeLivePlayerLabels(players.map((p) => ({ ...p, px: [90, 70] as [number, number] })).reverse(), 8, 15, 10);
    players.forEach((p) => {
      const label = a.get(p.steamid)!;
      expect(label.x).toBe(50);
      expect(label.y).toBe(73);
      expect(label.anchor).toBe("middle");
      expect(moved.get(p.steamid)?.x).toBeCloseTo(label.x + 40);
      expect(moved.get(p.steamid)?.y).toBeCloseTo(label.y + 20);
    });
    expect(a.get("3")?.text.endsWith("…")).toBe(true);
  });

  it("truncates Unicode by code point and preserves short multilingual names", () => {
    expect(truncatePlayerName("玩家一", 4)).toBe("玩家一");
    expect(truncatePlayerName("abcdefgh", 5)).toBe("abcd…");
  });
});

describe("defuse map effect", () => {
  it("fills the ring during a kit defuse and removes it at abort", () => {
    vi.stubGlobal("ResizeObserver", class {
      observe() {}
      disconnect() {}
    });
    const player: LivePlayer = { steamid: "42", name: "CT", px: [100, 100], hp: 100,
      side: "ct", place: null, color: "#2563c9", slot: 1, yaw: 90, activeWeapon: null,
      armor: null, hasHelmet: null, hasDefuser: true };
    const props = { radar: { image: "/radar.png", size: 1024, map: "de_ancient" }, deaths: [],
      bomb: { x: 0, y: 0, px: [120, 110] as [number, number], site: "A" }, grenades: [],
      bombPlantedT: 5,
      live: [player], playbackTime: 10, defuseProgressPercent: 20,
      reducedMotion: false, zoom: 1, center: null,
      onView: vi.fn(), highlight: null, selected: null, onSelect: vi.fn() };
    const { rerender } = render(<LangProvider><MapView {...props} defusingPlayer={player} /></LangProvider>);
    const effect = screen.getByTestId("defuse-effect");
    const pointer = screen.getByTestId("player-direction-pointer");
    expect(pointer.tagName.toLowerCase()).toBe("polygon");
    expect(pointer.getAttribute("points")).toBe("109.8,96.75 109.8,103.25 117.8,100");
    expect(pointer.getAttribute("transform")).toBe("rotate(-90 100 100)");
    expect(screen.queryByTestId("player-gun-barrel")).toBeNull();
    expect(screen.getByTestId("live-player").querySelector(".slot-num")?.getAttribute("transform")).toBeNull();
    expect(effect.querySelector("line")?.getAttribute("stroke")).toBe("#38bdf8");
    const ring = screen.getByTestId("defuse-timer-ring");
    const circumference = Number(ring.getAttribute("stroke-dasharray"));
    expect(Number(ring.getAttribute("stroke-dashoffset"))).toBeCloseTo(circumference * .8);
    expect(ring.getAttribute("transform")).toBe("rotate(-90 120 110)");
    rerender(<LangProvider><MapView {...props} bomb={null} defuseBombPx={[120, 110]}
      defuseProgressPercent={100} defusingPlayer={null} /></LangProvider>);
    expect(Number(screen.getByTestId("defuse-timer-ring").getAttribute("stroke-dashoffset"))).toBe(0);
    expect(screen.queryByTestId("bomb-icon")).toBeNull();
    rerender(<LangProvider><MapView {...props} playbackTime={12} defuseProgressPercent={null} defusingPlayer={null} /></LangProvider>);
    expect(screen.queryByTestId("defuse-effect")).toBeNull();
  });
});

describe("defuse HUD", () => {
  it("shows kit countdown and elapsed progress beside the map", () => {
    const { container } = render(<DefuseHud remaining={4.2} progressPercent={16} />);
    const hud = container.querySelector('[data-testid="defuse-countdown"]')!;
    expect(hud.getAttribute("aria-label")).toBe("Defuse 4.2s");
    expect(hud.querySelector(".defuse-hud-icon")).toBeTruthy();
    expect(hud.querySelector(".defuse-hud-track > span")?.getAttribute("style")).toContain("16%");
  });
});

describe("damage tracer map effect", () => {
  it("renders beneath live markers during the hit window and expires afterward", () => {
    vi.stubGlobal("ResizeObserver", class { observe() {} disconnect() {} });
    const live = [
      { steamid: "1", name: "Shooter", px: [100, 100] as [number, number], hp: 100,
        side: "ct", place: null, color: "#2563c9", slot: 1, activeWeapon: null,
        armor: null, hasHelmet: null, hasDefuser: null },
      { steamid: "2", name: "Target", px: [120, 100] as [number, number], hp: 80,
        side: "t", place: null, color: "#f0891c", slot: 1, activeWeapon: null,
        armor: null, hasHelmet: null, hasDefuser: null },
    ];
    const props = { radar: { image: "/radar.png", size: 1024, map: "de_ancient" }, deaths: [],
      bomb: null, grenades: [], bombPlantedT: null, live, defusingPlayer: null,
      positions: { step: .125, t_end: .125, note: "", frames: [
        { tick: 1000, t: 0, players: live.map((p) => ({ steamid: p.steamid, px: p.px, hp: p.hp,
          side: p.side as "ct" | "t", place: null })) },
      ] },
      damages: [{ id: 1, tick: 1008, attacker: "1", victim: "2", damage: 20 }],
      startTick: 1000, tickrate: 128, playbackTime: .0625, reducedMotion: false,
      zoom: 1, center: null, onView: vi.fn(), highlight: null, selected: null, onSelect: vi.fn() };
    const { container, rerender } = render(<LangProvider><MapView {...props} /></LangProvider>);
    const tracer = screen.getByTestId("damage-tracer");
    expect(tracer.tagName.toLowerCase()).toBe("line");
    expect(tracer.getAttribute("stroke")).toBe("#fff");
    expect(tracer.getAttribute("stroke-dasharray")).toBe("4 3");
    expect(Number(tracer.getAttribute("x1"))).toBeCloseTo(110.8);
    expect(container.querySelector('[data-layer="damage-tracers"] circle')).toBeNull();
    rerender(<LangProvider><MapView {...props} playbackTime={.078125} /></LangProvider>);
    expect(Number(screen.getByTestId("damage-tracer").getAttribute("opacity"))).toBeCloseTo(.48);
    rerender(<LangProvider><MapView {...props} playbackTime={.25} /></LangProvider>);
    expect(screen.queryByTestId("damage-tracer")).toBeNull();
  });
});

describe("flash halo", () => {
  it("renders above the marker, fades with remaining time, and supports a boolean fallback", () => {
    vi.stubGlobal("ResizeObserver", class { observe() {} disconnect() {} });
    const player: LivePlayer = { steamid: "1", name: "Flashed", px: [100, 100], hp: 100,
      side: "ct", place: null, color: "#2563c9", slot: 1, activeWeapon: null,
      armor: null, hasHelmet: null, hasDefuser: null, flashRemaining: 2 };
    const props = { radar: { image: "/radar.png", size: 1024, map: "de_ancient" }, deaths: [],
      bomb: null, bombPlantedT: null, grenades: [], playbackTime: 0, reducedMotion: false,
      zoom: 1, center: null, onView: vi.fn(), highlight: null, selected: null, onSelect: vi.fn() };
    const { container, rerender } = render(<LangProvider><MapView {...props} live={[player]} /></LangProvider>);
    const marker = container.querySelector('[data-testid="live-player"]')!;
    const halo = container.querySelector('[data-testid="flash-halo"]')!;
    expect(halo.getAttribute("stroke")).toBe("#ffffff");
    expect(halo.getAttribute("fill")).toBe("none");
    expect(halo.getAttribute("pointer-events")).toBe("none");
    expect(Number(halo.getAttribute("stroke-opacity"))).toBeCloseTo(.4);
    const body = marker.querySelector("circle");
    const slot = marker.querySelector(".slot-num");
    expect(body && (body.compareDocumentPosition(halo) & Node.DOCUMENT_POSITION_FOLLOWING)).toBeTruthy();
    expect(slot && (halo.compareDocumentPosition(slot) & Node.DOCUMENT_POSITION_FOLLOWING)).toBeTruthy();
    rerender(<LangProvider><MapView {...props} live={[{ ...player, flashRemaining: 0 }]} /></LangProvider>);
    expect(container.querySelector('[data-testid="flash-halo"]')).toBeNull();
    rerender(<LangProvider><MapView {...props} live={[{ ...player, flashRemaining: null, isFlashed: true }]} /></LangProvider>);
    expect(Number(container.querySelector('[data-testid="flash-halo"]')?.getAttribute("stroke-opacity"))).toBe(.8);
  });
});

describe("death map marker", () => {
  it("shows the victim X without a persistent attacker line or attacker marker", () => {
    vi.stubGlobal("ResizeObserver", class { observe() {} disconnect() {} });
    const death = {
      order: 1, tick: 1008, t_round: .0625,
      victim: { steamid: "2", name: "Target", side: "t", slot: 2, color: "#f0891c" },
      attacker: { steamid: "1", name: "Shooter", side: "ct", slot: 1, color: "#2563c9" },
      victim_px: [120, 100], attacker_px: [10, 10], weapon: "ak47",
    } as ReviewDeath;
    const { container } = render(<LangProvider><MapView
      radar={{ image: "/radar.png", size: 1024, map: "de_ancient" }} deaths={[death]}
      bomb={null} bombPlantedT={null} grenades={[]} live={[]} playbackTime={.1}
      reducedMotion={false} zoom={1} center={null} onView={vi.fn()}
      highlight={null} selected={null} onSelect={vi.fn()} /></LangProvider>);
    expect(screen.getByTestId("death-dot").querySelector(".death-x-mark")).toBeTruthy();
    expect(container.querySelector("line")).toBeNull();
    expect(container.querySelector('circle[cx="10"][cy="10"]')).toBeNull();
  });
});

describe("planted C4 countdown", () => {
  it("updates its radial ring when replay time is scrubbed", () => {
    const props = { x: 100, y: 100, radius: 10, site: "A", plantTime: 5, label: "วางบอมบ์" };
    const { container, rerender } = render(<svg><PlantedBomb {...props} playbackTime={5} /></svg>);
    const ring = () => container.querySelector('[data-testid="bomb-timer"] circle[stroke="#ef4444"]')!;
    expect(Number(ring().getAttribute("stroke-dashoffset"))).toBeCloseTo(0);
    rerender(<svg><PlantedBomb {...props} playbackTime={25} /></svg>);
    expect(Number(ring().getAttribute("stroke-dashoffset"))).toBeCloseTo(Math.PI * 15);
    rerender(<svg><PlantedBomb {...props} playbackTime={45} /></svg>);
    expect(Number(ring().getAttribute("stroke-dashoffset"))).toBeCloseTo(2 * Math.PI * 15);
  });
});
