import { useEffect, useState } from 'react';
import { api } from '../api.js';
import { RatingRadar, DiffBars } from '../components/charts.jsx';
import { Signed, ErrorBox, EmptyState, DIM_LABEL, fmtNum, fmtPct } from '../components/ui.jsx';

/**
 * เลือกผู้เล่นจากรายชื่อที่มีข้อมูลจริงในฐานข้อมูล
 * Sprint 0 ให้พิมพ์ Steam64 17 หลักเอง ซึ่งใช้จริงไม่ได้เลย (ไม่มีใครจำได้)
 * ตอนนี้ backend มี /api/players ที่คืนเฉพาะคนที่มีแมตช์แล้ว จึงทำเป็น dropdown ได้
 */
function PlayerPicker({ label, players, value, onChange }) {
  return (
    <div>
      <label>{label}</label>
      <select value={value} onChange={(e) => onChange(e.target.value)}>
        <option value="">— เลือกผู้เล่น —</option>
        {players.map((p) => (
          <option key={p.steam64_id} value={p.steam64_id}>
            {p.name} ({p.total_matches} แมตช์)
          </option>
        ))}
      </select>
    </div>
  );
}

export default function Compare() {
  const [players, setPlayers] = useState([]);
  const [a, setA] = useState('');
  const [b, setB] = useState('');
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    api.players().then(setPlayers).catch(setError);
  }, []);

  const run = async () => {
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      setResult(await api.compare(a.trim(), b.trim()));
    } catch (e) {
      setError(e);
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      <h1>เทียบผู้เล่นตัวต่อตัว</h1>
      <p className="sub">
        เลือกผู้เล่นสองคนเพื่อดูว่าฝั่งเราได้เปรียบหรือเสียเปรียบมิติไหน
        (เช่น AWPer ของเรา เทียบกับ AWPer ของคู่แข่ง)
      </p>

      <ErrorBox error={error} />

      {players.length === 0 && !error ? (
        <EmptyState title="ยังไม่มีผู้เล่นให้เทียบ">
          ต้องโหลดไฟล์ .dem เข้าระบบก่อน (หรือรัน <span className="mono">npm run db:seed</span> เพื่อดูข้อมูลตัวอย่าง)
        </EmptyState>
      ) : (
        <div className="card" style={{ marginBottom: 16 }}>
          <div className="row">
            <PlayerPicker label="ผู้เล่นของเรา" players={players} value={a} onChange={setA} />
            <PlayerPicker label="ผู้เล่นคู่แข่ง" players={players} value={b} onChange={setB} />
            <button className="primary" onClick={run} disabled={loading || !a || !b || a === b}>
              {loading ? 'กำลังดึงข้อมูล…' : 'เปรียบเทียบ'}
            </button>
          </div>
          {a && b && a === b && (
            <p className="small muted" style={{ marginBottom: 0 }}>เลือกคนเดียวกันสองช่อง ไม่มีอะไรให้เทียบ</p>
          )}
        </div>
      )}

      {result && (
        <>
          <div className="grid cols-2" style={{ marginBottom: 16 }}>
            <div className="card">
              <h3>เรดาร์เปรียบเทียบ</h3>
              <RatingRadar
                labels={DIM_LABEL}
                series={[
                  { name: result.a.name || 'ของเรา', rating: result.a.rating },
                  { name: result.b.name || 'คู่แข่ง', rating: result.b.rating },
                ]}
              />
            </div>
            <div className="card">
              <h3>ส่วนต่างรายมิติ</h3>
              <DiffBars diff={result.diff} labels={DIM_LABEL} names={[result.a.name, result.b.name]} />
              <p className="small muted" style={{ marginBottom: 0 }}>
                แท่งเขียว = <strong>{result.a.name}</strong> ได้เปรียบ · แท่งแดง = <strong>{result.b.name}</strong> ได้เปรียบ
              </p>
            </div>
          </div>

          <div className="card">
            <h3>ตัวเลขดิบที่อยู่เบื้องหลัง</h3>
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>ตัวชี้วัด</th>
                    <th className="num">{result.a.name}</th>
                    <th className="num">{result.b.name}</th>
                    <th className="num">ส่วนต่าง</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.keys(DIM_LABEL).map((d) => (
                    <tr key={d}>
                      <td>{DIM_LABEL[d]}</td>
                      <td className="num"><Signed value={result.a.rating?.[d]} /></td>
                      <td className="num"><Signed value={result.b.rating?.[d]} /></td>
                      <td className="num"><strong><Signed value={result.diff[d]} /></strong></td>
                    </tr>
                  ))}
                  <tr>
                    <td className="muted">ADR</td>
                    <td className="num">{fmtNum(result.a.stats?.adr, 1)}</td>
                    <td className="num">{fmtNum(result.b.stats?.adr, 1)}</td>
                    <td className="num muted">—</td>
                  </tr>
                  <tr>
                    <td className="muted">K/D</td>
                    <td className="num">{fmtNum(result.a.stats?.kd)}</td>
                    <td className="num">{fmtNum(result.b.stats?.kd)}</td>
                    <td className="num muted">—</td>
                  </tr>
                  <tr>
                    <td className="muted">อัตราชนะ</td>
                    <td className="num">{fmtPct(result.a.winrate)}</td>
                    <td className="num">{fmtPct(result.b.winrate)}</td>
                    <td className="num muted">—</td>
                  </tr>
                  <tr>
                    <td className="muted">จำนวนแมตช์ที่ใช้คิด</td>
                    <td className="num">{result.a.total_matches}</td>
                    <td className="num">{result.b.total_matches}</td>
                    <td className="num muted">—</td>
                  </tr>
                </tbody>
              </table>
            </div>
            <p className="small muted" style={{ marginBottom: 0 }}>
              ส่วนต่างเป็นบวก = ผู้เล่นของเราดีกว่าในมิตินั้น — ถ้าจำนวนแมตช์ต่างกันมาก
              ให้ระวังการตีความ คนที่เล่นน้อยกว่าคะแนนจะแกว่งกว่า
            </p>
          </div>
        </>
      )}
    </>
  );
}
