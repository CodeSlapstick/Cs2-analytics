import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../api.js';
import { useAuth } from '../auth-context.js';
import PlayerView from '../components/PlayerView.jsx';
import { Loading, ErrorBox, EmptyState, Stat, fmtDate } from '../components/ui.jsx';

/** แถบบนสุด: บอกว่าตอนนี้ในฐานข้อมูลมีข้อมูลอะไรอยู่บ้าง */
function SystemOverview({ overview }) {
  if (!overview) return null;
  return (
    <div className="grid cols-4" style={{ marginBottom: 20 }}>
      <Stat
        value={overview.matches}
        label="แมตช์ในฐานข้อมูล"
        hint={`มาจากไฟล์ .dem จริง ${overview.demo_matches} นัด`}
      />
      <Stat value={overview.players} label="ผู้เล่นที่มีข้อมูล" />
      <Stat value={overview.rounds} label="รอบทั้งหมด" />
      <Stat value={overview.events?.toLocaleString('th-TH')} label="เหตุการณ์ที่บันทึกไว้" />
    </div>
  );
}

export default function Dashboard() {
  const { user } = useAuth();
  const [data, setData] = useState(null);
  const [overview, setOverview] = useState(null);
  const [error, setError] = useState(null);
  const [noData, setNoData] = useState(false);

  useEffect(() => {
    let alive = true;
    setError(null);
    setNoData(false);

    api.overview().then((o) => alive && setOverview(o)).catch(() => {});

    Promise.all([api.profile(user.steam64_id), api.playerMatches(user.steam64_id)])
      .then(([profile, matches]) => alive && setData({ profile, matches }))
      .catch((e) => {
        if (!alive) return;
        // 404 = ยังไม่มีแมตช์ของคนนี้ ไม่ใช่ระบบพัง — แยกให้ผู้ใช้เข้าใจต่างกัน
        if (e.status === 404) setNoData(true);
        else setError(e);
      });
    return () => { alive = false; };
  }, [user.steam64_id]);

  if (error) {
    return (
      <>
        <h1>แดชบอร์ดของฉัน</h1>
        <ErrorBox error={error} />
      </>
    );
  }

  if (noData) {
    return (
      <>
        <h1>แดชบอร์ดของฉัน</h1>
        <p className="sub">
          Steam64 <span className="mono">{user.steam64_id}</span>
        </p>
        <SystemOverview overview={overview} />
        <EmptyState title="ยังไม่มีแมตช์ของคุณในฐานข้อมูล">
          <p>
            ระบบวิเคราะห์จากไฟล์ <span className="mono">.dem</span> ที่โหลดเข้ามาเท่านั้น
            ตอนนี้ยังไม่มีแมตช์ไหนที่ Steam64 นี้ลงเล่น
          </p>
          <p style={{ marginBottom: 0 }}>ทำได้สองทาง:</p>
          <ol style={{ marginTop: 4 }}>
            <li>
              โหลดไฟล์ demo ของตัวเองเข้าระบบ:{' '}
              <span className="mono">python parser/parse_demo.py match.dem -o backend/data/matches/</span>{' '}
              แล้ว <span className="mono">npm run etl -- data/matches</span>
            </li>
            <li>
              หรือดูข้อมูลตัวอย่างที่มีอยู่แล้วได้ที่หน้า <Link to="/matches">แมตช์</Link>
            </li>
          </ol>
        </EmptyState>
      </>
    );
  }

  if (!data) return <Loading />;

  return (
    <>
      <SystemOverview overview={overview} />
      <PlayerView profile={data.profile} matches={data.matches} title="แดชบอร์ดของฉัน" />
      {overview?.latest_match_at && (
        <p className="small muted" style={{ marginTop: 16 }}>
          แมตช์ล่าสุดในระบบ: {fmtDate(overview.latest_match_at)}
        </p>
      )}
    </>
  );
}
