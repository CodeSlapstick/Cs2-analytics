import type { GrenadeType, Px, ReviewGrenade } from "./api";

export const PROJECTILE_TRAIL_SECONDS = 0.7;
export const EFFECT_FADE_SECONDS = 0.45;
export const PULSE_SECONDS: Partial<Record<GrenadeType, number>> = { flash: 0.55, he: 0.7, decoy: 0.65 };

export interface ProjectileState {
  px: Px;
  source: "demo" | "endpoints";
  approximate: boolean;
}

export interface EffectState {
  kind: GrenadeType;
  progress: number;
  opacity: number;
}

const between = (a: Px, b: Px, f: number): Px => [a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f];

/** Projectile ณ เวลาจริง: ใช้ entity samples ก่อน และค่อย fallback เป็นเส้นตรงที่ติดป้ายว่า approximate */
export function projectileAt(n: ReviewGrenade, time: number): ProjectileState | null {
  if (n.t_throw == null || time < n.t_throw || (n.t_land != null && time >= n.t_land)) return null;
  const points = n.trajectory?.filter((p) => Number.isFinite(p.t) && p.px != null) ?? [];
  if (points.length) {
    if (time < points[0].t || time > points[points.length - 1].t) return null;
    let lo = 0;
    let hi = points.length - 1;
    while (lo < hi) {
      const mid = Math.ceil((lo + hi) / 2);
      if (points[mid].t <= time) lo = mid;
      else hi = mid - 1;
    }
    const cur = points[lo];
    const next = points[lo + 1];
    const frac = next && next.t > cur.t ? Math.max(0, Math.min(1, (time - cur.t) / (next.t - cur.t))) : 0;
    return { px: next ? between(cur.px, next.px, frac) : cur.px, source: "demo", approximate: false };
  }
  if (!n.throw_px || !n.land_px || n.t_land == null || n.t_land <= n.t_throw) return null;
  const frac = Math.max(0, Math.min(1, (time - n.t_throw) / (n.t_land - n.t_throw)));
  return { px: between(n.throw_px, n.land_px, frac), source: "endpoints", approximate: true };
}

export function projectileTrailAt(n: ReviewGrenade, time: number): { points: Px[]; approximate: boolean } | null {
  const projectile = projectileAt(n, time);
  if (!projectile) return null;
  if (projectile.source === "demo") {
    const points = (n.trajectory ?? []).filter((p) => p.t <= time && p.t >= time - PROJECTILE_TRAIL_SECONDS).map((p) => p.px);
    return { points: [...points, projectile.px], approximate: false };
  }
  return n.throw_px ? { points: [n.throw_px, projectile.px], approximate: true } : null;
}

/** Effect state ไม่เติม end time ที่ไม่มีในข้อมูล; fade เริ่มหลัง end จริงเท่านั้น */
export function effectAt(n: ReviewGrenade, time: number, reducedMotion = false): EffectState | null {
  if (n.t_land == null || !n.land_px || time < n.t_land) return null;
  if (n.type === "smoke" || n.type === "molotov") {
    if (n.t_end == null || time > n.t_end + (reducedMotion ? 0 : EFFECT_FADE_SECONDS)) return null;
    const opacity = time <= n.t_end || reducedMotion ? 1 : Math.max(0, 1 - (time - n.t_end) / EFFECT_FADE_SECONDS);
    const progress = n.t_end > n.t_land ? Math.max(0, Math.min(1, (time - n.t_land) / (n.t_end - n.t_land))) : 1;
    return { kind: n.type, progress, opacity };
  }
  const duration = PULSE_SECONDS[n.type] ?? 0;
  if (duration <= 0 || time > n.t_land + duration) return null;
  return { kind: n.type, progress: reducedMotion ? 0.5 : (time - n.t_land) / duration,
           opacity: reducedMotion ? 0.75 : Math.max(0, 1 - (time - n.t_land) / duration) };
}

export function nadeVisibleAt(n: ReviewGrenade, time: number, reducedMotion = false): boolean {
  return projectileAt(n, time) !== null || effectAt(n, time, reducedMotion) !== null;
}

export function filterGrenadesByTypes(nades: ReviewGrenade[], types: readonly string[]): ReviewGrenade[] {
  const allowed = new Set(types);
  return nades.filter((n) => allowed.has(n.type));
}
