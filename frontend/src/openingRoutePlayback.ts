import type { OpeningPoint, OpeningRound, Px } from "./api";

/** Never interpolate outside a recorded continuous segment or after death. */
export function openingAt(round: OpeningRound, time: number): { trails: Px[][]; marker: Px | null } {
  const trails: Px[][] = [];
  let marker: Px | null = null;
  for (const segment of round.segments) {
    const seen = segment.filter((p) => p.t <= time);
    if (!seen.length) continue;
    const last = seen[seen.length - 1];
    const next = segment[seen.length];
    const points = seen.map((p) => p.px);
    if (time <= segment[segment.length - 1].t && (round.death_t == null || time < round.death_t)) {
      marker = next && next.t > last.t && next.t - last.t <= round.max_gap
        ? between(last, next, time) : last.px;
      if (next && marker && time > last.t) points.push(marker);
    }
    trails.push(points);
  }
  return { trails, marker };
}

function between(a: OpeningPoint, b: OpeningPoint, time: number): Px {
  const f = Math.max(0, Math.min(1, (time - a.t) / (b.t - a.t)));
  return [a.px[0] + (b.px[0] - a.px[0]) * f, a.px[1] + (b.px[1] - a.px[1]) * f];
}
