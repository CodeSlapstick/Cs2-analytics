import { describe, expect, it } from "vitest";
import type { GrenadeType, ReviewGrenade } from "./api";
import { effectAt, filterGrenadesByTypes, nadeVisibleAt, projectileAt } from "./grenadePlayback";

const nade = (type: GrenadeType, patch: Partial<ReviewGrenade> = {}): ReviewGrenade => ({
  type, thrower: null, t_throw: 2, t_land: 4, t_end: 8, throw_px: [0, 0], land_px: [20, 0], r_px: 10,
  ...patch,
});

describe("grenade playback", () => {
  it("hides before throw, moves during flight, and stops being a projectile after landing", () => {
    const n = nade("smoke");
    expect(projectileAt(n, 1.99)).toBeNull();
    expect(projectileAt(n, 3)?.px).toEqual([10, 0]);
    expect(projectileAt(n, 4)).toBeNull();
  });

  it("prefers actual demo points and marks endpoint fallback as approximate", () => {
    const actual = nade("he", { trajectory: [
      { tick: 10, t: 2, px: [0, 0] }, { tick: 11, t: 3, px: [4, 8] }, { tick: 12, t: 4, px: [20, 0] },
    ] });
    expect(projectileAt(actual, 3)?.source).toBe("demo");
    expect(projectileAt(actual, 3)?.px).toEqual([4, 8]);
    expect(projectileAt(nade("he"), 3)?.approximate).toBe(true);
  });

  it("expires smoke/fire by real end time and does not invent missing end time", () => {
    expect(effectAt(nade("smoke"), 7.9)).not.toBeNull();
    expect(effectAt(nade("smoke"), 8.5)).toBeNull();
    expect(effectAt(nade("molotov"), 8.5)).toBeNull();
    expect(effectAt(nade("smoke", { t_end: null }), 5)).toBeNull();
  });

  it("flash/HE pulses expire and reduced motion keeps a static pulse", () => {
    expect(effectAt(nade("flash"), 4.2)).not.toBeNull();
    expect(effectAt(nade("flash"), 5)).toBeNull();
    expect(effectAt(nade("he"), 4.2, true)?.progress).toBe(0.5);
    expect(effectAt(nade("he"), 5)).toBeNull();
  });

  it("keeps utility filters and selected-death-time visibility exact", () => {
    const smoke = nade("smoke");
    const flash = nade("flash");
    expect(filterGrenadesByTypes([smoke, flash], ["smoke"])).toEqual([smoke]);
    expect(nadeVisibleAt(smoke, 3)).toBe(true);
    expect(nadeVisibleAt(smoke, 9)).toBe(false);
  });

  it("does not fabricate a projectile when landing or landing time is missing", () => {
    expect(projectileAt(nade("decoy", { land_px: null, t_land: null, t_end: null }), 3)).toBeNull();
  });
});
