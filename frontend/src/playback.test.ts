import { describe, expect, it } from "vitest";
import type { RoundPositions } from "./api";
import { activeDamageTracers, defuseAt, defuseCountdown, defuseHasKit, interpolateYaw, playersAt, resolveDamageTracers } from "./playback";

describe("defuse countdown", () => {
  it("uses five seconds with a kit and ten without one", () => {
    const event = { steamid: "42", start_t: 20, end_t: 28 };
    expect(defuseCountdown(event, 22, true)).toEqual({ duration: 5, remaining: 3, progress: .4 });
    expect(defuseCountdown(event, 22, false)).toEqual({ duration: 10, remaining: 8, progress: .2 });
    expect(defuseCountdown(event, 40, true).remaining).toBe(0);
  });

  it("reaches zero at a recorded completion but hides an abort immediately", () => {
    const completed = { steamid: "42", start_t: 50, end_t: 54.8, has_kit: true };
    const aborted = { steamid: "42", start_t: 60, end_t: 61, has_kit: true };
    const events = [completed, aborted];
    expect(defuseCountdown(completed, 50, true, true).remaining).toBe(5);
    expect(defuseCountdown(completed, 52.4, true, true).remaining).toBeCloseTo(2.5);
    expect(defuseCountdown(completed, 54.8, true, true).remaining).toBe(0);
    expect(defuseAt(events, 54.8, 54.8, "bomb_defused", 128)).toEqual({ event: completed, completed: true });
    expect(defuseAt(events, 54.95, 54.8, "bomb_defused", 128)).toEqual({ event: completed, completed: true });
    expect(defuseAt(events, 55.1, 54.8, "bomb_defused", 128)).toBeNull();
    expect(defuseAt([aborted], 60.9, null, null, 128)).toEqual({ event: aborted, completed: false });
    expect(defuseAt([aborted], 61, null, null, 128)).toBeNull();
    expect(defuseHasKit({ ...completed, has_kit: false }, true, false)).toBe(true);
    expect(defuseHasKit({ ...aborted, has_kit: null }, false, false)).toBe(false);
  });

  it("plays a synthetic ten-second no-kit defuse and stops a fake tap", () => {
    const tap = { steamid: "42", start_t: 30, end_t: 31, has_kit: false };
    const full = { steamid: "42", start_t: 40, end_t: 50, has_kit: false };
    expect(defuseAt([tap, full], 30, 50, "bomb_defused", 128)).toEqual({ event: tap, completed: false });
    expect(defuseAt([tap, full], 31, 50, "bomb_defused", 128)).toBeNull();
    expect(defuseHasKit(full, true, false)).toBe(false);
    expect(defuseCountdown(full, 40, false, true)).toEqual({ duration: 10, remaining: 10, progress: 0 });
    expect(defuseCountdown(full, 45, false, true)).toEqual({ duration: 10, remaining: 5, progress: .5 });
    expect(defuseCountdown(full, 50, false, true)).toEqual({ duration: 10, remaining: 0, progress: 1 });
    expect(defuseAt([tap, full], 50, 50, "bomb_defused", 128)).toEqual({ event: full, completed: true });
  });
});

const roster = new Map([["1", { name: "One", color: "#fff", slot: 1 }], ["2", { name: "Two", color: "#fff", slot: 2 }]]);
const player = (steamid: string, x: number) => ({ steamid, px: [x, 0] as [number, number], hp: 100, side: "ct" as const, place: null });

describe("playersAt", () => {
  it("uses recorded money and transfers C4 state at the frame boundary", () => {
    const pos: RoundPositions = { step: 1, t_end: 1, note: "", frames: [
      { t: 0, players: [{ ...player("1", 0), money: 3250, has_bomb: true }, { ...player("2", 5), money: 800, has_bomb: false }] },
      { t: 1, players: [{ ...player("1", 1), money: 3250, has_bomb: false }, { ...player("2", 6), money: 800, has_bomb: true }] },
    ] };
    expect(playersAt(pos, .9, roster).find((p) => p.steamid === "1")).toMatchObject({ money: 3250, hasBomb: true });
    expect(playersAt(pos, 1, roster).find((p) => p.steamid === "2")).toMatchObject({ money: 800, hasBomb: true });
  });
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
