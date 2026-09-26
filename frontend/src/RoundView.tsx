import { type KeyboardEvent, useEffect, useLayoutEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  api,
  ApiError,
  type ReviewDeath,
  type ReviewGrenade,
  type ReviewTeam,
  type RoundDetail,
  type RoundPositions,
} from "./api";
import {
  clampZoom,
  endReasonLabel,
  fmtT,
  MAX_ZOOM,
  NADE_COLOR,
  NADE_ICON,
  nadeActiveAt,
  nadeLabel,
  NADE_TYPES,
  type NadeType,
  NotFound,
  playerFill,
  playerInk,
  sideLabel,
  type ViewState,
  weaponLabel,
} from "./utils";
import { useT } from "./i18n";

/** แถวที่กดได้ (li ในไทม์ไลน์ / บริบท) — คลิก หรือ Enter / Space จากคีย์บอร์ด */
const pressable = (fn: () => void) => ({
  role: "button" as const,
  tabIndex: 0,
  onClick: fn,
  onKeyDown: (e: KeyboardEvent) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      fn();
    }
  },
});

// ================================================================================================
// เนื้อหาของหนึ่งรอบ
// ================================================================================================
interface RoundViewProps {
  demo: string;
  roundNum: number;
  view: ViewState;
  setView: (patch: Partial<ViewState>) => void;
}

/** เนื้อหาของหนึ่งรอบ: รายชื่อทีม / แผนที่ / ไทม์ไลน์ — state ทั้งหมดมาจาก URL · ไม่มีผลโมเดลในหน้านี้ (อยู่ที่ /analysis) */
export function RoundView({ demo, roundNum, view, setView }: RoundViewProps) {
  // โหมดเล่นย้อน: เวลาที่กำลังเล่นอยู่เก็บใน state (เปลี่ยนทุกเฟรม) แล้วเขียนลง URL ตอนหยุดเท่านั้น
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState<(typeof SPEEDS)[number]>(1);
  const [time, setTime] = useState(view.time ?? 0);
  // ชี้เมาส์ที่แถวในตาราง (หรือที่ตัวผู้เล่นบนแผนที่) = ไฮไลต์ชั่วคราว ไม่เขียนลง URL
  // ต่างจาก view.player ที่เป็นการ "กดค้างไว้" และติดไปกับลิงก์ที่แชร์ได้
  const [hover, setHover] = useState<string | null>(null);
  const { t } = useT();
  const q = useQuery({
    queryKey: ["review-round", demo, roundNum],
    queryFn: () => api.reviewRound(demo, roundNum),
    // ระหว่างโหลดรอบใหม่ของแมตช์เดิม ให้เห็นรอบก่อนไว้ก่อน (ไม่กระพริบ) แต่ห้ามโชว์รอบของแมตช์อื่น
    placeholderData: (prev: RoundDetail | undefined) => (prev && prev.match.demo_file === demo ? prev : undefined),
    retry: (count, err) => !(err instanceof ApiError && err.status === 404) && count < 1,
  });
  // ตำแหน่งผู้เล่นโหลดเฉพาะตอนเปิดโหมดเล่นย้อน (ราว 9 KB ต่อรอบ) — หน้าปกติไม่ต้องจ่ายค่านี้
  const positions = useQuery({
    queryKey: ["review-positions", demo, roundNum],
    queryFn: () => api.reviewPositions(demo, roundNum),
    enabled: view.playback,
    staleTime: Infinity, // ตำแหน่งของรอบที่แกะแล้วไม่เปลี่ยน
  });
  const endT = positions.data?.t_end ?? 0;

  // เปลี่ยนรอบ = เริ่มดูใหม่ตั้งแต่ต้นรอบ
  const roundKey = `${demo}/${roundNum}`;
  const seen = useRef(roundKey);
  useEffect(() => {
    if (seen.current === roundKey) return;
    seen.current = roundKey;
    setPlaying(false);
    setTime(0);
  }, [roundKey]);

  // นาฬิกาเดินด้วย requestAnimationFrame (ตามเวลาจริง ไม่ใช่จำนวนเฟรม) · หยุดเองเมื่อถึงท้ายรอบ
  useEffect(() => {
    if (!playing || endT <= 0) return;
    let raf = 0;
    let last = performance.now();
    const tick = (now: number) => {
      const dt = (now - last) / 1000;
      last = now;
      setTime((t) => {
        const next = t + dt * speed;
        if (next >= endT) {
          setPlaying(false);
          return endT;
        }
        return next;
      });
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [playing, speed, endT]);

  // หยุดแล้วค่อยเก็บวินาทีที่ดูค้างลง URL — แชร์ลิงก์ "ดูตั้งแต่วินาทีนี้" ได้ แต่ไม่อัปเดต router ทุกเฟรม
  useEffect(() => {
    if (!view.playback || playing) return;
    const t = Math.round(time * 10) / 10;
    if ((view.time ?? 0) !== t) setView({ time: t });
  }, [playing, view.playback, time]); // eslint-disable-line react-hooks/exhaustive-deps

  // เว้นวรรค = เล่น/หยุด · , กับ . = ถอย/เดินหน้าทีละวินาที (ลูกศรซ้ายขวายังเป็นเปลี่ยนรอบเหมือนเดิม)
  useEffect(() => {
    if (!view.playback) return;
    const onKey = (e: globalThis.KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return;
      if (e.code === "Space") {
        e.preventDefault();
        setPlaying((p) => !p);
      } else if (e.key === "," || e.key === ".") {
        e.preventDefault();
        setPlaying(false);
        setTime((t) => Math.max(0, Math.min(endT, t + (e.key === "." ? 1 : -1))));
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [view.playback, endT]);

  if (q.isLoading) return <p className="muted">{t("กำลังโหลดรอบ {n}…", { n: roundNum })}</p>;
  if (q.error instanceof ApiError && q.error.status === 404) return <NotFound title={t("ไม่พบรอบนี้")} detail={q.error.message} />;
  if (q.error) return <p className="err">{t("โหลดรอบนี้ไม่ได้: {msg}", { msg: (q.error as Error).message })}</p>;
  if (!q.data) return null;

  const d = q.data;
  const shownNades = d.grenades.filter((g) => view.nades.includes(g.type as NadeType));
  const anyNadeOn = shownNades.length > 0;
  // เล่นย้อน: แผนที่ต้องเห็นเฉพาะสิ่งที่เกิดขึ้นแล้ว ณ วินาทีนั้น (คนที่ตายแล้ว / ระเบิดที่ยังมีผล / บอมบ์ที่วางแล้ว)
  const pos = positions.data;
  const roster = new Map(
    d.teams.flatMap((t) => t.players.map((p) => [p.steamid, { name: p.name, color: p.color, slot: p.slot }] as const)),
  );
  const live = view.playback && pos ? playersAt(pos, time, roster) : null;
  // บางรอบในเดโมมีการตายที่บันทึกไว้ก่อนรอบเริ่ม (t_round ติดลบ — ส่วนใหญ่คือตกที่สูงตอนสลับรอบ)
  // โหมดเล่นย้อนนับเฉพาะการตายที่อยู่ในช่วงเวลาของรอบจริง ไม่งั้นคนคนเดียวจะโผล่ทั้งแบบยังไม่ตายและตายแล้วพร้อมกัน
  // (การตายเหล่านั้นยังอยู่ครบในแผนที่ปกติและในไทม์ไลน์ ไม่ได้ถูกซ่อนจากผู้ใช้)
  const shownDeaths = live ? d.deaths.filter((x) => x.t_round != null && x.t_round >= 0 && x.t_round <= time) : d.deaths;
  const liveNades = live ? shownNades.filter((n) => nadeActiveAt(n, time)) : shownNades;
  const plantT = d.round.bomb_planted_t;
  const shownBomb = live && plantT != null && time < plantT ? null : d.round.bomb;
  // ชี้เมาส์อยู่ให้ชนะการกดค้าง — ปล่อยเมาส์แล้วกลับไปที่ตัวที่กดค้างไว้เหมือนเดิม
  const focusPlayer = hover ?? view.player;

  return (
    <div className="review" data-testid="round-view">
      <div className="review-head">
        <h2>
          {t("รอบ {n}", { n: d.round.num })}
          {d.round.winner_side && <span className={`badge b-${d.round.winner_side} big`}>{t("{side} ชนะ", { side: sideLabel(d.round.winner_side) })}</span>}
        </h2>
        <span className="muted">
          {endReasonLabel(d.round.end_reason)}
          {d.round.bomb_planted_t != null && ` · ${t("วางบอมบ์ {time}", { time: fmtT(d.round.bomb_planted_t) })}`} · {t("ตาย {n} คน", { n: d.deaths.length })}
        </span>
        <div className="toggles">
          <span className="toggle-group">
            <span className="muted">{t("ระเบิด")}</span>
            {NADE_TYPES.map((k) => {
              const n = d.grenades.filter((g) => g.type === k).length;
              const on = n > 0 && view.nades.includes(k);   // รอบนี้ไม่มีชนิดนี้เลย = ปุ่มดับไว้ ไม่นับว่าเปิดอยู่
              return (
                <label key={k} className={`nade-toggle${on ? " on" : ""}`} title={t("{nade} {n} ลูกในรอบนี้", { nade: nadeLabel(k), n })}>
                  <input
                    type="checkbox"
                    checked={on}
                    disabled={n === 0}
                    onChange={(e) => setView({ nades: e.target.checked ? [...view.nades, k] : view.nades.filter((x) => x !== k) })}
                  />
                  <img className="nade-ico" src={NADE_ICON[k]} alt="" />
                  {nadeLabel(k)} {n}
                </label>
              );
            })}
            <button
              type="button"
              className="link-btn"
              onClick={() => setView({ nades: anyNadeOn ? [] : [...NADE_TYPES] })}
              disabled={d.grenades.length === 0}
            >
              {anyNadeOn ? t("ปิดทั้งหมด") : t("เปิดทั้งหมด")}
            </button>
            {anyNadeOn && view.death != null && <span className="muted">· {t("เฉพาะที่มีผลตอนการตาย #{n}", { n: view.death })}</span>}
          </span>
        </div>
      </div>

      {/* หน้าจอ laptop / projector: สามส่วนนี้อยู่ในความสูงจอเดียว แผนที่เป็นจัตุรัสเท่าที่ช่องให้ได้ (styles.css) */}
      <div className="review-grid">
        <aside className="roster-col" aria-label={t("ตารางระบุตัวผู้เล่น")}>
          <TeamRoster
            teams={d.teams}
            highlight={focusPlayer}
            onHighlight={(p) => setView({ player: p })}
            onHover={setHover}
            playback={view.playback}
          />
          {view.player && (
            <button type="button" className="link-btn" onClick={() => setView({ player: null })}>
              {t("ล้างการไฮไลต์")}
            </button>
          )}
        </aside>

        <section className="map-col" aria-label={t("แผนที่ของรอบ")}>
          <div className="map-stage">
            {d.radar ? (
              <MapView
                radar={d.radar}
                deaths={shownDeaths}
                bomb={shownBomb}
                grenades={liveNades}
                live={live}
                zoom={view.zoom}
                center={view.center}
                onView={(zoom, center) => setView({ zoom, center })}
                highlight={focusPlayer}
                onHover={setHover}
                selected={view.death}
                onSelect={(o) => setView({ death: o })}
              />
            ) : (
              <p className="muted">{t("ยังไม่มีภาพเรดาร์ของแมพ {map}", { map: d.match.map_name ?? "" })}</p>
            )}
            {/* ซูมลอยอยู่มุมแผนที่ — ไม่กินบรรทัดใต้แผนที่อีกแถว (ล้อเมาส์บนแผนที่ก็ซูมได้) */}
            <div className="map-zoom" role="group" aria-label={t("ซูมแผนที่")}>
              <button type="button" onClick={() => setView({ zoom: clampZoom(view.zoom * 1.4), center: view.center })}
                disabled={view.zoom >= MAX_ZOOM} aria-label={t("ซูมเข้า")} title={t("ซูมเข้า (หรือเลื่อนล้อเมาส์บนแผนที่)")}>+</button>
              <button type="button" onClick={() => {
                const next = clampZoom(view.zoom / 1.4);
                setView(next <= 1.01 ? { zoom: 1, center: null } : { zoom: next, center: view.center });
              }} disabled={view.zoom <= 1} aria-label={t("ซูมออก")} title={t("ซูมออก")}>−</button>
              {view.zoom > 1 && (
                <button type="button" className="mz-reset" onClick={() => setView({ zoom: 1, center: null })}
                  title={t("กลับไปเห็นเต็มแมพ")}>
                  {t("เต็มแมพ")}
                </button>
              )}
            </div>
          </div>
          {/* เล่นย้อน: กดครั้งเดียวทั้งเปิดโหมดและเริ่มเล่น (เดิมต้องกดเปิดโหมดก่อน แล้วกดเล่นอีกที) */}
          <div className="map-play">
            {!view.playback ? (
              <button
                type="button"
                className="pb-start"
                onClick={() => {
                  setTime(0);
                  setView({ playback: true, time: 0 });
                  setPlaying(true);
                }}
                data-testid="playback-start"
              >
                <IconPlay /> {t("เล่นย้อนรอบนี้")}
              </button>
            ) : positions.isLoading ? (
              <span className="muted small">{t("กำลังโหลดตำแหน่งผู้เล่น…")}</span>
            ) : positions.error ? (
              <span className="err small">{t("โหลดตำแหน่งไม่ได้: {msg}", { msg: (positions.error as Error).message })}</span>
            ) : endT <= 0 ? (
              <span className="muted small">{t("รอบนี้ไม่มีตำแหน่งผู้เล่นที่บันทึกไว้")}</span>
            ) : (
              <>
                <button type="button" className="pb-play" onClick={() => setPlaying((p) => !p)}
                  aria-label={playing ? t("หยุด") : t("เล่น")} aria-pressed={playing} title={t("เว้นวรรค = เล่น/หยุด")}>
                  {playing ? <IconPause /> : <IconPlay />}
                </button>
                <input
                  className="pb-range"
                  type="range"
                  min={0}
                  max={endT}
                  step={0.1}
                  value={Math.min(time, endT)}
                  onChange={(e) => {
                    setPlaying(false);
                    setTime(Number(e.target.value));
                  }}
                  aria-label={t("เลื่อนเวลาในรอบ")}
                  title={t(", กับ . = ถอย/เดินหน้าทีละวินาที")}
                />
                <span className="pb-clock">
                  {fmtT(time)} / {fmtT(endT)}
                </span>
                <span className="pb-speeds" role="group" aria-label={t("ความเร็ว")}>
                  {SPEEDS.map((sp) => (
                    <button key={sp} type="button" className={`pb-speed${speed === sp ? " on" : ""}`}
                      aria-pressed={speed === sp} onClick={() => setSpeed(sp)}>
                      {sp}×
                    </button>
                  ))}
                </span>
              </>
            )}
            {view.playback && (
              <button
                type="button"
                className="pb-close"
                onClick={() => {
                  setPlaying(false);
                  setTime(0);
                  setView({ playback: false, time: null });
                }}
                title={t("กลับไปภาพสรุปทั้งรอบ")}
              >
                {t("ภาพสรุปรอบ")}
              </button>
            )}
          </div>
          {view.playback && pos && pos.frames.length > 0 && <p className="muted small pb-note">{t(pos.note)}</p>}
          {anyNadeOn && (
            <div className="legend">
              {(["smoke", "flash", "he", "molotov"] as const).map((t) => (
                <span key={t}>
                  <img className="nade-ico" src={NADE_ICON[t]} alt="" /> {nadeLabel(t)}
                </span>
              ))}
              <span className="muted">{t("ชื่อข้างวง = คนขว้าง · เส้นประ = ทางที่ขว้างมา")}</span>
            </div>
          )}
        </section>

        <aside className="breakdown" aria-label={t("ไทม์ไลน์ของรอบ")}>
          <h3 className="panel-h">{t("ไทม์ไลน์")}</h3>
          <DeathTimeline
            deaths={d.deaths}
            highlight={view.player}
            selected={view.death}
            onSelect={(o) => setView({ death: o })}
            bombPlantedT={d.round.bomb_planted_t}
            grenades={shownNades}
          />
          <RoundSummary summary={d.summary} winner={d.round.winner_side} />
        </aside>
      </div>
    </div>
  );
}

/** ความเร็วที่เลือกได้ในโหมดเล่นย้อน */
const SPEEDS = [1, 2, 4] as const;

/** ผู้เล่นหนึ่งคนบนแผนที่ ณ วินาทีที่กำลังดู */
export interface LivePlayer {
  steamid: string;
  px: [number, number];
  hp: number;
  side: string | null;
  place: string | null;
  name: string;
  color: string;
  slot: number | null;   // หมายเลข 1-5 ที่แสดงบนตัวผู้เล่น — คงที่ทั้งแมตช์ (backend/review.py player_slots)
}

// ------------------------------------------------------------------ สีของทีมบนแผนที่ (โหมดเล่นย้อน)
// ทั้งทีมใช้สีเดียวกันตามฝั่ง แยกตัวบุคคลด้วยหมายเลข ไม่ใช่ด้วยสี (playerFill / playerInk อยู่ใน utils.tsx)
// (สีประจำตัว p.color ยังใช้อยู่ในโหมดปกติและในไทม์ไลน์ เพราะที่นั่นไม่มีหมายเลขกำกับ)

/** เส้นทาง ✕ สองขีดไขว้กัน รัศมี r รอบจุด (0,0) — ใช้วาดคนที่ตายแล้วในโหมดเล่นย้อน */
const crossPath = (r: number) => `M${-r},${-r} L${r},${r} M${r},${-r} L${-r},${r}`;

/**
 * ตำแหน่งของทุกคน ณ วินาที t — เลื่อนระหว่างสองเฟรมที่บันทึกไว้ให้เดินลื่น
 * (ช่วงระหว่างวินาทีเป็นการวาดประมาณ ไม่ใช่ข้อมูลจากเดโม — มีหมายเหตุกำกับใต้แผนที่)
 */
function playersAt(pos: RoundPositions, t: number,
                   roster: Map<string, { name: string; color: string; slot: number | null }>): LivePlayer[] {
  if (pos.frames.length === 0) return [];
  const i = Math.max(0, Math.min(pos.frames.length - 1, Math.floor(t / pos.step)));
  const cur = pos.frames[i];
  const next = pos.frames[i + 1];
  const frac = next ? Math.max(0, Math.min(1, (t - cur.t) / (next.t - cur.t))) : 0;
  return cur.players.map((p) => {
    const to = next?.players.find((n) => n.steamid === p.steamid);   // ไม่มีในเฟรมถัดไป = ตายแล้ว ไม่ต้องเลื่อน
    const info = roster.get(p.steamid);
    return {
      steamid: p.steamid,
      px: to ? ([p.px[0] + (to.px[0] - p.px[0]) * frac, p.px[1] + (to.px[1] - p.px[1]) * frac] as [number, number]) : p.px,
      hp: p.hp,
      side: p.side,
      place: p.place,
      name: info?.name ?? p.steamid,
      color: info?.color ?? "#9aa4b2",
      slot: info?.slot ?? null,
    };
  });
}

// ================================================================================================
// แผนที่เรดาร์ (SVG)
// ================================================================================================
type Anchor = "start" | "middle" | "end";
interface LabelPos {
  x: number;
  y: number;
  anchor: Anchor;
}

/**
 * วางป้ายชื่อไม่ให้ทับกัน และไม่ทับวงของคนอื่น — ลองใต้วง เหนือวง ขวา ซ้าย (แล้วถอยออกไปอีกขั้น)
 * เอาตำแหน่งแรกที่ว่าง (ความกว้างตัวอักษรประมาณเอา ไม่ต้องวัดจริง — แค่กันซ้อนกันจนอ่านไม่ออก)
 */
function labelPlacer() {
  type Box = [number, number, number, number];
  const boxes: Box[] = [];
  const hit = (b: Box) => boxes.some((o) => b[0] < o[2] && b[2] > o[0] && b[1] < o[3] && b[3] > o[1]);
  const block = (x: number, y: number, r: number) => boxes.push([x - r, y - r, x + r, y + r]);
  const place = (x: number, y: number, r: number, text: string, size: number): LabelPos => {
    const w = text.length * size * 0.58 + 6;
    const tries: [LabelPos, Box][] = [];
    for (const gap of [0, size + 4, 2 * (size + 4)]) {
      const R = r + gap;
      tries.push(
        [{ x, y: y + R + size, anchor: "middle" }, [x - w / 2, y + R + 2, x + w / 2, y + R + size + 4]],
        [{ x, y: y - R - 6, anchor: "middle" }, [x - w / 2, y - R - size - 6, x + w / 2, y - R - 2]],
        [{ x: x + R + 6, y: y + size / 3, anchor: "start" }, [x + R + 4, y - size / 2, x + R + 6 + w, y + size / 2]],
        [{ x: x - R - 6, y: y + size / 3, anchor: "end" }, [x - R - 6 - w, y - size / 2, x - R - 4, y + size / 2]],
      );
    }
    const [pos, box] = tries.find(([, b]) => !hit(b)) ?? tries[0];
    boxes.push(box);
    return pos;
  };
  return { place, block };
}

interface MapProps {
  radar: NonNullable<RoundDetail["radar"]>;
  deaths: ReviewDeath[];
  bomb: RoundDetail["round"]["bomb"];
  grenades: ReviewGrenade[];
  live?: LivePlayer[] | null; // โหมดเล่นย้อน: คนที่ยังไม่ตาย ณ วินาทีที่ดู (null = ปิดโหมด)
  onHover?: (steamid: string | null) => void; // ชี้เมาส์ที่ตัวผู้เล่น -> ไฮไลต์แถวในตารางข้างแผนที่
  zoom: number;
  center: [number, number] | null;
  onView: (zoom: number, center: [number, number] | null) => void;
  highlight: string | null; // steamid ที่ถูกกดในรายชื่อ
  selected: number | null; // ลำดับการตายที่ถูกเลือก
  onSelect: (order: number | null) => void;
}

/**
 * แผนที่ของรอบ — วาดเป็น SVG ในพิกัด "พิกเซลของภาพเรดาร์" ที่ backend แปลงมาให้แล้ว (backend/review.py)
 * frontend ไม่มีสูตรแปลงพิกัดของตัวเอง
 * มีจุดตอนตาย (ชื่อคนตายใต้วง) + ระเบิด (วงที่จุดตก ชื่อคนขว้าง เส้นประจากจุดขว้าง)
 * โหมดเล่นย้อน (prop live) เพิ่มตัวผู้เล่น ณ วินาทีที่ดู — ไม่มีเส้นทางเดินย้อนหลัง
 * เลือกการตายแล้ว ระเบิดที่แสดงเหลือเฉพาะลูกที่มีผลอยู่ ณ วินาทีนั้น (ควัน/ไฟที่ยังไม่หมด แฟลช/HE ที่เพิ่งแตก)
 */
export function MapView({ radar, deaths, bomb, grenades, live, zoom, center, onView, highlight, onHover, selected, onSelect }: MapProps) {
  const s = radar.size;
  // ---- ซูม/เลื่อนดู: viewBox คือกรอบที่มองอยู่ · เก็บบน URL เพื่อให้รีเฟรช/แชร์ลิงก์แล้วเห็นกรอบเดิม
  const span = s / zoom;
  const clampC = (v: number) => Math.min(s - span / 2, Math.max(span / 2, v));
  const cx = clampC(center?.[0] ?? s / 2);
  const cy = clampC(center?.[1] ?? s / 2);
  const x0 = cx - span / 2;
  const y0 = cy - span / 2;
  const drag = useRef<{ x: number; y: number; cx: number; cy: number; moved: number } | null>(null);
  const { t } = useT();

  /** พิกัดบนจอ -> พิกัดในภาพเรดาร์ (ใช้ตอนซูมที่ตำแหน่งเมาส์) */
  const toMap = (clientX: number, clientY: number) => {
    const r = svgRef.current!.getBoundingClientRect();
    return [x0 + ((clientX - r.left) / r.width) * span, y0 + ((clientY - r.top) / r.height) * span] as const;
  };
  const zoomAt = (factor: number, clientX?: number, clientY?: number) => {
    const next = clampZoom(zoom * factor);
    if (next === zoom) return;
    if (next === 1) return onView(1, null);
    if (clientX === undefined || clientY === undefined) return onView(next, [cx, cy]);
    const [mx, my] = toMap(clientX, clientY);            // จุดใต้เมาส์ต้องอยู่ที่เดิมหลังซูม
    const k = 1 - zoom / next;
    onView(next, [cx + (mx - cx) * k, cy + (my - cy) * k]);
  };
  // วง / ป้าย / เส้น กำหนดเป็น "พิกเซลบนจอ" ไม่ใช่หน่วยของภาพ — แผนที่เล็กบน laptop ป้ายไม่หดจนอ่านไม่ออก
  // แผนที่ใหญ่บน projector ขยายตามอีกนิด (สูงสุด 1.35 เท่า) ให้อ่านได้จากระยะไกล
  const svgRef = useRef<SVGSVGElement>(null);
  const [shown, setShown] = useState(0); // ความกว้างที่แสดงจริง (px)
  useLayoutEffect(() => {
    const el = svgRef.current;
    if (!el) return;
    setShown(el.getBoundingClientRect().width);
    const ro = new ResizeObserver(([e]) => setShown(e.contentRect.width));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  const U = shown > 0 ? (span / shown) * Math.min(1.35, Math.max(1, shown / 620)) : 1; // หน่วยภาพต่อ 1 px บนจอ (ตามกรอบที่ซูมอยู่)
  const z = {
    dot: 12 * U, dotSel: 15 * U, num: 12 * U, name: 13 * U, atk: 5 * U, atkName: 12 * U,
    nade: 6 * U, nadeIco: 22 * U, nadeName: 12 * U, line: 2 * U, bomb: 10 * U,
  };
  const halo = (size: number) => ({ fontSize: size, strokeWidth: size * 0.3 });

  const selT = selected === null ? null : (deaths.find((d) => d.order === selected)?.t_round ?? null);
  // โหมดเล่นย้อนกรองตามเวลาที่กำลังดูมาแล้ว จึงไม่กรองซ้ำด้วยการตายที่เลือก
  const nades = grenades.filter((n) => n.land_px && (live ? true : selT === null || nadeActiveAt(n, selT)));
  const nadeFocus = (n: ReviewGrenade) => !highlight || n.thrower?.steamid === highlight;
  const dotR = (d: ReviewDeath) => (selected === d.order ? z.dotSel : z.dot);
  const { place, block } = labelPlacer();
  // วงทุกวงเป็นสิ่งกีดขวางของป้าย (ควัน/ไฟเป็นวงโปร่ง ป้ายทับได้)
  deaths.forEach((d) => {
    if (d.victim_px) block(d.victim_px[0], d.victim_px[1], dotR(d));
    if (d.attacker_px) block(d.attacker_px[0], d.attacker_px[1], z.atk);
  });
  nades.forEach((n) => n.r_px === 0 && block(n.land_px![0], n.land_px![1], z.nadeIco / 2));
  live?.forEach((p) => block(p.px[0], p.px[1], z.dot * 0.9));   // ยังกันไม่ให้ป้ายอื่นทับตัวผู้เล่น
  const deathLabel = new Map<number, LabelPos>();
  deaths.forEach((d) => {
    if (d.victim_px) deathLabel.set(d.order, place(d.victim_px[0], d.victim_px[1], dotR(d), d.victim.name, z.name));
  });
  const nadeLabelPos = nades.map((n) =>
    place(n.land_px![0], n.land_px![1], n.r_px > 0 ? n.r_px : z.nadeIco / 2, `${n.thrower?.name ?? "?"} · ${nadeLabel(n.type)}`, z.nadeName),
  );
  const involved = (d: ReviewDeath) =>
    !highlight || d.victim.steamid === highlight || d.attacker?.steamid === highlight;
  const focus = (d: ReviewDeath) => (selected === null ? involved(d) : selected === d.order);

  return (
    <svg
      ref={svgRef}
      viewBox={`${x0} ${y0} ${span} ${span}`}
      className={`radar${zoom > 1 ? " zoomed" : ""}`}
      data-testid="radar-svg"
      data-zoom={zoom.toFixed(2)}
      onClick={() => {
        if ((drag.current?.moved ?? 0) < 4) onSelect(null);   // ลากแล้วไม่นับเป็นคลิกล้างการเลือก
      }}
      onWheel={(e) => zoomAt(e.deltaY < 0 ? 1.2 : 1 / 1.2, e.clientX, e.clientY)}
      onPointerDown={(e) => {
        if (zoom <= 1 || e.button !== 0) return;
        drag.current = { x: e.clientX, y: e.clientY, cx, cy, moved: 0 };
        e.currentTarget.setPointerCapture(e.pointerId);
      }}
      onPointerMove={(e) => {
        const dr = drag.current;
        if (!dr) return;
        const r = e.currentTarget.getBoundingClientRect();
        const dx = ((e.clientX - dr.x) / r.width) * span;
        const dy = ((e.clientY - dr.y) / r.height) * span;
        dr.moved = Math.max(dr.moved, Math.abs(e.clientX - dr.x) + Math.abs(e.clientY - dr.y));
        onView(zoom, [dr.cx - dx, dr.cy - dy]);
      }}
      onPointerUp={(e) => {
        e.currentTarget.releasePointerCapture(e.pointerId);
        window.setTimeout(() => (drag.current = null), 0);
      }}
    >
      <image href={radar.image} x={0} y={0} width={s} height={s} />

      {bomb?.px && (
        <g transform={`translate(${bomb.px[0]}, ${bomb.px[1]})`} data-testid="bomb-icon">
          <rect x={-z.bomb} y={-z.bomb} width={2 * z.bomb} height={2 * z.bomb} rx={z.bomb * 0.35} fill="#dc2626" stroke="#fff" strokeWidth={z.line} />
          <text textAnchor="middle" dy={z.bomb * 0.38} className="bomb-label" style={{ fontSize: z.bomb * 1.05 }}>
            C4
          </text>
          <title>{`${t("วางบอมบ์")}${bomb.site ? ` (${bomb.site})` : ""}`}</title>
        </g>
      )}

      {/* ระเบิด: วงที่จุดตก (ควัน/ไฟตามขนาดจริงโดยประมาณ) + ชื่อคนขว้าง + เส้นประจากจุดที่ขว้าง */}
      {nades.map((n, i) => {
        const [x, y] = n.land_px!;
        const c = NADE_COLOR[n.type] ?? "#fff";
        const who = n.thrower?.name ?? "?";
        return (
          <g key={`n${i}`} opacity={nadeFocus(n) ? 1 : 0.15} data-testid="nade">
            {n.throw_px && (
              <line x1={n.throw_px[0]} y1={n.throw_px[1]} x2={x} y2={y} stroke={n.thrower?.color ?? c}
                strokeWidth={z.line * 0.8} strokeDasharray={`${5 * U} ${5 * U}`} opacity={0.5} />
            )}
            {/* ควัน/ไฟ = วงโปร่งตามขนาดที่มีผลจริง + ไอคอนกลางวง · แฟลช/HE = ไอคอนอย่างเดียว (แตกแล้วหายทันที) */}
            {n.r_px > 0 && (
              <circle cx={x} cy={y} r={n.r_px} fill={c} fillOpacity={0.32} stroke={c} strokeWidth={z.line} />
            )}
            {NADE_ICON[n.type] ? (
              <image href={NADE_ICON[n.type]} x={x - z.nadeIco / 2} y={y - z.nadeIco / 2} width={z.nadeIco} height={z.nadeIco} />
            ) : (
              <circle cx={x} cy={y} r={z.nade} fill={c} stroke={c} strokeWidth={z.line} />
            )}
            <text x={nadeLabelPos[i].x} y={nadeLabelPos[i].y} textAnchor={nadeLabelPos[i].anchor} className="nade-label"
              style={{ ...halo(z.nadeName), fill: n.thrower?.color ?? c }}>
              {who} · {nadeLabel(n.type)}
            </text>
            <title>{`${t("{time} {who} ({side}) ขว้าง{nade}", { time: fmtT(n.t_land), who, side: sideLabel(n.thrower?.side), nade: nadeLabel(n.type) })}${
              n.t_end != null && n.t_end > (n.t_land ?? 0) ? ` · ${t("มีผลถึง {time}", { time: fmtT(n.t_end) })}` : ""}`}</title>
          </g>
        );
      })}

      {/* เส้นทิศทางการยิง: จากคนยิงไปคนตาย */}
      {deaths.map(
        (d) =>
          d.attacker_px &&
          d.victim_px && (
            <line
              key={`l${d.order}`}
              x1={d.attacker_px[0]}
              y1={d.attacker_px[1]}
              x2={d.victim_px[0]}
              y2={d.victim_px[1]}
              stroke={d.attacker?.color ?? "#fff"}
              strokeWidth={z.line * 1.2}
              opacity={focus(d) ? 0.9 : 0.1}
            />
          ),
      )}
      {deaths.map(
        (d) =>
          d.attacker_px && (
            <g key={`a${d.order}`} opacity={focus(d) ? 1 : 0.15}>
              <circle cx={d.attacker_px[0]} cy={d.attacker_px[1]} r={z.atk} fill={d.attacker?.color ?? "#fff"} stroke="#0b1220" strokeWidth={z.line * 0.8} />
              {d.attacker && (selected === d.order || (highlight && focus(d))) && (
                <text x={d.attacker_px[0]} y={d.attacker_px[1] - z.atk - 4 * U} textAnchor="middle" className="dot-name atk" style={halo(z.atkName)}>
                  {d.attacker.name}
                </text>
              )}
            </g>
          ),
      )}

      {/* โหมดเล่นย้อน: ตัวผู้เล่นที่ยังไม่ตาย ณ วินาทีนั้น
          วงทึบสีของฝั่ง (CT ฟ้า / T ส้ม) + หมายเลข 1-5 ในวง — ไม่มีชื่อบนแผนที่ ชื่ออยู่ในตารางข้างแผนที่
          ขอบวงเป็นสีเข้มไว้ให้ยังแยกออกจากกันตอนสองคนยืนชิดกัน (สีเดียวกันทั้งทีม) */}
      {live?.map((p) => (
        <g
          key={`live-${p.steamid}`}
          opacity={!highlight || highlight === p.steamid ? 1 : 0.28}
          data-testid="live-player"
          data-slot={p.slot ?? ""}
          data-side={p.side ?? ""}
          onMouseEnter={() => onHover?.(p.steamid)}
          onMouseLeave={() => onHover?.(null)}
        >
          <circle
            cx={p.px[0]}
            cy={p.px[1]}
            r={highlight === p.steamid ? z.dot : z.dot * 0.9}
            fill={playerFill(p.side)}
            stroke={highlight === p.steamid ? "#fff" : "#0b1220"}
            strokeWidth={z.line * (highlight === p.steamid ? 2 : 1.2)}
          />
          <text
            x={p.px[0]}
            y={p.px[1]}
            dy={z.num * 0.36}
            textAnchor="middle"
            className="slot-num"
            style={{ fontSize: z.num * 1.05, fill: playerInk(p.side) }}
          >
            {p.slot ?? "?"}
          </text>
          <title>{`${p.slot ?? "?"} · ${p.name} · ${p.hp} HP${p.place ? ` · ${p.place}` : ""}`}</title>
        </g>
      ))}

      {/* จุดตาย — ตัวเลขบนแผนที่ต้องหมายถึงสิ่งเดียวกันเสมอในแต่ละโหมด ไม่ปนกัน
            โหมดเล่นย้อน  ✕ กลวงสีของฝั่ง + "หมายเลขผู้เล่น" (ทุกเลขบนแผนที่ = หมายเลขผู้เล่น)
            โหมดปกติ      วงทึบสีประจำตัว + "ลำดับการตาย" (ตายคนที่ 3 ขึ้นเลข 3) พร้อมชื่อข้างวง
          ลำดับการตายยังอ่านได้จากไทม์ไลน์ใต้แผนที่ในทั้งสองโหมด */}
      {deaths.map(
        (d) =>
          d.victim_px && (
            <g
              key={`v${d.order}`}
              transform={`translate(${d.victim_px[0]}, ${d.victim_px[1]})`}
              className="death-dot"
              opacity={focus(d) ? 1 : 0.22}
              onClick={(e) => {
                e.stopPropagation();
                onSelect(selected === d.order ? null : d.order);
              }}
              data-testid="death-dot"
              data-mode={live ? "playback" : "normal"}
            >
              {live ? (
                <>
                  {/* ✕ กลวง: เส้นล่างสีเข้มไว้ให้ยังเห็นบนพื้นเรดาร์ส่วนที่สว่าง */}
                  <path d={crossPath(dotR(d))} stroke="#0b1220" strokeWidth={z.line * 3.2} strokeLinecap="round" fill="none" />
                  <path d={crossPath(dotR(d))} stroke={playerFill(d.victim.side)} strokeWidth={z.line * 1.8}
                    strokeLinecap="round" fill="none" />
                  <text x={dotR(d) * 1.05} y={-dotR(d) * 0.75} textAnchor="start" className="slot-num dead"
                    style={{ ...halo(z.num), fill: playerFill(d.victim.side) }}>
                    {d.victim.slot ?? "?"}
                  </text>
                </>
              ) : (
                <>
                  <circle r={dotR(d)} fill={d.victim.color} stroke={selected === d.order ? "#fff" : "#0b1220"} strokeWidth={z.line * 1.3} />
                  <text textAnchor="middle" dy={z.num * 0.36} className="death-num" style={{ fontSize: z.num }}>
                    {d.order}
                  </text>
                  <text x={deathLabel.get(d.order)!.x - d.victim_px[0]} y={deathLabel.get(d.order)!.y - d.victim_px[1]}
                    textAnchor={deathLabel.get(d.order)!.anchor} className="dot-name" style={halo(z.name)}>
                    {d.victim.name}
                  </text>
                </>
              )}
              <title>{`${live ? `${d.victim.slot ?? "?"} · ` : `${d.order}. `}${t("{time} {victim} ตาย · {weapon}", { time: fmtT(d.t_round), victim: d.victim.name, weapon: weaponLabel(d.weapon) })}${d.attacker ? ` · ${t("โดย {name}", { name: d.attacker.name })}` : ""}`}</title>
            </g>
          ),
      )}
    </svg>
  );
}

// ================================================================================================
// ตารางระบุตัวผู้เล่น (legend ข้างแผนที่)
// ================================================================================================
interface RosterProps {
  teams: ReviewTeam[];
  highlight: string | null;
  onHighlight: (steamid: string | null) => void;
  /** ไฮไลต์ชั่วคราวตอนเอาเมาส์ชี้ — แยกจาก highlight ที่กดค้างไว้ */
  onHover: (steamid: string | null) => void;
  playback: boolean;
}

/**
 * บอกว่าหมายเลขไหนคือใคร — ตารางนี้คือสิ่งที่ทำให้หมายเลขบนแผนที่มีความหมาย
 *
 * จัดกล่องตามทีม (clan) ซึ่งในหนึ่งรอบเท่ากับจัดตามฝั่งอยู่แล้ว เพราะทีมหนึ่งเล่นได้ฝั่งเดียวต่อรอบ
 * หัวกล่องจึงใช้สีของฝั่งที่ทีมนั้นเล่น "รอบนี้" — ครึ่งหลังสลับฝั่ง สีหัวกล่องก็สลับตาม
 * แต่หมายเลขในกล่องไม่ขยับ เพราะมาจาก player_slots() ที่ผูกกับทีม ไม่ผูกกับฝั่ง
 *
 * วงกลมเลขหน้าแถวใช้สีและรูปทรงเดียวกับบนแผนที่ เพื่อให้กวาดตาเทียบกันได้ทันที
 */
export function TeamRoster({ teams, highlight, onHighlight, onHover, playback }: RosterProps) {
  const { t: tx } = useT();
  return (
    <div className="roster" data-testid="team-roster">
      {teams.map((t) => (
        <div className={`team-box side-${t.side_this_round}`} key={t.clan}>
          <div className="team-head">
            <b>{t.clan}</b>
            <span className={`badge b-${t.side_this_round}`}>{sideLabel(t.side_this_round)}</span>
            <span className="muted small">{tx("รอบนี้")}</span>
          </div>
          <ul>
            {[...t.players].sort((a, b) => (a.slot ?? 99) - (b.slot ?? 99)).map((p) => (
              <li
                key={p.steamid}
                className={[
                  highlight === p.steamid ? "on" : highlight ? "dim" : "",
                  p.survived ? "" : "dead",
                ].filter(Boolean).join(" ")}
                onMouseEnter={() => onHover(p.steamid)}
                onMouseLeave={() => onHover(null)}
                data-testid="roster-row"
                data-slot={p.slot ?? ""}
                data-dead={p.survived ? "0" : "1"}
              >
                <button
                  type="button"
                  className="pname"
                  onClick={() => onHighlight(highlight === p.steamid ? null : p.steamid)}
                  title={tx("กดเพื่อไฮไลต์เฉพาะเหตุการณ์ของคนนี้ค้างไว้")}
                >
                  <span
                    className="pslot"
                    style={{ background: playerFill(t.side_this_round), color: playerInk(t.side_this_round) }}
                    aria-hidden="true"
                  >
                    {p.slot ?? "?"}
                  </span>
                  <span className="pn">{p.name}</span>
                  {p.kills > 0 && <span className="kills">{tx("{n} คิล", { n: p.kills })}</span>}
                </button>
                <div className="pstat">
                  {p.survived ? (
                    <span className="alive">{tx("รอดถึงจบรอบ")}</span>
                  ) : (
                    <>
                      {tx("ตาย {time} · {weapon}", { time: fmtT(p.died_at_t), weapon: weaponLabel(p.weapon) })}
                      {p.killed_by ? ` · ${tx("โดย {name}", { name: p.killed_by })}` : ""}
                      {p.death_order ? <span className="muted"> (#{p.death_order})</span> : null}
                    </>
                  )}
                </div>
              </li>
            ))}
          </ul>
        </div>
      ))}
      <p className="roster-note muted small">
        {playback
          ? tx("เลขบนแผนที่ = หมายเลขผู้เล่นในตารางนี้ · ✕ = ตายแล้ว")
          : tx("เลขบนแผนที่ = ลำดับการตาย (ตรงกับไทม์ไลน์) · เลขในตารางนี้ = หมายเลขผู้เล่น ใช้ตอนเล่นย้อน")}
      </p>
    </div>
  );
}

// ================================================================================================
// ไทม์ไลน์การตาย
// ================================================================================================
interface TimelineProps {
  deaths: ReviewDeath[];
  highlight: string | null;
  selected: number | null;
  onSelect: (order: number | null) => void;
  bombPlantedT: number | null;
  grenades: ReviewGrenade[];
}

const involved = (d: ReviewDeath, h: string | null) => !h || d.victim.steamid === h || d.attacker?.steamid === h;

function Who({ p }: { p: ReviewDeath["victim"] }) {
  return (
    <span className="who">
      <span className="pdot" style={{ background: p.color }} />
      {p.name} <span className="muted">({sideLabel(p.side)})</span>
    </span>
  );
}

/** ไล่ตามเวลา: 0:23  Alice (T) ฆ่า Bob (CT) · AK-47 · HS · ระยะ 640u · A Site */
export function DeathTimeline({ deaths, highlight, selected, onSelect, bombPlantedT, grenades }: TimelineProps) {
  type Item =
    | { t: number; kind: "death"; d: ReviewDeath }
    | { t: number; kind: "bomb" }
    | { t: number; kind: "nade"; n: ReviewGrenade; i: number };
  const items: Item[] = deaths.map((d) => ({ t: d.t_round ?? 0, kind: "death" as const, d }));
  if (bombPlantedT != null) items.push({ t: bombPlantedT, kind: "bomb" });
  grenades.forEach((n, i) => items.push({ t: n.t_land ?? n.t_throw ?? 0, kind: "nade", n, i }));
  items.sort((a, b) => a.t - b.t);
  const { t, tn } = useT();

  return (
    <ol className="timeline-list" data-testid="death-timeline">
      {items.map((it) =>
        it.kind === "bomb" ? (
          <li key="bomb" className="tl-bomb">
            <span className="tl-t">{fmtT(it.t)}</span> {t("วางบอมบ์")}
          </li>
        ) : it.kind === "nade" ? (
          <li key={`n${it.i}`} className={`tl-nade ${!highlight || it.n.thrower?.steamid === highlight ? "" : "dim"}`}>
            <img className="nade-dot" src={NADE_ICON[it.n.type]} alt="" />
            <span className="tl-t">{fmtT(it.t)}</span>
            <span className="tl-text">
              {tn("{who} ขว้าง{nade}", { who: it.n.thrower ? <Who p={it.n.thrower} /> : "?", nade: nadeLabel(it.n.type) })}
            </span>
          </li>
        ) : (
          <li
            key={it.d.order}
            className={`${selected === it.d.order ? "sel" : ""} ${involved(it.d, highlight) ? "" : "dim"}`}
            {...pressable(() => onSelect(selected === it.d.order ? null : it.d.order))}
          >
            <span className="tl-num" style={{ background: it.d.victim.color }}>
              {it.d.order}
            </span>
            <span className="tl-t">{fmtT(it.d.t_round)}</span>
            <span className="tl-text">
              {it.d.attacker && it.d.is_duel ? (
                tn("{attacker} ฆ่า {victim}", { attacker: <Who p={it.d.attacker} />, victim: <Who p={it.d.victim} /> })
              ) : it.d.team_kill && it.d.attacker ? (
                tn("{attacker} ยิงเพื่อนร่วมทีม {victim}", { attacker: <Who p={it.d.attacker} />, victim: <Who p={it.d.victim} /> })
              ) : (
                tn("{victim} ตาย", { victim: <Who p={it.d.victim} /> })
              )}
              <span className="tl-meta">
                {" · "}
                {weaponLabel(it.d.weapon)}
                {it.d.headshot && " · HS"}
                {it.d.distance != null && ` · ${t("ระยะ {d}u", { d: it.d.distance })}`}
                {it.d.place && ` · ${it.d.place}`}
                {it.d.attacker_blind && ` · ${t("คนยิงโดนแฟลช")}`}
                {it.d.thru_smoke && ` · ${t("ยิงผ่านควัน")}`}
                {it.d.penetrated > 0 && ` · ${t("ทะลุกำแพง")}`}
                {it.d.noscope && " · noscope"}
                {it.d.assister && ` · ${t("ช่วย: {name}", { name: it.d.assister })}`}
              </span>
            </span>
          </li>
        ),
      )}
      {deaths.length === 0 && <li className="muted">{t("ไม่มีใครตายในรอบนี้")}</li>}
    </ol>
  );
}

// ================================================================================================
// สรุปรอบ — ข้อเท็จจริงจากเดโมล้วน ๆ ไม่มีตัวเลขจากโมเดล (ส่วนนั้นอยู่ที่ /analysis)
// ================================================================================================
/** สรุปรอบ: ใครตายคนแรก / ฝั่งที่เสียคนแรกแพ้ไหม */
export function RoundSummary({ summary, winner }: { summary: RoundDetail["summary"]; winner: RoundDetail["round"]["winner_side"] }) {
  const f = summary.first_death;
  const { t, tn } = useT();
  return (
    <section className="summary" data-testid="round-summary">
      <h3 className="panel-h">{t("สรุปรอบ")}</h3>
      {f ? (
        <p>
          {tn("ตายคนแรก: {name} ({side}) ที่ {place} วินาทีที่ {time}", {
            name: <b>{f.name}</b>, side: sideLabel(f.side), place: f.place ?? "—", time: fmtT(f.t_round),
          })}
          {f.by ? ` ${t("โดย {name}", { name: f.by })}` : ""}
        </p>
      ) : (
        <p className="muted">{t("รอบนี้ไม่มีใครตาย")}</p>
      )}
      {summary.first_death_side_lost !== null && f && (
        <p>
          {t(summary.first_death_side_lost
            ? "ฝั่ง {side} เสียคนแรก และแพ้รอบนี้ (ผู้ชนะ {winner})"
            : "ฝั่ง {side} เสียคนแรก และชนะรอบนี้ (ผู้ชนะ {winner})", { side: sideLabel(f.side), winner: sideLabel(winner) })}
        </p>
      )}
    </section>
  );
}


/** ไอคอนเล่น / หยุด — วาดเองให้เข้าชุดกับไอคอนอื่นในแอป */
function IconPlay() {
  return (
    <svg width="13" height="13" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
      <path d="M7 4.5 20 12 7 19.5Z" fill="currentColor" />
    </svg>
  );
}

function IconPause() {
  return (
    <svg width="13" height="13" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
      <path d="M7.5 4.5h3.5v15H7.5zM13 4.5h3.5v15H13z" fill="currentColor" />
    </svg>
  );
}

