import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { api } from '../api.js';
import PlayerView from '../components/PlayerView.jsx';
import { Loading, ErrorBox, EmptyState } from '../components/ui.jsx';

export default function Player() {
  const { steam64 } = useParams();
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [noData, setNoData] = useState(false);

  useEffect(() => {
    let alive = true;
    setData(null);
    setError(null);
    setNoData(false);
    Promise.all([api.profile(steam64), api.playerMatches(steam64)])
      .then(([profile, matches]) => alive && setData({ profile, matches }))
      .catch((e) => {
        if (!alive) return;
        if (e.status === 404) setNoData(true);
        else setError(e);
      });
    return () => { alive = false; };
  }, [steam64]);

  if (error) return <><h1>ส่องผู้เล่น</h1><ErrorBox error={error} /></>;

  if (noData) {
    return (
      <>
        <h1>ส่องผู้เล่น</h1>
        <p className="sub">Steam64 <span className="mono">{steam64}</span></p>
        <EmptyState title="ยังไม่มีข้อมูลของผู้เล่นคนนี้">
          ระบบวิเคราะห์เฉพาะผู้เล่นที่ปรากฏในไฟล์ <span className="mono">.dem</span> ที่โหลดเข้ามาแล้ว
          ถ้าจะส่องคู่แข่งคนนี้ ต้องหาไฟล์ demo ที่เขาลงเล่นมาโหลดเข้าระบบก่อน
        </EmptyState>
      </>
    );
  }

  if (!data) return <Loading />;
  return <PlayerView profile={data.profile} matches={data.matches} />;
}
