import { type KeyboardEvent, useEffect, useLayoutEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  api,
  ApiError,
  type GridOverlay,
  type ReviewDeath,
  type ReviewGrenade,
  type ReviewTeam,
  type RoundDetail,
  type RoundPositions,
} from "./api";
import {
  clampZoom,
  clusterColor,
  endReasonLabel,
  fmtT,
  MAX_ZOOM,
  NADE_COLOR,
  nadeActiveAt,
  nadeLabel,
  NADE_TYPES,
  type NadeType,
  NotFound,
  pct,
  sideLabel,
  type ViewState,
  weaponLabel,
} from "./utils";

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

/** เนื้อหาของหนึ่งรอบ: รายชื่อทีม / แผนที่ / ไทม์ไลน์ + บริบทจาก grid_ml1 — state ทั้งหมดมาจาก URL */
export function RoundView({ demo, roundNum, view, setView }: RoundViewProps) {
  // โหมดเล่นย้อน: เวลาที่กำลังเล่นอยู่เก็บใน state (เปลี่ยนทุกเฟรม) แล้วเขียนลง URL ตอนหยุดเท่านั้น
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState<(typeof SPEEDS)[number]>(1);
  const [time, setTime] = useState(view.time ?? 0);
  const q = useQuery({
    queryKey: ["review-round", demo, roundNum],
    queryFn: () => api.reviewRound(demo, roundNum),
    // ระหว่างโหลดรอบใหม่ของแมตช์เดิม ให้เห็นรอบก่อนไว้ก่อน (ไม่กระพริบ) แต่ห้ามโชว์รอบของแมตช์อื่น
    placeholderData: (prev: RoundDetail | undefined) => (prev && prev.match.demo_file === demo ? prev : undefined),
    retry: (count, err) => !(err instanceof ApiError && err.status === 404) && count < 1,
  });
  const mapName = q.data?.radar?.map;
  const grid = useQuery({
    queryKey: ["review-grid", mapName],
    queryFn: () => api.reviewGrid(mapName!),
    enabled: !!mapName,
    staleTime: Infinity, // ผล grid_ml1 ไม่เปลี่ยนระหว่างใช้งาน
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

  if (q.isLoading) return <p className="muted">กำลังโหลดรอบ {roundNum}…</p>;
  if (q.error instanceof ApiError && q.error.status === 404) return <NotFound title="ไม่พบรอบนี้" detail={q.error.message} />;
  if (q.error) return <p className="err">โหลดรอบนี้ไม่ได้: {(q.error as Error).message}</p>;
  if (!q.data) return null;

  const d = q.data;
  const overlay = grid.data?.available ? grid.data : undefined;
  const shownNades = d.grenades.filter((g) => view.nades.includes(g.type as NadeType));
  const anyNadeOn = shownNades.length > 0;
  // เล่นย้อน: แผนที่ต้องเห็นเฉพาะสิ่งที่เกิดขึ้นแล้ว ณ วินาทีนั้น (คนที่ตายแล้ว / ระเบิดที่ยังมีผล / บอมบ์ที่วางแล้ว)
  const pos = positions.data;
  const roster = new Map(
    d.teams.flatMap((t) => t.players.map((p) => [p.steamid, { name: p.name, color: p.color }] as const)),
  );
  const live = view.playback && pos ? playersAt(pos, time, roster) : null;
  // บางรอบในเดโมมีการตายที่บันทึกไว้ก่อนรอบเริ่ม (t_round ติดลบ — ส่วนใหญ่คือตกที่สูงตอนสลับรอบ)
  // โหมดเล่นย้อนนับเฉพาะการตายที่อยู่ในช่วงเวลาของรอบจริง ไม่งั้นคนคนเดียวจะโผล่ทั้งแบบยังไม่ตายและตายแล้วพร้อมกัน
  // (การตายเหล่านั้นยังอยู่ครบในแผนที่ปกติและในไทม์ไลน์ ไม่ได้ถูกซ่อนจากผู้ใช้)
  const shownDeaths = live ? d.deaths.filter((x) => x.t_round != null && x.t_round >= 0 && x.t_round <= time) : d.deaths;
  const liveNades = live ? shownNades.filter((n) => nadeActiveAt(n, time)) : shownNades;
  const plantT = d.round.bomb_planted_t;
  const shownBomb = live && plantT != null && time < plantT ? null : d.round.bomb;

  return (
    <div className="review" data-testid="round-view">
      <div className="review-head">
        <h2>
          รอบ {d.round.num}
          {d.round.winner_side && <span className={`badge b-${d.round.winner_side} big`}>{sideLabel(d.round.winner_side)} ชนะ</span>}
        </h2>
        <span className="muted">
          {endReasonLabel(d.round.end_reason)}
          {d.round.bomb_planted_t != null && ` · วางบอมบ์ ${fmtT(d.round.bomb_planted_t)}`} · ตาย {d.deaths.length} คน
        </span>
        <div className="toggles">
          <span className="toggle-group">
            <span className="muted">ระเบิด</span>
            {NADE_TYPES.map((t) => {
              const n = d.grenades.filter((g) => g.type === t).length;
              const on = n > 0 && view.nades.includes(t);   // รอบนี้ไม่มีชนิดนี้เลย = ปุ่มดับไว้ ไม่นับว่าเปิดอยู่
              return (
                <label key={t} className={`nade-toggle${on ? " on" : ""}`} title={`${nadeLabel(t)} ${n} ลูกในรอบนี้`}>
                  <input
                    type="checkbox"
                    checked={on}
                    disabled={n === 0}
                    onChange={(e) => setView({ nades: e.target.checked ? [...view.nades, t] : view.nades.filter((x) => x !== t) })}
                  />
                  <i style={{ background: NADE_COLOR[t] }} />
                  {nadeLabel(t)} {n}
                </label>
              );
            })}
            <button
              type="button"
              className="link-btn"
              onClick={() => setView({ nades: anyNadeOn ? [] : [...NADE_TYPES] })}
              disabled={d.grenades.length === 0}
            >
              {anyNadeOn ? "ปิดทั้งหมด" : "เปิดทั้งหมด"}
            </button>
            {anyNadeOn && view.death != null && <span className="muted">· เฉพาะที่มีผลตอนการตาย #{view.death}</span>}
          </span>
          <label>
            <input type="checkbox" checked={view.cells} disabled={!overlay} onChange={(e) => setView({ cells: e.target.checked })} />
            ประเภทช่อง (grid_ml1)
          </label>
          <label>
            <input type="checkbox" checked={view.hotspots} disabled={!overlay} onChange={(e) => setView({ hotspots: e.target.checked })} />
            วง hotspot {overlay?.hotspots?.length ?? ""} จุด
          </label>
        </div>
      </div>

      {/* หน้าจอ laptop / projector: สามส่วนนี้อยู่ในความสูงจอเดียว แผนที่เป็นจัตุรัสเท่าที่ช่องให้ได้ (styles.css) */}
      <div className="review-grid">
        <aside className="roster-col" aria-label="รายชื่อทีม">
          <TeamRoster teams={d.teams} highlight={view.player} onHighlight={(p) => setView({ player: p })} />
          {view.player && (
            <button type="button" className="link-btn" onClick={() => setView({ player: null })}>
              ล้างการไฮไลต์
            </button>
          )}
        </aside>

        <section className="map-col" aria-label="แผนที่ของรอบ">
          <div className="map-stage">
            {d.radar ? (
              <MapView
                radar={d.radar}
                deaths={shownDeaths}
                bomb={shownBomb}
                overlay={overlay}
                showCells={view.cells}
                showHotspots={view.hotspots}
                grenades={liveNades}
                live={live}
                zoom={view.zoom}
                center={view.center}
                onView={(zoom, center) => setView({ zoom, center })}
                highlight={view.player}
                selected={view.death}
                onSelect={(o) => setView({ death: o })}
              />
            ) : (
              <p className="muted">ยังไม่มีภาพเรดาร์ของแมพ {d.match.map_name}</p>
            )}
          </div>
          <div className="map-play">
            <button
              type="button"
              className={`pb-mode${view.playback ? " on" : ""}`}
              aria-pressed={view.playback}
              onClick={() => {
                setPlaying(false);
                setTime(0);
                setView({ playback: !view.playback, time: view.playback ? null : 0 });
              }}
            >
              {view.playback ? "ปิดโหมดเล่นย้อน" : "โหมดเล่นย้อน"}
            </button>
            {view.playback &&
              (positions.isLoading ? (
                <span className="muted small">กำลังโหลดตำแหน่งผู้เล่น…</span>
              ) : positions.error ? (
                <span className="err small">โหลดตำแหน่งไม่ได้: {(positions.error as Error).message}</span>
              ) : endT <= 0 ? (
                <span className="muted small">รอบนี้ไม่มีตำแหน่งผู้เล่นที่บันทึกไว้</span>
              ) : (
                <>
                  <button type="button" className="pb-play" onClick={() => setPlaying((p) => !p)}
                    aria-label={playing ? "หยุด" : "เล่น"} aria-pressed={playing}>
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
                    aria-label="เลื่อนเวลาในรอบ"
                  />
                  <span className="pb-clock">
                    {fmtT(time)} / {fmtT(endT)}
                  </span>
                  {SPEEDS.map((sp) => (
                    <button key={sp} type="button" className={`pb-speed${speed === sp ? " on" : ""}`}
                      aria-pressed={speed === sp} onClick={() => setSpeed(sp)}>
                      {sp}×
                    </button>
                  ))}
                  <span className="muted small">เว้นวรรค = เล่น/หยุด · , . = ทีละวินาที</span>
                </>
              ))}
          </div>
          <div className="map-zoom">
            <button type="button" onClick={() => setView({ zoom: clampZoom(view.zoom * 1.4), center: view.center })}
              disabled={view.zoom >= MAX_ZOOM} aria-label="ซูมเข้า">+</button>
            <button type="button" onClick={() => {
              const next = clampZoom(view.zoom / 1.4);
              setView(next <= 1.01 ? { zoom: 1, center: null } : { zoom: next, center: view.center });
            }} disabled={view.zoom <= 1} aria-label="ซูมออก">−</button>
            <button type="button" className="link-btn" onClick={() => setView({ zoom: 1, center: null })} disabled={view.zoom <= 1}>
              เต็มแมพ
            </button>
            <span className="muted small">{view.zoom > 1 ? `ซูม ${view.zoom.toFixed(1)}× · ลากเพื่อเลื่อนดู` : "เลื่อนล้อเมาส์บนแผนที่เพื่อซูม"}</span>
          </div>
          {view.playback && pos && pos.frames.length > 0 && <p className="muted small pb-note">{pos.note}</p>}
          {anyNadeOn && (
            <div className="legend">
              {(["smoke", "flash", "he", "molotov"] as const).map((t) => (
                <span key={t}>
                  <i style={{ background: NADE_COLOR[t] }} /> {nadeLabel(t)}
                </span>
              ))}
              <span className="muted">ชื่อข้างวง = คนขว้าง · เส้นประ = ทางที่ขว้างมา</span>
            </div>
          )}
          {view.cells && overlay?.clusters && (
            <div className="legend">
              {overlay.clusters.map((c) => (
                <span key={c.id}>
                  <i style={{ background: clusterColor(c.id) }} /> type {c.id}: {c.name} · CT ชนะดวล {pct(c.ct_win)}
                </span>
              ))}
              <span className="muted">จาก {overlay.source?.label}</span>
            </div>
          )}
        </section>

        <aside className="breakdown" aria-label="ไทม์ไลน์และบริบทของรอบ">
          <h3 className="panel-h">ไทม์ไลน์</h3>
          <DeathTimeline
            deaths={d.deaths}
            highlight={view.player}
            selected={view.death}
            onSelect={(o) => setView({ death: o })}
            bombPlantedT={d.round.bomb_planted_t}
            grenades={shownNades}
          />
          <RoundSummary summary={d.summary} winner={d.round.winner_side} grid={d.grid} />
          <DeathContext
            deaths={d.deaths}
            grid={d.grid}
            highlight={view.player}
            selected={view.death}
            onSelect={(o) => setView({ death: o })}
          />
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
}

/**
 * ตำแหน่งของทุกคน ณ วินาที t — เลื่อนระหว่างสองเฟรมที่บันทึกไว้ให้เดินลื่น
 * (ช่วงระหว่างวินาทีเป็นการวาดประมาณ ไม่ใช่ข้อมูลจากเดโม — มีหมายเหตุกำกับใต้แผนที่)
 */
function playersAt(pos: RoundPositions, t: number, roster: Map<string, { name: string; color: string }>): LivePlayer[] {
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
  overlay: GridOverlay | undefined;
  showCells: boolean;
  showHotspots: boolean;
  grenades: ReviewGrenade[];
  live?: LivePlayer[] | null; // โหมดเล่นย้อน: คนที่ยังไม่ตาย ณ วินาทีที่ดู (null = ปิดโหมด)
  zoom: number;
  center: [number, number] | null;
  onView: (zoom: number, center: [number, number] | null) => void;
  highlight: string | null; // steamid ที่ถูกกดในรายชื่อ
  selected: number | null; // ลำดับการตายที่ถูกเลือก
  onSelect: (order: number | null) => void;
}

/**
 * แผนที่ของรอบ — วาดเป็น SVG ในพิกัด "พิกเซลของภาพเรดาร์" ที่ backend แปลงมาให้แล้ว (backend/review.py)
 * frontend ไม่มีสูตรแปลงพิกัดของตัวเอง จุดบนจอจึงตรงกับช่องที่ grid_ml1 ใช้เสมอ
 * มีจุดตอนตาย (ชื่อคนตายใต้วง) + ระเบิด (วงที่จุดตก ชื่อคนขว้าง เส้นประจากจุดขว้าง)
 * โหมดเล่นย้อน (prop live) เพิ่มตัวผู้เล่น ณ วินาทีที่ดู — ไม่มีเส้นทางเดินย้อนหลัง
 * เลือกการตายแล้ว ระเบิดที่แสดงเหลือเฉพาะลูกที่มีผลอยู่ ณ วินาทีนั้น (ควัน/ไฟที่ยังไม่หมด แฟลช/HE ที่เพิ่งแตก)
 */
export function MapView({ radar, deaths, bomb, overlay, showCells, showHotspots, grenades, live, zoom, center, onView, highlight, selected, onSelect }: MapProps) {
  const s = radar.size;
  // ---- ซูม/เลื่อนดู: viewBox คือกรอบที่มองอยู่ · เก็บบน URL เพื่อให้รีเฟรช/แชร์ลิงก์แล้วเห็นกรอบเดิม
  const span = s / zoom;
  const clampC = (v: number) => Math.min(s - span / 2, Math.max(span / 2, v));
  const cx = clampC(center?.[0] ?? s / 2);
  const cy = clampC(center?.[1] ?? s / 2);
  const x0 = cx - span / 2;
  const y0 = cy - span / 2;
  const drag = useRef<{ x: number; y: number; cx: number; cy: number; moved: number } | null>(null);

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
    nade: 6 * U, nadeName: 12 * U, line: 2 * U, hs: 14 * U, bomb: 10 * U,
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
  nades.forEach((n) => n.r_px === 0 && block(n.land_px![0], n.land_px![1], z.nade));
  live?.forEach((p) => block(p.px[0], p.px[1], z.dot * 0.8));
  const deathLabel = new Map<number, LabelPos>();
  deaths.forEach((d) => {
    if (d.victim_px) deathLabel.set(d.order, place(d.victim_px[0], d.victim_px[1], dotR(d), d.victim.name, z.name));
  });
  // โหมดเล่นย้อน: ชื่อคนวางทีหลังจุดตาย เพราะจุดตายมีเลขกำกับอยู่แล้ว ชื่อคนเป็นตัวที่ขยับหนีได้
  const liveLabel = live?.map((p) => place(p.px[0], p.px[1], z.dot * 0.8, p.name, z.name * 0.92)) ?? [];
  const nadeLabelPos = nades.map((n) =>
    place(n.land_px![0], n.land_px![1], n.r_px > 0 ? n.r_px : z.nade, `${n.thrower?.name ?? "?"} · ${nadeLabel(n.type)}`, z.nadeName),
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

      {showCells &&
        overlay?.cells?.map((c) => (
          <rect
            key={`${c.cx}-${c.cy}`}
            x={c.x}
            y={c.y}
            width={c.w}
            height={c.w}
            fill={clusterColor(c.cluster_id)}
            opacity={0.42}
            data-testid="overlay-cell"
          >
            <title>{`ช่อง (${c.cx}, ${c.cy}) · type ${c.cluster_id}`}</title>
          </rect>
        ))}

      {showHotspots &&
        overlay?.hotspots?.map((h) => (
          <g key={h.id} data-testid="overlay-hotspot">
            <circle cx={h.px} cy={h.py} r={h.r} fill="none" stroke="#ffffff" strokeWidth={z.line * 1.4}
              strokeDasharray={`${8 * U} ${6 * U}`} opacity={0.85} />
            <text x={h.px} y={h.py - h.r - 4 * U} textAnchor="middle" className="hs-label" style={halo(z.hs)}>
              #{h.id}
            </text>
          </g>
        ))}

      {bomb?.px && (
        <g transform={`translate(${bomb.px[0]}, ${bomb.px[1]})`} data-testid="bomb-icon">
          <rect x={-z.bomb} y={-z.bomb} width={2 * z.bomb} height={2 * z.bomb} rx={z.bomb * 0.35} fill="#dc2626" stroke="#fff" strokeWidth={z.line} />
          <text textAnchor="middle" dy={z.bomb * 0.38} className="bomb-label" style={{ fontSize: z.bomb * 1.05 }}>
            C4
          </text>
          <title>{`วางบอมบ์${bomb.site ? ` (${bomb.site})` : ""}`}</title>
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
            <circle cx={x} cy={y} r={n.r_px > 0 ? n.r_px : z.nade} fill={c} fillOpacity={n.r_px > 0 ? 0.4 : 0.95}
              stroke={c} strokeWidth={z.line} />
            <text x={nadeLabelPos[i].x} y={nadeLabelPos[i].y} textAnchor={nadeLabelPos[i].anchor} className="nade-label"
              style={{ ...halo(z.nadeName), fill: n.thrower?.color ?? c }}>
              {who} · {nadeLabel(n.type)}
            </text>
            <title>{`${fmtT(n.t_land)} ${who} (${sideLabel(n.thrower?.side)}) ขว้าง${nadeLabel(n.type)}${
              n.t_end != null && n.t_end > (n.t_land ?? 0) ? ` · มีผลถึง ${fmtT(n.t_end)}` : ""}`}</title>
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

      {/* โหมดเล่นย้อน: ตัวผู้เล่นที่ยังไม่ตาย ณ วินาทีนั้น — วงในสีของคน ขอบสีตามฝั่ง */}
      {live?.map((p, i) => (
        <g key={`live-${p.steamid}`} opacity={!highlight || highlight === p.steamid ? 1 : 0.3} data-testid="live-player">
          <circle cx={p.px[0]} cy={p.px[1]} r={z.dot * 0.8} fill={p.color}
            stroke={p.side === "ct" ? "#58a6ff" : "#ff9d2e"} strokeWidth={z.line * 1.4} />
          <text x={liveLabel[i].x} y={liveLabel[i].y} textAnchor={liveLabel[i].anchor} className="dot-name" style={halo(z.name * 0.92)}>
            {p.name}
          </text>
          <title>{`${p.name} · ${p.hp} HP${p.place ? ` · ${p.place}` : ""}`}</title>
        </g>
      ))}

      {/* จุดตาย: สีตามคนตาย มีเลขลำดับ ชื่อคนตายข้างวง */}
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
            >
              <circle r={dotR(d)} fill={d.victim.color} stroke={selected === d.order ? "#fff" : "#0b1220"} strokeWidth={z.line * 1.3} />
              <text textAnchor="middle" dy={z.num * 0.36} className="death-num" style={{ fontSize: z.num }}>
                {d.order}
              </text>
              <text x={deathLabel.get(d.order)!.x - d.victim_px[0]} y={deathLabel.get(d.order)!.y - d.victim_px[1]}
                textAnchor={deathLabel.get(d.order)!.anchor} className="dot-name" style={halo(z.name)}>
                {d.victim.name}
              </text>
              <title>{`${d.order}. ${fmtT(d.t_round)} ${d.victim.name} ตาย · ${weaponLabel(d.weapon)}${d.attacker ? ` · โดย ${d.attacker.name}` : ""}`}</title>
            </g>
          ),
      )}
    </svg>
  );
}

// ================================================================================================
// รายชื่อสองทีม
// ================================================================================================
interface RosterProps {
  teams: ReviewTeam[];
  highlight: string | null;
  onHighlight: (steamid: string | null) => void;
}

/** สองกล่องแยกตามทีม (ชื่อทีมคงที่ทั้งแมตช์) — หัวกล่องบอกว่ารอบนี้ทีมนั้นเล่นฝั่งไหน */
export function TeamRoster({ teams, highlight, onHighlight }: RosterProps) {
  return (
    <div className="roster" data-testid="team-roster">
      {teams.map((t) => (
        <div className="team-box" key={t.clan}>
          <div className="team-head">
            <b>{t.clan}</b>
            <span className={`badge b-${t.side_this_round}`}>{sideLabel(t.side_this_round)}</span>
            <span className="muted small">รอบนี้</span>
          </div>
          <ul>
            {t.players.map((p) => (
              <li key={p.steamid} className={highlight === p.steamid ? "on" : highlight ? "dim" : ""}>
                <button
                  type="button"
                  className="pname"
                  onClick={() => onHighlight(highlight === p.steamid ? null : p.steamid)}
                  title="กดเพื่อไฮไลต์เฉพาะเหตุการณ์ของคนนี้"
                >
                  <span className="pdot" style={{ background: p.color }} />
                  {p.name}
                  {p.kills > 0 && <span className="kills">{p.kills} คิล</span>}
                </button>
                <div className="pstat">
                  {p.survived ? (
                    <span className="alive">รอดถึงจบรอบ</span>
                  ) : (
                    <>
                      ตาย {fmtT(p.died_at_t)} · {weaponLabel(p.weapon)}
                      {p.killed_by ? ` · โดย ${p.killed_by}` : ""}
                      {p.death_order ? <span className="muted"> (#{p.death_order})</span> : null}
                    </>
                  )}
                </div>
              </li>
            ))}
          </ul>
        </div>
      ))}
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

  return (
    <ol className="timeline-list" data-testid="death-timeline">
      {items.map((it) =>
        it.kind === "bomb" ? (
          <li key="bomb" className="tl-bomb">
            <span className="tl-t">{fmtT(it.t)}</span> วางบอมบ์
          </li>
        ) : it.kind === "nade" ? (
          <li key={`n${it.i}`} className={`tl-nade ${!highlight || it.n.thrower?.steamid === highlight ? "" : "dim"}`}>
            <span className="nade-dot" style={{ background: NADE_COLOR[it.n.type] }} />
            <span className="tl-t">{fmtT(it.t)}</span>
            <span className="tl-text">
              {it.n.thrower ? <Who p={it.n.thrower} /> : "?"} ขว้าง{nadeLabel(it.n.type)}
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
                <>
                  <Who p={it.d.attacker} /> ฆ่า <Who p={it.d.victim} />
                </>
              ) : it.d.team_kill && it.d.attacker ? (
                <>
                  <Who p={it.d.attacker} /> ยิงเพื่อนร่วมทีม <Who p={it.d.victim} />
                </>
              ) : (
                <>
                  <Who p={it.d.victim} /> ตาย
                </>
              )}
              <span className="tl-meta">
                {" · "}
                {weaponLabel(it.d.weapon)}
                {it.d.headshot && " · HS"}
                {it.d.distance != null && ` · ระยะ ${it.d.distance}u`}
                {it.d.place && ` · ${it.d.place}`}
                {it.d.attacker_blind && " · คนยิงโดนแฟลช"}
                {it.d.thru_smoke && " · ยิงผ่านควัน"}
                {it.d.penetrated > 0 && " · ทะลุกำแพง"}
                {it.d.noscope && " · noscope"}
                {it.d.assister && ` · ช่วย: ${it.d.assister}`}
              </span>
            </span>
          </li>
        ),
      )}
      {deaths.length === 0 && <li className="muted">ไม่มีใครตายในรอบนี้</li>}
    </ol>
  );
}

// ================================================================================================
// บริบทของการตาย (grid_ml1) + สรุปรอบ
// ================================================================================================
interface ContextProps {
  deaths: ReviewDeath[];
  grid: RoundDetail["grid"];
  highlight: string | null;
  selected: number | null;
  onSelect: (order: number | null) => void;
}

/**
 * บริบทของการตายแต่ละครั้ง จากผล research/models/grid_ml1.py
 * ตัวเลขทุกตัวมาจากทั้งดาต้าเซ็ต (ทุกแมตช์รวมกัน) ไม่ใช่จากรอบหรือแมตช์นี้
 * ct_win = สัดส่วนที่ฝั่ง CT เป็นฝ่ายชนะการดวลในพื้นที่นั้น
 */
export function DeathContext({ deaths, grid, highlight, selected, onSelect }: ContextProps) {
  return (
    <section className="ctx" data-testid="death-context">
      <h3 className="panel-h">บริบทของแต่ละการตาย</h3>
      {grid ? (
        <p className="ctx-source">
          ตัวเลขในส่วนนี้มาจาก <b>{grid.source.label}</b> ไม่ใช่สถิติของแมตช์นี้ · "CT ชนะดวล" คือสัดส่วนที่ CT
          เป็นฝ่ายชนะการดวลในพื้นที่นั้น
        </p>
      ) : (
        <p className="muted">ยังไม่มีผล grid_ml1 ของแมพนี้ — แสดงบริบทไม่ได้</p>
      )}
      <ul className="ctx-list">
        {deaths.map((d) => {
          const dim = highlight && d.victim.steamid !== highlight && d.attacker?.steamid !== highlight;
          return (
            <li
              key={d.order}
              className={`${selected === d.order ? "sel" : ""} ${dim ? "dim" : ""}`}
              {...pressable(() => onSelect(selected === d.order ? null : d.order))}
              data-testid="context-item"
            >
              <div className="ctx-head">
                <span className="tl-num" style={{ background: d.victim.color }}>
                  {d.order}
                </span>
                <b>{d.victim.name}</b> <span className="muted">({sideLabel(d.victim.side)}) · {fmtT(d.t_round)}</span>
                {d.disadvantaged && (
                  <span className="tag-warn">ช่องที่ฝั่งตรงข้ามชนะดวล {pct(d.enemy_win)}</span>
                )}
              </div>
              <ContextText d={d} grid={grid} />
            </li>
          );
        })}
      </ul>
    </section>
  );
}

function ContextText({ d, grid }: { d: ReviewDeath; grid: RoundDetail["grid"] }) {
  if (d.reason === "no_model" || !grid) return <p className="muted small">ยังไม่มีผล grid_ml1 ของแมพนี้</p>;
  if (d.reason === "no_position") return <p className="muted small">ไม่มีพิกัดของการตายครั้งนี้</p>;
  if (d.reason === "insufficient" || !d.cell)
    return (
      <p className="muted small">
        พื้นที่นี้มีข้อมูลไม่พอสรุป — ในดาต้าเซ็ตมีการดวลในช่องนี้น้อยกว่า {grid.min_kills} ครั้ง จึงไม่แสดงตัวเลข
      </p>
    );
  const c = d.cell;
  return (
    <div className="small">
      {!d.is_duel && (
        <p className="muted">ครั้งนี้ไม่ใช่การดวล (ตายจาก C4 / ตกที่สูง / เพื่อนร่วมทีม) ตัวเลขด้านล่างเป็นของการดวลในพื้นที่นี้</p>
      )}
      <p>
        {d.victim.name} ตายในช่องประเภท{" "}
        <span className="ctype">
          <i style={{ background: clusterColor(c.cluster_id) }} />
          type {c.cluster_id}: {c.cluster_name}
        </span>{" "}
        ซึ่งทั้งดาต้าเซ็ต {grid.source.matches} แมตช์ CT ชนะดวลในกลุ่มนี้ <b>{pct(c.ct_win)}</b> (เฉลี่ยทั้งแมพ{" "}
        {pct(grid.ct_win_overall)})
      </p>
      {d.hotspot ? (
        <p>
          อยู่ใน hotspot #{d.hotspot.id} ({d.hotspot.place}) คิดเป็น {pct(d.hotspot.share)} ของการดวลทั้งหมด
        </p>
      ) : (
        <p className="muted">ไม่อยู่ใน hotspot ใดใน {grid.source.matches} แมตช์</p>
      )}
    </div>
  );
}

/** สรุปรอบ: ใครตายคนแรก / ฝั่งที่เสียคนแรกแพ้ไหม / ตายในช่องที่ฝั่งตรงข้ามชนะดวลกี่คน */
export function RoundSummary({ summary, winner, grid }: { summary: RoundDetail["summary"]; winner: RoundDetail["round"]["winner_side"]; grid: RoundDetail["grid"] }) {
  const f = summary.first_death;
  return (
    <section className="summary" data-testid="round-summary">
      <h3 className="panel-h">สรุปรอบ</h3>
      {f ? (
        <p>
          ตายคนแรก: <b>{f.name}</b> ({sideLabel(f.side)}) ที่ {f.place ?? "—"} วินาทีที่ {fmtT(f.t_round)}
          {f.by ? ` โดย ${f.by}` : ""}
        </p>
      ) : (
        <p className="muted">รอบนี้ไม่มีใครตาย</p>
      )}
      {summary.first_death_side_lost !== null && f && (
        <p>
          ฝั่ง {sideLabel(f.side)} เสียคนแรก และ{summary.first_death_side_lost ? "แพ้" : "ชนะ"}รอบนี้ (ผู้ชนะ {sideLabel(winner)})
        </p>
      )}
      {grid ? (
        <p>
          ตายในช่องที่ฝั่งตรงข้ามชนะดวลเกินครึ่ง (ตามดาต้าเซ็ต {grid.source.matches} แมตช์): CT{" "}
          <b>{summary.disadvantaged_deaths.ct}</b> คน · T <b>{summary.disadvantaged_deaths.t}</b> คน
          <span className="muted"> · มีบริบท {summary.deaths_with_context} จาก {summary.duel_deaths} การดวล</span>
        </p>
      ) : null}
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

