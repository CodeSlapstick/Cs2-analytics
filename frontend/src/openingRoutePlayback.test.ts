import { describe, expect, it } from "vitest";
import type { OpeningRound } from "./api";
import { openingAt } from "./openingRoutePlayback";

const round: OpeningRound = {
  key: "1:1", demo_file: "real.dem", match_name: "A vs B", match_date: null,
  round_num: 1, side: "t", clock_available: true, utility: [], death_t: null,
  max_gap: 1.5, segments: [[{ t: 0, px: [0, 0] }, { t: 1, px: [10, 20] }], [{ t: 4, px: [40, 80] }, { t: 5, px: [50, 100] }]],
};
describe("opening route shared clock", () => {
  it("interpolates only recorded continuous intervals and immediately follows a seek", () => {
    expect(openingAt(round, 0.5).marker).toEqual([5, 10]);
    expect(openingAt(round, 4.5).marker).toEqual([45, 90]);
    expect(openingAt(round, 0).trails).toEqual([[[0, 0]]]);
  });
  it("never connects an outage or retains a marker beyond the recording", () => {
    expect(openingAt(round, 2).marker).toBeNull();
    expect(openingAt(round, 30).marker).toBeNull();
    expect(openingAt(round, 30).trails).toHaveLength(2);
  });
  it("stops at death, handles missing data, and never shows a future point", () => {
    expect(openingAt({ ...round, death_t: 0.5 }, 0.5).marker).toBeNull();
    expect(openingAt({ ...round, segments: [] }, 20)).toEqual({ trails: [], marker: null });
    expect(openingAt(round, -1)).toEqual({ trails: [], marker: null });
  });
});
