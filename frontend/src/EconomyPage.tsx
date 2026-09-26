import { useLayoutEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Navigate, useParams } from "react-router-dom";
import { api, matchesQuery, type MatchEconomy, type TeamBuy } from "./api";
import { useT } from "./i18n";
import { Breadcrumb, endReasonLabel, MapThumb, MatchTabs, matchTitle, NotFound, num } from "./utils";

// ================================================================================================
// เศรษฐกิจของแมตช์: /matches/{demo_file}/economy
// ================================================================================================
/**
 * ตอบคำถามโค้ชสามข้อ ตามลำดับที่ถาม:
 *   1. ซื้อแบบไหนแล้วชนะกี่รอบ          (ผลรอบตามประเภทการซื้อ — กรองฝั่งได้)
 *   2. ของสองทีมห่างกันแค่ไหนแต่ละรอบ   (มูลค่าอุปกรณ์ + ส่วนต่าง)
 *   3. รอบไหนซื้ออะไร ใครชนะ            (รายรอบ แบบกระจกซ้าย-ขวา)
 *
 * ประเภทการซื้อ "ทั้งทีม" มาจาก view round_economy ที่เดียว (backend ผูกฝั่งกับทีมให้แล้ว)
 * สีของทีมเป็นคู่ทอง/ม่วง ไม่ใช่ฟ้า/ส้ม เพราะฟ้า/ส้มในแอปนี้แปลว่า "ฝั่ง" CT/T และทีมสลับฝั่งตอนพักครึ่ง
 * สีของประเภทการซื้อไล่เขียวอ่อน -> เข้มตามเงินที่ใช้ (ปืนสั้นเป็นเทาเพราะเป็นรอบบังคับ ไม่ใช่การเลือก)
 */
const BUY_LABEL: Record<TeamBuy, string> = {
  pistol: "ปืนสั้น",
  eco: "Eco",
  semi_eco: "Semi-eco",
  semi_buy: "Semi-buy",
  full: "Full buy",
};
const BUY_FILL: Record<TeamBuy, string> = {
  pistol: "#94a3b8", eco: "#d3ecd9", semi_eco: "#9fd4ac", semi_buy: "#4fa872", full: "#1f6b43",
};
const BUY_INK: Record<TeamBuy, string> = {
  pistol: "#1e293b", eco: "#14351f", semi_eco: "#14351f", semi_buy: "#ffffff", full: "#ffffff",
};
const BUY_RULE = "ทั้งทีมรวมกัน ≤ $5,000 = Eco · ≤ $10,000 = Semi-eco · ≤ $20,000 = Semi-buy · มากกว่านั้น = Full buy · รอบ 1 และ 13 = ปืนสั้นเสมอ";
const TEAM_COLOR = ["#b98300", "#6a55e0"];
type Side = "all" | "ct" | "t";

const money = (v: number | null | undefined) => (v == null ? "—" : `$${num(v)}`);

export function EconomyPage() {
  const { t } = useT();
  const { demo } = useParams();
  const matches = useQuery(matchesQuery);
  const entry = demo ? (matches.data ?? []).find((m) => m.demo_file === demo) : undefined;
  const q = useQuery({
    queryKey: ["economy", demo],
    queryFn: () => api.economy(demo!),
    enabled: !!entry && entry.status === "done",
    staleTime: 5 * 60_000,
  });

  if (matches.error) return <p className="err">{t("โหลดรายการแมตช์ไม่ได้: {msg}", { msg: (matches.error as Error).message })}</p>;
  if (!matches.data) return <p className="muted">{t("กำลังโหลด…")}</p>;
  if (!entry) return <NotFound title={t("ไม่พบแมตช์นี้")} detail={t("ไม่มีแมตช์ {demo} ในระบบ", { demo: demo ?? "" })} />;
  if (entry.status !== "done") return <Navigate to={`/matches/${encodeURIComponent(entry.demo_file)}`} replace />;

  const d = q.data;
  const ready = d && d.teams.length === 2 && d.rounds.length > 0;
  return (
    <div className="econ-page" data-testid="economy-page">
      <Breadcrumb items={[{ label: t("แมตช์"), to: "/matches" }, { label: matchTitle(entry) }]} />
      <div className="page-head mt-head">
        <MapThumb map={entry.map_name} className="mh-thumb" />
        <div>
          <h1>{matchTitle(entry)}</h1>
          <p className="muted small">{entry.map_name} · {t("{n} รอบ", { n: num(entry.rounds) })}</p>
        </div>
      </div>
      <MatchTabs demo={entry.demo_file} />

      {q.isLoading && <p className="muted">{t("กำลังโหลดเศรษฐกิจ…")}</p>}
      {q.error && <p className="err">{t("โหลดข้อมูลไม่ได้: {msg}", { msg: (q.error as Error).message })}</p>}
      {d && !ready && <p className="muted card">{t("แมตช์นี้ไม่มีข้อมูลมูลค่าอุปกรณ์รายรอบ (เดโมรุ่นเก่า) — โหลดเดโมซ้ำเพื่อคำนวณ")}</p>}
      {ready && (
        <>
          <div className="econ-teams" aria-label={t("สีของทีม")}>
            {d.teams.map((team, i) => (
              <span key={team}><i style={{ background: TEAM_COLOR[i] }} />{i === 0 ? t("{team} (เริ่มฝั่ง CT)", { team }) : t("{team} (เริ่มฝั่ง T)", { team })}</span>
            ))}
          </div>
          <OutcomeByBuy data={d} />
          <section className="card">
            <div className="card-head">
              <h2>{t("มูลค่าอุปกรณ์ทั้งทีม")}</h2>
              <span className="muted small">{t("ตอนหมดเวลาซื้อของ · แถบล่างคือทีมที่ชนะรอบนั้น")}</span>
            </div>
            <EquipLines data={d} />
          </section>
          <section className="card">
            <div className="card-head">
              <h2>{t("ใครมีของมากกว่า")}</h2>
              <span className="muted small">{t("ส่วนต่างมูลค่าอุปกรณ์ · แท่งขึ้น = {a} มากกว่า · แท่งลง = {b} มากกว่า", { a: d.teams[0], b: d.teams[1] })}</span>
            </div>
            <AdvantageBars data={d} />
          </section>
          <RoundBreakdown data={d} />
        </>
      )}
    </div>
  );
}

// ------------------------------------------------------------------ 1. ผลรอบตามประเภทการซื้อ
function OutcomeByBuy({ data }: { data: MatchEconomy }) {
  const { t } = useT();
  const [side, setSide] = useState<Side>("all");
  return (
    <section className="card" data-testid="econ-outcomes">
      <div className="card-head">
        <h2>{t("ซื้อแบบไหน ชนะกี่รอบ")}</h2>
        <div className="seg" role="group" aria-label={t("ฝั่ง")}>
          {(["all", "ct", "t"] as const).map((s) => (
            <button key={s} type="button" className={`seg-btn${side === s ? " on" : ""}`} aria-pressed={side === s}
              onClick={() => setSide(s)}>
              {t(s === "all" ? "ทั้งสองฝั่ง" : s === "ct" ? "ตอนเป็น CT" : "ตอนเป็น T")}
            </button>
          ))}
        </div>
      </div>
      <div className="econ-outcomes">
        {data.teams.map((team, i) => {
          const mine = data.rounds.map((r) => r.teams[team]).filter((x) => x && (side === "all" || x.side === side));
          return (
            <div key={team} className="eo-team">
              <h3><i style={{ background: TEAM_COLOR[i] }} />{team}</h3>
              <ul className="eo-rows">
                {data.buy_types.map((b) => {
                  const rs = mine.filter((x) => x.buy_type === b);
                  const won = rs.filter((x) => x.won).length;
                  const lost = rs.length - won;
                  return (
                    <li key={b} className={rs.length ? "" : "empty"}>
                      <span className="eo-label"><i style={{ background: BUY_FILL[b] }} />{t(BUY_LABEL[b])}</span>
                      <b className="eo-pct">{rs.length ? `${Math.round((won / rs.length) * 100)}%` : "—"}</b>
                      <span className="eo-bar" aria-hidden="true">
                        {rs.length > 0 && (
                          <>
                            <i className="w" style={{ flexGrow: won }} />
                            <i className="l" style={{ flexGrow: lost }} />
                          </>
                        )}
                      </span>
                      <span className="eo-n small muted">
                        {rs.length ? t("ชนะ {won} · แพ้ {lost}", { won, lost }) : t("ไม่มีรอบแบบนี้")}
                      </span>
                    </li>
                  );
                })}
              </ul>
            </div>
          );
        })}
      </div>
      <p className="muted small econ-rule">{t(BUY_RULE)}</p>
    </section>
  );
}

// ------------------------------------------------------------------ กราฟ: ความกว้างจริงของกล่อง
/** วาด SVG ที่ความกว้างจริงเป็นพิกเซล — ตัวหนังสือบนแกนไม่ย่อตามจอจนอ่านไม่ออก (ต่างจาก viewBox ยืด) */
function useWidth<E extends HTMLElement>() {
  const ref = useRef<E>(null);
  const [w, setW] = useState(0);
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    setW(el.getBoundingClientRect().width);
    const ro = new ResizeObserver(([e]) => setW(e.contentRect.width));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  return [ref, w] as const;
}

const PAD = { l: 58, r: 14, t: 12, b: 46 };
const niceMax = (v: number) => Math.max(10000, Math.ceil(v / 10000) * 10000);
const kFmt = (v: number) => (v === 0 ? "0" : `${v / 1000}K`);

function xScale(n: number, w: number) {
  const inner = w - PAD.l - PAD.r;
  return (i: number) => PAD.l + (n <= 1 ? inner / 2 : (i * inner) / (n - 1));
}
/** เลขรอบบนแกน x — จอแคบแสดงเว้นทีละ 2 / 3 รอบ ไม่ให้ทับกัน */
const tickEvery = (n: number, w: number) => Math.max(1, Math.ceil((n * 22) / Math.max(1, w - PAD.l - PAD.r)));
/** เส้นพักครึ่ง: ระหว่างรอบ 12 กับ 13 */
const halfIndex = (data: MatchEconomy) => data.rounds.findIndex((r) => r.round_num === 13);

// ------------------------------------------------------------------ 2. มูลค่าอุปกรณ์ (เส้น)
function EquipLines({ data }: { data: MatchEconomy }) {
  const { t } = useT();
  const [ref, w] = useWidth<HTMLDivElement>();
  const H = 280;
  const n = data.rounds.length;
  const vals = data.teams.map((tm) => data.rounds.map((r) => r.teams[tm]?.equip ?? null));
  const max = niceMax(Math.max(...vals.flat().map((v) => v ?? 0)));
  const x = xScale(n, w);
  const y = (v: number) => PAD.t + (1 - v / max) * (H - PAD.t - PAD.b - 16);
  const base = y(0);
  const every = tickEvery(n, w);
  const half = halfIndex(data);
  return (
    <div ref={ref} className="econ-chart">
      {w > 0 && (
        <svg width={w} height={H} role="img" aria-label={t("กราฟมูลค่าอุปกรณ์ทั้งทีมรายรอบ")}>
          {Array.from({ length: max / 10000 + 1 }, (_, k) => k * 10000).map((v) => (
            <g key={v}>
              <line x1={PAD.l} x2={w - PAD.r} y1={y(v)} y2={y(v)} className="gl" />
              <text x={PAD.l - 8} y={y(v) + 4} textAnchor="end" className="ax">{kFmt(v)}</text>
            </g>
          ))}
          {half > 0 && <line x1={(x(half - 1) + x(half)) / 2} x2={(x(half - 1) + x(half)) / 2} y1={PAD.t} y2={base} className="half" />}
          {vals.map((vs, ti) => (
            <g key={ti}>
              <polyline fill="none" stroke={TEAM_COLOR[ti]} strokeWidth={2.5} strokeLinejoin="round"
                points={vs.map((v, i) => (v == null ? null : `${x(i)},${y(v)}`)).filter(Boolean).join(" ")} />
              {vs.map((v, i) => v != null && (
                <circle key={i} cx={x(i)} cy={y(v)} r={3.5} fill="#fff" stroke={TEAM_COLOR[ti]} strokeWidth={2}>
                  <title>{t("รอบ {n} · {team} {v}", { n: data.rounds[i].round_num, team: data.teams[ti], v: money(v) })}</title>
                </circle>
              ))}
            </g>
          ))}
          {/* แถบผู้ชนะใต้แกน — สีของทีมที่ชนะรอบนั้น */}
          {data.rounds.map((r, i) => {
            const ti = r.winner_team ? data.teams.indexOf(r.winner_team) : -1;
            const bw = Math.max(4, Math.min(14, (w - PAD.l - PAD.r) / n - 3));
            return (
              <g key={r.round_num}>
                <rect x={x(i) - bw / 2} y={base + 6} width={bw} height={6} rx={1.5}
                  fill={ti >= 0 ? TEAM_COLOR[ti] : "#cbd5e1"}>
                  <title>{t("รอบ {n} · {team} ชนะ · {reason}", { n: r.round_num, team: r.winner_team ?? "?", reason: endReasonLabel(r.end_reason) })}</title>
                </rect>
                {(i % every === 0 || i === n - 1) && (
                  <text x={x(i)} y={base + 28} textAnchor="middle" className="ax">{r.round_num}</text>
                )}
              </g>
            );
          })}
          <text x={PAD.l} y={H - 4} className="ax">{t("รอบ")}</text>
        </svg>
      )}
    </div>
  );
}

// ------------------------------------------------------------------ 3. ส่วนต่าง (แท่งขึ้น-ลง)
function AdvantageBars({ data }: { data: MatchEconomy }) {
  const { t } = useT();
  const [ref, w] = useWidth<HTMLDivElement>();
  const H = 240;
  const [a, b] = data.teams;
  const diffs = data.rounds.map((r) => {
    const va = r.teams[a]?.equip;
    const vb = r.teams[b]?.equip;
    return va == null || vb == null ? null : va - vb;
  });
  const lim = niceMax(Math.max(...diffs.map((v) => Math.abs(v ?? 0))));
  const n = data.rounds.length;
  const inner = w - PAD.l - PAD.r;
  const slot = inner / Math.max(1, n);
  const cx = (i: number) => PAD.l + slot * (i + 0.5);
  const y = (v: number) => PAD.t + ((lim - v) / (2 * lim)) * (H - PAD.t - PAD.b);
  const every = tickEvery(n, w);
  const half = halfIndex(data);
  const steps = [-lim, -lim / 2, 0, lim / 2, lim];
  return (
    <div ref={ref} className="econ-chart">
      {w > 0 && (
        <svg width={w} height={H} role="img" aria-label={t("กราฟส่วนต่างมูลค่าอุปกรณ์รายรอบ")}>
          {steps.map((v) => (
            <g key={v}>
              <line x1={PAD.l} x2={w - PAD.r} y1={y(v)} y2={y(v)} className={v === 0 ? "zero" : "gl"} />
              <text x={PAD.l - 8} y={y(v) + 4} textAnchor="end" className="ax">
                {v === 0 ? "0" : `${v > 0 ? "+" : "−"}${kFmt(Math.abs(v))}`}
              </text>
            </g>
          ))}
          {half > 0 && <line x1={PAD.l + slot * half} x2={PAD.l + slot * half} y1={PAD.t} y2={H - PAD.b} className="half" />}
          {diffs.map((v, i) => {
            if (v == null) return null;
            const bw = Math.max(3, slot * 0.62);
            const top = Math.min(y(v), y(0));
            const lead = v >= 0 ? a : b;
            return (
              <rect key={i} x={cx(i) - bw / 2} y={top} width={bw} height={Math.max(1, Math.abs(y(v) - y(0)))} rx={2}
                fill={TEAM_COLOR[v >= 0 ? 0 : 1]}>
                <title>{t("รอบ {n} · {team} มากกว่า {v}", { n: data.rounds[i].round_num, team: lead, v: money(Math.abs(v)) })}</title>
              </rect>
            );
          })}
          {data.rounds.map((r, i) => (i % every === 0 || i === n - 1) && (
            <text key={r.round_num} x={cx(i)} y={H - PAD.b + 18} textAnchor="middle" className="ax">{r.round_num}</text>
          ))}
          <text x={PAD.l} y={H - 4} className="ax">{t("รอบ")}</text>
        </svg>
      )}
    </div>
  );
}

// ------------------------------------------------------------------ 4. รายรอบ (กระจกซ้าย-ขวา)
function RoundBreakdown({ data }: { data: MatchEconomy }) {
  const { t } = useT();
  const [a, b] = data.teams;
  const max = Math.max(1, ...data.rounds.flatMap((r) => [r.teams[a]?.equip ?? 0, r.teams[b]?.equip ?? 0]));
  const share = (team: string) => {
    const rs = data.rounds.map((r) => r.teams[team]?.buy_type).filter(Boolean);
    return data.buy_types.map((bt) => ({ bt, pct: rs.length ? Math.round((rs.filter((x) => x === bt).length / rs.length) * 100) : 0 }));
  };
  const Bar = ({ team, r, dir }: { team: string; r: MatchEconomy["rounds"][number]; dir: "l" | "r" }) => {
    const x = r.teams[team];
    if (!x || x.equip == null || !x.buy_type) return <span className="rb-bar-wrap" />;
    return (
      <span className={`rb-bar-wrap ${dir}`}>
        <span className="rb-bar"
          style={{ width: `${Math.max(8, (x.equip / max) * 100)}%`, background: BUY_FILL[x.buy_type], color: BUY_INK[x.buy_type] }}
          title={t(x.won ? "{team} · {buy} · {money} · ฝั่ง {side} · ชนะ" : "{team} · {buy} · {money} · ฝั่ง {side}",
            { team, buy: t(BUY_LABEL[x.buy_type]), money: money(x.equip), side: x.side.toUpperCase() })}>
          {money(x.equip)}
        </span>
      </span>
    );
  };
  return (
    <section className="card" data-testid="econ-breakdown">
      <div className="card-head">
        <h2>{t("รายรอบ")}</h2>
        <span className="muted small">{t("สีแท่ง = ประเภทการซื้อ · ● = ทีมที่ชนะรอบนั้น")}</span>
      </div>
      <div className="rb-share">
        {[a, b].map((team, i) => (
          <div key={team} className="rb-share-team">
            <h3><i style={{ background: TEAM_COLOR[i] }} />{team}</h3>
            <ul>
              {share(team).map(({ bt, pct }) => (
                <li key={bt}><i style={{ background: BUY_FILL[bt] }} /><b>{pct}%</b><span>{t(BUY_LABEL[bt])}</span></li>
              ))}
            </ul>
          </div>
        ))}
      </div>
      <ol className="rb-rows">
        {data.rounds.map((r) => (
          <li key={r.round_num} className={r.round_num === 13 ? "after-half" : ""}>
            <Bar team={a} r={r} dir="l" />
            <span className="rb-mid" title={t("{team} ชนะ · {reason}", { team: r.winner_team ?? "?", reason: endReasonLabel(r.end_reason) })}>
              <i className={r.winner_team === a ? "on" : ""} style={{ background: r.winner_team === a ? TEAM_COLOR[0] : undefined }} />
              <b>{r.round_num}</b>
              <i className={r.winner_team === b ? "on" : ""} style={{ background: r.winner_team === b ? TEAM_COLOR[1] : undefined }} />
            </span>
            <Bar team={b} r={r} dir="r" />
          </li>
        ))}
      </ol>
      <ul className="rb-legend small">
        {data.buy_types.map((bt) => <li key={bt}><i style={{ background: BUY_FILL[bt] }} />{t(BUY_LABEL[bt])}</li>)}
      </ul>
    </section>
  );
}
