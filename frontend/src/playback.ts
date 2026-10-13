import type { ReviewDefuse, RoundDetail, RoundPositions } from "./api";

/** ช่วงสำเร็จยึด tick ที่บอมบ์ถูกกู้; ช่วงยกเลิกหยุดทันทีที่ end_t */
export function defuseAt(
  events: ReviewDefuse[] | undefined, time: number, resolvedT: number | null | undefined,
  endReason: string | null, tickrate: number,
): { event: ReviewDefuse; completed: boolean } | null {
  if (!events?.length) return null;
  const tolerance = tickrate > 0 ? 2 / tickrate : .05;
  const completedEvent = endReason === "bomb_defused"
    ? resolvedT != null
      ? events.find((event) => Math.abs(event.end_t - resolvedT) <= tolerance)
      : events.reduce((latest, event) => event.end_t > latest.end_t ? event : latest)
    : null;
  const active = events.find((event) => event.start_t <= time && time < event.end_t);
  if (active) return { event: active, completed: active === completedEvent };
  // แสดง 0.0s สั้น ๆ หลังสำเร็จเพื่อให้เห็นวงเต็ม แม้ requestAnimationFrame ข้าม tick สุดท้าย
  if (completedEvent && completedEvent.end_t <= time && time < completedEvent.end_t + .2) {
    return { event: completedEvent, completed: true };
  }
  return null;
}

/** ใช้เวลาสำเร็จจริงแก้ข้อมูลคิทที่ขาด/ขัดกัน โดยไม่เดาคิทจากการกู้ที่ยกเลิกเร็ว */
export function defuseHasKit(event: ReviewDefuse, completed: boolean, playerHasDefuser: boolean | null | undefined): boolean {
  const actualDuration = event.end_t - event.start_t;
  if (completed && actualDuration > 0 && actualDuration <= 5.5) return true;
  if (completed && actualDuration >= 8) return false;
  return event.has_kit ?? playerHasDefuser ?? false;
}

/** ค่าเดียวกันสำหรับ HUD และวงบนแผนที่; การกู้สำเร็จจบที่ end_t จริงของเดโม */
export function defuseCountdown(event: ReviewDefuse, time: number, hasKit: boolean, completed = false) {
  const duration = hasKit ? 5 : 10;
  const actualDuration = event.end_t - event.start_t;
  const elapsed = Math.max(0, time - event.start_t);
  const progress = Math.min(1, elapsed / (completed && actualDuration > 0 ? actualDuration : duration));
  return { duration, remaining: duration * (1 - progress), progress };
}

export interface LivePlayer {
  steamid: string;
  px: [number, number];
  hp: number;
  yaw?: number | null;
  flashRemaining?: number | null;
  isFlashed?: boolean | null;
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

/** มุมสั้นสุดข้ามรอยต่อ 0°/360° เพื่อให้ลำกล้องหมุนต่อเนื่อง */
export function interpolateYaw(from: number, to: number, fraction: number): number {
  const delta = ((to - from + 540) % 360) - 180;
  return (from + delta * fraction + 360) % 360;
}

export type PlaybackRoster = Map<string, { name: string; color: string; slot: number | null }>;

export interface DamageTracer {
  id: number;
  tick: number;
  attacker: string;
  victim: string;
  from: [number, number];
  to: [number, number];
}

/** จับตำแหน่งที่ใกล้ tick ยิงที่สุดเพียงครั้งเดียว; ไม่ค้นหาทุกเฟรมที่ replay เดิน */
export function resolveDamageTracers(
  damages: NonNullable<RoundDetail["damages"]>, positions: RoundPositions,
  startTick: number, tickrate: number,
): DamageTracer[] {
  const tracks = new Map<string, { tick: number; px: [number, number] }[]>();
  for (const frame of positions.frames) {
    const tick = frame.tick ?? startTick + frame.t * tickrate;
    for (const player of frame.players) {
      const track = tracks.get(player.steamid) ?? [];
      track.push({ tick, px: player.px });
      tracks.set(player.steamid, track);
    }
  }
  const maxGap = Math.max(tickrate * .25, positions.step * tickrate * 1.5);
  const nearest = (steamid: string, tick: number): [number, number] | null => {
    const track = tracks.get(steamid);
    if (!track?.length) return null;
    let lo = 0;
    let hi = track.length;
    while (lo < hi) {
      const mid = (lo + hi) >>> 1;
      if (track[mid].tick < tick) lo = mid + 1;
      else hi = mid;
    }
    const before = track[lo - 1];
    const after = track[lo];
    const closest = !before ? after : !after ? before
      : tick - before.tick <= after.tick - tick ? before : after;
    return closest && Math.abs(closest.tick - tick) <= maxGap ? closest.px : null;
  };
  const seen = new Set<string>();
  const tracers: DamageTracer[] = [];
  for (const event of damages) {
    if (!event.attacker || !event.victim || event.attacker === event.victim) continue;
    const key = `${event.tick}:${event.attacker}:${event.victim}`;
    if (seen.has(key)) continue; // หลายนัดโดนใน tick เดียวกันใช้เส้นเดียว
    const from = nearest(event.attacker, event.tick);
    const to = nearest(event.victim, event.tick);
    if (!from || !to) continue;
    seen.add(key);
    tracers.push({ id: event.id, tick: event.tick, attacker: event.attacker, victim: event.victim, from, to });
  }
  return tracers.sort((a, b) => a.tick - b.tick);
}

/** เลือกเฉพาะกระสุนในช่วงสั้น ๆ แล้วลดความทึบตามอายุ tick */
export function activeDamageTracers(tracers: DamageTracer[], currentTick: number, durationTicks: number) {
  const active: (DamageTracer & { opacity: number })[] = [];
  let lo = 0;
  let hi = tracers.length;
  while (lo < hi) {
    const mid = (lo + hi) >>> 1;
    if (tracers[mid].tick <= currentTick - durationTicks) lo = mid + 1;
    else hi = mid;
  }
  for (let i = lo; i < tracers.length && tracers[i].tick <= currentTick; i += 1) {
    active.push({ ...tracers[i], opacity: Math.max(0, 1 - (currentTick - tracers[i].tick) / durationTicks) });
  }
  return active;
}

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
        yaw: p.yaw == null ? null : to?.yaw == null ? p.yaw : interpolateYaw(p.yaw, to.yaw, frac),
        // เวลาตาบอดลดตามเวลาจริงระหว่าง snapshot โดยไม่คาดเดาแฟลชใหม่จากเฟรมถัดไป
        flashRemaining: p.flash_remaining == null ? null : Math.max(0, p.flash_remaining - (t - cur.t)),
        isFlashed: p.is_flashed ?? null,
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
