import type { RoundPositions } from "./api";

export interface LivePlayer {
  steamid: string;
  px: [number, number];
  hp: number;
  side: string | null;
  place: string | null;
  name: string;
  color: string;
  slot: number | null;
  activeWeapon: string | null;
  armor: number | null;
  hasHelmet: boolean | null;
  hasDefuser: boolean | null;
}

export type PlaybackRoster = Map<string, { name: string; color: string; slot: number | null }>;

/** Interpolate ด้วยเวลาจริงของ frame จึงใช้ได้ทั้งข้อมูล 8 Hz ใหม่และ fixture 1 Hz เดิม */
export function playersAt(pos: RoundPositions, t: number, roster: PlaybackRoster): LivePlayer[] {
  const frames = pos.frames;
  if (frames.length === 0) return [];

  let lo = 0;
  let hi = frames.length - 1;
  while (lo < hi) {
    const mid = Math.ceil((lo + hi) / 2);
    if (frames[mid].t <= t) lo = mid;
    else hi = mid - 1;
  }
  const index = lo;
  const cur = frames[index];
  const next = frames[index + 1];
  const span = next ? next.t - cur.t : 0;
  const frac = span > 0 ? Math.max(0, Math.min(1, (t - cur.t) / span)) : 0;
  const continuouslyPresent = new Set(frames[0].players.map((p) => p.steamid));
  for (let frameIndex = 1; frameIndex <= index; frameIndex += 1) {
    const present = new Set(frames[frameIndex].players.map((p) => p.steamid));
    for (const steamid of continuouslyPresent) if (!present.has(steamid)) continuouslyPresent.delete(steamid);
  }

  return cur.players
    // ผู้เล่นเกิดใหม่กลางรอบไม่ได้: ถ้าหายจาก snapshot แล้ว ห้ามให้แถวผิดปกติภายหลังทำให้กลับมาแสดง
    .filter((p) => continuouslyPresent.has(p.steamid))
    .map((p) => {
      const to = next?.players.find((n) => n.steamid === p.steamid);
      const info = roster.get(p.steamid);
      return {
        steamid: p.steamid,
        px: to ? [p.px[0] + (to.px[0] - p.px[0]) * frac, p.px[1] + (to.px[1] - p.px[1]) * frac] : p.px,
        hp: p.hp,
        side: p.side,
        place: p.place,
        name: info?.name ?? p.steamid,
        color: info?.color ?? "#9aa4b2",
        slot: info?.slot ?? null,
        activeWeapon: p.active_weapon ?? null,
        armor: p.armor ?? null,
        hasHelmet: p.has_helmet ?? null,
        hasDefuser: p.has_defuser ?? null,
      } as LivePlayer;
    });
}
