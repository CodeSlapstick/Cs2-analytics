import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { ApiError, playerApi, type PlayerMap, type PlayerWeapon } from "./api";
import { NotFound, weaponLabel } from "./utils";

/**
 * หน้าสถิติรายคน — ทุกตัวเลขมาจากเดโมที่โหลดเข้าระบบเท่านั้น
 *   /player                 = คนที่ล็อกอินอยู่ (ต้องล็อกอินด้วย Steam)
 *   /player/{steamid64}     = ผู้เล่นคนใดก็ได้ที่อยู่ในเดโมที่โหลดไว้
 */
export function PlayerPage() {
  const { steamId } = useParams();
  const who = steamId ?? "me";
  const summary = useQuery({ queryKey: ["player", who], queryFn: () => playerApi.summary(who), retry: false });
  const matches = useQuery({ queryKey: ["player-matches", who], queryFn: () => playerApi.matches(who), retry: false, enabled: !!summary.data });
  const maps = useQuery({ queryKey: ["player-maps", who], queryFn: () => playerApi.maps(who), retry: false, enabled: !!summary.data });
  const weapons = useQuery({ queryKey: ["player-weapons", who], queryFn: () => playerApi.weapons(who), retry: false, enabled: !!summary.data });

  if (summary.isLoading) return <p className="muted">กำลังโหลดสถิติ…</p>;
  if (summary.error instanceof ApiError) return <PlayerEmpty status={summary.error.status} message={summary.error.message} mine={!steamId} />;
  if (summary.error) return <p className="err">โหลดสถิติไม่ได้: {(summary.error as Error).message}</p>;
  if (!summary.data) return <NotFound title="ไม่พบผู้เล่นคนนี้" />;

  const d = summary.data;
  const t = d.totals;
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
        {d.player.avatar ? <img className="pl-avatar" src={d.player.avatar} alt="" /> : <span className="pl-avatar ph" aria-hidden="true" />}
        <div>
          <h1>{d.player.name}</h1>
          <p className="muted">
            {d.source.label}
            {d.player.linked_account && <> · บัญชีในระบบ: {d.player.linked_account}</>}
          </p>
        </div>
        <span className="badge b-ct pl-mode">CS2 · 5v5</span>
      </header>

      <section className="pl-grid" aria-label="ภาพรวม">
        <article className="card pl-card">
          <h2>K/D</h2>
          <Gauge value={t.kd} max={2} label={t.kd.toFixed(2)} />
          <p className="muted small">
            {t.kills} คิล · {t.deaths} ตาย · {t.assists} ช่วย
          </p>
        </article>

        <article className="card pl-card">
          <h2>Rating 1.0</h2>
          <Gauge value={t.rating} max={2} label={t.rating.toFixed(2)} />
          <p className="muted small">
            Rating 2.0 (ประมาณการ): <b>{d.rating2_approx.toFixed(2)}</b>
            <br />
            HLTV ไม่เปิดสูตร 2.0 — ค่านี้เป็นสูตรประมาณของชุมชน
          </p>
        </article>

        <article className="card pl-card pl-wide">
          <h2>Clutch 1v1 – 1v5</h2>
          {d.clutches.length === 0 ? (
            <p className="muted small">ยังไม่เจอสถานการณ์ clutch ในเดโมที่โหลดไว้</p>
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
          <h2>ชนะรอบ (round win rate)</h2>
          <Gauge value={t.win_rate} max={100} label={`${t.win_rate.toFixed(0)}%`} unit />
          <p className="muted small">
            {t.rounds} รอบใน {t.matches} แมตช์
            {record && (
              <>
                <br />
                แมตช์: ชนะ {record.win} · แพ้ {record.loss}
                {record.draw > 0 && <> · เสมอ {record.draw}</>}
              </>
            )}
          </p>
        </article>

        <article className="card pl-card">
          <h2>HS% · ADR · KAST</h2>
          <ul className="pl-nums">
            <li>
              <b>{t.hs_rate.toFixed(0)}%</b>
              <span>หัว ({t.headshots} จาก {t.kills})</span>
            </li>
            <li>
              <b>{t.adr.toFixed(1)}</b>
              <span>ADR</span>
            </li>
            <li>
              <b>{t.kast.toFixed(0)}%</b>
              <span>KAST</span>
            </li>
            <li>
              <b>{t.survival_rate.toFixed(0)}%</b>
              <span>รอดจบรอบ</span>
            </li>
          </ul>
        </article>

        <article className="card pl-card pl-wide">
          <h2>Entry — คิลแรกของรอบ</h2>
          <div className="pl-donuts">
            <Donut label="รวม" value={entryRate(d.entry.both)} won={d.entry.both.kills} lost={d.entry.both.deaths} />
            <Donut label="ฝั่ง T" value={entryRate(d.entry.t)} won={d.entry.t.kills} lost={d.entry.t.deaths} tone="t" />
            <Donut label="ฝั่ง CT" value={entryRate(d.entry.ct)} won={d.entry.ct.kills} lost={d.entry.ct.deaths} tone="ct" />
          </div>
          <p className="muted small">นับเฉพาะรอบที่ผู้เล่นคนนี้เป็นคนเปิดรอบ (คิลแรก) หรือเป็นคนแรกที่ตาย</p>
        </article>
      </section>

      <section className="pl-panels">
        <article className="card">
          <h2>แมตช์ล่าสุด</h2>
          {matches.data?.length ? (
            <ul className="pl-matches">
              {matches.data.map((m) => (
                <li key={m.match_id} className={`r-${m.result}`}>
                  <Link to={`/matches/${encodeURIComponent(m.demo_file)}/rounds/1`}>
                    <span className="pl-res">{m.result === "win" ? "ชนะ" : m.result === "loss" ? "แพ้" : "เสมอ"}</span>
                    <span className="pl-mt">
                      {m.team_a && m.team_b ? `${m.team_a} vs ${m.team_b}` : m.demo_file}
                      <span className="muted small"> · {m.map_name} · {m.rounds_won}/{m.rounds} รอบ</span>
                    </span>
                    <span className="pl-rt">{Number(m.rating).toFixed(2)}</span>
                  </Link>
                </li>
              ))}
            </ul>
          ) : (
            <p className="muted small">{matches.isLoading ? "กำลังโหลด…" : "ยังไม่มีแมตช์"}</p>
          )}
        </article>

        <article className="card">
          <h2>แมพที่เล่นบ่อย</h2>
          <Bars
            rows={(maps.data ?? []).map((m: PlayerMap) => ({
              key: m.map_name,
              label: m.map_name,
              value: m.matches,
              note: `ชนะ ${m.wins}/${m.matches} · rating ${Number(m.rating).toFixed(2)}`,
              ratio: m.win_rate / 100,
            }))}
            empty={maps.isLoading ? "กำลังโหลด…" : "ยังไม่มีข้อมูลแมพ"}
          />
        </article>

        <article className="card">
          <h2>อาวุธที่ฆ่าบ่อย</h2>
          <Bars
            rows={(weapons.data ?? []).map((w: PlayerWeapon) => ({
              key: w.weapon,
              label: weaponLabel(w.weapon),
              value: w.kills,
              note: `หัว ${w.hs_rate.toFixed(0)}% (${w.headshots})`,
              ratio: w.hs_rate / 100,
            }))}
            empty={weapons.isLoading ? "กำลังโหลด…" : "ยังไม่มีข้อมูลอาวุธ"}
          />
        </article>
      </section>
    </div>
  );
}

/** ยังไม่ผูก Steam (409) หรือไม่มีข้อมูลในเดโม (404) — บอกตรง ๆ ว่าทำอะไรต่อ ไม่โชว์ตัวเลขปลอม */
function PlayerEmpty({ status, message, mine }: { status: number; message: string; mine: boolean }) {
  return (
    <div className="pl-empty" data-testid="player-empty">
      <h1>{status === 409 ? "ยังไม่ได้ผูกบัญชีกับ Steam" : "ยังไม่มีสถิติของคุณ"}</h1>
      <p className="muted">{message}</p>
      {mine && (
        <p className="muted">
          สถิติจะขึ้นเมื่อมีเดโมที่คุณลงเล่นอยู่ในระบบ — อัปโหลดเดโมของทีมที่หน้าแมตช์ แล้วกลับมาที่หน้านี้
        </p>
      )}
      <Link className="btn-primary" to="/matches">
        ไปหน้าแมตช์
      </Link>
    </div>
  );
}

// ------------------------------------------------------------------ กราฟวาดเอง (SVG) — ไม่ใช้ไลบรารีกราฟ
const ARC = 2 * Math.PI * 52;

/** เกจวงกลม: สีไล่แดง -> เหลือง -> เขียว ตามสัดส่วนของค่าเทียบ max */
function Gauge({ value, max, label, unit = false }: { value: number; max: number; label: string; unit?: boolean }) {
  const ratio = Math.max(0, Math.min(1, value / max));
  const hue = Math.round(8 + ratio * 122); // 8 = แดง, 130 = เขียว
  return (
    <svg className="pl-gauge" viewBox="0 0 120 120" role="img" aria-label={`${label}${unit ? "" : ` จาก ${max}`}`}>
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
  return (
    <div className={`pl-donut ${tone}`}>
      <svg viewBox="0 0 120 120" role="img" aria-label={`${label} ${won} ชนะ ${lost} แพ้`}>
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
  return (
    <div className={`pl-pie${attempts === 0 ? " none" : ""}`}>
      <svg viewBox="0 0 120 120" role="img" aria-label={`${label} ชนะ ${wins} จาก ${attempts}`}>
        <circle cx="60" cy="60" r="52" className="pl-track" />
        <circle cx="60" cy="60" r="52" className="pl-arc" strokeDasharray={`${ratio * ARC} ${ARC}`} transform="rotate(-90 60 60)" />
        <text x="60" y="60" className="pl-gauge-v" textAnchor="middle" dominantBaseline="central">
          {attempts === 0 ? "—" : wins}
        </text>
      </svg>
      <span>{label}</span>
      <span className="muted small">{attempts === 0 ? "ไม่มี" : `${wins}/${attempts}`}</span>
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
