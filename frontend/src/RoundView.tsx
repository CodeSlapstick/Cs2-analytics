import { type KeyboardEvent, useEffect, useLayoutEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  api,
  ApiError,
  type GridOverlay,
  type ReviewDeath,
  type ReviewGrenade,
  type ReviewPerson,
  type ReviewTeam,
  type RoundDetail,
  type RoundPositions,
} from "./api";
import {
  ADV_ALPHA,
  ADV_STEPS,
  advantageLevel,
  AVOID_FILL,
  AVOID_STEP,
  clampZoom,
  endReasonLabel,
  fmtT,
  FREQ_ALPHA,
  FREQ_FILL,
  freqBands,
  type FreqBreaks,
  freqBreaks,
  freqLevel,
  type GridLayer,
  MAX_ZOOM,
  NADE_COLOR,
  nadeActiveAt,
  nadeLabel,
  NADE_TYPES,
  type NadeType,
  NotFound,
  pct,
  playerNumbers,
  SCREEN,
  SIDE_FILL,
  sideFill,
  sideLabel,
  type ViewState,
  weaponLabel,
} from "./utils";

/** แถวที่กดได้ (li ในไทม์ไลน์) — คลิก หรือ Enter / Space จากคีย์บอร์ด */
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

/** ความเร็วที่เลือกได้ในโหมดเล่นย้อน */
const SPEEDS = [1, 2, 4] as const;
type Speed = (typeof SPEEDS)[number];

/**
 * เนื้อหาของหนึ่งรอบ — ซ้าย: ชั้นข้อมูล / แผนที่ / key / แถบเล่นย้อน · ขวา: สองทีม (เลข 1–5) + ไทม์ไลน์
 * state ทั้งหมดมาจาก URL · คนแต่ละคนแยกกันด้วย "สีฝั่ง + เลข" ไม่ใช่สีรายคน
 */
export function RoundView({ demo, roundNum, view, setView }: RoundViewProps) {
  // โหมดเล่นย้อน: เวลาที่กำลังเล่นอยู่เก็บใน state (เปลี่ยนทุกเฟรม) แล้วเขียนลง URL ตอนหยุดเท่านั้น
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState<Speed>(1);
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
  // ขอบของสี่ขั้นความถี่ คิดจากช่องของแมพนี้เอง (192 ช่องบน Mirage) ไม่ใช่เลขที่ตั้งไว้ตายตัว
  const breaks: FreqBreaks | null = overlay?.cells ? freqBreaks(overlay.cells.map((c) => c.duels)) : null;
  const numbers = playerNumbers(d.teams);
  const shownNades = d.grenades.filter((g) => view.nades.includes(g.type as NadeType));
  const anyNadeOn = shownNades.length > 0;
  // เล่นย้อน: แผนที่ต้องเห็นเฉพาะสิ่งที่เกิดขึ้นแล้ว ณ วินาทีนั้น (คนที่ตายแล้ว / ระเบิดที่ยังมีผล / บอมบ์ที่วางแล้ว)
  const pos = positions.data;
  const live = view.playback && pos ? playersAt(pos, time, d.teams) : null;
  // บางรอบในเดโมมีการตายที่บันทึกไว้ก่อนรอบเริ่ม (t_round ติดลบ — ส่วนใหญ่คือตกที่สูงตอนสลับรอบ)
  // โหมดเล่นย้อนนับเฉพาะการตายที่อยู่ในช่วงเวลาของรอบจริง ไม่งั้นคนคนเดียวจะโผล่ทั้งแบบยังไม่ตายและตายแล้วพร้อมกัน
  // (การตายเหล่านั้นยังอยู่ครบในแผนที่ปกติและในไทม์ไลน์ ไม่ได้ถูกซ่อนจากผู้ใช้)
  const shownDeaths = live ? d.deaths.filter((x) => x.t_round != null && x.t_round >= 0 && x.t_round <= time) : d.deaths;
  const liveNades = live ? shownNades.filter((n) => nadeActiveAt(n, time)) : shownNades;
  const plantT = d.round.bomb_planted_t;
  const shownBomb = live && plantT != null && time < plantT ? null : d.round.bomb;

  // กด ▶ ครั้งแรก = เปิดโหมดเล่นย้อน (โหลดตำแหน่ง) แล้วเล่นทันทีเมื่อโหลดเสร็จ — ไม่ต้องกดสองที
  const togglePlay = () => {
    if (!view.playback) setView({ playback: true, time: 0 });
    setPlaying((p) => !p);
  };
  const exitPlayback = () => {
    setPlaying(false);
    setTime(0);
    setView({ playback: false, time: null });
  };
  const pbReady = view.playback && !positions.isLoading && !positions.error && endT > 0;

  return (
    <div className="review" data-testid="round-view">
      <div className="review-head">
        <h2>
          รอบ <span className="num">{d.round.num}</span>
        </h2>
        {d.round.winner_side && <span className={`side-tag ${d.round.winner_side}`}>{sideLabel(d.round.winner_side)} ชนะ</span>}
        <span className="muted">
          {endReasonLabel(d.round.end_reason)}
          {plantT != null && ` · วางบอมบ์ ${fmtT(plantT)}`} · ตาย {d.deaths.length} คน
        </span>
      </div>

      {/* หน้าจอ laptop / projector: สองคอลัมน์ในความสูงจอเดียว แผนที่เป็นจัตุรัสเท่าที่ช่องให้ได้ (styles.css) */}
      <div className="review-grid">
        <section className="map-col" aria-label="แผนที่ของรอบ">
          <LayerBar view={view} setView={setView} overlay={overlay} grenades={d.grenades} />
          <div className="map-stage">
            {d.radar ? (
              <MapView
                radar={d.radar}
                deaths={shownDeaths}
                bomb={shownBomb}
                overlay={overlay}
                layer={view.grid}
                breaks={breaks}
                showHotspots={view.hotspots}
                grenades={liveNades}
                live={live}
                numbers={numbers}
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
          <MapKey layer={view.grid} breaks={breaks} nades={view.nades} anyNade={anyNadeOn} hotspots={view.hotspots} overlay={overlay} playback={!!live} />

          <div className="playbar" data-testid="playbar">
            <button
              type="button"
              className="pb-play"
              onClick={togglePlay}
              disabled={view.playback && !pbReady}
              aria-label={playing ? "หยุด" : "เล่นย้อน"}
              aria-pressed={playing}
              title="เว้นวรรค = เล่น/หยุด · , . = ถอย/เดินหน้าทีละวินาที"
            >
              {playing ? <IconPause /> : <IconPlay />}
            </button>
            <input
              className="pb-range"
              type="range"
              min={0}
              max={Math.max(endT, 1)}
              step={0.1}
              value={Math.min(time, endT)}
              disabled={!pbReady}
              onChange={(e) => {
                setPlaying(false);
                setTime(Number(e.target.value));
              }}
              aria-label="เลื่อนเวลาในรอบ"
            />
            <span className="pb-clock num">
              {fmtT(time)} / {fmtT(endT)}
            </span>
            {SPEEDS.map((sp) => (
              <button key={sp} type="button" className={`pb-speed num${speed === sp ? " on" : ""}`}
                aria-pressed={speed === sp} disabled={!view.playback} onClick={() => setSpeed(sp)}>
                {sp}×
              </button>
            ))}
            <span className="pb-status muted small">
              {!view.playback ? (
                "กดเล่นเพื่อดูว่าใครเดินไปทางไหนตามเวลา"
              ) : positions.isLoading ? (
                "กำลังโหลดตำแหน่งผู้เล่น…"
              ) : positions.error ? (
                <span className="err">โหลดตำแหน่งไม่ได้: {(positions.error as Error).message}</span>
              ) : endT <= 0 ? (
                "รอบนี้ไม่มีตำแหน่งผู้เล่นที่บันทึกไว้"
              ) : (
                pos?.note
              )}
            </span>
            {view.playback && (
              <button type="button" className="link-btn" onClick={exitPlayback}>
                ปิดโหมดเล่นย้อน
              </button>
            )}
          </div>
        </section>

        <aside className="side-col" aria-label="รายชื่อทีมและไทม์ไลน์">
          <TeamRoster teams={d.teams} numbers={numbers} highlight={view.player} onHighlight={(p) => setView({ player: p })} />
          <h3 className="panel-h">ไทม์ไลน์</h3>
          <DeathTimeline
            deaths={d.deaths}
            numbers={numbers}
            highlight={view.player}
            selected={view.death}
            onSelect={(o) => setView({ death: o })}
            bombPlantedT={plantT}
            grenades={shownNades}
          />
        </aside>
      </div>
    </div>
  );
}

// ================================================================================================
// แถวชั้นข้อมูลเหนือแผนที่: พื้นที่ได้เปรียบ (เลือกฝั่ง) · ระเบิด · จุดที่ดวลกันบ่อย · ซูม
// ================================================================================================
interface LayerBarProps {
  view: ViewState;
  setView: (patch: Partial<ViewState>) => void;
  overlay: GridOverlay | undefined;
  grenades: ReviewGrenade[];
}

/** สี่ตัวเลือกของการระบายกริด — ระบายได้ทีละอย่างเพราะหนึ่งช่องมีได้สีเดียว */
const GRID_LAYERS: { key: GridLayer; label: string; hint: string }[] = [
  { key: "off", label: "ปิด", hint: "เห็นแผนที่เปล่า ๆ" },
  { key: "freq", label: "ดวลบ่อย", hint: "ยิ่งสว่าง = ตรงนั้นดวลกันบ่อย (ทั้งดาต้าเซ็ต)" },
  { key: "ct", label: "CT ได้เปรียบ", hint: "ระบายช่องที่ฝั่ง CT ชนะดวลบ่อย และช่องที่ T ชนะบ่อยเป็นสีแดง" },
  { key: "t", label: "T ได้เปรียบ", hint: "ระบายช่องที่ฝั่ง T ชนะดวลบ่อย และช่องที่ CT ชนะบ่อยเป็นสีแดง" },
];

function LayerBar({ view, setView, overlay, grenades }: LayerBarProps) {
  const noModel = !overlay;
  return (
    <div className="layers" data-testid="layer-bar">
      <div className="seg" role="group" aria-label="ระบายกริดด้วย">
        <span className="seg-h">ระบายกริดด้วย</span>
        {GRID_LAYERS.map(({ key, label, hint }) => (
          <button
            key={key}
            type="button"
            className={`seg-btn${key === "ct" || key === "t" ? ` ${key}` : ""}${key === "freq" ? " freq" : ""}${
              view.grid === key ? " on" : ""
            }`}
            aria-pressed={view.grid === key}
            disabled={noModel && key !== "off"}
            title={noModel ? "ยังไม่มีข้อมูลการดวลของแมพนี้" : hint}
            onClick={() => setView({ grid: key })}
            data-testid={`grid-${key}`}
          >
            {label}
          </button>
        ))}
      </div>

      <div className="seg" role="group" aria-label="ระเบิด">
        <span className="seg-h">ระเบิด</span>
        {NADE_TYPES.map((t) => {
          const n = grenades.filter((g) => g.type === t).length;
          const on = n > 0 && view.nades.includes(t); // รอบนี้ไม่มีชนิดนี้เลย = ปุ่มดับไว้ ไม่นับว่าเปิดอยู่
          return (
            <label key={t} className={`nade-toggle${on ? " on" : ""}`} title={`${nadeLabel(t)} ${n} ลูกในรอบนี้`}>
              <input
                type="checkbox"
                checked={on}
                disabled={n === 0}
                onChange={(e) => setView({ nades: e.target.checked ? [...view.nades, t] : view.nades.filter((x) => x !== t) })}
              />
              <i style={{ background: NADE_COLOR[t] }} />
              {nadeLabel(t)} <span className="num">{n}</span>
            </label>
          );
        })}
      </div>

      <label className="seg-check" title={noModel ? "ยังไม่มีข้อมูลการดวลของแมพนี้" : "วงที่โมเดลหาเจอเองว่าคนมักปะทะกันตรงนี้"}>
        <input type="checkbox" checked={view.hotspots} disabled={noModel} onChange={(e) => setView({ hotspots: e.target.checked })} />
        วงจุดปะทะ{overlay?.hotspots ? <span className="num"> {overlay.hotspots.length}</span> : null}
      </label>

      <div className="zoom" role="group" aria-label="ซูมแผนที่">
        <button type="button" onClick={() => setView({ zoom: clampZoom(view.zoom * 1.4), center: view.center })}
          disabled={view.zoom >= MAX_ZOOM} aria-label="ซูมเข้า" title="ซูมเข้า (หรือหมุนล้อเมาส์บนแผนที่)">+</button>
        <button type="button" onClick={() => {
          const next = clampZoom(view.zoom / 1.4);
          setView(next <= 1.01 ? { zoom: 1, center: null } : { zoom: next, center: view.center });
        }} disabled={view.zoom <= 1} aria-label="ซูมออก" title="ซูมออก">−</button>
        {view.zoom > 1 && (
          <button type="button" className="link-btn" onClick={() => setView({ zoom: 1, center: null })}>
            เต็มแมพ <span className="num">{view.zoom.toFixed(1)}×</span>
          </button>
        )}
      </div>
    </div>
  );
}

// ================================================================================================
// key ใต้แผนที่ — ทุกสัญลักษณ์ที่วาดอยู่บนแผนที่ต้องมีคำอธิบายที่นี่ (แสดงเฉพาะชั้นที่เปิดอยู่)
// ================================================================================================
interface KeyProps {
  layer: GridLayer;
  breaks: FreqBreaks | null;
  nades: NadeType[];
  anyNade: boolean;
  hotspots: boolean;
  overlay: GridOverlay | undefined;
  playback: boolean;
}

function MapKey({ layer, breaks, nades, anyNade, hotspots, overlay, playback }: KeyProps) {
  const adv = layer === "ct" || layer === "t" ? layer : null;
  const shownNades = NADE_TYPES.filter((t) => nades.includes(t));
  return (
    <ul className="map-key" aria-label="คำอธิบายสัญลักษณ์บนแผนที่" data-testid="map-key">
      <li>
        <span className="ks live" style={{ background: SIDE_FILL.ct }}>1</span>
        <span className="ks live" style={{ background: SIDE_FILL.t }}>1</span>
        เลข = ผู้เล่น (ฟ้า CT · ส้ม T){playback && " · วงทึบ = อยู่ตรงนี้ ณ วินาทีที่ดู"}
      </li>
      <li>
        <span className="ks dead" style={{ borderColor: SIDE_FILL.ct, color: SIDE_FILL.ct }}>3</span>
        วงกลวง = จุดที่ตาย · เส้นจากจุดเล็ก = ยิงมาจากไหน
      </li>
      <li>
        <span className="ks bomb">C4</span>
        บอมบ์
      </li>
      {anyNade && shownNades.length > 0 && (
        <li>
          {shownNades.map((t) => (
            <span key={t} className="key-nade">
              <span className="ks nade" style={{ background: NADE_COLOR[t] }} />
              {nadeLabel(t)}
            </span>
          ))}
          (เลขข้างวง = คนขว้าง · เส้นประ = ทางที่ขว้าง)
        </li>
      )}
      {hotspots && overlay?.hotspots && (
        <li>
          <span className="ks hs" />
          วงประ = จุดปะทะที่โมเดลหาเจอ {overlay.hotspots.length} จุด
        </li>
      )}
      {layer === "freq" && breaks && overlay && (
        <li className="key-adv" data-testid="key-freq">
          จำนวนการดวลในช่องนั้น ยิ่งเข้มยิ่งดวลบ่อย —
          {freqBands(breaks).map((b) => (
            <span key={b.level} className="key-band">
              <span className="ks adv" style={{ background: FREQ_FILL[b.level], opacity: FREQ_ALPHA + b.level * 0.06 }} />
              {b.label}
            </span>
          ))}
          ครั้ง<span className="muted"> — {overlay.source?.label} ไม่ใช่ผลของรอบนี้</span>
        </li>
      )}
      {adv && overlay && (
        <li className="key-adv" data-testid="key-adv">
          <span className="ks adv" style={{ background: SIDE_FILL[adv], opacity: ADV_ALPHA[1] }} />
          <span className="ks adv" style={{ background: SIDE_FILL[adv], opacity: ADV_ALPHA[2] }} />
          <span className="ks adv" style={{ background: SIDE_FILL[adv], opacity: ADV_ALPHA[3] }} />
          ฝั่ง {sideLabel(adv)} ชนะดวล ≥ {pct(ADV_STEPS[1])} / {pct(ADV_STEPS[2])} / {pct(ADV_STEPS[3])} (ยิ่งเข้มยิ่งบ่อย)
          <span className="ks adv avoid" style={{ background: AVOID_FILL }} />
          ฝั่งตรงข้ามชนะ ≥ {pct(AVOID_STEP)}
          <span className="muted"> — {overlay.source?.label} ไม่ใช่ผลของรอบนี้</span>
        </li>
      )}
    </ul>
  );
}

// ================================================================================================
// โหมดเล่นย้อน: ตำแหน่ง ณ วินาที t
// ================================================================================================
/** ผู้เล่นหนึ่งคนบนแผนที่ ณ วินาทีที่กำลังดู */
export interface LivePlayer {
  steamid: string;
  px: [number, number];
  hp: number;
  side: string | null;
  place: string | null;
  name: string;
}

/**
 * ตำแหน่งของทุกคน ณ วินาที t — เลื่อนระหว่างสองเฟรมที่บันทึกไว้ให้เดินลื่น
 * (ช่วงระหว่างวินาทีเป็นการวาดประมาณ ไม่ใช่ข้อมูลจากเดโม — มีหมายเหตุกำกับใต้แผนที่)
 */
function playersAt(pos: RoundPositions, t: number, teams: ReviewTeam[]): LivePlayer[] {
  if (pos.frames.length === 0) return [];
  const names = new Map(teams.flatMap((tm) => tm.players.map((p) => [p.steamid, p.name] as const)));
  const i = Math.max(0, Math.min(pos.frames.length - 1, Math.floor(t / pos.step)));
  const cur = pos.frames[i];
  const next = pos.frames[i + 1];
  const frac = next ? Math.max(0, Math.min(1, (t - cur.t) / (next.t - cur.t))) : 0;
  return cur.players.map((p) => {
    const to = next?.players.find((n) => n.steamid === p.steamid); // ไม่มีในเฟรมถัดไป = ตายแล้ว ไม่ต้องเลื่อน
    return {
      steamid: p.steamid,
      px: to ? ([p.px[0] + (to.px[0] - p.px[0]) * frac, p.px[1] + (to.px[1] - p.px[1]) * frac] as [number, number]) : p.px,
      hp: p.hp,
      side: p.side,
      place: p.place,
      name: names.get(p.steamid) ?? p.steamid,
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
 * วางป้ายไม่ให้ทับกัน และไม่ทับวงของคนอื่น — ลองใต้วง เหนือวง ขวา ซ้าย (แล้วถอยออกไปอีกขั้น)
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
  layer: GridLayer; // ระบายกริดด้วยอะไร: ปิด / ความถี่ / ความได้เปรียบของฝั่งนั้น
  breaks: FreqBreaks | null; // ขอบสี่ขั้นของชั้นความถี่
  showHotspots: boolean;
  grenades: ReviewGrenade[];
  live?: LivePlayer[] | null; // โหมดเล่นย้อน: คนที่ยังไม่ตาย ณ วินาทีที่ดู (null = ปิดโหมด)
  numbers: Map<string, number>; // steamid -> เลข 1–5
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
 * ทุกคนใช้สีฝั่ง + เลขประจำตัว: วงทึบ = ตัวผู้เล่น (เล่นย้อน) · วงกลวง = ตำแหน่งที่ตาย · จุดเล็ก + เส้น = คนยิง
 * ชื่อคนขึ้นเฉพาะคนที่ถูกเลือก/ไฮไลต์ (ชื่อทั้งหมดอยู่ในรายชื่อและไทม์ไลน์) — แผนที่จะได้ไม่รก
 */
export function MapView({ radar, deaths, bomb, overlay, layer, breaks, showHotspots, grenades, live, numbers, zoom, center, onView, highlight, selected, onSelect }: MapProps) {
  const adv = layer === "ct" || layer === "t" ? layer : null;
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
    const [mx, my] = toMap(clientX, clientY); // จุดใต้เมาส์ต้องอยู่ที่เดิมหลังซูม
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
    dot: 13 * U, dotSel: 16 * U, num: 13 * U, name: 13 * U, atk: 5 * U, atkName: 12 * U,
    nade: 6 * U, nadeNum: 11 * U, line: 2 * U, hs: 14 * U, bomb: 10 * U,
  };
  const halo = (size: number) => ({ fontSize: size, strokeWidth: size * 0.3 });
  const num = (steamid: string | undefined) => (steamid ? numbers.get(steamid) ?? "?" : "?");

  const selT = selected === null ? null : (deaths.find((d) => d.order === selected)?.t_round ?? null);
  // โหมดเล่นย้อนกรองตามเวลาที่กำลังดูมาแล้ว จึงไม่กรองซ้ำด้วยการตายที่เลือก
  const nades = grenades.filter((n) => n.land_px && (live ? true : selT === null || nadeActiveAt(n, selT)));
  const nadeFocus = (n: ReviewGrenade) => !highlight || n.thrower?.steamid === highlight;
  const dotR = (d: ReviewDeath) => (selected === d.order ? z.dotSel : z.dot);
  const involved = (d: ReviewDeath) => !highlight || d.victim.steamid === highlight || d.attacker?.steamid === highlight;
  const focus = (d: ReviewDeath) => (selected === null ? involved(d) : selected === d.order);
  // ชื่อบนแผนที่ขึ้นเฉพาะคนที่ถูกเลือกหรือไฮไลต์ — ที่เหลือใช้เลขอย่างเดียว
  const showName = (steamid: string, order?: number) => highlight === steamid || (order !== undefined && selected === order);

  const { place, block } = labelPlacer();
  // วงทุกวงเป็นสิ่งกีดขวางของป้าย (ควัน/ไฟเป็นวงโปร่ง ป้ายทับได้)
  deaths.forEach((d) => {
    if (d.victim_px) block(d.victim_px[0], d.victim_px[1], dotR(d));
    if (d.attacker_px) block(d.attacker_px[0], d.attacker_px[1], z.atk);
  });
  nades.forEach((n) => n.r_px === 0 && block(n.land_px![0], n.land_px![1], z.nade));
  live?.forEach((p) => block(p.px[0], p.px[1], z.dot * 0.85));
  const deathLabel = new Map<number, LabelPos>();
  deaths.forEach((d) => {
    if (d.victim_px && showName(d.victim.steamid, d.order))
      deathLabel.set(d.order, place(d.victim_px[0], d.victim_px[1], dotR(d), d.victim.name, z.name));
  });
  const liveLabel = new Map<string, LabelPos>();
  live?.forEach((p) => {
    if (showName(p.steamid)) liveLabel.set(p.steamid, place(p.px[0], p.px[1], z.dot * 0.85, p.name, z.name));
  });
  const nadeLabelPos = nades.map((n) =>
    place(n.land_px![0], n.land_px![1], n.r_px > 0 ? n.r_px : z.nade, String(num(n.thrower?.steamid)), z.nadeNum),
  );
  // ชื่อจุดปะทะวางท้ายสุด — เป็นชั้นรอง ต้องหลบชื่อคนกับเลขการตาย ไม่ใช่ให้ของสำคัญกว่าหลบมัน
  // จุดที่อยู่ริมแมพอาจถูกดันออกนอกกรอบที่มองอยู่ ดึงกลับเข้ามาไม่ให้ตัวหนังสือโดนตัดครึ่ง
  // ต้องคิดจาก "ขอบซ้ายจริงของข้อความ" ไม่ใช่จุดอ้างอิง เพราะป้ายที่จัดกึ่งกลางกินที่ไปทางซ้ายอีกครึ่งหนึ่ง
  const insideView = (p: LabelPos, text: string, size: number): LabelPos => {
    const w = text.length * size * 0.58 + 6;
    const m = 4 * U;
    const left = p.anchor === "start" ? p.x : p.anchor === "end" ? p.x - w : p.x - w / 2;
    if (left < x0 + m) return { x: x0 + m, y: p.y, anchor: "start" };
    if (left + w > x0 + span - m) return { x: x0 + span - m, y: p.y, anchor: "end" };
    return p;
  };
  const hotspotLabel = showHotspots
    ? (overlay?.hotspots ?? []).map((h) => insideView(place(h.px, h.py, h.r, h.place, z.hs), h.place, z.hs))
    : [];

  return (
    <svg
      ref={svgRef}
      viewBox={`${x0} ${y0} ${span} ${span}`}
      className={`radar${zoom > 1 ? " zoomed" : ""}`}
      data-testid="radar-svg"
      data-zoom={zoom.toFixed(2)}
      onClick={() => {
        if ((drag.current?.moved ?? 0) < 4) onSelect(null); // ลากแล้วไม่นับเป็นคลิกล้างการเลือก
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

      {/* ดวลบ่อยแค่ไหน: ไล่เฉดม่วงเฉดเดียว จาง = น้อย เข้ม = บ่อย (ลำดับอยู่ที่ความสว่าง ไม่ใช่ที่สี) */}
      {layer === "freq" &&
        breaks &&
        overlay?.cells?.map((c) => {
          const lv = freqLevel(c.duels, breaks);
          return (
            <rect
              key={`${c.cx}-${c.cy}`}
              x={c.x}
              y={c.y}
              width={c.w}
              height={c.w}
              fill={FREQ_FILL[lv]}
              opacity={FREQ_ALPHA + lv * 0.06}
              data-testid="overlay-cell"
              data-level={lv}
            >
              <title>{`ดวลกันในช่องนี้ ${c.duels} ครั้ง (ทั้งดาต้าเซ็ต)`}</title>
            </rect>
          );
        })}

      {/* พื้นที่ได้เปรียบของฝั่งที่เลือก: สีฝั่ง 3 ระดับ + แดงเฉพาะช่องที่ฝั่งตรงข้ามชนะบ่อย (ข้อมูลทั้งดาต้าเซ็ต) */}
      {adv &&
        overlay?.cells?.map((c) => {
          const lv = advantageLevel(c.ct_win, adv);
          if (lv === 0) return null;
          const w = adv === "ct" ? c.ct_win : 1 - c.ct_win;
          return (
            <rect
              key={`${c.cx}-${c.cy}`}
              x={c.x}
              y={c.y}
              width={c.w}
              height={c.w}
              fill={lv < 0 ? AVOID_FILL : SIDE_FILL[adv]}
              opacity={lv === -1 ? 0.55 : ADV_ALPHA[lv]}
              data-testid="overlay-cell"
              data-level={lv}
            >
              <title>{`ฝั่ง ${sideLabel(adv)} ชนะดวลในช่องนี้ ${pct(w)} (จาก ${c.duels} ดวลทั้งดาต้าเซ็ต)`}</title>
            </rect>
          );
        })}

      {showHotspots &&
        overlay?.hotspots?.map((h, i) => (
          <g key={h.id} data-testid="overlay-hotspot">
            <circle cx={h.px} cy={h.py} r={h.r} fill="none" stroke="#ffffff" strokeWidth={z.line * 1.2}
              strokeDasharray={`${8 * U} ${6 * U}`} opacity={0.8} />
            <text x={hotspotLabel[i].x} y={hotspotLabel[i].y} textAnchor={hotspotLabel[i].anchor} className="hs-label" style={halo(z.hs)}>
              {h.place}
            </text>
            <title>{`${h.place} · ${pct(h.share)} ของการดวลทั้งหมด (${h.duels} ดวล) · CT ชนะดวล ${pct(h.ct_win)}`}</title>
          </g>
        ))}

      {bomb?.px && (
        <g transform={`translate(${bomb.px[0]}, ${bomb.px[1]})`} data-testid="bomb-icon">
          <rect x={-z.bomb} y={-z.bomb} width={2 * z.bomb} height={2 * z.bomb} rx={z.bomb * 0.3} fill={AVOID_FILL} stroke="#fff" strokeWidth={z.line} />
          <text textAnchor="middle" dy={z.bomb * 0.38} className="bomb-label" style={{ fontSize: z.bomb * 1.05 }}>
            C4
          </text>
          <title>{`วางบอมบ์${bomb.site ? ` (${bomb.site})` : ""}`}</title>
        </g>
      )}

      {/* ระเบิด: วงที่จุดตก (ควัน/ไฟตามขนาดจริงโดยประมาณ) + เลขคนขว้าง + เส้นประจากจุดที่ขว้าง */}
      {nades.map((n, i) => {
        const [x, y] = n.land_px!;
        const c = NADE_COLOR[n.type] ?? "#fff";
        const who = n.thrower?.name ?? "?";
        const sc = sideFill(n.thrower?.side);
        return (
          <g key={`n${i}`} opacity={nadeFocus(n) ? 1 : 0.15} data-testid="nade">
            {n.throw_px && (
              <line x1={n.throw_px[0]} y1={n.throw_px[1]} x2={x} y2={y} stroke={sc}
                strokeWidth={z.line * 0.8} strokeDasharray={`${5 * U} ${5 * U}`} opacity={0.6} />
            )}
            <circle cx={x} cy={y} r={n.r_px > 0 ? n.r_px : z.nade} fill={c} fillOpacity={n.r_px > 0 ? 0.35 : 0.95}
              stroke={c} strokeWidth={z.line} />
            <text x={nadeLabelPos[i].x} y={nadeLabelPos[i].y} textAnchor={nadeLabelPos[i].anchor} className="map-num halo"
              style={{ ...halo(z.nadeNum), fill: sc }}>
              {num(n.thrower?.steamid)}
            </text>
            <title>{`${fmtT(n.t_land)} ${who} (${sideLabel(n.thrower?.side)}) ขว้าง${nadeLabel(n.type)}${
              n.t_end != null && n.t_end > (n.t_land ?? 0) ? ` · มีผลถึง ${fmtT(n.t_end)}` : ""}`}</title>
          </g>
        );
      })}

      {/* เส้นทิศทางการยิง: จากคนยิงไปคนตาย — สีตามฝั่งของคนยิง */}
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
              stroke={sideFill(d.attacker?.side)}
              strokeWidth={z.line * 1.2}
              opacity={focus(d) ? 0.85 : 0.1}
            />
          ),
      )}
      {deaths.map(
        (d) =>
          d.attacker_px && (
            <g key={`a${d.order}`} opacity={focus(d) ? 1 : 0.15}>
              <circle cx={d.attacker_px[0]} cy={d.attacker_px[1]} r={z.atk} fill={sideFill(d.attacker?.side)} stroke={SCREEN} strokeWidth={z.line * 0.8} />
              {d.attacker && (selected === d.order || (highlight && focus(d))) && (
                <text x={d.attacker_px[0]} y={d.attacker_px[1] - z.atk - 4 * U} textAnchor="middle" className="dot-name" style={halo(z.atkName)}>
                  {num(d.attacker.steamid)} {d.attacker.name}
                </text>
              )}
            </g>
          ),
      )}

      {/* โหมดเล่นย้อน: ตัวผู้เล่นที่ยังไม่ตาย ณ วินาทีนั้น — วงทึบสีฝั่ง เลขประจำตัวข้างใน */}
      {live?.map((p) => (
        <g key={`live-${p.steamid}`} opacity={!highlight || highlight === p.steamid ? 1 : 0.3} data-testid="live-player">
          <circle cx={p.px[0]} cy={p.px[1]} r={z.dot * 0.85} fill={sideFill(p.side)} stroke={highlight === p.steamid ? "#fff" : SCREEN} strokeWidth={z.line} />
          <text x={p.px[0]} y={p.px[1]} textAnchor="middle" dy={z.num * 0.36} className="map-num" style={{ fontSize: z.num, fill: SCREEN }}>
            {num(p.steamid)}
          </text>
          {liveLabel.has(p.steamid) && (
            <text x={liveLabel.get(p.steamid)!.x} y={liveLabel.get(p.steamid)!.y} textAnchor={liveLabel.get(p.steamid)!.anchor} className="dot-name" style={halo(z.name)}>
              {p.name}
            </text>
          )}
          <title>{`${num(p.steamid)} ${p.name} · ${p.hp} HP${p.place ? ` · ${p.place}` : ""}`}</title>
        </g>
      ))}

      {/* ตำแหน่งที่ตาย: วงกลวงสีฝั่งของคนตาย เลขประจำตัวข้างใน (ชื่อขึ้นเมื่อเลือก) */}
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
              <circle r={dotR(d)} fill={SCREEN} fillOpacity={0.85} stroke={selected === d.order ? "#fff" : sideFill(d.victim.side)} strokeWidth={z.line * 1.5} />
              <text textAnchor="middle" dy={z.num * 0.36} className="map-num" style={{ fontSize: z.num, fill: selected === d.order ? "#fff" : sideFill(d.victim.side) }}>
                {num(d.victim.steamid)}
              </text>
              {deathLabel.has(d.order) && (
                <text x={deathLabel.get(d.order)!.x - d.victim_px[0]} y={deathLabel.get(d.order)!.y - d.victim_px[1]}
                  textAnchor={deathLabel.get(d.order)!.anchor} className="dot-name" style={halo(z.name)}>
                  {d.victim.name}
                </text>
              )}
              <title>{`${fmtT(d.t_round)} ${num(d.victim.steamid)} ${d.victim.name} ตาย · ${weaponLabel(d.weapon)}${d.attacker ? ` · โดย ${num(d.attacker.steamid)} ${d.attacker.name}` : ""}`}</title>
            </g>
          ),
      )}
    </svg>
  );
}

// ================================================================================================
// รายชื่อสองทีม — เลข 1–5 ของแต่ละคนคือเลขเดียวกับบนแผนที่และในไทม์ไลน์
// ================================================================================================
interface RosterProps {
  teams: ReviewTeam[];
  numbers: Map<string, number>;
  highlight: string | null;
  onHighlight: (steamid: string | null) => void;
}

/** สองกล่องแยกตามทีม (ชื่อทีมคงที่ทั้งแมตช์) — ป้ายฝั่งบอกว่ารอบนี้ทีมนั้นเล่น CT หรือ T */
export function TeamRoster({ teams, numbers, highlight, onHighlight }: RosterProps) {
  return (
    <div className="roster" data-testid="team-roster">
      {teams.map((t) => (
        <div className={`team ${t.side_this_round}`} key={t.clan}>
          <div className="team-head">
            <span className={`side-tag ${t.side_this_round}`}>{sideLabel(t.side_this_round)}</span>
            <b>{t.clan}</b>
          </div>
          <ul>
            {t.players.map((p) => (
              <li key={p.steamid} className={highlight === p.steamid ? "on" : highlight ? "dim" : ""}>
                <button
                  type="button"
                  className="prow"
                  aria-pressed={highlight === p.steamid}
                  onClick={() => onHighlight(highlight === p.steamid ? null : p.steamid)}
                  title="กดเพื่อดูเฉพาะเหตุการณ์ของคนนี้"
                >
                  <span className={`pnum ${t.side_this_round}`}>{numbers.get(p.steamid)}</span>
                  <span className="pname">{p.name}</span>
                  <span className="pstat">
                    {p.survived ? <span className="alive">รอด</span> : <>ตาย <span className="num">{fmtT(p.died_at_t)}</span></>}
                  </span>
                  <span className="kills num" title="จำนวนคิลในรอบนี้">{p.kills > 0 ? `${p.kills}K` : ""}</span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      ))}
      {highlight && (
        <button type="button" className="link-btn" onClick={() => onHighlight(null)}>
          กลับมาดูทุกคน
        </button>
      )}
    </div>
  );
}

// ================================================================================================
// ไทม์ไลน์
// ================================================================================================
interface TimelineProps {
  deaths: ReviewDeath[];
  numbers: Map<string, number>;
  highlight: string | null;
  selected: number | null;
  onSelect: (order: number | null) => void;
  bombPlantedT: number | null;
  grenades: ReviewGrenade[];
}

const involvedIn = (d: ReviewDeath, h: string | null) => !h || d.victim.steamid === h || d.attacker?.steamid === h;

function Who({ p, numbers }: { p: ReviewPerson; numbers: Map<string, number> }) {
  return (
    <span className="who">
      <span className={`pnum ${p.side ?? ""}`}>{numbers.get(p.steamid) ?? "?"}</span>
      {p.name}
    </span>
  );
}

/** ไล่ตามเวลา: 0:23  ③ Alice ฆ่า ① Bob · AK-47 · HS · ระยะ 640u · A Site */
export function DeathTimeline({ deaths, numbers, highlight, selected, onSelect, bombPlantedT, grenades }: TimelineProps) {
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
            <span className="tl-t num">{fmtT(it.t)}</span>
            <span className="tl-text">วางบอมบ์</span>
          </li>
        ) : it.kind === "nade" ? (
          <li key={`n${it.i}`} className={`tl-nade ${!highlight || it.n.thrower?.steamid === highlight ? "" : "dim"}`}>
            <span className="tl-t num">{fmtT(it.t)}</span>
            <span className="tl-text">
              <span className="nade-dot" style={{ background: NADE_COLOR[it.n.type] }} />
              {it.n.thrower ? <Who p={it.n.thrower} numbers={numbers} /> : "?"} ขว้าง{nadeLabel(it.n.type)}
            </span>
          </li>
        ) : (
          <li
            key={it.d.order}
            className={`tl-death ${selected === it.d.order ? "sel" : ""} ${involvedIn(it.d, highlight) ? "" : "dim"}`}
            {...pressable(() => onSelect(selected === it.d.order ? null : it.d.order))}
            aria-pressed={selected === it.d.order}
          >
            <span className="tl-t num">{fmtT(it.d.t_round)}</span>
            <span className="tl-text">
              {it.d.attacker && it.d.is_duel ? (
                <>
                  <Who p={it.d.attacker} numbers={numbers} /> ฆ่า <Who p={it.d.victim} numbers={numbers} />
                </>
              ) : it.d.team_kill && it.d.attacker ? (
                <>
                  <Who p={it.d.attacker} numbers={numbers} /> ยิงเพื่อนร่วมทีม <Who p={it.d.victim} numbers={numbers} />
                </>
              ) : (
                <>
                  <Who p={it.d.victim} numbers={numbers} /> ตาย
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

/** ไอคอนเล่น / หยุด — วาดเองให้เข้าชุดกับไอคอนอื่นในแอป */
function IconPlay() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
      <path d="M7 4.5 20 12 7 19.5Z" fill="currentColor" />
    </svg>
  );
}

function IconPause() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
      <path d="M7.5 4.5h3.5v15H7.5zM13 4.5h3.5v15H13z" fill="currentColor" />
    </svg>
  );
}
