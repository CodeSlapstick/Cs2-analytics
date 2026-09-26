import { useQuery } from "@tanstack/react-query";
import { Link, useLocation, useParams } from "react-router-dom";
import { ApiError, auth, isGuest, playerApi, type PlayerMap, type PlayerWeapon } from "./api";
import { MapThumb, NotFound, num, weaponLabel } from "./utils";
import unknownAvatar from "./assets/avatar-unknown.jpg";
import { useT } from "./i18n";

/**
 * หน้าสถิติรายคน — ทุกตัวเลขมาจากเดโมที่โหลดเข้าระบบเท่านั้น
 *   /player                 = คนที่ล็อกอินอยู่ (ต้องล็อกอินด้วย Steam — โหมดเยี่ยมชมไม่มี "ฉัน")
 *   /player/{steamid64}     = ผู้เล่นคนใดก็ได้ที่อยู่ในเดโมที่โหลดไว้ (โหมดเยี่ยมชมดูได้ตามปกติ)
 */
export function PlayerPage() {
  const { steamId } = useParams();
  const who = steamId ?? "me";
  const { t, tn } = useT();
  const summary = useQuery({ queryKey: ["player", who], queryFn: () => playerApi.summary(who), retry: false });
  const matches = useQuery({ queryKey: ["player-matches", who], queryFn: () => playerApi.matches(who), retry: false, enabled: !!summary.data });
  const maps = useQuery({ queryKey: ["player-maps", who], queryFn: () => playerApi.maps(who), retry: false, enabled: !!summary.data });
  const weapons = useQuery({ queryKey: ["player-weapons", who], queryFn: () => playerApi.weapons(who), retry: false, enabled: !!summary.data });

  if (summary.isLoading) return <p className="muted">{t("กำลังโหลดสถิติ…")}</p>;
  if (summary.error instanceof ApiError) {
    return <PlayerEmpty status={summary.error.status} message={summary.error.message} mine={!steamId} />;
  }
  if (summary.error) return <p className="err">{t("โหลดสถิติไม่ได้: {msg}", { msg: t((summary.error as Error).message) })}</p>;
  if (!summary.data) return <NotFound title="ไม่พบผู้เล่นคนนี้" />;

  const d = summary.data;
  const tot = d.totals;
  const record = matches.data
    ? {
        win: matches.data.filter((m) => m.result === "win").length,
        loss: matches.data.filter((m) => m.result === "loss").length,
        draw: matches.data.filter((m) => m.result === "draw").length,
      }
    : null;
  const entryRate = (e: { kills: number; deaths: number }) => (e.kills + e.deaths > 0 ? e.kills / (e.kills + e.deaths) : null);

  return (
    <div className="player" data-testid="player-page">
      <header className="pl-head">
        {d.player.avatar ? <img className="pl-avatar" src={d.player.avatar} alt="" /> : <img className="pl-avatar" src={unknownAvatar} alt="" />}
        <div>
          <h1>{d.player.name}</h1>
          <p className="muted">
            {t("จาก {n} แมตช์ที่โหลดเข้าระบบ", { n: num(d.source.matches) })}
            {d.player.linked_account && <> · {t("บัญชีในระบบ: {account}", { account: d.player.linked_account })}</>}
          </p>
        </div>
      </header>

      <section className="pl-grid" aria-label={t("ภาพรวม")}>
        <article className="card pl-card">
          <h2>K/D</h2>
          <Gauge value={tot.kd} max={2} label={tot.kd.toFixed(2)} />
          <p className="muted small">
            {t("{k} คิล · {d} ตาย · {a} ช่วย", { k: tot.kills, d: tot.deaths, a: tot.assists })}
          </p>
        </article>

        <article className="card pl-card">
          <h2>Rating 1.0</h2>
          <Gauge value={tot.rating} max={2} label={tot.rating.toFixed(2)} />
          <p className="muted small">
            {tn("Rating 2.0 (ประมาณการ): {v}", { v: <b>{d.rating2_approx.toFixed(2)}</b> })}
            <br />
            {t("HLTV ไม่เปิดสูตร 2.0 — ค่านี้เป็นสูตรประมาณของชุมชน")}
          </p>
        </article>

        <article className="card pl-card pl-wide">
          <h2>Clutch 1v1 – 1v5</h2>
          {d.clutches.length === 0 ? (
            <p className="muted small">{t("ยังไม่เจอสถานการณ์ clutch ในเดโมที่โหลดไว้")}</p>
          ) : (
            <div className="pl-clutches">
              {[1, 2, 3, 4, 5].map((vs) => {
                const c = d.clutches.find((x) => x.vs === vs) ?? { vs, attempts: 0, wins: 0 };
                return <MiniPie key={vs} label={`1v${vs}`} wins={c.wins} attempts={c.attempts} />;
              })}
            </div>
          )}
        </article>

        <article className="card pl-card">
          <h2>{t("ชนะรอบ (round win rate)")}</h2>
          <Gauge value={tot.win_rate} max={100} label={`${tot.win_rate.toFixed(0)}%`} unit />
          <p className="muted small">
            {t("{r} รอบใน {m} แมตช์", { r: tot.rounds, m: tot.matches })}
            {record && (
              <>
                <br />
                {t("แมตช์: ชนะ {w} · แพ้ {l}", { w: record.win, l: record.loss })}
                {record.draw > 0 && <> · {t("เสมอ {n}", { n: record.draw })}</>}
              </>
            )}
          </p>
        </article>

        <article className="card pl-card">
          <h2>HS% · ADR · KAST</h2>
          <ul className="pl-nums">
            <li>
              <b>{tot.hs_rate.toFixed(0)}%</b>
              <span>{t("หัว ({hs} จาก {k})", { hs: tot.headshots, k: tot.kills })}</span>
            </li>
            <li>
              <b>{tot.adr.toFixed(1)}</b>
              <span>ADR</span>
            </li>
            <li>
              <b>{tot.kast.toFixed(0)}%</b>
              <span>KAST</span>
            </li>
            <li>
              <b>{tot.survival_rate.toFixed(0)}%</b>
              <span>{t("รอดจบรอบ")}</span>
            </li>
          </ul>
        </article>

        <article className="card pl-card pl-wide">
          <h2>{t("Entry — คิลแรกของรอบ")}</h2>
          <div className="pl-donuts">
            <Donut label={t("รวม")} value={entryRate(d.entry.both)} won={d.entry.both.kills} lost={d.entry.both.deaths} />
            <Donut label={t("ฝั่ง T")} value={entryRate(d.entry.t)} won={d.entry.t.kills} lost={d.entry.t.deaths} tone="t" />
            <Donut label={t("ฝั่ง CT")} value={entryRate(d.entry.ct)} won={d.entry.ct.kills} lost={d.entry.ct.deaths} tone="ct" />
          </div>
          <p className="muted small">{t("นับเฉพาะรอบที่ผู้เล่นคนนี้เป็นคนเปิดรอบ (คิลแรก) หรือเป็นคนแรกที่ตาย")}</p>
        </article>
      </section>

      <section className="pl-panels">
        <article className="card">
          <h2>{t("แมตช์ล่าสุด")}</h2>
          {matches.data?.length ? (
            <ul className="pl-matches">
              {matches.data.map((m) => (
                <li key={m.match_id} className={`r-${m.result}`}>
                  <Link to={`/matches/${encodeURIComponent(m.demo_file)}/rounds/1`}>
                    <MapThumb map={m.map_name} className="pl-thumb" />
                    <span className="pl-res">{m.result === "win" ? t("ชนะ") : m.result === "loss" ? t("แพ้") : t("เสมอ")}</span>
                    <span className="pl-mt">
                      {m.team_a && m.team_b ? `${m.team_a} vs ${m.team_b}` : m.demo_file}
                      <span className="muted small"> · {m.map_name} · {t("{won}/{total} รอบ", { won: m.rounds_won, total: m.rounds })}</span>
                    </span>
                    <span className="pl-rt">{Number(m.rating).toFixed(2)}</span>
                  </Link>
                </li>
              ))}
            </ul>
          ) : (
            <p className="muted small">{matches.isLoading ? t("กำลังโหลด…") : t("ยังไม่มีแมตช์")}</p>
          )}
        </article>

        <article className="card">
          <h2>{t("แมพที่เล่นบ่อย")}</h2>
          <Bars
            rows={(maps.data ?? []).map((m: PlayerMap) => ({
              key: m.map_name,
              label: m.map_name,
              value: m.matches,
              note: t("ชนะ {w}/{n} · rating {r}", { w: m.wins, n: m.matches, r: Number(m.rating).toFixed(2) }),
              ratio: m.win_rate / 100,
            }))}
            empty={maps.isLoading ? t("กำลังโหลด…") : t("ยังไม่มีข้อมูลแมพ")}
          />
        </article>

        <article className="card">
          <h2>{t("อาวุธที่ฆ่าบ่อย")}</h2>
          <Bars
            rows={(weapons.data ?? []).map((w: PlayerWeapon) => ({
              key: w.weapon,
              label: weaponLabel(w.weapon),
              value: w.kills,
              note: t("หัว {pct}% ({n})", { pct: w.hs_rate.toFixed(0), n: w.headshots }),
              ratio: w.hs_rate / 100,
            }))}
            empty={weapons.isLoading ? t("กำลังโหลด…") : t("ยังไม่มีข้อมูลอาวุธ")}
          />
        </article>
      </section>
    </div>
  );
}

/** ยังไม่ผูก Steam (409) หรือไม่มีข้อมูลในเดโม (404) — บอกตรง ๆ ว่าทำอะไรต่อ ไม่โชว์ตัวเลขปลอม */
/**
 * ไม่มีสถิติให้แสดง — แยกสองเหตุคนละเรื่องออกจากกัน
 *   409  ไม่มี "ฉัน" ให้ชี้ (โหมดเยี่ยมชม หรือบัญชีที่ไม่มี steam_id) -> ทางออกคือล็อกอิน Steam
 *   404  มี "ฉัน" แต่ยังไม่มีเดโมที่คนนี้ลงเล่น                        -> ทางออกคืออัปโหลดเดโม
 */
function PlayerEmpty({ status, message, mine }: { status: number; message: string; mine: boolean }) {
  const me = useQuery({ queryKey: ["me"], queryFn: auth.me, retry: false, staleTime: 5 * 60_000 });
  const guest = isGuest(me.data?.user);
  const needsSteam = status === 409;
  const { pathname } = useLocation();
  const { t } = useT();

  return (
    <div className="pl-empty card" data-testid="player-empty" data-reason={needsSteam ? "no-steam" : "no-data"}>
      <h1>{needsSteam ? t("ยังไม่มีสถิติของตัวเอง") : t("ยังไม่มีสถิติของคุณ")}</h1>
      <p className="muted">{t(message)}</p>

      {needsSteam && guest && (
        <>
          <p className="muted">
            {t("คุณกำลังใช้โหมดเยี่ยมชม ซึ่งไม่ผูกกับบัญชี Steam จึงยังไม่รู้ว่า \"คุณ\" คือผู้เล่นคนไหนในเดโม — ล็อกอินด้วย Steam แล้วสถิติของตัวเองจะขึ้นเองถ้ามีเดโมที่คุณลงเล่นอยู่ในระบบ")}
          </p>
          <a className="btn-primary" href={`/auth/steam/login?next=${encodeURIComponent(pathname)}`}>
            {t("ล็อกอินด้วย Steam เพื่อดูสถิติของตัวเอง")}
          </a>
          <p className="muted small">{t("ระหว่างนี้ยังเปิดดูสถิติของผู้เล่นคนอื่นได้จากสกอร์บอร์ดในหน้าสรุปแมตช์")}</p>
        </>
      )}

      {needsSteam && !guest && (
        <a className="btn-primary" href={`/auth/steam/login?next=${encodeURIComponent(pathname)}`}>
          {t("ล็อกอินด้วย Steam")}
        </a>
      )}

      {!needsSteam && (
        <>
          {mine && (
            <p className="muted">
              {t("สถิติจะขึ้นเมื่อมีเดโมที่คุณลงเล่นอยู่ในระบบ — อัปโหลดเดโมของทีมที่หน้าแมตช์ แล้วกลับมาที่หน้านี้")}
            </p>
          )}
          <Link className="btn-primary" to="/matches">
            {t("ไปหน้าแมตช์")}
          </Link>
        </>
      )}
    </div>
  );
}

// ------------------------------------------------------------------ กราฟวาดเอง (SVG) — ไม่ใช้ไลบรารีกราฟ
const ARC = 2 * Math.PI * 52;

/** เกจวงกลม: สีไล่แดง -> เหลือง -> เขียว ตามสัดส่วนของค่าเทียบ max */
function Gauge({ value, max, label, unit = false }: { value: number; max: number; label: string; unit?: boolean }) {
  const ratio = Math.max(0, Math.min(1, value / max));
  const hue = Math.round(8 + ratio * 122); // 8 = แดง, 130 = เขียว
  const { t } = useT();
  return (
    <svg className="pl-gauge" viewBox="0 0 120 120" role="img" aria-label={unit ? label : t("{v} จาก {max}", { v: label, max })}>
      <circle cx="60" cy="60" r="52" className="pl-track" />
      <circle
        cx="60"
        cy="60"
        r="52"
        className="pl-arc"
        style={{ stroke: `hsl(${hue} 85% 55%)` }}
        strokeDasharray={`${ratio * ARC} ${ARC}`}
        transform="rotate(-90 60 60)"
      />
      <text x="60" y="60" className="pl-gauge-v" textAnchor="middle" dominantBaseline="central">
        {label}
      </text>
    </svg>
  );
}

/** โดนัท entry: ส่วนสีคือคิลแรกที่ชนะ ส่วนจางคือที่ตายก่อน */
function Donut({ label, value, won, lost, tone = "" }: { label: string; value: number | null; won: number; lost: number; tone?: string }) {
  const ratio = value ?? 0;
  const { t } = useT();
  return (
    <div className={`pl-donut ${tone}`}>
      <svg viewBox="0 0 120 120" role="img" aria-label={t("{label} {won} ชนะ {lost} แพ้", { label, won, lost })}>
        <circle cx="60" cy="60" r="52" className="pl-track" />
        <circle cx="60" cy="60" r="52" className="pl-arc" strokeDasharray={`${ratio * ARC} ${ARC}`} transform="rotate(-90 60 60)" />
        <text x="60" y="54" className="pl-gauge-v" textAnchor="middle" dominantBaseline="central">
          {value === null ? "—" : `${Math.round(ratio * 100)}%`}
        </text>
        <text x="60" y="78" className="pl-gauge-s" textAnchor="middle" dominantBaseline="central">
          {won}W {lost}L
        </text>
      </svg>
      <span>{label}</span>
    </div>
  );
}

/** พายเล็กของ clutch 1vN */
function MiniPie({ label, wins, attempts }: { label: string; wins: number; attempts: number }) {
  const ratio = attempts > 0 ? wins / attempts : 0;
  const { t } = useT();
  return (
    <div className={`pl-pie${attempts === 0 ? " none" : ""}`}>
      <svg viewBox="0 0 120 120" role="img" aria-label={t("{label} ชนะ {wins} จาก {attempts}", { label, wins, attempts })}>
        <circle cx="60" cy="60" r="52" className="pl-track" />
        <circle cx="60" cy="60" r="52" className="pl-arc" strokeDasharray={`${ratio * ARC} ${ARC}`} transform="rotate(-90 60 60)" />
        <text x="60" y="60" className="pl-gauge-v" textAnchor="middle" dominantBaseline="central">
          {attempts === 0 ? "—" : wins}
        </text>
      </svg>
      <span>{label}</span>
      <span className="muted small">{attempts === 0 ? t("ไม่มี") : `${wins}/${attempts}`}</span>
    </div>
  );
}

interface BarRow {
  key: string;
  label: string;
  value: number;
  note: string;
  ratio: number;
}

/** แถบสัดส่วน: ความยาวแถบ = ค่าเทียบกับแถวที่มากที่สุด */
function Bars({ rows, empty }: { rows: BarRow[]; empty: string }) {
  if (rows.length === 0) return <p className="muted small">{empty}</p>;
  const top = Math.max(...rows.map((r) => r.value), 1);
  return (
    <ul className="pl-bars">
      {rows.map((r) => (
        <li key={r.key}>
          <span className="pl-bl">{r.label}</span>
          <span className="pl-bv">{r.value}</span>
          <span className="pl-bar">
            <i style={{ width: `${(r.value / top) * 100}%` }} />
          </span>
          <span className="muted small">{r.note}</span>
        </li>
      ))}
    </ul>
  );
}
