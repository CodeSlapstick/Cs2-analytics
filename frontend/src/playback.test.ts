import { describe, expect, it } from "vitest";
import type { RoundPositions } from "./api";
import { playersAt } from "./playback";

const roster = new Map([["1", { name: "One", color: "#fff", slot: 1 }], ["2", { name: "Two", color: "#fff", slot: 2 }]]);
const player = (steamid: string, x: number) => ({ steamid, px: [x, 0] as [number, number], hp: 100, side: "ct" as const, place: null });

describe("playersAt", () => {
  it("interpolates from actual frame times", () => {
    const pos: RoundPositions = { step: 0.125, t_end: 0.125, note: "", frames: [
      { tick: 100, t: 0, players: [player("1", 0)] },
      { tick: 108, t: 0.125, players: [player("1", 10)] },
    ] };
    expect(playersAt(pos, 0.0625, roster)[0].px[0]).toBeCloseTo(5);
  });

  it("keeps legacy 1 Hz fixtures compatible", () => {
    const pos: RoundPositions = { step: 1, t_end: 1, note: "", frames: [
      { t: 0, players: [player("1", 0)] }, { t: 1, players: [player("1", 20)] },
    ] };
    expect(playersAt(pos, 0.25, roster)[0].px[0]).toBeCloseTo(5);
  });

  it("does not show a player again after a missing/dead frame", () => {
    const pos: RoundPositions = { step: 1, t_end: 3, note: "", frames: [
      { t: 0, players: [player("1", 0), player("2", 0)] },
      { t: 1, players: [player("1", 10)] },
      { t: 2, players: [player("1", 20), player("2", 20)] },
      { t: 3, players: [player("1", 30), player("2", 30)] },
    ] };
    expect(playersAt(pos, 1, roster).map((p) => p.steamid)).toEqual(["1"]);
    expect(playersAt(pos, 2, roster).map((p) => p.steamid)).toEqual(["1"]);
    expect(playersAt(pos, 3, roster).map((p) => p.steamid)).toEqual(["1"]);
  });
});
