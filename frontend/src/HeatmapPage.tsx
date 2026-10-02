import { type RefObject, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { Navigate, useParams, useSearchParams } from "react-router-dom";
import { api, matchesQuery, type HeatEvent, type MatchHeatmap } from "./api";
import { tr, useT } from "./i18n";
import { Breadcrumb, MapThumb, MatchTabs, matchTitle, NADE_ICON, NotFound, num } from "./utils";

// ================================================================================================
// heatmap ของแมตช์เดียว: /matches/{demo_file}/heatmap
// ================================================================================================
/**
 * "ในแมตช์นี้ เรื่องนี้เกิดตรงไหนบ่อย" — คิล / ตาย / ยืน / ระเบิดแต่ละชนิด บนภาพเรดาร์
 *
 * เป็นข้อเท็จจริงจากเดโมล้วน ไม่มีผลโมเดล — แค่นับว่ามีกี่จุดทับกันแล้วไล่สี น้ำเงิน (น้อย) -> แดง (มาก)
 * backend ส่งจุดเป็นพิกเซลบนภาพเรดาร์มาให้แล้ว หน้านี้ไม่มีสูตรแปลงพิกัดของตัวเอง
 *
 * สิ่งที่เลือกแล้วแชร์ลิงก์ได้ (event / ฝั่ง / รอบ) อยู่บน URL · ผู้เล่นที่เลือกกับค่าการแสดงผลไม่อยู่
 */
type Side = "all" | "ct" | "t";

const EVENTS: { key: HeatEvent; label: string; who: string; group: "คน" | "ระเบิด" }[] = [
  { key: "kills", label: "คิล", who: "ตำแหน่งคนยิงตอนยิงคู่แข่งตาย", group: "คน" },
  { key: "deaths", label: "ตาย", who: "ตำแหน่งที่ผู้เล่นตาย", group: "คน" },
  { key: "positions", label: "ยืน", who: "ตำแหน่งที่ผู้เล่นยืน เก็บ 8 ครั้งต่อวินาทีตลอดรอบ", group: "คน" },
  { key: "smoke", label: "สโมค", who: "จุดที่สโมคแตก", group: "ระเบิด" },
  { key: "flash", label: "แฟลช", who: "จุดที่แฟลชแตก", group: "ระเบิด" },
  { key: "he", label: "HE", who: "จุดที่ HE แตก", group: "ระเบิด" },
  { key: "molotov", label: "โมโลตอฟ", who: "จุดที่โมโลตอฟตก", group: "ระเบิด" },
];
const SIDES: { key: Side; label: string }[] = [
  { key: "all", label: "ทั้งสองฝั่ง" },
  { key: "ct", label: "CT" },
  { key: "t", label: "T" },
];
const range = (from: number, to: number) => Array.from({ length: Math.max(0, to - from + 1) }, (_, i) => from + i);

/** MR12 regulation, then one six-round block per overtime; the final block may be shorter. */
function roundPresets(total: number) {
  const presets: { key: string; label: string; rounds: number[] | null }[] = [
    { key: "all", label: "ทุกรอบ", rounds: null },
  ];
  if (total > 0) presets.push({ key: "first_half", label: "ครึ่งแรก", rounds: range(1, Math.min(12, total)) });
  if (total > 12) presets.push({ key: "second_half", label: "ครึ่งหลัง", rounds: range(13, Math.min(24, total)) });
  if (total > 24) presets.push({ key: "ot_all", label: "ต่อเวลาทั้งหมด", rounds: range(25, total) });
  for (let start = 25, n = 1; start <= total; start += 6, n += 1) {
    presets.push({ key: `ot${n}`, label: `OT${n}`, rounds: range(start, Math.min(start + 5, total)) });
  }
  return presets;
}

function selectedRound(raw: string | null, legacyHalf: string | null, total: number, presets: ReturnType<typeof roundPresets>): string {
  if (raw === null) raw = ({ "1": "first_half", "2": "second_half", ot: "ot_all" } as Record<string, string>)[legacyHalf ?? ""] ?? "all";
  if (presets.some((preset) => preset.key === raw)) return raw;
  const n = Number(raw);
  return /^\d+$/.test(raw) && Number.isInteger(n) && n >= 1 && n <= total ? String(n) : "all";
}

export function HeatmapPage() {
  const { t } = useT();
  const { demo } = useParams();
  const matches = useQuery(matchesQuery);
  const entry = demo ? (matches.data ?? []).find((m) => m.demo_file === demo) : undefined;

  if (matches.error) return <p className="err">{t("โหลดรายการแมตช์ไม่ได้: {msg}", { msg: (matches.error as Error).message })}</p>;
  if (!matches.data) return <p className="muted">{t("กำลังโหลด…")}</p>;
  if (!entry) return <NotFound title={t("ไม่พบแมตช์นี้")} detail={t("ไม่มีแมตช์ {demo} ในระบบ", { demo: demo ?? "" })} />;
  if (entry.status !== "done") return <Navigate to={`/matches/${encodeURIComponent(entry.demo_file)}`} replace />;

  return <HeatmapBody demo={entry.demo_file} title={matchTitle(entry)} totalRounds={entry.rounds} />;
}

function HeatmapBody({ demo, title, totalRounds }: { demo: string; title: string; totalRounds: number }) {
  const { t, tn } = useT();
  const [params, setParams] = useSearchParams();
  const ev = (EVENTS.find((e) => e.key === params.get("ev"))?.key ?? "kills") as HeatEvent;
  const side = (SIDES.find((s) => s.key === params.get("side"))?.key ?? "all") as Side;
  const presets = roundPresets(totalRounds);
  const round = selectedRound(params.get("round"), params.get("half"), totalRounds, presets);
  const put = (key: string, value: string, fallback: string) =>
    setParams((prev) => {
      const next = new URLSearchParams(prev);
      if (value === fallback) next.delete(key);
      else next.set(key, value);
      return next;
    }, { replace: true });
  const putRound = (value: string) => setParams((prev) => {
    const next = new URLSearchParams(prev);
    next.set("round", value);
    next.delete("half");
    return next;
  }, { replace: true });

  // null = ทุกคน · [] = ไม่เลือกใครเลย (ไม่ต้องถาม backend — ว่างแน่นอน)
  const [players, setPlayers] = useState<string[] | null>(null);
  const [radius, setRadius] = useState(22);
  const [blur, setBlur] = useState(18);
  const [opacity, setOpacity] = useState(0.85);
  const rounds = presets.find((preset) => preset.key === round)?.rounds ?? (round === "all" ? null : [Number(round)]);
  const none = players !== null && players.length === 0;

  const q = useQuery({
    queryKey: ["heatmap", demo, ev, side, players?.join(",") ?? null, rounds?.join(",") ?? null],
    queryFn: () => api.heatmap(demo, ev, side, players, rounds),
    enabled: !none,
    placeholderData: keepPreviousData, // เปลี่ยนตัวกรองแล้วแผนที่ไม่กระพริบหาย
    staleTime: 5 * 60_000,
  });
  // รายชื่อต้องอยู่ต่อแม้ตอนเลือก "ไม่เอาเลย" (ไม่ได้ถาม backend) — จำชุดล่าสุดไว้
  const lastRoster = useRef<MatchHeatmap["roster"]>([]);
  if (q.data) lastRoster.current = q.data.roster;
  const roster = lastRoster.current;
  const teams = useMemo(() => {
    const byTeam = new Map<string, string[]>();
    roster.forEach((p) => {
      const tm = p.team ?? "ไม่ทราบทีม";
      byTeam.set(tm, [...(byTeam.get(tm) ?? []), p.steam_id]);
    });
    return [...byTeam];
  }, [roster]);
  const sameSet = (a: string[], b: string[]) => a.length === b.length && a.every((x) => b.includes(x));
  const activeTeam = players === null ? "all" : (teams.find(([, ids]) => sameSet(ids, players))?.[0] ?? null);

  const playerOn = (id: string) => players === null || players.includes(id);
  const togglePlayer = (id: string) => {
    const base = players ?? roster.map((p) => p.steam_id);
    const next = base.includes(id) ? base.filter((x) => x !== id) : [...base, id];
    setPlayers(next.length === roster.length ? null : next);
  };

  const meta = EVENTS.find((e) => e.key === ev)!;
  const data = q.data;
  const currentData = q.isPlaceholderData && !none ? null : data;
  const empty = none || (currentData?.count === 0);
  const canvasRef = useRef<HTMLCanvasElement>(null);

  return (
    <div className="heat-page" data-testid="heatmap-page">
      <Breadcrumb items={[{ label: t("แมตช์"), to: "/matches" }, { label: title }]} />
      <div className="page-head mt-head">
        <MapThumb map={data?.map} className="mh-thumb" />
        <div>
          <h1>{title}</h1>
          <p className="muted small">{data?.map ?? "…"} · {t("{n} รอบ", { n: num(totalRounds) })}</p>
        </div>
      </div>
      <MatchTabs demo={demo} />

      <div className="heat-grid">
        <section className="heat-map-col" aria-label={t("แผนที่ heatmap")}>
          <div className="heat-map">
            {q.error ? (
              <p className="err">{t("โหลดข้อมูลไม่ได้: {msg}", { msg: (q.error as Error).message })}</p>
            ) : data ? (
              <>
                <HeatCanvas data={data} points={empty || q.isPlaceholderData ? [] : data.points} radius={radius} blur={blur}
                  opacity={opacity} canvasRef={canvasRef} />
                {empty && <div className="heat-empty" role="status">
                  {t(none ? "ยังไม่ได้เลือกผู้เล่น" : "ไม่พบข้อมูลในรอบที่เลือก")}
                </div>}
                {q.isPlaceholderData && !none && <div className="heat-empty" role="status">{t("กำลังอัปเดต…")}</div>}
              </>
            ) : none ? (
              <p className="muted">{t("ยังไม่ได้เลือกผู้เล่น")}</p>
            ) : (
              <p className="muted">{t("กำลังโหลด…")}</p>
            )}
          </div>
          <div className="heat-foot">
            <span className="heat-key" aria-hidden="true">
              <span>{t("น้อย")}</span><i /><span>{t("มาก")}</span>
            </span>
            <span className="small">
              {tn("{n} จุด · {who}", { n: <b>{none ? 0 : q.isPlaceholderData ? "…" : num(data?.count ?? 0)}</b>, who: t(meta.who) })}
              {q.isFetching && <span className="muted"> · {t("กำลังอัปเดต…")}</span>}
            </span>
          </div>
        </section>

        <aside className="card heat-panel" aria-label={t("ตัวเลือก heatmap")}>
          <fieldset className="hp-field">
            <legend>{t("ดูอะไร")}</legend>
            {(["คน", "ระเบิด"] as const).map((g) => (
              <div className="seg" role="group" aria-label={t(g)} key={g}>
                {EVENTS.filter((e) => e.group === g).map((e) => (
                  <button key={e.key} type="button" className={`seg-btn${ev === e.key ? " on" : ""}`}
                    aria-pressed={ev === e.key} onClick={() => put("ev", e.key, "kills")} data-testid={`hm-ev-${e.key}`}>
                    {NADE_ICON[e.key] && <img className="nade-ico" src={NADE_ICON[e.key]} alt="" />}
                    {t(e.label)}
                  </button>
                ))}
              </div>
            ))}
          </fieldset>

          <fieldset className="hp-field">
            <legend>{t("ฝั่ง · ช่วงเกม")}</legend>
            <div className="seg" role="group" aria-label={t("ฝั่ง")}>
              {SIDES.map((s) => (
                <button key={s.key} type="button" className={`seg-btn${side === s.key ? " on" : ""}`}
                  aria-pressed={side === s.key} onClick={() => put("side", s.key, "all")}>
                  {t(s.label)}
                </button>
              ))}
            </div>
            <div className="seg" role="group" aria-label={t("ช่วงเกม")}>
              {presets.map((preset) => (
                <button key={preset.key} type="button" className={`seg-btn${round === preset.key ? " on" : ""}`}
                  aria-pressed={round === preset.key} onClick={() => putRound(preset.key)}>
                  {t(preset.label)}
                </button>
              ))}
            </div>
            <label className="hm-round-select">
              <span>{t("เลือกรอบเดียว")}</span>
              <select value={/^\d+$/.test(round) ? round : ""} onChange={(e) => e.target.value && putRound(e.target.value)}>
                <option value="" disabled>{t("เลือกรอบ")}</option>
                {range(1, totalRounds).map((n) => <option key={n} value={n}>{t("รอบ {n}", { n })}</option>)}
              </select>
            </label>
          </fieldset>

          <fieldset className="hp-field">
            <legend>{t("ทีม")}</legend>
            <div className="seg" role="group" aria-label={t("ทีม")}>
              <button type="button" className={`seg-btn${activeTeam === "all" ? " on" : ""}`}
                aria-pressed={activeTeam === "all"} onClick={() => setPlayers(null)}>
                {t("ทุกทีม")}
              </button>
              {teams.map(([team, ids]) => (
                <button key={team} type="button" className={`seg-btn${activeTeam === team ? " on" : ""}`}
                  aria-pressed={activeTeam === team} onClick={() => setPlayers(ids)}>
                  {team === "ไม่ทราบทีม" ? t(team) : team}
                </button>
              ))}
            </div>
          </fieldset>

          <fieldset className="hp-field">
            <legend className="hp-legend-row">
              <span>{t("ผู้เล่น")}</span>
              <span className="hm-quick">
                <button type="button" className="link-btn" onClick={() => setPlayers(null)}>{t("ทั้งหมด")}</button>
                {" · "}
                <button type="button" className="link-btn" onClick={() => setPlayers([])}>{t("ไม่เอาเลย")}</button>
              </span>
            </legend>
            <div className="hm-pills" role="group" aria-label={t("เลือกผู้เล่น")}>
              {roster.map((p) => (
                <button key={p.steam_id} type="button"
                  className={`hm-pill${playerOn(p.steam_id) ? ` ${p.start_side ?? ""} on` : ""}`}
                  aria-pressed={playerOn(p.steam_id)} onClick={() => togglePlayer(p.steam_id)}>
                  {p.name}
                </button>
              ))}
            </div>
            {none && <p className="muted small hp-note">{t('ยังไม่ได้เลือกใคร — กดชื่อผู้เล่น หรือ "ทั้งหมด"')}</p>}
          </fieldset>

          <fieldset className="hp-field">
            <legend>{t("การแสดงผล")}</legend>
            <Slider label={t("รัศมี")} value={radius} min={6} max={60} step={1} onChange={setRadius} />
            <Slider label={t("ความเบลอ")} value={blur} min={0} max={40} step={1} onChange={setBlur} />
            <Slider label={t("ความทึบ")} value={opacity} min={0.15} max={1} step={0.05} onChange={setOpacity}
              format={(v) => `${Math.round(v * 100)}%`} />
          </fieldset>

          <button type="button" className="btn-primary btn-icon hp-export" disabled={!currentData || none}
            onClick={() => currentData && exportPng(currentData, canvasRef.current, opacity, `${title} · ${t(meta.label)}`, demo, ev)}>
            <IconDownload /> {t("ดาวน์โหลดรูป (PNG)")}
          </button>
        </aside>
      </div>
    </div>
  );
}

function Slider({ label, value, min, max, step, onChange, format }: {
  label: string; value: number; min: number; max: number; step: number;
  onChange: (v: number) => void; format?: (v: number) => string;
}) {
  return (
    <label className="hp-slider">
      <span className="hp-slider-h"><span>{label}</span><span className="muted">{format ? format(value) : value}</span></span>
      <input type="range" min={min} max={max} step={step} value={value} onChange={(e) => onChange(Number(e.target.value))} />
    </label>
  );
}

// ================================================================================================
// วาด heatmap บน canvas
// ================================================================================================
/**
 * วิธีเดียวกับ heatmap ทั่วไป (แบบ simpleheat):
 *   1. ประทับวงกลมเบลอสีดำโปร่งแสงลงทุกจุด — จุดยิ่งทับกันมาก ช่องนั้นยิ่งทึบ
 *   2. อ่านความทึบทีละพิกเซลแล้วแปลงเป็นสีจากแถบสี น้ำเงิน -> ฟ้า -> เขียว -> เหลือง -> แดง
 * ความทึบต่อจุดปรับตามจำนวนจุดที่ทับกันมากที่สุด เพื่อให้ทั้งคิล 100 จุดและตำแหน่งยืน 6,000 จุด
 * ยังมีสีแดงเฉพาะที่หนาแน่นที่สุดจริง ๆ ไม่ใช่แดงทั้งแผนที่
 */
const RAMP: [number, string][] = [
  [0.0, "#1432ff"], [0.3, "#00b4ff"], [0.5, "#1fe07a"], [0.7, "#ffe600"], [0.85, "#ff8a00"], [1.0, "#ff1e1e"],
];

let palette: Uint8ClampedArray | null = null;
function getPalette(): Uint8ClampedArray {
  if (palette) return palette;
  const c = document.createElement("canvas");
  c.width = 256;
  c.height = 1;
  const g = c.getContext("2d")!;
  const grad = g.createLinearGradient(0, 0, 256, 0);
  RAMP.forEach(([at, col]) => grad.addColorStop(at, col));
  g.fillStyle = grad;
  g.fillRect(0, 0, 256, 1);
  palette = g.getImageData(0, 0, 256, 1).data;
  return palette;
}

function drawHeat(canvas: HTMLCanvasElement, size: number, points: [number, number][], radius: number, blur: number) {
  canvas.width = size;
  canvas.height = size;
  const ctx = canvas.getContext("2d", { willReadFrequently: true })!;
  ctx.clearRect(0, 0, size, size);
  if (points.length === 0) return;

  // แสตมป์วงกลมเบลอ — วาดวงไว้นอกกรอบแล้วเหลือแค่เงา ได้ขอบนุ่มโดยไม่มีวงแข็งตรงกลาง
  const r2 = radius + blur;
  const stamp = document.createElement("canvas");
  stamp.width = stamp.height = r2 * 2;
  const s = stamp.getContext("2d")!;
  s.shadowOffsetX = s.shadowOffsetY = r2 * 2;
  s.shadowBlur = blur;
  s.shadowColor = "black";
  s.beginPath();
  s.arc(-r2, -r2, radius, 0, Math.PI * 2);
  s.fill();

  // จุดที่ทับกันมากที่สุดราวกี่จุด (นับลงช่องขนาดเท่ารัศมี) -> ความทึบต่อจุด
  const cell = Math.max(4, radius);
  const bins = new Map<number, number>();
  let peak = 1;
  for (const [x, y] of points) {
    const k = Math.floor(x / cell) * 4096 + Math.floor(y / cell);
    const n = (bins.get(k) ?? 0) + 1;
    bins.set(k, n);
    if (n > peak) peak = n;
  }
  ctx.globalAlpha = Math.min(1, Math.max(0.012, 1.8 / peak));
  for (const [x, y] of points) ctx.drawImage(stamp, x - r2, y - r2);

  // ความทึบ -> สี
  const img = ctx.getImageData(0, 0, size, size);
  const px = img.data;
  const pal = getPalette();
  for (let i = 3; i < px.length; i += 4) {
    const a = px[i];
    if (a < 3) {
      px[i] = 0;
      continue;
    }
    const j = a * 4;
    px[i - 3] = pal[j];
    px[i - 2] = pal[j + 1];
    px[i - 1] = pal[j + 2];
    px[i] = Math.min(255, 70 + a * 1.4); // ส่วนบาง ๆ ยังเห็นเป็นฟ้าจาง ไม่หายไปกับพื้น
  }
  ctx.putImageData(img, 0, 0);
}

const MAX_Z = 6;

function HeatCanvas({ data, points, radius, blur, opacity, canvasRef }: {
  data: MatchHeatmap;
  points: [number, number][];
  radius: number;
  blur: number;
  opacity: number;
  canvasRef: RefObject<HTMLCanvasElement>;
}) {
  const { t } = useT();
  const size = data.radar.size;
  useLayoutEffect(() => {
    if (canvasRef.current) drawHeat(canvasRef.current, size, points, radius, blur);
  }, [points, radius, blur, size, canvasRef]);

  // ---- ซูม/เลื่อน: z = เท่า, (tx, ty) = เลื่อนเป็นสัดส่วนของกล่อง
  const [view, setView] = useState({ z: 1, tx: 0, ty: 0 });
  const box = useRef<HTMLDivElement>(null);
  const drag = useRef<{ x: number; y: number; tx: number; ty: number } | null>(null);
  const clamp = (z: number, tx: number, ty: number) => {
    const lim = 1 - z; // เลื่อนได้ไม่เกินขอบภาพ
    return { z, tx: Math.min(0, Math.max(lim, tx)), ty: Math.min(0, Math.max(lim, ty)) };
  };
  const zoomAt = (factor: number, cx = 0.5, cy = 0.5) =>
    setView((v) => {
      const z = Math.min(MAX_Z, Math.max(1, v.z * factor));
      if (z === 1) return { z: 1, tx: 0, ty: 0 };
      const k = z / v.z; // จุดใต้เมาส์อยู่ที่เดิมหลังซูม
      return clamp(z, cx - (cx - v.tx) * k, cy - (cy - v.ty) * k);
    });
  useEffect(() => {
    const el = box.current;
    if (!el) return;
    const onWheel = (e: WheelEvent) => {
      e.preventDefault(); // ไม่ให้ทั้งหน้าเลื่อนตอนหมุนล้อบนแผนที่
      const r = el.getBoundingClientRect();
      zoomAt(e.deltaY < 0 ? 1.2 : 1 / 1.2, (e.clientX - r.left) / r.width, (e.clientY - r.top) / r.height);
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  }, []);

  return (
    <div
      className={`heat-box${view.z > 1 ? " zoomed" : ""}`}
      ref={box}
      onPointerDown={(e) => {
        if (view.z <= 1 || e.button !== 0) return;
        drag.current = { x: e.clientX, y: e.clientY, tx: view.tx, ty: view.ty };
        e.currentTarget.setPointerCapture(e.pointerId);
      }}
      onPointerMove={(e) => {
        const d = drag.current;
        if (!d) return;
        const r = e.currentTarget.getBoundingClientRect();
        setView((v) => clamp(v.z, d.tx + (e.clientX - d.x) / r.width, d.ty + (e.clientY - d.y) / r.height));
      }}
      onPointerUp={() => (drag.current = null)}
      data-testid="heatmap-box"
    >
      <div className="heat-stage" style={{ transform: `translate(${view.tx * 100}%, ${view.ty * 100}%) scale(${view.z})` }}>
        <img src={data.radar.image} alt={t("ภาพเรดาร์ {map}", { map: data.radar.map })} draggable={false} />
        <canvas ref={canvasRef} style={{ opacity }} data-testid="heatmap-canvas" />
      </div>
      <div className="map-zoom" role="group" aria-label={t("ซูมแผนที่")}>
        <button type="button" onClick={() => zoomAt(1.4)} disabled={view.z >= MAX_Z} aria-label={t("ซูมเข้า")}
          title={t("ซูมเข้า (หรือหมุนล้อเมาส์บนแผนที่)")}>+</button>
        <button type="button" onClick={() => zoomAt(1 / 1.4)} disabled={view.z <= 1} aria-label={t("ซูมออก")} title={t("ซูมออก")}>−</button>
        {view.z > 1 && (
          <button type="button" className="mz-reset" onClick={() => setView({ z: 1, tx: 0, ty: 0 })}>{t("เต็มแมพ")}</button>
        )}
      </div>
    </div>
  );
}

/** รวมภาพเรดาร์ + heatmap + บรรทัดบอกว่าเป็นรูปอะไร เป็นไฟล์ PNG เดียว (เอาไปใส่สไลด์/ส่งในทีมได้) */
function exportPng(data: MatchHeatmap, heat: HTMLCanvasElement | null, opacity: number, caption: string,
                   demo: string, ev: string) {
  if (!heat) return;
  const size = data.radar.size;
  const img = new Image();
  img.onload = () => {
    const out = document.createElement("canvas");
    out.width = out.height = size;
    const g = out.getContext("2d")!;
    g.fillStyle = "#0a0f1a";
    g.fillRect(0, 0, size, size);
    g.drawImage(img, 0, 0, size, size);
    g.globalAlpha = opacity;
    g.drawImage(heat, 0, 0);
    g.globalAlpha = 1;
    g.font = "600 22px system-ui, 'Segoe UI', 'Leelawadee UI', sans-serif";
    g.fillStyle = "rgba(10, 15, 26, .78)";
    const text = tr("{caption} · {n} จุด", { caption, n: data.count });
    g.fillRect(16, size - 52, g.measureText(text).width + 24, 36);
    g.fillStyle = "#e8eef8";
    g.fillText(text, 28, size - 26);
    out.toBlob((blob) => {
      if (!blob) return;
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = `${demo.replace(/\.dem$/i, "")}-heatmap-${ev}.png`;
      a.click();
      setTimeout(() => URL.revokeObjectURL(a.href), 1000);
    }, "image/png");
  };
  img.src = data.radar.image;
}

function IconDownload() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
      strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false">
      <path d="M12 4v11M7 10l5 5 5-5M5 19h14" />
    </svg>
  );
}
