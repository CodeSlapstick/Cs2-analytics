import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { api, isBusy, type RoundRow, type ScoreRow } from "../api";

const END_REASON: Record<string, string> = {
  ct_killed: "ฆ่า CT หมดทีม",
  t_killed: "ฆ่า T หมดทีม",
  bomb_exploded: "ระเบิดลง",
  bomb_defused: "กู้ระเบิดสำเร็จ",
  time_ran_out: "หมดเวลา",
  ct_win: "CT ชนะ",
  t_win: "T ชนะ",
};

export function MatchOverview() {
  const { id } = useParams();
  const q = useQuery({
    queryKey: ["match", id],
    queryFn: () => api.match(id!),
    enabled: !!id,
    // ถ้ามาถึงหน้านี้ตอนยังแกะไม่เสร็จ ให้ poll ต่อจนกว่าจะ done/error
    refetchInterval: (query) => (query.state.data && isBusy(query.state.data.match.status) ? 2000 : false),
  });

  if (q.isLoading) return <p className="muted">กำลังโหลด…</p>;
  if (q.error) return <p className="err">โหลดแมตช์ไม่ได้: {(q.error as Error).message}</p>;
  if (!q.data) return null;

  const { match, rounds, scoreboard } = q.data;
  const title = match.team_a && match.team_b ? `${match.team_a} vs ${match.team_b}` : match.demo_file;

  return (
    <>
      <p className="eyebrow">
        <Link to="/">← Match Library</Link> · {match.map_name ?? "?"} · แมตช์ #{match.id}
      </p>
      <h1>{title}</h1>

      {match.status !== "done" ? (
        <section className="card">
          <p>
            สถานะ: <span className={`badge b-${match.status}`}>{match.status}</span>
            {match.error_message && <span className="err"> — {match.error_message}</span>}
          </p>
          {isBusy(match.status) && <p className="muted">กำลังแกะเดโมในเบื้องหลัง หน้านี้จะอัปเดตเอง</p>}
        </section>
      ) : (
        <>
          <div className="scoreline">
            <span className="badge b-ct">CT {match.ct_rounds}</span>
            <span className="badge b-t">T {match.t_rounds}</span>
            <span className="muted">
              · {match.rounds} รอบ · {match.kills} คิล · {match.tickrate} tick
            </span>
          </div>

          <section className="card">
            <p className="eyebrow">ROUND TIMELINE</p>
            <h2>ใครชนะรอบไหน</h2>
            <RoundTimeline rounds={rounds} />
          </section>

          <section className="card">
            <p className="eyebrow">SCOREBOARD</p>
            <h2>สกอร์บอร์ด</h2>
            <Scoreboard rows={scoreboard} />
          </section>
        </>
      )}
    </>
  );
}

function RoundTimeline({ rounds }: { rounds: RoundRow[] }) {
  return (
    <>
      <div className="timeline" data-testid="round-timeline">
        {rounds.map((r) => (
          <div
            key={r.round_num}
            className={`rbox ${r.winner_side ?? "none"}`}
            title={`รอบ ${r.round_num} · ${r.winner_side?.toUpperCase() ?? "?"} ชนะ · ${END_REASON[r.end_reason ?? ""] ?? r.end_reason ?? ""}${r.bomb_planted ? " · วางระเบิด" : ""}`}
          >
            {r.round_num}
          </div>
        ))}
      </div>
      <table className="tbl compact">
        <thead>
          <tr>
            <th>รอบ</th>
            <th>ผู้ชนะ</th>
            <th>จบด้วย</th>
            <th>ระเบิด</th>
            <th className="num">คิล</th>
            <th>CT ซื้อ</th>
            <th>T ซื้อ</th>
          </tr>
        </thead>
        <tbody>
          {rounds.map((r) => (
            <tr key={r.round_num}>
              <td>{r.round_num}</td>
              <td>{r.winner_side ? <span className={`badge b-${r.winner_side}`}>{r.winner_side.toUpperCase()}</span> : "—"}</td>
              <td>{END_REASON[r.end_reason ?? ""] ?? r.end_reason ?? "—"}</td>
              <td>{r.bomb_planted ? "วางแล้ว" : ""}</td>
              <td className="num">{r.kills}</td>
              <td>{r.ct_buy_type ?? ""}</td>
              <td>{r.t_buy_type ?? ""}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}

function Scoreboard({ rows }: { rows: ScoreRow[] }) {
  const sorted = [...rows].sort((a, b) => b.rating - a.rating);
  return (
    <table className="tbl" data-testid="scoreboard">
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
          <th className="num">Rating</th>
        </tr>
      </thead>
      <tbody>
        {sorted.map((p) => (
          <tr key={p.steam_id}>
            <td>{p.name}</td>
            <td>{p.start_side ? <span className={`badge b-${p.start_side}`}>{p.start_side.toUpperCase()}</span> : "—"}</td>
            <td className="num">{p.kills}</td>
            <td className="num">{p.deaths}</td>
            <td className="num">{p.assists}</td>
            <td className="num">{p.hs_rate.toFixed(0)}%</td>
            <td className="num">{p.adr.toFixed(1)}</td>
            <td className="num">{p.kast.toFixed(0)}%</td>
            <td className="num">
              <b>{p.rating.toFixed(2)}</b>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
