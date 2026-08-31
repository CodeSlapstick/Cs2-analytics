/**
 * ข้อสรุปเชิงลึกของแมพ — ส่วนที่ตอบว่า "แล้วต้องแก้อะไร"
 *
 * แผนที่กับตารางคะแนนบอกว่า "พื้นที่ไหนใครได้เปรียบ" ซึ่งยังเป็นแค่ตัวเลข
 * ส่วนนี้เดินต่ออีกก้าวไปเป็นข้อสรุปที่โค้ชเอาไปสั่งลูกทีมได้
 *
 * ตัวกรองฝั่ง T/CT อยู่บนสุดเพราะแผนของโค้ชคนละแผนกันสองฝั่ง — ตัวเลขที่รวม
 * สองฝั่งไว้ด้วยกันดูดีแต่เอาไปวางแผนไม่ได้
 *
 * ทุกตารางแสดงขนาดกลุ่มตัวอย่างเสมอ และแถวที่ข้อมูลน้อยเกินเกณฑ์ถูกทำให้จาง
 * พร้อมป้ายกำกับ ไม่ได้ซ่อนทิ้ง — โค้ชควรเห็นว่ามีข้อมูลอะไรอยู่ แค่ต้องรู้ว่ายังเชื่อไม่ได้
 */
import { useEffect, useState } from 'react';
import { api } from '../api.js';
import { Loading, ErrorBox, PlayerLink } from './ui.jsx';

const SIDES = [
  { key: null, label: 'ทั้งแมตช์' },
  { key: 't', label: 'ตอนเล่นฝั่ง T' },
  { key: 'ct', label: 'ตอนเล่นฝั่ง CT' },
];

const signed = (v) => (v === null || v === undefined ? '—' : v > 0 ? `+${v}` : `${v}`);

export default function MapInsights({ mapName }) {
  const [side, setSide] = useState(null);
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!mapName) return undefined;
    let alive = true;
    setData(null);
    setError(null);
    api.mapInsights(mapName, side)
      .then((d) => alive && setData(d))
      .catch((e) => alive && setError(e));
    return () => { alive = false; };
  }, [mapName, side]);

  return (
    <>
      <h2>ข้อสรุปเชิงลึก</h2>
      <p className="sub">
        จากตัวเลขพื้นที่ไปเป็นสิ่งที่เอาไปซ้อมได้ — ทุกข้อสรุปติดขนาดกลุ่มตัวอย่างมาด้วย
        และข้อที่ข้อมูลน้อยเกินไประบบจะไม่สรุปให้เลย
      </p>

      <div className="card" style={{ marginBottom: 16 }}>
        <div className="row">
          {SIDES.map((s) => (
            <button key={s.label}
                    className={side === s.key ? 'primary' : ''}
                    style={{ flex: '0 0 auto' }}
                    onClick={() => setSide(s.key)}>
              {s.label}
            </button>
          ))}
        </div>
        <p className="small muted" style={{ margin: '10px 0 0' }}>
          ฝั่งของแต่ละรอบอนุมานจากข้อมูลจริงของรอบนั้น (ทีมไหนชนะ + ฝั่งไหนชนะ)
          ไม่ได้คำนวณจากกติกาสลับฝั่ง จึงไม่เพี้ยนเมื่อมี overtime
        </p>
      </div>

      <ErrorBox error={error} />
      {!data && !error && <Loading text="กำลังวิเคราะห์…" />}
      {data && <Report data={data} />}
    </>
  );
}

function Report({ data }) {
  const { scope, first_blood: fb, zone_impact: impact, exposure, findings, thresholds, players } = data;

  return (
    <>
      <div className="findings">
        {findings.map((f, i) => (
          <div key={i} className={`finding ${f.kind}`}>
            <span className="finding-tag">
              {f.kind === 'strong' ? 'จุดแข็ง / ใช้ได้เลย' : f.kind === 'warn' ? 'จุดที่ต้องแก้' : 'หมายเหตุ'}
            </span>
            <p>{f.text}</p>
          </div>
        ))}
      </div>

      <div className="grid cols-3" style={{ margin: '18px 0' }}>
        <div className="card">
          <div className="stat">{scope.rounds}</div>
          <div className="stat-label">รอบที่วิเคราะห์</div>
        </div>
        <div className="card">
          <div className="stat">{scope.round_win_pct}%</div>
          <div className="stat-label">อัตราชนะรอบ ({scope.wins}/{scope.rounds})</div>
        </div>
        <div className="card" title="เทียบกับอัตราชนะปกติของทีมในขอบเขตเดียวกัน">
          <div className={`stat ${fb.lift > 0 ? 'pos' : fb.lift < 0 ? 'neg' : ''}`}>
            {fb.win_pct === null ? '—' : `${fb.win_pct}%`}
          </div>
          <div className="stat-label">
            ชนะรอบเมื่อได้คิลแรก ({fb.wins}/{fb.rounds}) · ต่างจากปกติ {signed(fb.lift)} จุด
          </div>
        </div>
      </div>

      <h3>พื้นที่ไหนชี้ผลรอบ</h3>
      <div className="card">
        <p className="small muted" style={{ marginTop: 0 }}>
          ดูจากรอบที่ทีมได้คิลแรกในพื้นที่นั้น แล้วรอบจบลงยังไง — ใช้คิลแรกเพราะเป็นเหตุการณ์
          ที่เกิดก่อนทุกอย่าง จึงตีความว่าเป็นต้นเหตุได้ ไม่ใช่ผลพลอยได้ของการที่กำลังจะชนะอยู่แล้ว
        </p>
        <div className="tablewrap">
          <table>
            <thead>
              <tr>
                <th>พื้นที่</th>
                <th className="num">รอบที่เปิดตรงนี้</th>
                <th className="num">ชนะรอบ</th>
                <th className="num">ต่างจากปกติ</th>
              </tr>
            </thead>
            <tbody>
              {impact.filter((z) => z.rounds > 0).map((z) => (
                <tr key={z.zone_id} className={z.enough ? '' : 'row-weak'}>
                  <td>
                    {z.name}
                    {!z.enough && <span className="tag sample" style={{ marginLeft: 6 }}>ข้อมูลน้อย</span>}
                  </td>
                  <td className="num">{z.rounds}</td>
                  <td className="num">{z.win_pct}% ({z.wins}/{z.rounds})</td>
                  <td className={`num ${z.lift > 0 ? 'pos' : z.lift < 0 ? 'neg' : ''}`}>{signed(z.lift)}</td>
                </tr>
              ))}
              {impact.every((z) => z.rounds === 0) && (
                <tr><td colSpan={4} className="muted">ยังไม่มีรอบที่ทีมนี้เป็นฝ่ายได้คิลแรก</td></tr>
              )}
            </tbody>
          </table>
        </div>
        <p className="small muted" style={{ marginBottom: 0 }}>
          แถวที่จางคือมีรอบน้อยกว่า {thresholds.min_rounds} รอบ — แสดงไว้ให้เห็นว่ามีข้อมูลอะไร แต่ยังสรุปไม่ได้
        </p>
      </div>

      <h3>ทีมและผู้เล่น</h3>
      <div className="card">
        <p className="small muted" style={{ marginTop: 0 }}>
          K/D บอกว่าใครเล่นดี แต่ไม่บอกว่าต้องแก้ตรงไหน — คอลัมน์ "ตายบ่อยสุดที่"
          คือสิ่งที่โค้ชเอาไปคุยกับคนคนนั้นได้ตรง ๆ · แสดงทั้งสองทีมเพราะโค้ชต้องส่องคู่แข่งด้วย
        </p>
        {[2, 3].map((team) => {
          const roster = players.filter((p) => p.team_number === team);
          if (roster.length === 0) return null;
          return (
            <div key={team} style={{ marginBottom: 18 }}>
              <div className="team-head">
                <span className={`swatch ${team === 2 ? 'gold' : 'blue'}`} />
                <b>{team === 2 ? 'ทีมที่เริ่มฝั่ง T' : 'ทีมที่เริ่มฝั่ง CT'}</b>
                <span className="small muted">
                  {roster.map((p) => p.name).join(' · ')}
                </span>
              </div>
              <div className="tablewrap">
                <table>
                  <thead>
                    <tr>
                      <th>ผู้เล่น</th>
                      <th className="num">คิล</th>
                      <th className="num">ตาย</th>
                      <th className="num">K/D</th>
                      <th className="num">ตายเดี่ยว</th>
                      <th>ทำคิลมากสุดที่</th>
                      <th>ตายบ่อยสุดที่</th>
                    </tr>
                  </thead>
                  <tbody>
                    {roster.map((p) => (
                      <tr key={p.steam64_id}>
                        <td><PlayerLink steam64={p.steam64_id}>{p.name}</PlayerLink></td>
                        <td className="num">{p.kills}</td>
                        <td className="num">{p.deaths}</td>
                        <td className={`num ${p.kd >= 1 ? 'pos' : 'neg'}`}>{p.kd ?? '—'}</td>
                        <td className={`num ${p.untraded_pct >= 80 ? 'neg' : ''}`}>
                          {p.untraded_deaths} ({p.untraded_pct}%)
                        </td>
                        <td className="small">
                          {p.top_kill_zone ? `${p.top_kill_zone.name} (${p.top_kill_zone.count})` : '—'}
                        </td>
                        <td className="small">
                          {p.top_death_zone ? `${p.top_death_zone.name} (${p.top_death_zone.count})` : '—'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          );
        })}
        <p className="small muted" style={{ marginBottom: 0 }}>
          "ตายเดี่ยว" = ตายแล้วไม่มีเพื่อนล้างแค้นให้ทันภายใน 5 วินาที ·
          ตัวเลขเปลี่ยนตามฝั่งที่เลือกด้านบน
        </p>
      </div>

      <h3>ตายแล้วไม่มีใครล้างแค้นให้</h3>
      <div className="card">
        <p className="small muted" style={{ marginTop: 0 }}>
          ตายเดี่ยวโดยไม่มีเพื่อนล้างแค้นภายใน 5 วินาที เป็นปัญหา<b>การยืนตำแหน่งและระยะห่าง</b>
          ซึ่งแก้ได้ด้วยการซ้อม ต่างจาก "ยิงไม่แม่น" ที่แก้ยากกว่ามาก ·
          ใช้นิยาม trade เดียวกับสกอร์บอร์ด ตัวเลขจึงตรงกันเสมอ
        </p>
        <div className="tablewrap">
          <table>
            <thead>
              <tr>
                <th>พื้นที่</th>
                <th className="num">ตายที่นี่</th>
                <th className="num">ไม่ถูกล้างแค้น</th>
                <th className="num">สัดส่วน</th>
              </tr>
            </thead>
            <tbody>
              {exposure.map((z) => (
                <tr key={z.zone_id} className={z.enough ? '' : 'row-weak'}>
                  <td>
                    {z.name}
                    {!z.enough && <span className="tag sample" style={{ marginLeft: 6 }}>ข้อมูลน้อย</span>}
                  </td>
                  <td className="num">{z.deaths}</td>
                  <td className="num">{z.untraded}</td>
                  <td className={`num ${z.untraded_pct >= 70 ? 'neg' : ''}`}>{z.untraded_pct}%</td>
                </tr>
              ))}
              {exposure.length === 0 && (
                <tr><td colSpan={4} className="muted">ยังไม่มีข้อมูลการตายในขอบเขตนี้</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </>
  );
}
