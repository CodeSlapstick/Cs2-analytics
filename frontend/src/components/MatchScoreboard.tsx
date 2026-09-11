import { useQuery } from "@tanstack/react-query";
import { api } from "../api";
import { sideLabel } from "../review/format";

/** สกอร์บอร์ดทั้งแมตช์ (เดิมอยู่หน้า Match Overview) — เป็นแผงพับได้ในหน้ารอบ */
export function MatchScoreboard({ matchId }: { matchId: number }) {
  const q = useQuery({ queryKey: ["match", matchId], queryFn: () => api.match(matchId) });
  if (q.isLoading) return <p className="muted small">กำลังโหลดสกอร์บอร์ด…</p>;
  if (q.error || !q.data) return <p className="err small">โหลดสกอร์บอร์ดไม่ได้: {(q.error as Error | null)?.message}</p>;

  const features = q.data.features ?? {};
  const hasFeatures = Object.keys(features).length > 0;
  const rows = [...q.data.scoreboard].sort((a, b) => b.rating - a.rating);

  return (
    <div className="scoreboard-wrap" data-testid="scoreboard">
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
            <th className="num" title="เปิดรอบ: คิลแรก / ตายแรก">
              เปิด K/D
            </th>
            <th className="num" title="ฆ่าคนที่เพิ่งฆ่าเพื่อนภายใน 5 วินาที">
              Trade
            </th>
            <th className="num" title="ชนะ / เจอสถานการณ์เหลือคนเดียว">
              Clutch
            </th>
            <th className="num">Rating</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((p) => {
            const f = features[p.steam_id];
            return (
              <tr key={p.steam_id}>
                <td>{p.name}</td>
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
                <td className="num">
                  <b>{p.rating.toFixed(2)}</b>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      {!hasFeatures && <p className="muted small">แมตช์นี้ยังไม่มีฟีเจอร์ opening / trade / clutch — โหลดเดโมซ้ำเพื่อคำนวณ</p>}
    </div>
  );
}
