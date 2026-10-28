import { useQuery } from "@tanstack/react-query";
import { Link, useLocation, useParams, useSearchParams } from "react-router-dom";
import { ApiError, auth, isGuest, playerApi, type PlayerMap, type PlayerProfileFilters, type PlayerWeapon } from "./api";
import { MapThumb, weaponLabel } from "./utils";
import unknownAvatar from "./assets/avatar-unknown.jpg";
import { useT } from "./i18n";

const FEATURE_LABELS: Record<string, string> = {
  opening_attempt_rate: "Entry attempts / round", opening_kill_rate: "Opening kills / round",
  trade_kills_per_round: "Trade kills / round", traded_death_rate: "Traded deaths / round",
  flash_assists_per_round: "Flash assists / round", assists_per_round: "Assists / round",
  early_engagement_rate: "Early engagements / round", postplant_kills_per_round: "Post-plant kills / round",
  site_engagement_rate: "Site engagements / round", avg_kill_time: "Average kill time",
  place_diversity: "Position diversity", place_concentration: "Position concentration",
};

function isoDate(value: string | null) {
  return value ? new Intl.DateTimeFormat(undefined, { dateStyle: "medium" }).format(new Date(value)) : "—";
}

export function PlayerPage() {
  const { steamId } = useParams();
  const who = steamId ?? "me";
  const { t } = useT();
  const valueOrData = (value: number | null | undefined, digits = 1, suffix = "") => value == null ? t("ไม่มีข้อมูล") : `${value.toFixed(digits)}${suffix}`;
  const [params, setParams] = useSearchParams();
  const recentRaw = Number(params.get("recent") ?? 0);
  const filters: PlayerProfileFilters = {
    recent: ([0, 5, 10, 20].includes(recentRaw) ? recentRaw : 0) as 0 | 5 | 10 | 20,
    date_from: params.get("from") || undefined, date_to: params.get("to") || undefined,
    map: params.get("map") || undefined,
    side: params.get("side") === "ct" ? "ct" : params.get("side") === "t" ? "t" : "all",
  };
  const profile = useQuery({
    queryKey: ["player-profile", who, filters.recent, filters.date_from, filters.date_to, filters.map, filters.side],
    queryFn: () => playerApi.profile(who, filters), retry: false,
  });

  function change(key: "recent" | "from" | "to" | "map" | "side", value: string) {
    const next = new URLSearchParams(params);
    if (!value || value === "0" || value === "all") next.delete(key); else next.set(key, value);
    setParams(next, { replace: true });
  }

  if (profile.isLoading) return <p className="muted">{t("กำลังโหลดสถิติ…")}</p>;
  if (profile.error instanceof ApiError) return <PlayerEmpty status={profile.error.status} message={profile.error.message} mine={!steamId} />;
  if (profile.error) return <p className="err">{t("โหลดสถิติไม่ได้: {msg}", { msg: t((profile.error as Error).message) })}</p>;
  if (!profile.data) return null;

  const d = profile.data;
  const tot = d.totals;
  const entryRate = (entry: { kills: number; deaths: number }) => entry.kills + entry.deaths ? entry.kills / (entry.kills + entry.deaths) : null;
  return <div className="player" data-testid="player-page">
    <header className="pl-head">
      <img className="pl-avatar" src={d.player.avatar || unknownAvatar} alt="" referrerPolicy="no-referrer" />
      <div className="pl-identity"><h1>{d.player.name}</h1><p className="muted">{d.player.account_name || `Steam ${d.player.steam_id}`} {d.player.latest_team ? `· ${d.player.latest_team}` : ""}</p><p className="muted small">{t("ข้อมูล {matches} แมตช์ · {rounds} รอบ", { matches: d.source.selected_matches, rounds: d.source.selected_rounds })} · {isoDate(d.data_range.from)} – {isoDate(d.data_range.to)}</p></div>
      <div className="pl-source"><strong>{d.source.selected_matches}</strong><span>{t("แมตช์ที่ใช้คำนวณ")}</span></div>
    </header>

    <section className="pl-filters card" aria-label={t("ตัวกรองข้อมูลผู้เล่น")}>
      <label>{t("ช่วงแมตช์")}<select value={filters.recent} onChange={(event) => change("recent", event.target.value)}><option value={0}>{t("ทุกแมตช์")}</option><option value={5}>{t("5 แมตช์ล่าสุด")}</option><option value={10}>{t("10 แมตช์ล่าสุด")}</option><option value={20}>{t("20 แมตช์ล่าสุด")}</option></select></label>
      <label>{t("ตั้งแต่วันที่นำเข้า")}<input type="date" value={filters.date_from ?? ""} max={filters.date_to} onChange={(event) => change("from", event.target.value)} /></label>
      <label>{t("ถึงวันที่นำเข้า")}<input type="date" value={filters.date_to ?? ""} min={filters.date_from} onChange={(event) => change("to", event.target.value)} /></label>
      <label>{t("แผนที่")}<select value={filters.map ?? ""} onChange={(event) => change("map", event.target.value)}><option value="">{t("ทุกแผนที่")}</option>{d.filters.available_maps.map((map) => <option key={map} value={map}>{map}</option>)}</select></label>
      <label>{t("ฝั่ง")}<select value={filters.side} onChange={(event) => change("side", event.target.value)}><option value="all">{t("ทั้งสองฝั่ง")}</option><option value="ct">CT</option><option value="t">T</option></select></label>
    </section>

    {!tot ? <section className="card pl-filter-empty"><h2>{t("ไม่มีข้อมูลตามตัวกรองนี้")}</h2><p className="muted">{t("ลองขยายช่วงแมตช์ วันที่ แผนที่ หรือเลือกทั้งสองฝั่ง")}</p></section> : <>
      <section className="pl-grid" aria-label={t("สถิติหลัก")}>
        <article className="card pl-card"><h2>K/D</h2><Gauge value={tot.kd ?? 0} max={2} label={valueOrData(tot.kd, 2)} /><p className="muted small">{t("{k} คิล · {d} ตาย · {a} ช่วย", { k: tot.kills, d: tot.deaths, a: tot.assists })}</p></article>
        <article className="card pl-card"><h2>{t("Rating 1.0 ที่คำนวณ")}</h2><Gauge value={tot.rating ?? 0} max={2} label={valueOrData(tot.rating, 2)} /><p className="muted small">{t("ใช้สูตร Rating 1.0 ที่เผยแพร่ ไม่ใช่ค่าจาก stat feed อย่างเป็นทางการ")}<br />{t("Rating 2.0 ค่าประมาณ: {v}", { v: tot.rating2_approx.toFixed(2) })}<br />{t("ไม่ใช่ค่า HLTV Rating 2.0 อย่างเป็นทางการ")}</p></article>
        <article className="card pl-card"><h2>{t("ชนะรอบ")}</h2><Gauge value={tot.win_rate} max={100} label={valueOrData(tot.win_rate, 0, "%")} unit /><p className="muted small">{t("{r} รอบใน {m} แมตช์", { r: tot.rounds, m: tot.matches })}</p></article>
        <article className="card pl-card"><h2>HS% · ADR · KAST</h2><ul className="pl-nums"><li><b>{valueOrData(tot.hs_rate, 0, "%")}</b><span>{t("HS จาก kills")}</span></li><li><b>{valueOrData(tot.adr, 1)}</b><span>ADR</span></li><li><b>{valueOrData(tot.kast, 0, "%")}</b><span>KAST</span></li><li><b>{valueOrData(tot.survival_rate, 0, "%")}</b><span>{t("รอดจบรอบ")}</span></li></ul></article>
        <article className="card pl-card pl-wide"><h2>{t("Clutch 1v1–1v5")}</h2>{d.clutches ? <div className="pl-clutches">{d.clutches.map((clutch) => <MiniPie key={clutch.vs} label={`1v${clutch.vs}`} wins={clutch.wins} attempts={clutch.attempts} />)}</div> : <p className="muted">{t("ไม่มีข้อมูล")}</p>}</article>
        <article className="card pl-card pl-wide"><h2>{t("Entry — First kill / First death")}</h2><div className="pl-donuts"><Donut label={t("รวม")} value={entryRate(d.entry.both)} won={d.entry.both.kills} lost={d.entry.both.deaths} /><Donut label={t("ฝั่ง CT")} value={entryRate(d.entry.ct)} won={d.entry.ct.kills} lost={d.entry.ct.deaths} tone="ct" /><Donut label={t("ฝั่ง T")} value={entryRate(d.entry.t)} won={d.entry.t.kills} lost={d.entry.t.deaths} tone="t" /></div><p className="muted small">{t("เปอร์เซ็นต์ = First kills / (First kills + First deaths)")}</p></article>
      </section>

      <section className="pl-panels">
        <article className="card pl-panel-wide"><h2>{t("แมตช์ล่าสุด")}</h2><ul className="pl-matches">{d.recent_matches.map((match) => <li key={match.match_id} className={`r-${match.result}`}><Link to={`/matches/${encodeURIComponent(match.demo_file)}/rounds/1?p=${encodeURIComponent(d.player.steam_id)}`}><MapThumb map={match.map_name} className="pl-thumb" /><span className="pl-res">{match.result === "win" ? t("ชนะ") : match.result === "loss" ? t("แพ้") : t("เสมอ")}</span><span className="pl-mt">{match.team_a && match.team_b ? `${match.team_a} vs ${match.team_b}` : match.demo_file}<small>{match.map_name} · {isoDate(match.imported_at)} · {match.kills}/{match.deaths}/{match.assists}</small></span><span className="pl-rt">{valueOrData(match.rating, 2)}</span></Link></li>)}</ul></article>
        <article className="card"><h2>{t("แมพที่เล่นบ่อย")}</h2><Bars rows={d.maps.map((map: PlayerMap & { kd: number | null }) => ({ key: map.map_name, label: map.map_name, value: map.matches, note: t("Win {win}% · Rating {rating} · K/D {kd}", { win: map.win_rate.toFixed(0), rating: valueOrData(map.rating, 2), kd: valueOrData(map.kd, 2) }), ratio: map.win_rate / 100 }))} empty={t("ยังไม่มีข้อมูลแมพ")} /></article>
        <article className="card"><h2>{t("อาวุธที่ฆ่าบ่อย")}</h2><Bars rows={d.weapons.map((weapon: PlayerWeapon) => ({ key: weapon.weapon, label: weaponLabel(weapon.weapon), value: weapon.kills, note: `${t("HS {pct}%", { pct: weapon.hs_rate.toFixed(0) })} · ${t("Accuracy: ไม่มีข้อมูล")}`, ratio: weapon.hs_rate / 100 }))} empty={t("ยังไม่มีข้อมูลอาวุธ")} /></article>
        <BehaviorCard behavior={d.behavior} />
      </section>

      <details className="card pl-formulas"><summary>{t("สูตรและข้อจำกัดของข้อมูล")}</summary><dl>{Object.entries(d.formulas).map(([key, formula]) => <div key={key}><dt>{key}</dt><dd>{formula}</dd></div>)}</dl><p className="muted small">{t("วันที่ในตัวกรองคือวันที่นำเข้า demo เพราะ parser ยังไม่มีวันที่แข่งขัน")}</p><p className="muted small">{t("Accuracy ไม่มีข้อมูล เพราะ parser ยังไม่เก็บจำนวนกระสุนที่ยิงและโดน")}</p></details>
    </>}
  </div>;
}

function BehaviorCard({ behavior }: { behavior: Awaited<ReturnType<typeof playerApi.profile>>["behavior"] }) {
  const { t } = useT();
  return <article className="card pl-panel-wide"><h2>{t("Player Role & Behavior")}</h2><p className="muted small">{t("สรุปจากโมเดลอ้างอิงระดับผู้เล่น–แมตช์–ฝั่ง ไม่ใช่ระดับฝีมือหรือบทบาทถาวร")}</p><div className="pl-behavior">{behavior.sides.map((side) => <section key={side.side} className={`side-${side.side}`}><h3>{side.side.toUpperCase()}</h3>{side.available ? <><strong>{side.role}</strong><p className="muted small">{t("จาก {profiles} โปรไฟล์ · {rounds} รอบ", { profiles: side.profiles ?? 0, rounds: side.rounds ?? 0 })}</p><ul>{side.signals?.map((signal) => <li key={signal.feature}><span>{FEATURE_LABELS[signal.feature] ?? signal.feature}</span><b>{signal.value.toFixed(2)}</b></li>)}</ul></> : <p className="muted">{t("ข้อมูลไม่เพียงพอ")}</p>}</section>)}</div></article>;
}

function PlayerEmpty({ status, message, mine }: { status: number; message: string; mine: boolean }) {
  const me = useQuery({ queryKey: ["me"], queryFn: auth.me, retry: false, staleTime: 5 * 60_000 });
  const guest = isGuest(me.data?.user);
  const needsSteam = status === 409;
  const { pathname } = useLocation();
  const { t } = useT();
  return <div className="pl-empty card"><h1>{needsSteam ? t("ยังไม่มีสถิติของตัวเอง") : t("ยังไม่มีสถิติของคุณ")}</h1><p className="muted">{t(message)}</p>{needsSteam && guest ? <><p className="muted">{t("My Stats ต้องใช้ Steam ID ที่ยืนยันจากบัญชี ไม่เดาจาก nickname")}</p><a className="btn-primary" href={`/auth/steam/login?next=${encodeURIComponent(pathname)}`}>{t("ล็อกอินด้วย Steam เพื่อดูสถิติของตัวเอง")}</a></> : needsSteam ? <Link className="btn-primary" to="/players?link=1">{t("ค้นหาและยืนยันผู้เล่นของคุณ")}</Link> : <>{mine && <p className="muted">{t("บัญชีเชื่อมกับ Steam แล้ว แต่ยังไม่มี demo ของ Steam ID นี้ในระบบ")}</p>}<Link className="btn-primary" to="/matches">{t("ไปหน้าแมตช์")}</Link></>}</div>;
}

const ARC = 2 * Math.PI * 52;
function Gauge({ value, max, label, unit = false }: { value: number; max: number; label: string; unit?: boolean }) {
  const ratio = Math.max(0, Math.min(1, value / max));
  const { t } = useT();
  return <svg className="pl-gauge" viewBox="0 0 120 120" role="img" aria-label={unit ? label : t("{v} จาก {max}", { v: label, max })}><circle cx="60" cy="60" r="52" className="pl-track" /><circle cx="60" cy="60" r="52" className="pl-arc" strokeDasharray={`${ratio * ARC} ${ARC}`} transform="rotate(-90 60 60)" /><text x="60" y="60" className="pl-gauge-v" textAnchor="middle" dominantBaseline="central">{label}</text></svg>;
}

function Donut({ label, value, won, lost, tone = "" }: { label: string; value: number | null; won: number; lost: number; tone?: string }) {
  const ratio = value ?? 0;
  const { t } = useT();
  return <div className={`pl-donut ${tone}`}><svg viewBox="0 0 120 120" role="img" aria-label={t("{label} {won} ชนะ {lost} แพ้", { label, won, lost })}><circle cx="60" cy="60" r="52" className="pl-track" /><circle cx="60" cy="60" r="52" className="pl-arc" strokeDasharray={`${ratio * ARC} ${ARC}`} transform="rotate(-90 60 60)" /><text x="60" y="54" className="pl-gauge-v" textAnchor="middle" dominantBaseline="central">{value == null ? "—" : `${Math.round(ratio * 100)}%`}</text><text x="60" y="78" className="pl-gauge-s" textAnchor="middle" dominantBaseline="central">{won} FK · {lost} FD</text></svg><span>{label}</span></div>;
}

function MiniPie({ label, wins, attempts }: { label: string; wins: number; attempts: number }) {
  const ratio = attempts ? wins / attempts : 0;
  const { t } = useT();
  return <div className={`pl-pie${attempts ? "" : " none"}`}><svg viewBox="0 0 120 120" role="img" aria-label={t("{label} ชนะ {wins} จาก {attempts}", { label, wins, attempts })}><circle cx="60" cy="60" r="52" className="pl-track" /><circle cx="60" cy="60" r="52" className="pl-arc" strokeDasharray={`${ratio * ARC} ${ARC}`} transform="rotate(-90 60 60)" /><text x="60" y="60" className="pl-gauge-v" textAnchor="middle" dominantBaseline="central">{attempts ? wins : "—"}</text></svg><span>{label}</span><span className="muted small">{attempts ? `${wins}/${attempts}` : t("ไม่มี")}</span></div>;
}

interface BarRow { key: string; label: string; value: number; note: string; ratio: number }
function Bars({ rows, empty }: { rows: BarRow[]; empty: string }) {
  if (!rows.length) return <p className="muted small">{empty}</p>;
  const top = Math.max(...rows.map((row) => row.value), 1);
  return <ul className="pl-bars">{rows.map((row) => <li key={row.key}><span className="pl-bl">{row.label}</span><span className="pl-bv">{row.value}</span><span className="pl-bar"><i style={{ width: `${(row.value / top) * 100}%` }} /></span><span className="muted small">{row.note}</span></li>)}</ul>;
}
