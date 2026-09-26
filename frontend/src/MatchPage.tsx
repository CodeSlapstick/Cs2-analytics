import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { api, isBusy, matchesQuery, type Match, type RoundListItem } from "./api";
import { Breadcrumb, endReasonLabel, MapThumb, MatchTabs, matchTitle, NotFound, num, sideLabel } from "./utils";
import { tr, useT } from "./i18n";

// ================================================================================================
// หน้าสรุปแมตช์: /matches/{demo_file}
// ================================================================================================
/**
 * ตอบคำถาม "แมตช์นี้ผลเป็นยังไง" — ทั้งแมตช์ ไม่ใช่รายรอบ
 *
 * สกอร์บอร์ดเดิมเป็นแผงพับซ่อนอยู่ในหน้ารีวิวรอบ ต้องกดเปิดทุกครั้งถึงจะเห็น
 * ย้ายมาเป็นเนื้อหาหลักของหน้านี้ เพราะเป็นข้อมูลระดับแมตช์ คนละระดับกับรอบ
 *
 * ผลรายรอบอยู่บนสุดเพราะเป็นทางเข้าหน้ารีวิวรอบ — กดช่องไหนก็เข้าไปดูรอบนั้น
 */
export function MatchPage() {
  const { demo } = useParams();
  const matches = useQuery(matchesQuery);
  const entry = demo ? (matches.data ?? []).find((m) => m.demo_file === demo) : undefined;
  const { t } = useT();

  if (matches.error) return <p className="err">{t("โหลดรายการแมตช์ไม่ได้: {msg}", { msg: (matches.error as Error).message })}</p>;
  if (!matches.data) return <p className="muted">{t("กำลังโหลด…")}</p>;
  if (!entry) return <NotFound title={t("ไม่พบแมตช์นี้")} detail={t("ไม่มีแมตช์ {demo} ในระบบ", { demo: demo ?? "" })} />;

  return (
    <div className="match-page" data-testid="match-page">
      <Breadcrumb items={[{ label: t("แมตช์"), to: "/matches" }, { label: matchTitle(entry) }]} />
      <MatchHead entry={entry} />
      {entry.status === "done" && <MatchTabs demo={entry.demo_file} />}
      {entry.status === "done" ? (
        <>
          <RoundTiles demo={entry.demo_file} />
          <section className="card">
            <div className="card-head">
              <h2>{t("สกอร์บอร์ด")}</h2>
              <span className="muted small">{t("เรียงตาม Rating · กดชื่อเพื่อดูสถิติรายคน")}</span>
            </div>
            <MatchScoreboard matchId={entry.id} />
          </section>
        </>
      ) : (
        <MatchProgress entry={entry} />
      )}
    </div>
  );
}

function MatchHead({ entry }: { entry: Match }) {
  const done = entry.status === "done";
  const { t } = useT();
  return (
    <div className="page-head head-row">
      <div className="mt-head">
        <MapThumb map={entry.map_name} className="mh-thumb" />
        <div>
        <h1>{matchTitle(entry)}</h1>
        <p className="muted small">
          {entry.map_name ?? t("ยังไม่รู้แมพ")}
          {done && <> · {t("{n} รอบ", { n: num(entry.rounds) })} · {t("{n} คิล", { n: num(entry.kills) })}</>}
          <span className="mono" title={t("ชื่อไฟล์เดโม")}> · {entry.demo_file}</span>
        </p>
        </div>
      </div>
      {done && (
        <div className="mh-facts">
          <span className="score-big" aria-label={t("CT ชนะ {ct} รอบ T ชนะ {t} รอบ", { ct: entry.ct_rounds, t: entry.t_rounds })}>
            <span className="ct">CT {entry.ct_rounds}</span>
            <span className="sep">:</span>
            <span className="t">{entry.t_rounds} T</span>
          </span>
        </div>
      )}
    </div>
  );
}

// ------------------------------------------------------------------ ผลรายรอบ (สารบัญไปหน้ารีวิวรอบ)
/**
 * รอบไหนใครชนะ จบด้วยอะไร — เป็นช่องสี่เหลี่ยมเรียงตามครึ่งเกม ไม่ใช่ตาราง 24 แถว
 * กวาดตาทีเดียวเห็นว่าครึ่งไหนฝั่งไหนกินยาว กดช่องไหนก็เข้ารีวิวรอบนั้น
 * ครึ่งละ 12 รอบ (MR12) · ต่อเวลาครึ่งละ 3 รอบ
 */
function halfOf(n: number): string {
  if (n <= 12) return tr("ครึ่งแรก");
  if (n <= 24) return tr("ครึ่งหลัง");
  return tr("ต่อเวลา {n}", { n: Math.floor((n - 25) / 6) + 1 });
}

function RoundTiles({ demo }: { demo: string }) {
  const q = useQuery({ queryKey: ["review-rounds", demo], queryFn: () => api.reviewRounds(demo) });
  const { t } = useT();
  if (q.isLoading) return <p className="muted">{t("กำลังโหลดผลรายรอบ…")}</p>;
  if (q.error || !q.data) return <p className="err">{t("โหลดผลรายรอบไม่ได้: {msg}", { msg: (q.error as Error | null)?.message ?? "" })}</p>;

  const groups = new Map<string, RoundListItem[]>();
  q.data.forEach((r) => {
    const k = halfOf(r.round_num);
    groups.set(k, [...(groups.get(k) ?? []), r]);
  });

  return (
    <section className="card" data-testid="round-table">
      <div className="card-head">
        <h2>{t("ผลรายรอบ")}</h2>
        <span className="muted small">{t("กดรอบไหนก็เปิดดูบนแผนที่")}</span>
      </div>
      <div className="halves">
        {[...groups].map(([label, rows]) => (
          <div key={label} className="half">
            <h3>{label}</h3>
            <ol className="rtiles">
              {rows.map((r) => (
                <li key={r.round_num}>
                  <Link className="rtile" to={`/matches/${encodeURIComponent(demo)}/rounds/${r.round_num}`}
                    data-testid="round-row" title={t("รอบ {n} · {side} ชนะ", { n: r.round_num, side: sideLabel(r.winner_side) })}>
                    <span className={`rbox ${r.winner_side ?? "none"}`}>{r.round_num}</span>
                    <span className="rt-why">{endReasonLabel(r.end_reason)}</span>
                    <span className="rt-dd">{t("ตาย {n}", { n: r.deaths_count })}</span>
                  </Link>
                </li>
              ))}
            </ol>
          </div>
        ))}
      </div>
    </section>
  );
}

// ------------------------------------------------------------------ แมตช์ที่ยังแกะไม่เสร็จ
/** ความคืบหน้าของการแกะ — poll สถานะเองผ่าน matchesQuery แล้วหน้านี้จะเปลี่ยนเป็นสกอร์บอร์ดเมื่อเสร็จ */
function MatchProgress({ entry }: { entry: Match }) {
  const { t, tn } = useT();
  const label = { queued: "รอคิวแกะเดโม", parsing: "กำลังแกะเดโม", error: "แกะเดโมไม่สำเร็จ", done: "" }[entry.status];
  return (
    <section className="card progress-state" data-testid="match-progress" data-status={entry.status}>
      <h2>{label && t(label)}</h2>
      {isBusy(entry.status) ? (
        <>
          <div className="progress-bar"><i /></div>
          <p className="muted">{t("แกะเสร็จแล้วหน้านี้จะเปลี่ยนเป็นผลการแข่งให้เอง ไม่ต้องรีเฟรช — ปิดหน้านี้ไปก่อนก็ได้")}</p>
        </>
      ) : (
        <>
          <p className="err">{entry.error_message && t(entry.error_message)}</p>
          <p className="muted">
            {tn("ลองอัปโหลดไฟล์เดิมอีกครั้งได้ที่{link} — แมตช์ที่แกะไม่สำเร็จส่งซ้ำได้เลย", {
              link: <Link to="/matches">{t("หน้าแมตช์")}</Link>,
            })}
          </p>
        </>
      )}
    </section>
  );
}

// ------------------------------------------------------------------ สกอร์บอร์ด
/** สกอร์บอร์ดทั้งแมตช์ — features (opening/trade/clutch) ว่างได้ในแมตช์เก่าที่ยังไม่ backfill */
export function MatchScoreboard({ matchId }: { matchId: number }) {
  const q = useQuery({ queryKey: ["match", matchId], queryFn: () => api.match(matchId) });
  const { t } = useT();
  if (q.isLoading) return <p className="muted small">{t("กำลังโหลดสกอร์บอร์ด…")}</p>;
  if (q.error || !q.data) return <p className="err small">{t("โหลดสกอร์บอร์ดไม่ได้: {msg}", { msg: (q.error as Error | null)?.message ?? "" })}</p>;

  const features = q.data.features ?? {};
  const hasFeatures = Object.keys(features).length > 0;
  const rows = [...q.data.scoreboard].sort((a, b) => b.rating - a.rating);

  return (
    <div className="tbl-wrap" data-testid="scoreboard">
      <table className="tbl compact">
        <thead>
          <tr>
            <th>{t("นักแข่ง")}</th>
            <th>{t("ฝั่งเริ่ม")}</th>
            <th className="num">K</th>
            <th className="num">D</th>
            <th className="num">A</th>
            <th className="num">HS%</th>
            <th className="num">ADR</th>
            <th className="num">KAST</th>
            <th className="num" title={t("เปิดรอบ: คิลแรก / ตายแรก")}>{t("เปิด K/D")}</th>
            <th className="num" title={t("ฆ่าคนที่เพิ่งฆ่าเพื่อนภายใน 5 วินาที")}>Trade</th>
            <th className="num" title={t("ชนะ / เจอสถานการณ์เหลือคนเดียว")}>Clutch</th>
            <th className="num">Rating</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((p) => {
            const f = features[p.steam_id];
            return (
              <tr key={p.steam_id}>
                <td><Link to={`/player/${p.steam_id}`} className="row-title">{p.name}</Link></td>
                <td>{p.start_side ? <span className={`badge b-${p.start_side}`}>{sideLabel(p.start_side)}</span> : "—"}</td>
                <td className="num">{p.kills}</td>
                <td className="num">{p.deaths}</td>
                <td className="num">{p.assists}</td>
                <td className="num">{p.hs_rate.toFixed(0)}%</td>
                <td className="num">{p.adr.toFixed(1)}</td>
                <td className="num">{p.kast.toFixed(0)}%</td>
                <td className="num">{f ? `${f.opening_kills}/${f.opening_deaths}` : "—"}</td>
                <td className="num">{f ? f.trade_kills : "—"}</td>
                <td className="num">{f ? `${f.clutch_wins}/${f.clutch_attempts}` : "—"}</td>
                <td className="num"><b>{p.rating.toFixed(2)}</b></td>
              </tr>
            );
          })}
        </tbody>
      </table>
      {!hasFeatures && <p className="muted small">{t("แมตช์นี้ยังไม่มีฟีเจอร์ opening / trade / clutch — โหลดเดโมซ้ำเพื่อคำนวณ")}</p>}
    </div>
  );
}
