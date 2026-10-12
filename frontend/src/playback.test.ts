import { describe, expect, it } from "vitest";
import type { RoundPositions } from "./api";
import { activeDamageTracers, interpolateYaw, playersAt, resolveDamageTracers } from "./playback";

const roster = new Map([["1", { name: "One", color: "#fff", slot: 1 }], ["2", { name: "Two", color: "#fff", slot: 2 }]]);
const player = (steamid: string, x: number) => ({ steamid, px: [x, 0] as [number, number], hp: 100, side: "ct" as const, place: null });

describe("playersAt", () => {
  it("interpolates yaw across the 360-degree boundary", () => {
    expect(interpolateYaw(350, 10, 0.5)).toBeCloseTo(0);
    expect(interpolateYaw(10, 350, 0.5)).toBeCloseTo(0);
    const pos: RoundPositions = { step: 1, t_end: 1, note: "", frames: [
      { t: 0, players: [{ ...player("1", 0), yaw: 350 }] },
      { t: 1, players: [{ ...player("1", 0), yaw: 10 }] },
    ] };
    expect(playersAt(pos, 0.5, roster)[0].yaw).toBeCloseTo(0);
  });

  it("interpolates from actual frame times", () => {
    const pos: RoundPositions = { step: 0.125, t_end: 0.125, note: "", frames: [
      { tick: 100, t: 0, players: [player("1", 0)] },
      { tick: 108, t: 0.125, players: [player("1", 10)] },
    ] };
    expect(playersAt(pos, 0.0625, roster)[0].px[0]).toBeCloseTo(5);
  });

  it("counts down flash time between snapshots and stops at zero", () => {
    const pos: RoundPositions = { step: 1, t_end: 1, note: "", frames: [
      { t: 0, players: [{ ...player("1", 0), flash_remaining: 1 }] },
      { t: 1, players: [{ ...player("1", 0), flash_remaining: 0 }] },
    ] };
    expect(playersAt(pos, .4, roster)[0].flashRemaining).toBeCloseTo(.6);
    expect(playersAt(pos, 1, roster)[0].flashRemaining).toBe(0);
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

describe("damage tracers", () => {
  it("resolves sampled positions and fades only recent valid hits", () => {
    const pos: RoundPositions = { step: .125, t_end: .125, note: "", frames: [
      { tick: 1000, t: 0, players: [player("1", 10), player("2", 20)] },
      { tick: 1016, t: .125, players: [player("1", 12), player("2", 22)] },
    ] };
    const damages = [
      { id: 1, tick: 1008, attacker: "1", victim: "2", damage: 30 },
      { id: 2, tick: 1008, attacker: "1", victim: "2", damage: 10 },
      { id: 3, tick: 1008, attacker: "", victim: "2", damage: 30 },
      { id: 4, tick: 1008, attacker: "1", victim: "missing", damage: 30 },
    ];
    const tracers = resolveDamageTracers(damages, pos, 1000, 128);
    expect(tracers).toHaveLength(1);
    expect(tracers[0]).toMatchObject({ from: [10, 0], to: [20, 0] });
    expect(activeDamageTracers(tracers, 1010, 16)[0].opacity).toBeCloseTo(.875);
    expect(activeDamageTracers(tracers, 1024, 16)).toEqual([]);
  });
});
