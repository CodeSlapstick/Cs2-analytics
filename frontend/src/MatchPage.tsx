import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { api, isBusy, matchesQuery, type Match, type RoundListItem } from "./api";
import { Breadcrumb, endReasonLabel, matchTitle, NotFound, num, sideLabel } from "./utils";

// ================================================================================================
// หน้าสรุปแมตช์: /matches/{demo_file}
// ================================================================================================
/**
 * ตอบคำถาม "แมตช์นี้ผลเป็นยังไง" — ทั้งแมตช์ ไม่ใช่รายรอบ
 *
 * สกอร์บอร์ดเดิมเป็นแผงพับซ่อนอยู่ในหน้ารีวิวรอบ ต้องกดเปิดทุกครั้งถึงจะเห็น
 * ย้ายมาเป็นเนื้อหาหลักของหน้านี้ เพราะเป็นข้อมูลระดับแมตช์ คนละระดับกับรอบ
 *
 * ตารางผลรายรอบด้านล่างทำหน้าที่เป็นสารบัญ — กดแถวไหนก็เข้าไปรีวิวรอบนั้น
 */
export function MatchPage() {
  const { demo } = useParams();
  const matches = useQuery(matchesQuery);
  const entry = demo ? (matches.data ?? []).find((m) => m.demo_file === demo) : undefined;

  if (matches.error) return <p className="err">โหลดรายการแมตช์ไม่ได้: {(matches.error as Error).message}</p>;
  if (!matches.data) return <p className="muted">กำลังโหลด…</p>;
  if (!entry) return <NotFound title="ไม่พบแมตช์นี้" detail={`ไม่มีแมตช์ ${demo} ในระบบ`} />;

  return (
    <div className="match-page" data-testid="match-page">
      <Breadcrumb items={[{ label: "แมตช์", to: "/matches" }, { label: matchTitle(entry) }]} />
      <MatchHead entry={entry} />
      {entry.status === "done" ? (
        <>
          <section className="card">
            <div className="card-head">
              <h2>สกอร์บอร์ดทั้งแมตช์</h2>
              <span className="muted small">เรียงตาม Rating</span>
            </div>
            <MatchScoreboard matchId={entry.id} />
          </section>
          <RoundTable demo={entry.demo_file} />
        </>
      ) : (
        <MatchProgress entry={entry} />
      )}
    </div>
  );
}

function MatchHead({ entry }: { entry: Match }) {
  const done = entry.status === "done";
  return (
    <div className="page-head match-head">
      <div>
        <p className="eyebrow">{entry.map_name ?? "ยังไม่รู้แมพ"}</p>
        <h1>{matchTitle(entry)}</h1>
        <p className="muted small mono">{entry.demo_file}</p>
      </div>
      {done && (
        <div className="mh-facts">
          <span className="badge b-ct big">CT {entry.ct_rounds}</span>
          <span className="badge b-t big">T {entry.t_rounds}</span>
          <span className="muted">{num(entry.rounds)} รอบ · {num(entry.kills)} คิล</span>
          <Link className="btn-primary" to={`/matches/${encodeURIComponent(entry.demo_file)}/rounds/1`}>
            เปิดรีวิวรอบ →
          </Link>
        </div>
      )}
    </div>
  );
}

// ------------------------------------------------------------------ ตารางผลรายรอบ (สารบัญไปหน้ารีวิวรอบ)
/** รอบไหนใครชนะ จบด้วยอะไร ตายกี่คน — กดแถวเพื่อเข้าไปดูแผนที่ของรอบนั้น */
function RoundTable({ demo }: { demo: string }) {
  const q = useQuery({ queryKey: ["review-rounds", demo], queryFn: () => api.reviewRounds(demo) });
  if (q.isLoading) return <p className="muted">กำลังโหลดผลรายรอบ…</p>;
  if (q.error || !q.data) return <p className="err">โหลดผลรายรอบไม่ได้: {(q.error as Error | null)?.message}</p>;

  const rows = q.data;
  const half = (side: "ct" | "t") => rows.filter((r) => r.winner_side === side).length;

  return (
    <section className="card">
      <div className="card-head">
        <h2>ผลรายรอบ</h2>
        <span className="muted small">
          CT ชนะ {half("ct")} · T ชนะ {half("t")} · รวม {rows.length} รอบ
        </span>
      </div>
      <div className="tbl-wrap">
        <table className="tbl compact" data-testid="round-table">
          <thead>
            <tr>
              <th className="num">รอบ</th>
              <th>ฝั่งที่ชนะ</th>
              <th>จบด้วย</th>
              <th className="num">ตาย</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => <RoundRowLine key={r.round_num} demo={demo} r={r} />)}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function RoundRowLine({ demo, r }: { demo: string; r: RoundListItem }) {
  const to = `/matches/${encodeURIComponent(demo)}/rounds/${r.round_num}`;
  return (
    <tr data-testid="round-row">
      <td className="num"><Link to={to} className="row-title">{r.round_num}</Link></td>
      <td>
        {r.winner_side
          ? <span className={`badge b-${r.winner_side}`}>{sideLabel(r.winner_side)}</span>
          : <span className="muted">—</span>}
      </td>
      <td>{endReasonLabel(r.end_reason)}</td>
      <td className="num">{r.deaths_count}</td>
      <td><Link className="btn-sm" to={to}>ดูแผนที่ →</Link></td>
    </tr>
  );
}

// ------------------------------------------------------------------ แมตช์ที่ยังแกะไม่เสร็จ
/** ความคืบหน้าของการแกะ — poll สถานะเองผ่าน matchesQuery แล้วหน้านี้จะเปลี่ยนเป็นสกอร์บอร์ดเมื่อเสร็จ */
function MatchProgress({ entry }: { entry: Match }) {
  const label = { queued: "รอคิวแกะเดโม", parsing: "กำลังแกะเดโม", error: "แกะเดโมไม่สำเร็จ", done: "" }[entry.status];
  return (
    <section className="card progress-state" data-testid="match-progress" data-status={entry.status}>
      <h2>{label}</h2>
      {isBusy(entry.status) ? (
        <>
          <div className="progress-bar"><i /></div>
          <p className="muted">หน้านี้จะแสดงสกอร์บอร์ดให้เองเมื่อแกะเสร็จ — ไม่ต้องรีเฟรช</p>
        </>
      ) : (
        <>
          <p className="err">{entry.error_message}</p>
          <p className="muted">
            อัปโหลดไฟล์เดิมซ้ำได้ที่<Link to="/matches">หน้าแมตช์</Link> — แมตช์ที่แกะไม่สำเร็จส่งใหม่ได้โดยไม่ต้องติ๊กโหลดทับ
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
  if (q.isLoading) return <p className="muted small">กำลังโหลดสกอร์บอร์ด…</p>;
  if (q.error || !q.data) return <p className="err small">โหลดสกอร์บอร์ดไม่ได้: {(q.error as Error | null)?.message}</p>;

  const features = q.data.features ?? {};
  const hasFeatures = Object.keys(features).length > 0;
  const rows = [...q.data.scoreboard].sort((a, b) => b.rating - a.rating);

  return (
    <div className="tbl-wrap" data-testid="scoreboard">
      <table className="tbl compact">
        <thead>
          <tr>
            <th>นักแข่ง</th>
            <th>ฝั่งเริ่ม</th>
            <th className="num">K</th>
            <th className="num">D</th>
            <th className="num">A</th>
            <th className="num">HS%</th>
            <th className="num">ADR</th>
            <th className="num">KAST</th>
            <th className="num" title="เปิดรอบ: คิลแรก / ตายแรก">เปิด K/D</th>
            <th className="num" title="ฆ่าคนที่เพิ่งฆ่าเพื่อนภายใน 5 วินาที">Trade</th>
            <th className="num" title="ชนะ / เจอสถานการณ์เหลือคนเดียว">Clutch</th>
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
      {!hasFeatures && <p className="muted small">แมตช์นี้ยังไม่มีฟีเจอร์ opening / trade / clutch — โหลดเดโมซ้ำเพื่อคำนวณ</p>}
    </div>
  );
}
