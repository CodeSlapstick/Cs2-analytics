/**
 * Map analytics — โซนของแมพที่ได้จาก unsupervised learning พร้อมคะแนนแต่ละโซน
 *
 * ตอบคำถามที่โค้ชถามจริง ๆ ว่า "ทีมเราแพ้ตรงไหนของแมพ" ซึ่งสกอร์บอร์ดตอบไม่ได้
 * เพราะสกอร์บอร์ดรวมทั้งแมพเป็นตัวเลขเดียว
 *
 * หน้านี้แสดงทั้งสามชั้นที่อาจารย์ขอ: ตัวโมเดล (แบ่งโซนยังไง ดีกว่ากริดแค่ไหน),
 * ผลลัพธ์เชิงภาพ (แผนที่), และตารางตัวเลขดิบไว้ตรวจย้อนหลัง
 */
import { useEffect, useState } from 'react';
import { api } from '../api.js';
import { Loading, ErrorBox, EmptyState, fmtDateTime } from '../components/ui.jsx';
import ZoneMap from '../components/ZoneMap.jsx';
import MapInsights from '../components/MapInsights.jsx';

export default function MapAnalytics() {
  const [maps, setMaps] = useState(null);
  const [mapName, setMapName] = useState(null);
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    api.maps()
      .then((m) => {
        setMaps(m);
        // เลือกแมพแรกที่ fit โซนไว้แล้วให้อัตโนมัติ ผู้ใช้จะได้ไม่เจอหน้าว่าง
        const fitted = m.find((x) => x.has_zones);
        if (fitted) setMapName(fitted.map_name);
      })
      .catch(setError);
  }, []);

  useEffect(() => {
    if (!mapName) return;
    let alive = true;
    setData(null);
    setError(null);
    api.mapZones(mapName)
      .then((d) => alive && setData(d))
      .catch((e) => alive && setError(e));
    return () => { alive = false; };
  }, [mapName]);

  const fitted = (maps || []).filter((m) => m.has_zones);

  return (
    <>
      <h1>วิเคราะห์พื้นที่ในแมพ</h1>
      <p className="sub">
        แบ่งแมพเป็นโซนด้วย unsupervised learning จากพิกัดที่มีคนตายจริงในไฟล์ .dem
        แล้วให้คะแนนว่าแต่ละโซนฝั่งไหนได้เปรียบ
      </p>

      <ErrorBox error={error} />

      {maps === null && <Loading />}

      {maps !== null && fitted.length === 0 && (
        <EmptyState title="ยังไม่ได้แบ่งโซนของแมพไหนเลย">
          ต้องมีแมตช์จากไฟล์ .dem จริงก่อน (ข้อมูลจำลองจาก <code>db:seed</code> ใช้ไม่ได้
          เพราะพิกัดเป็นการสุ่ม) แล้วรัน:
          <pre className="code">python parser/map_zones.py de_dust2</pre>
        </EmptyState>
      )}

      {fitted.length > 0 && (
        <div className="card" style={{ marginBottom: 16 }}>
          <div className="row">
            {fitted.map((m) => (
              <button key={m.map_name}
                      className={m.map_name === mapName ? 'primary' : ''}
                      style={{ flex: '0 0 auto' }}
                      onClick={() => setMapName(m.map_name)}>
                {m.map_name}
              </button>
            ))}
          </div>
        </div>
      )}

      {mapName && data === null && !error && <Loading text="กำลังคำนวณคะแนนโซน…" />}

      {data && <ZoneReport data={data} />}
    </>
  );
}

const zoneName = (zones, id) => zones.find((z) => z.zone_id === id)?.name ?? `โซน ${id}`;

/** ช่องกริดที่อันตรายที่สุด — ตัวเลขดิบไว้ตรวจย้อนหลังและอ้างอิงตอนคุยกับทีม */
function GridTable({ grid }) {
  const top = grid.cells.slice(0, 10);
  return (
    <>
      <h2>ช่องกริดที่มีคนตายมากที่สุด</h2>
      <div className="card">
        <table>
          <thead>
            <tr>
              <th>ช่อง</th>
              <th className="num">ตายทั้งหมด</th>
              <th className="num">คิลของฝั่งเริ่ม T</th>
              <th className="num">คิลของฝั่งเริ่ม CT</th>
              <th className="num">คะแนนฝั่งเริ่ม T</th>
            </tr>
          </thead>
          <tbody>
            {top.map((c) => (
              <tr key={c.label}>
                <td className="mono">{c.label}</td>
                <td className="num">{c.deaths}</td>
                <td className="num">{c.team2}</td>
                <td className="num">{c.team3}</td>
                <td className={`num ${c.score > 0 ? 'pos' : c.score < 0 ? 'neg' : ''}`}>
                  {c.score > 0 ? '+' : ''}{c.score}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="small muted" style={{ marginTop: 10 }}>
          ช่องละ {grid.cell_size} หน่วยเกม (~{(grid.cell_size / 52.5).toFixed(1)} เมตร) ·
          มีข้อมูล {grid.cells.length} ช่อง · ชื่อช่องนับจากมุมบนซ้ายของภาพแมพ
        </p>
      </div>
    </>
  );
}

function ZoneReport({ data }) {
  const { model, fit_from: fit, scored_from: scored } = data;
  const beatsGrid = model.silhouette > model.grid_baseline_silhouette;

  if (scored.kills === 0) {
    return (
      <EmptyState title="มีโซนแล้ว แต่ยังไม่มีแมตช์จริงให้คิดคะแนน">
        โซนถูก fit ไว้จาก {fit.matches} แมตช์ แต่ตอนนี้ฐานข้อมูลไม่มีแมตช์
        ที่มาจากไฟล์ .dem ของแมพนี้เหลืออยู่
      </EmptyState>
    );
  }

  return (
    <>
      <h2>โมเดลที่ใช้แบ่งโซน</h2>
      <div className="grid cols-4">
        <div className="card">
          <div className="stat">{data.zones.length}</div>
          <div className="stat-label">โซน (จาก k={model.k})</div>
        </div>
        <div className="card">
          <div className="stat">{model.silhouette}</div>
          <div className="stat-label">silhouette ของ {model.algorithm}</div>
        </div>
        <div className="card">
          <div className="stat">{model.grid_baseline_silhouette}</div>
          <div className="stat-label">baseline: ตีกริดตายตัว</div>
        </div>
        <div className="card">
          <div className="stat">{fit.deaths}</div>
          <div className="stat-label">จุดตายที่ใช้ fit</div>
        </div>
      </div>

      <div className={`notice ${beatsGrid ? '' : 'error'}`} style={{ marginBottom: 20 }}>
        {beatsGrid ? (
          <>
            การแบ่งด้วย {model.algorithm} ได้ silhouette <strong>{model.silhouette}</strong>{' '}
            สูงกว่าการตีกริดสี่เหลี่ยมตายตัวที่ได้ {model.grid_baseline_silhouette}{' '}
            — แปลว่าขอบโซนที่ได้เกาะไปตามที่คนปะทะกันจริง ไม่ใช่หั่นตามเส้นที่เราลากเอง
          </>
        ) : (
          <>
            silhouette ของ {model.algorithm} ({model.silhouette}) ยังไม่ชนะกริดตายตัว
            ({model.grid_baseline_silhouette}) — ข้อมูลอาจยังน้อยเกินไป ควรโหลดแมตช์เพิ่มแล้ว fit ใหม่
          </>
        )}
      </div>

      <p className="small muted">
        จำนวนโซน k เลือกโดย{model.k_chosen_by} ภายใต้เงื่อนไขว่าทุกโซนต้องมีจุดอย่างน้อย{' '}
        {model.min_points_per_zone} จุด · fit เมื่อ {fmtDateTime(data.fitted_at)} จาก{' '}
        {fit.matches} แมตช์ · คิดคะแนนจาก {scored.matches} แมตช์ ({scored.kills} คิล)
        เฉพาะแมตช์ที่มาจากไฟล์ .dem จริง
      </p>

      <h2>แผนที่โซน</h2>
      <div className="card">
        <ZoneMap zones={data.zones} grid={data.grid} flows={data.flows} radar={data.radar} />
      </div>

      <MapInsights mapName={data.map_name} />

      <h2>เส้นทางการปะทะที่พบบ่อย</h2>
      <div className="card">
        <p className="small muted" style={{ marginTop: 0 }}>
          นับจากโซนที่คนยิงยืนอยู่ ไปยังโซนที่คนตายอยู่ — ตอบว่าทีมไหนกดดันจากทางไหน
          (ดูเป็นลูกศรบนแผนที่ได้ด้วย แต่เปิดพร้อมกันหลายเส้นแล้วอ่านยาก จึงปิดไว้ก่อน)
        </p>
        <table>
          <thead>
            <tr><th>จากโซน</th><th>ไปโซน</th><th className="num">คิล</th></tr>
          </thead>
          <tbody>
            {data.flows.slice(0, 8).map((f) => (
              <tr key={`${f.from}-${f.to}`}>
                <td>{zoneName(data.zones, f.from)}</td>
                <td>{zoneName(data.zones, f.to)}</td>
                <td className="num">{f.kills}</td>
              </tr>
            ))}
            {data.flows.length === 0 && (
              <tr><td colSpan={3} className="muted">ยังไม่มีการปะทะข้ามโซน</td></tr>
            )}
          </tbody>
        </table>
      </div>

      {data.grid && <GridTable grid={data.grid} />}

      <h2>ตารางคะแนนรายโซน</h2>
      <div className="card">
        <table>
          <thead>
            <tr>
              <th>โซน</th>
              <th className="num">ปะทะ</th>
              <th className="num">คิล (เริ่ม T)</th>
              <th className="num">คิล (เริ่ม CT)</th>
              <th className="num">คะแนนฝั่งเริ่ม T</th>
              <th className="num">เปิดไฟต์ T/CT</th>
              <th>อาวุธที่ใช้บ่อย</th>
            </tr>
          </thead>
          <tbody>
            {data.zones.map((z) => (
              <tr key={z.zone_id}>
                <td>
                  {z.name}
                  {z.low_sample && <span className="tag sample" style={{ marginLeft: 6 }}>ข้อมูลน้อย</span>}
                </td>
                <td className="num">{z.duels}</td>
                <td className="num">{z.team2.kills}</td>
                <td className="num">{z.team3.kills}</td>
                <td className={`num ${z.team2.score > 0 ? 'pos' : z.team2.score < 0 ? 'neg' : ''}`}>
                  {z.team2.score > 0 ? '+' : ''}{z.team2.score ?? '—'}
                </td>
                <td className="num">{z.opening.team2}/{z.opening.team3}</td>
                <td className="small muted">
                  {(z.top_weapons || []).map((w) => `${w.weapon} ${w.kills}`).join(' · ') || '—'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="small muted" style={{ marginTop: 10 }}>
          คะแนนอยู่ในช่วง −10 ถึง +10 สเกลเดียวกับ KPI 5 มิติ · 0 = สูสี · บวก = ทีมที่เริ่มฝั่ง T
          ได้เปรียบในโซนนั้น · คิดจากสัดส่วนคิลที่ถ่วงด้วยจำนวนการปะทะ โซนที่ปะทะน้อยคะแนนจึงถูกดึงเข้าหา 0
        </p>
      </div>
    </>
  );
}
