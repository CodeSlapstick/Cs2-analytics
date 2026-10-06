import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";
import { api, type OpeningRound, type OpeningRoutes, type Side } from "./api";
import { useT } from "./i18n";
import { openingAt } from "./openingRoutePlayback";
import "./opening-route.css";

const TYPES = ["flash", "smoke", "molotov", "he", "decoy"] as const;
const LABELS = { flash: "Flash", smoke: "Smoke", molotov: "Molotov / Incendiary", he: "HE", decoy: "Decoy" };

export function OpeningRoutePage() {
  const { t } = useT();
  const [params, setParams] = useSearchParams();
  const catalog = useQuery({ queryKey: ["opening-catalog"], queryFn: api.openingCatalog });
  const players = useMemo(() => {
    const result = new Map<string, { id: string; name: string; matches: Set<number> }>();
    for (const row of catalog.data ?? []) {
      const player = result.get(row.steamid) ?? { id: row.steamid, name: row.name ?? "—", matches: new Set<number>() };
      player.matches.add(row.id); result.set(row.steamid, player);
    }
    return [...result.values()].sort((a, b) => b.matches.size - a.matches.size || a.name.localeCompare(b.name));
  }, [catalog.data]);
  const player = players.find((p) => p.id === params.get("player")) ?? players[0];
  const maps = useMemo(() => {
    const result = new Map<string, Set<number>>();
    for (const row of catalog.data ?? []) {
      if (row.steamid !== player?.id || !row.map_name) continue;
      const ids = result.get(row.map_name) ?? new Set<number>(); ids.add(row.id); result.set(row.map_name, ids);
    }
    return [...result.entries()].sort((a, b) => b[1].size - a[1].size || a[0].localeCompare(b[0]));
  }, [catalog.data, player?.id]);
  const map = maps.find(([name]) => name === params.get("map"))?.[0] ?? maps[0]?.[0];
  const side: Side = params.get("side") === "ct" ? "ct" : "t";
  const scope = [5, 10].includes(Number(params.get("scope"))) ? Number(params.get("scope")) : 0;
  const routes = useQuery({
    queryKey: ["opening-routes", player?.id, map, side, scope],
    queryFn: () => api.openingRoutes(player!.id, map!, side, scope), enabled: !!player && !!map,
  });
  const selection = `${player?.id}:${map}:${side}:${scope}`;
  function change(key: string, value: string) {
    const next = new URLSearchParams(params); next.set(key, value);
    if (key === "player") next.delete("map");
    setParams(next);
  }
  return <section className="opening-page">
    <header className="opening-heading"><h1>Opening Route</h1>
      <p className="muted">{t("เปรียบเทียบเส้นทางและ Utility ของผู้เล่นใน 30 วินาทีแรกของหลายรอบบน radar เดียวกัน")}</p>
    </header>
    <div className="opening-filters filters card">
      <label>{t("ผู้เล่น")}<select value={player?.id ?? ""} onChange={(e) => change("player", e.target.value)} disabled={!players.length}>
        {!players.length && <option value="">—</option>}
        {players.map((p) => <option key={p.id} value={p.id}>{p.name} · {t("{n} แมตช์", { n: p.matches.size })}</option>)}
      </select></label>
      <label>{t("แผนที่")}<select value={map ?? ""} onChange={(e) => change("map", e.target.value)} disabled={!maps.length}>
        {!maps.length && <option value="">—</option>}
        {maps.map(([name, ids]) => <option key={name} value={name}>{name.replace("de_", "")} · {t("{n} แมตช์", { n: ids.size })}</option>)}
      </select></label>
      <label>{t("ขอบเขต")}<select value={scope} onChange={(e) => change("scope", e.target.value)}>
        <option value={5}>{t("5 แมตช์ล่าสุด")}</option><option value={10}>{t("10 แมตช์ล่าสุด")}</option><option value={0}>{t("ทั้งหมด")}</option>
      </select></label>
      <div className="opening-side" role="group" aria-label={t("ฝั่งของผู้เล่นในแต่ละรอบ")}>
        {(["t", "ct"] as const).map((s) => <button type="button" key={s} aria-pressed={s === side} className={s === side ? "btn-ghost active" : "btn-ghost"} onClick={() => change("side", s)}>{s.toUpperCase()}</button>)}
      </div>
    </div>
    {catalog.isError || routes.isError ? <div className="card" role="alert"><p>{t("โหลด Opening Route ไม่สำเร็จ")}</p><p className="muted">{String((catalog.error ?? routes.error)?.message ?? "")}</p><button type="button" className="btn-ghost" onClick={() => { void catalog.refetch(); if (player && map) void routes.refetch(); }}>{t("ลองอีกครั้ง")}</button></div>
      : catalog.isPending || (player && map && routes.isPending) ? <div className="card" role="status">{t("กำลังโหลดเส้นทางและ Utility…")}</div>
      : !players.length ? <div className="card"><h2>{t("ยังไม่มีข้อมูล Opening Route")}</h2><p>{t("นำเข้าแมตช์ที่มีตำแหน่งผู้เล่นหรือ Utility ก่อน")}</p><Link to="/matches">{t("แมตช์")}</Link></div>
      : routes.data ? <OpeningRouteStage key={selection} data={routes.data} playerName={player?.name ?? "—"} map={map ?? "—"} side={side} /> : null}
  </section>;
}

export function OpeningRouteStage({ data, playerName, map, side }: { data: OpeningRoutes; playerName: string; map: string; side: Side }) {
  const { t } = useT();
  const [time, setTime] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(1);
  const [opacity, setOpacity] = useState(0.65);
  const [showTrails, setShowTrails] = useState(true);
  const [showUtility, setShowUtility] = useState(true);
  const [hidden, setHidden] = useState<Set<string>>(() => new Set(data.rounds.slice(8).map((r) => r.key)));
  const visible = data.rounds.filter((r) => !hidden.has(r.key));
  useEffect(() => {
    if (!playing) return;
    let frame = 0; let last: number | null = null; let elapsed = time;
    function step(now: number) {
      if (last != null) elapsed = Math.min(30, elapsed + (now - last) / 1000 * speed);
      last = now; setTime(elapsed);
      if (elapsed >= 30) { setPlaying(false); return; }
      frame = requestAnimationFrame(step);
    }
    frame = requestAnimationFrame(step);
    return () => cancelAnimationFrame(frame);
    // time is captured on start/speed change; frame progress doesn't restart the effect.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [playing, speed]);
  const size = data.radar?.size ?? 1024;
  return <>
    <div className="opening-summary"><strong>{playerName}</strong><span>{map} · {side.toUpperCase()}</span><span>{t("{n} แมตช์", { n: data.matches })}</span><span>{t("แสดง {visible} / {total} รอบ", { visible: visible.length, total: data.rounds.length })}</span></div>
    {data.undated_matches > 0 && <p className="opening-note">{t("{n} แมตช์ไม่มีวันที่แข่งขัน: รวมใน ‘ทั้งหมด’ และไม่รวมใน ‘ล่าสุด’", { n: data.undated_matches })}</p>}
    <p className="opening-note">{t("ล่าสุดเรียงจากวันที่ YYYY-MM-DD ในชื่อไฟล์ ไม่ใช้วันอัปโหลด")}</p>
    {!data.rounds.length ? <div className="card"><h2>{t("ไม่มีรอบที่ตรงกับตัวกรอง")}</h2><p>{t("ลองเลือกทั้งหมด เปลี่ยนฝั่ง ผู้เล่น หรือแผนที่")}</p></div> :
    <div className="opening-layout">
      <div className="opening-main card">
        {data.radar ? <svg className="opening-radar" viewBox={`0 0 ${size} ${size}`} role="img" aria-label={t("Radar เส้นทางเปิดรอบ {map}", { map })}>
          <image href={data.radar.image} width={size} height={size} />
          {data.rounds.map((round, index) => hidden.has(round.key) ? null : <RoundOverlay key={round.key} round={round} index={index} time={time} opacity={opacity} showTrails={showTrails} showUtility={showUtility} size={size} />)}
        </svg> : <div className="opening-map-missing" role="status">{t("แผนที่นี้ยังไม่มี radar ที่ปรับเทียบแล้ว")}</div>}
        <div className="opening-playback">
          <button type="button" className="btn-primary" aria-label={playing ? t("หยุดชั่วคราว") : t("เล่น")} onClick={() => { if (time >= 30) setTime(0); setPlaying((p) => !p); }}>
            <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true">{playing ? <path d="M3 2h3v12H3zm7 0h3v12h-3z" /> : <path d="M4 2l10 6-10 6z" />}</svg>
            {playing ? t("หยุดชั่วคราว") : t("เล่น")}
          </button>
          <button type="button" className="btn-ghost" onClick={() => { setPlaying(false); setTime(0); }}>{t("กลับ 0 วินาที")}</button>
          <label className="opening-timeline"><span className="sr-only">{t("เวลา Playback")}</span><input type="range" min="0" max="30" step="0.1" value={time} onChange={(e) => { setPlaying(false); setTime(Number(e.target.value)); }} /></label>
          <output className="opening-clock" aria-label={t("เวลาปัจจุบัน")}>{time.toFixed(1)} / 30s</output>
          <label className="an-select"><span className="sr-only">{t("ความเร็ว Playback")}</span><select value={speed} onChange={(e) => setSpeed(Number(e.target.value))}>{[1, 2, 4].map((s) => <option key={s} value={s}>{s}x</option>)}</select></label>
        </div>
        <div className="opening-layers">
          <label><input type="checkbox" checked={showTrails} onChange={(e) => setShowTrails(e.target.checked)} />{t("เส้นทาง")}</label>
          <label><input type="checkbox" checked={showUtility} onChange={(e) => setShowUtility(e.target.checked)} />Utility</label>
          <label className="opening-opacity">{t("ความทึบ")}<input type="range" min="0.1" max="1" step="0.05" value={opacity} onChange={(e) => setOpacity(Number(e.target.value))} /><output>{Math.round(opacity * 100)}%</output></label>
        </div>
        <div className="opening-utility-key" aria-label="Utility legend">{TYPES.map((type) => <span key={type}><i className={`opening-utility-${type}`} />{LABELS[type]}</span>)}</div>
        <p className="opening-note">{t("จุด Utility คือจุดขว้างและจุดตกที่บันทึกไว้ เส้นบินแสดงเฉพาะ trajectory จริง ไม่เติมเวลาหรือเส้นทางที่ขาดหาย")}</p>
      </div>
      <aside className="opening-rounds card" aria-label={t("รายการรอบ")}><h2>{t("รายการรอบ")} <span className="muted">({data.rounds.length})</span></h2>
        <div className="opening-round-actions"><button type="button" className="btn-ghost" onClick={() => setHidden(new Set())}>{t("แสดงทุกรอบ")}</button><button type="button" className="btn-ghost" onClick={() => setHidden(new Set(data.rounds.map((r) => r.key)))}>{t("ซ่อนทุกรอบ")}</button></div>
        <div className="opening-round-scroll">{data.rounds.map((round, index) => <div key={round.key} className={`opening-round opening-series-${index % 8} ${hidden.has(round.key) ? "is-hidden" : ""}`}>
          <button type="button" className="opening-round-toggle" aria-pressed={!hidden.has(round.key)} title={`${round.match_name} · ${round.demo_file}`} onClick={() => setHidden((prev) => { const next = new Set(prev); if (next.has(round.key)) next.delete(round.key); else next.add(round.key); return next; })}>
            <span className="opening-round-number">{index + 1}</span><span className="opening-round-copy"><strong>R{round.round_num} · {round.match_name}</strong><small>{round.match_date ?? "—"} · {round.utility?.length ?? "—"} Utility · {hidden.has(round.key) ? t("ซ่อน") : t("แสดง")}</small>
              {!round.clock_available ? <small>{t("ไม่มีเวลาเริ่มรอบ")}</small> : !round.segments.length && <small>{t("ไม่มีตำแหน่งผู้เล่นในช่วงนี้")}</small>}
            </span>
          </button>
          <Link className="opening-evidence" to={`/matches/${encodeURIComponent(round.demo_file)}/rounds/${round.round_num}`} aria-label={t("เปิดหลักฐานรอบ {n}", { n: round.round_num })}>{t("ดูรอบ")}</Link>
        </div>)}</div>
      </aside>
    </div>}
    <p className="opening-note">{t("t=0 ใช้ start_tick ที่บันทึกไว้: parser ใช้ freeze end และ fallback เป็น round start เมื่อ event หาย ข้อมูลเดิมไม่ระบุที่มา จึงยืนยัน live start ทุกแมตช์ไม่ได้")}</p>
    <p className="opening-note">{t("Marker หยุดเมื่อผู้เล่นตายหรือข้อมูลสิ้นสุด ไม่เชื่อมช่วงหาย Interpolate เฉพาะ segment ต่อเนื่อง ไม่เกิน 1.5 เท่าของช่วง snapshot ปกติ และสูงสุด 1.5 วินาที")}</p>
    <p className="opening-note">{t("จำนวน Utility นับเหตุการณ์ที่บันทึกไว้ในช่วง 0–30 วินาทีเท่านั้น ข้อมูลเดิมรวม Molotov และ Incendiary เป็นชนิดเดียวกัน และไม่ได้รับรองความครบถ้วนของ event")}</p>
  </>;
}

function RoundOverlay({ round, index, time, opacity, showTrails, showUtility, size }: { round: OpeningRound; index: number; time: number; opacity: number; showTrails: boolean; showUtility: boolean; size: number }) {
  const { t } = useT();
  const state = openingAt(round, time);
  const scale = size / 1024;
  return <g className={`opening-series-${index % 8}`} opacity={opacity}>
    {showTrails && state.trails.map((points, i) => <polyline key={i} points={points.map((p) => p.join(",")).join(" ")} className="opening-route-line" strokeWidth={3 * scale} strokeDasharray={index >= 8 ? `${8 * scale} ${4 * scale}` : undefined} />)}
    {state.marker && <g><circle cx={state.marker[0]} cy={state.marker[1]} r={10 * scale} className="opening-marker" /><text x={state.marker[0]} y={state.marker[1]} dy=".35em" textAnchor="middle" className="opening-marker-label" fontSize={11 * scale}>{index + 1}</text><title>{round.match_name} · R{round.round_num} · {time.toFixed(1)}s</title></g>}
    {showUtility && (round.utility ?? []).filter((g) => g.t_throw != null && g.t_throw <= time).map((g, i) => {
      const landed = g.t_land != null && g.t_land <= time;
      const trajectory = (g.trajectory ?? []).filter((p) => p.t <= time && p.t >= (g.t_throw ?? 0));
      const tip = `${LABELS[g.type] ?? g.type} · R${round.round_num} · ${round.match_name} · ${g.t_throw?.toFixed(1) ?? "—"}s`;
      return <g key={i} className={`opening-utility-${g.type}`} tabIndex={0} aria-label={tip}>
        <title>{tip}</title>
        {trajectory.length > 1 && <polyline points={trajectory.map((p) => p.px.join(",")).join(" ")} fill="none" stroke="currentColor" strokeWidth={2 * scale} />}
        {g.throw_px && <circle cx={g.throw_px[0]} cy={g.throw_px[1]} r={5 * scale} fill="none" stroke="currentColor" strokeWidth={2 * scale}><title>{tip} · {t("จุดขว้าง")}</title></circle>}
        {landed && g.land_px && <rect x={g.land_px[0] - 4 * scale} y={g.land_px[1] - 4 * scale} width={8 * scale} height={8 * scale} fill="currentColor"><title>{tip} · {t("จุดตก")}</title></rect>}
        {trajectory.length > 0 && !landed && <circle cx={trajectory.at(-1)!.px[0]} cy={trajectory.at(-1)!.px[1]} r={4 * scale} fill="currentColor" />}
      </g>;
    })}
  </g>;
}
