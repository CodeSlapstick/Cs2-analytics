import { useEffect, useState } from 'react';
import { api } from '../api.js';
import { Loading, ErrorBox, EmptyState, SourceTag, fmtDateTime } from '../components/ui.jsx';

/**
 * หน้าใหม่ของ Sprint 1 — รายการแมตช์ทั้งหมดที่โหลดเข้าฐานข้อมูลแล้ว
 * Sprint 0 ไม่มีหน้านี้เพราะข้อมูลถูกสุ่มขึ้นมาสด ๆ ไม่มี "คลังแมตช์" ให้เปิดดู
 */
export default function Matches() {
  const [matches, setMatches] = useState(null);
  const [error, setError] = useState(null);
  const [mine, setMine] = useState(false);

  useEffect(() => {
    let alive = true;
    setMatches(null);
    setError(null);
    api
      .matches({ limit: 50, mine: mine ? 1 : undefined })
      .then((m) => alive && setMatches(m))
      .catch((e) => alive && setError(e));
    return () => { alive = false; };
  }, [mine]);

  return (
    <>
      <h1>แมตช์</h1>
      <p className="sub">
        แมตช์ทั้งหมดที่ผ่าน pipeline เข้ามาแล้ว (parse ไฟล์ .dem → ETL → PostgreSQL)
      </p>

      <ErrorBox error={error} />

      <div className="card" style={{ marginBottom: 16 }}>
        <div className="row">
          <button className={mine ? '' : 'primary'} style={{ flex: '0 0 auto' }} onClick={() => setMine(false)}>
            ทุกแมตช์
          </button>
          <button className={mine ? 'primary' : ''} style={{ flex: '0 0 auto' }} onClick={() => setMine(true)}>
            เฉพาะแมตช์ที่ฉันลงเล่น
          </button>
        </div>
      </div>

      {!matches ? (
        <Loading />
      ) : matches.length === 0 ? (
        <EmptyState title={mine ? 'ยังไม่มีแมตช์ที่คุณลงเล่น' : 'ยังไม่มีแมตช์ในฐานข้อมูล'}>
          <p>โหลดข้อมูลเข้าระบบด้วยสองคำสั่งนี้:</p>
          <pre className="code">
{`python parser/parse_demo.py match.dem -o backend/data/matches/
npm run etl -- data/matches`}
          </pre>
          <p style={{ marginBottom: 0 }}>
            หรือสร้างข้อมูลตัวอย่างไว้ทดสอบ: <span className="mono">npm run db:seed</span>
          </p>
        </EmptyState>
      ) : (
        <div className="card">
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>วันที่</th><th>แมพ</th><th className="num">สกอร์</th>
                  <th className="num">รอบ</th><th className="num">ผู้เล่น</th>
                  <th>ที่มา</th>
                </tr>
              </thead>
              <tbody>
                {matches.map((m) => (
                  <tr key={m.id}>
                    <td className="muted">{fmtDateTime(m.finished_at)}</td>
                    <td>{m.map_name}</td>
                    <td className="num mono">{m.score_team2}–{m.score_team3}</td>
                    <td className="num">{m.rounds_played}</td>
                    <td className="num">{m.player_count}</td>
                    <td>
                      <SourceTag source={m.source} />
                      {m.demo_file && <div className="small muted mono">{m.demo_file}</div>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </>
  );
}
