import { Link } from 'react-router-dom';
import { RatingRadar, FormChart } from './charts.jsx';
import {
  Signed, Stat, Outcome, SourceTag, DIM_LABEL, DIM_HINT,
  fmtPct, fmtNum, fmtDate,
} from './ui.jsx';

/**
 * มุมมองโปรไฟล์ผู้เล่น ใช้ร่วมกันทั้งหน้าแดชบอร์ดของเราและหน้าส่องคู่แข่ง
 *
 * ทุกตัวเลขในหน้านี้มาจากไฟล์ .dem ที่โหลดเข้าฐานข้อมูลแล้ว (ตาราง match_players)
 * ไม่มีค่าที่สุ่มขึ้นมาเหมือน Sprint 0 อีกแล้ว — ค่าที่คำนวณไม่ได้จะขึ้นเป็น "—"
 */
export default function PlayerView({ profile, matches, title }) {
  if (!profile) return null;

  const recent = matches?.length ? matches : profile.recent_matches || [];
  const wins = recent.filter((m) => m.outcome === 'win').length;
  const s = profile.stats || {};

  return (
    <>
      <h1>{title || profile.name}</h1>
      <p className="sub">
        Steam64 <span className="mono">{profile.steam64_id}</span>
        {' · '}
        <a href={`https://steamcommunity.com/profiles/${profile.steam64_id}`} target="_blank" rel="noreferrer">
          โปรไฟล์ Steam
        </a>
        {' · '}
        {profile.rounds_played} รอบจาก {profile.total_matches} แมตช์
      </p>

      <div className="grid cols-4" style={{ marginBottom: 16 }}>
        <Stat value={fmtPct(profile.winrate)} label="อัตราชนะ" hint={`ชนะ ${profile.wins} แพ้ ${profile.losses}`} />
        <Stat value={fmtNum(s.adr, 1)} label="ADR (ดาเมจต่อรอบ)" />
        <Stat value={fmtNum(s.kd)} label="K/D" hint={`${profile.totals?.kills} คิล / ${profile.totals?.deaths} ตาย`} />
        <Stat value={`${wins}/${recent.length}`} label="ชนะในแมตช์ล่าสุด" />
      </div>

      <div className="grid cols-2" style={{ marginBottom: 16 }}>
        <div className="card">
          <h3>มิติความสามารถ (KPI)</h3>
          <RatingRadar series={[{ name: profile.name || 'ผู้เล่น', rating: profile.rating }]} labels={DIM_LABEL} />
          <table style={{ marginTop: 8 }}>
            <tbody>
              {Object.keys(DIM_LABEL).map((d) => (
                <tr key={d} title={DIM_HINT[d]}>
                  <td>{DIM_LABEL[d]}</td>
                  <td className="muted small">{DIM_HINT[d]}</td>
                  <td className="num"><Signed value={profile.rating?.[d]} /></td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="small muted" style={{ marginBottom: 0 }}>
            สเกล −10 ถึง +10 โดย 0 = ระดับกลางตามค่าฐานใน <span className="mono">backend/src/lib/kpi.js</span>
          </p>
        </div>

        <div className="card">
          <h3>ฟอร์มย้อนหลัง</h3>
          {recent.length > 0
            ? <FormChart matches={recent} />
            : <p className="muted small">ยังไม่มีข้อมูลแมตช์</p>}

          <h3 style={{ marginTop: 18 }}>ตัวเลขที่ใช้คิดคะแนน</h3>
          <table>
            <tbody>
              <tr><td>คิลต่อรอบ (KPR)</td><td className="num">{fmtNum(s.kpr)}</td></tr>
              <tr><td>ตายต่อรอบ (DPR)</td><td className="num">{fmtNum(s.dpr)}</td></tr>
              <tr><td>อัตรายิงหัว</td><td className="num">{fmtPct(s.hs_pct)}</td></tr>
              <tr><td>รอดจนจบรอบ</td><td className="num">{fmtPct(s.survival_rate)}</td></tr>
              <tr><td>ดาเมจยูทิลิตี้ต่อรอบ</td><td className="num">{fmtNum(s.utility_damage_per_round, 1)}</td></tr>
              <tr><td>ยูทิลิตี้ที่ใช้ต่อรอบ</td><td className="num">{fmtNum(s.nades_per_round, 1)}</td></tr>
              <tr>
                <td>ชนะดวลเปิดไฟต์</td>
                <td className="num">
                  {fmtPct(s.opening_win_pct)}
                  <span className="muted small"> ({profile.totals?.opening_kills}/{(profile.totals?.opening_kills ?? 0) + (profile.totals?.opening_deaths ?? 0)})</span>
                </td>
              </tr>
              <tr>
                <td>ชนะคลัตช์ (1vX)</td>
                <td className="num">
                  {fmtPct(s.clutch_win_pct)}
                  <span className="muted small"> ({profile.totals?.clutches_won}/{profile.totals?.clutches_attempted})</span>
                </td>
              </tr>
              <tr><td>ตายแล้วเพื่อนล้างแค้นให้ทัน</td><td className="num">{fmtPct(s.traded_death_pct)}</td></tr>
            </tbody>
          </table>
        </div>
      </div>

      <div className="card">
        <h3>แมตช์ล่าสุด</h3>
        {recent.length === 0 ? (
          <p className="muted small">ยังไม่มีข้อมูลแมตช์</p>
        ) : (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>วันที่</th><th>แมพ</th><th>ผล</th><th className="num">สกอร์</th>
                  <th className="num">K/D/A</th><th className="num">ADR</th>
                  <th className="num">HS%</th><th className="num">KPI</th><th></th>
                </tr>
              </thead>
              <tbody>
                {recent.slice(0, 15).map((m) => (
                  <tr key={m.id}>
                    <td className="muted">{fmtDate(m.finished_at)}</td>
                    <td>{m.map_name} <SourceTag source={m.source} /></td>
                    <td><Outcome value={m.outcome} /></td>
                    <td className="num mono">{m.score?.[0]}–{m.score?.[1]}</td>
                    <td className="num mono">{m.kills}/{m.deaths}/{m.assists}</td>
                    <td className="num">{fmtNum(m.adr, 1)}</td>
                    <td className="num">{fmtPct(m.hs_pct, 0)}</td>
                    <td className="num"><Signed value={m.performance_rating} /></td>
                    <td className="num"><Link to={`/match/${m.id}`}>รายละเอียด</Link></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </>
  );
}
