/**
 * แผนที่วิเคราะห์พื้นที่ — วางข้อมูลการปะทะทับภาพเรดาร์ของแมพ
 *
 * มีสองชั้นที่ตอบคนละคำถาม เปิด/ปิดได้อิสระ:
 *
 *   กริด  "ตรงพิกัดนี้เกิดอะไรขึ้น"  ช่องสี่เหลี่ยมขนาดเท่ากันทั้งแมพ ชี้ตำแหน่งได้แม่น
 *         และเรียกชื่อช่องได้ (K4) แบบเดียวกับที่โค้ชเรียกในห้องประชุม
 *   โซน   "พื้นที่นี้เรียกว่าอะไร ใครคุมอยู่"  มาจาก KMeans หยาบกว่าแต่มีความหมาย
 *
 * ค่าปรับเทียบพิกัด (pos_x/pos_y/scale/grid) มาจาก backend/data/radars.json
 * ผ่าน API ไม่ได้เขียนซ้ำไว้ฝั่งนี้ — ถ้าเขียนสองที่แล้วแก้ข้างเดียว จุดจะไปตกผิดที่
 * โดยที่หน้าเว็บยังดูปกติทุกอย่าง ซึ่งเป็นบั๊กที่จับยากที่สุดแบบหนึ่ง
 *
 * โซนไม่วาดขอบแล้ว เหลือแค่ชื่อกับ hotspot — ขอบโซนทับเส้นกริดแล้วลายตา
 * และตัวกริดเองก็บอกตำแหน่งได้ละเอียดกว่าอยู่แล้ว ขอบเขตโซนที่แน่นอนดูได้จาก
 * ตารางคะแนนรายโซนใต้แผนที่
 *
 * ลูกศรทิศทางการปะทะปิดไว้เป็นค่าเริ่มต้น เปิดพร้อมกันหลายเส้นแล้วอ่านไม่ออก
 * ข้อมูลเดียวกันอยู่ในตาราง "เส้นทางการปะทะ" ใต้แผนที่ ซึ่งอ่านง่ายกว่า
 */
import { useMemo, useState } from 'react';

// ขั้วของสเกล diverging — ผ่านการตรวจ contrast/CVD บนพื้น navy แล้ว
const POLE_T = '#b8801f'; // ทีมที่เริ่มฝั่ง T ได้เปรียบ
const POLE_CT = '#3d7ed4'; // ทีมที่เริ่มฝั่ง CT ได้เปรียบ
const MID = '#4a5a75'; // กลาง = สูสี ต้องเป็นเทา ไม่ใช่สีที่สาม
const EDGE_T = '#e0a33e';
const EDGE_CT = '#5b9bf3';

/** คะแนนตั้งแต่ ±5 ขึ้นไปถือว่าสุดสเกลสีแล้ว */
const FULL_SCALE = 5;

const VIEW = 900; // กรอบของผังเปล่า ใช้เมื่อแมพนั้นยังไม่มีภาพเรดาร์

function mix(a, b, t) {
  const pa = [1, 3, 5].map((i) => parseInt(a.slice(i, i + 2), 16));
  const pb = [1, 3, 5].map((i) => parseInt(b.slice(i, i + 2), 16));
  return `#${pa.map((v, i) => Math.round(v + (pb[i] - v) * t).toString(16).padStart(2, '0')).join('')}`;
}

/** คะแนน −10..+10 -> สีบนสเกลสองขั้ว (0 = เทากลาง) */
function scoreColor(score) {
  if (score === null || score === undefined) return MID;
  const t = Math.min(Math.abs(Number(score)) / FULL_SCALE, 1);
  return mix(MID, Number(score) >= 0 ? POLE_T : POLE_CT, t);
}

/** ตัวแปลงพิกัดเกม -> พิกเซลบนภาพเรดาร์ (ใช้ค่าที่ backend ส่งมา) */
function radarProjection(radar) {
  if (!radar) return null;
  return {
    size: radar.size,
    x: (gx) => (gx - radar.pos_x) / radar.scale,
    // แกน y ในเกมเพิ่มขึ้นไปทางเหนือ แต่ในภาพเพิ่มลงล่าง จึงต้องกลับด้าน
    y: (gy) => (radar.pos_y - gy) / radar.scale,
    len: (d) => d / radar.scale,
  };
}

/** ทางสำรองเมื่อแมพนั้นยังไม่มีภาพเรดาร์ — จัดกรอบจากขอบเขตของโซนเอง */
function fallbackProjection(zones) {
  const pts = zones.flatMap((z) => [[z.bbox[0], z.bbox[1]], [z.bbox[2], z.bbox[3]]]);
  const xs = pts.map((p) => p[0]);
  const ys = pts.map((p) => p[1]);
  const minX = Math.min(...xs);
  const maxX = Math.max(...xs);
  const minY = Math.min(...ys);
  const maxY = Math.max(...ys);
  const pad = 48;
  const scale = (VIEW - pad * 2) / (Math.max(maxX - minX, maxY - minY) || 1);
  const offX = pad + ((VIEW - pad * 2) - (maxX - minX) * scale) / 2;
  const offY = pad + ((VIEW - pad * 2) - (maxY - minY) * scale) / 2;
  return {
    size: VIEW,
    x: (gx) => offX + (gx - minX) * scale,
    y: (gy) => offY + (maxY - gy) * scale,
    len: (d) => d * scale,
  };
}

const signed = (v) => (v > 0 ? `+${v}` : `${v}`);

/** A, B, … Z, AA — ต้องให้ผลตรงกับ columnLabel() ฝั่ง backend เป๊ะ ๆ */
function colLabel(i) {
  let n = i;
  let out = '';
  do {
    out = String.fromCharCode(65 + (n % 26)) + out;
    n = Math.floor(n / 26) - 1;
  } while (n >= 0);
  return out;
}

export default function ZoneMap({ zones, grid = null, flows = [], radar = null, teamNames = {}, height = 620 }) {
  const [hoverZone, setHoverZone] = useState(null);
  const [hoverCell, setHoverCell] = useState(null);
  const [showGrid, setShowGrid] = useState(true);
  const [showZones, setShowZones] = useState(true);
  const [showFlows, setShowFlows] = useState(false);

  const proj = useMemo(
    () => radarProjection(radar) || (zones?.length ? fallbackProjection(zones) : null),
    [radar, zones]
  );
  const byId = useMemo(() => new Map((zones || []).map((z) => [z.zone_id, z])), [zones]);

  if (!proj || !zones?.length) return null;

  const view = proj.size;
  const maxFlow = Math.max(1, ...flows.map((f) => f.kills));
  const nameT = teamNames.team2 || 'ทีมที่เริ่มฝั่ง T';
  const nameCT = teamNames.team3 || 'ทีมที่เริ่มฝั่ง CT';
  const k = view / 900; // ตัวคูณให้เส้นและตัวอักษรโตตามกรอบ
  const halo = { paintOrder: 'stroke', stroke: '#0b1a33', strokeWidth: 4 * k, strokeLinejoin: 'round' };
  const cellPx = grid ? proj.len(grid.cell_size) : 0;
  const activeCell = hoverCell && grid ? grid.cells.find((c) => c.label === hoverCell) : null;

  return (
    <div className="zonemap">
      <div className="zonemap-controls small">
        <label><input type="checkbox" checked={showGrid} onChange={(e) => setShowGrid(e.target.checked)} /> กริด</label>
        <label><input type="checkbox" checked={showZones} onChange={(e) => setShowZones(e.target.checked)} /> ชื่อโซน + hotspot</label>
        <label><input type="checkbox" checked={showFlows} onChange={(e) => setShowFlows(e.target.checked)} /> ลูกศรทิศทางการยิง</label>
      </div>

      <svg viewBox={`0 0 ${view} ${view}`} style={{ width: '100%', height, display: 'block' }}
           role="img" aria-label="แผนที่วิเคราะห์พื้นที่">
        <defs>
          {/* ลดความจัดของภาพเรดาร์ ให้จมเป็นพื้นหลัง ไม่แย่งสายตากับข้อมูลที่วางทับ */}
          <filter id="zm-recede"><feColorMatrix type="saturate" values="0.35" /></filter>
          <marker id="zm-arrow" viewBox="0 0 10 10" refX="9" refY="5"
                  markerWidth="5" markerHeight="5" orient="auto-start-reverse">
            <path d="M 0 0 L 10 5 L 0 10 z" fill="#dbe5f5" />
          </marker>
        </defs>

        {radar
          ? <image href={radar.image} x="0" y="0" width={view} height={view} filter="url(#zm-recede)" />
          : <rect x="0" y="0" width={view} height={view} fill="#0b1a33" />}

        {showGrid && grid && (
          <g>
            {/* เส้นกริดบาง ๆ ทั้งแมพ ให้เห็นว่าช่องที่มีข้อมูลใหญ่เท่าไรเทียบกับที่ไม่มี */}
            <g stroke="#8ea3c4" strokeOpacity="0.16" strokeWidth={1 * k}>
              {Array.from({ length: Math.ceil(view / cellPx) + 1 }, (_, i) => (
                <line key={`v${i}`} x1={i * cellPx} y1="0" x2={i * cellPx} y2={view} />
              ))}
              {Array.from({ length: Math.ceil(view / cellPx) + 1 }, (_, i) => (
                <line key={`h${i}`} x1="0" y1={i * cellPx} x2={view} y2={i * cellPx} />
              ))}
            </g>

            {grid.cells.map((c) => {
              // ความทึบบอก "มีข้อมูลแค่ไหน" ส่วนสีบอก "ใครได้เปรียบ" — คนละเรื่องกัน
              // ช่องที่มีคิลเดียวจึงจางจนไม่ตะโกน แม้คะแนนจะสุดขั้ว
              const weight = 0.28 + 0.62 * (c.deaths / Math.max(1, grid.max_deaths));
              const on = hoverCell === c.label;
              return (
                <rect key={c.label}
                      x={proj.x(c.x0)} y={proj.y(c.y0)} width={cellPx} height={cellPx}
                      fill={scoreColor(c.score)} fillOpacity={on ? 0.9 : weight}
                      stroke="#e2ebfa" strokeOpacity={on ? 0.9 : 0.25} strokeWidth={1.2 * k}
                      onMouseEnter={() => setHoverCell(c.label)}
                      onMouseLeave={() => setHoverCell(null)}
                      style={{ cursor: 'pointer' }} />
              );
            })}

            {/* ป้ายคอลัมน์/แถวของเราเอง — ภาพเรดาร์มีตัวเลขกริดของมันอยู่แล้วแต่จางมาก
                และเรายืนยันไม่ได้ว่าเริ่มนับตรงไหน จึงเขียนของเราทับให้อ่านได้ชัดเจน */}
            <g fill="#8ea3c4" fontSize={12 * k} textAnchor="middle" style={{ pointerEvents: 'none' }}>
              {Array.from({ length: Math.ceil(view / cellPx) }, (_, i) => (
                <text key={`cl${i}`} x={(i + 0.5) * cellPx} y={14 * k}>{colLabel(i)}</text>
              ))}
              {Array.from({ length: Math.ceil(view / cellPx) }, (_, i) => (
                <text key={`rl${i}`} x={10 * k} y={(i + 0.5) * cellPx + 4 * k}>{i + 1}</text>
              ))}
            </g>
          </g>
        )}

        {showFlows && (
          <g style={{ pointerEvents: 'none' }}>
            {flows.map((f) => {
              const a = byId.get(f.from);
              const b = byId.get(f.to);
              if (!a || !b) return null;
              return (
                <line key={`${f.from}-${f.to}`}
                      x1={proj.x(a.centroid[0])} y1={proj.y(a.centroid[1])}
                      x2={proj.x(b.centroid[0])} y2={proj.y(b.centroid[1])}
                      stroke="#dbe5f5" strokeWidth={(1.5 + (f.kills / maxFlow) * 5) * k}
                      strokeLinecap="round" markerEnd="url(#zm-arrow)" opacity="0.65" />
              );
            })}
          </g>
        )}

        {showZones && (
          <g>
            {zones.map((z) => (
              <g key={z.zone_id}>
                {/* hotspot จาก DBSCAN — วงแหวนสีพื้นกันไม่ให้จุดจมหายไปในสีของกริด */}
                {(z.hotspots || []).map((h, i) => (
                  <circle key={i} cx={proj.x(h.x)} cy={proj.y(h.y)} r={5 * k}
                          fill="#f2f6ff" stroke="#0b1a33" strokeWidth={2 * k}
                          style={{ pointerEvents: 'none' }} />
                ))}
                {/* ป้ายชื่อเป็นตัวรับ hover ของโซนแทนขอบเขตที่เอาออกไปแล้ว */}
                <text x={proj.x(z.centroid[0])} y={proj.y(z.centroid[1])} textAnchor="middle"
                      style={{ ...halo, cursor: 'pointer' }} fill="#f2f6ff"
                      fontSize={19 * k} fontWeight="600"
                      onMouseEnter={() => setHoverZone(z.zone_id)}
                      onMouseLeave={() => setHoverZone(null)}>
                  {z.name} {z.team2?.score === null ? '' : signed(z.team2.score)}
                </text>
              </g>
            ))}
          </g>
        )}
      </svg>

      <div className="zonemap-legend small">
        <span className="zm-key"><i style={{ background: EDGE_CT }} /> {nameCT} ได้เปรียบ</span>
        <span className="zm-ramp" aria-hidden="true"
              style={{ background: `linear-gradient(90deg, ${POLE_CT}, ${MID}, ${POLE_T})` }} />
        <span className="zm-key"><i style={{ background: EDGE_T }} /> {nameT} ได้เปรียบ</span>
        <span className="muted zm-note">
          สี = ใครได้เปรียบ · ความทึบ = มีข้อมูลมากแค่ไหน ·
          <i className="zm-dot" /> จุดขาว = hotspot จาก DBSCAN
        </span>
      </div>

      {activeCell && <CellTip cell={activeCell} nameT={nameT} nameCT={nameCT} />}
      {!activeCell && hoverZone !== null && byId.get(hoverZone) && (
        <ZoneTip zone={byId.get(hoverZone)} nameT={nameT} nameCT={nameCT} />
      )}
    </div>
  );
}

function CellTip({ cell, nameT, nameCT }) {
  return (
    <div className="zonemap-tip card">
      <strong>ช่อง {cell.label}</strong>
      <div className="small muted" style={{ marginBottom: 6 }}>ตายที่นี่ {cell.deaths} ครั้ง</div>
      <table className="tip-table">
        <tbody>
          <tr><td>{nameT}</td><td>{cell.team2} คิล</td>
            <td className={cell.score > 0 ? 'pos' : cell.score < 0 ? 'neg' : ''}>{signed(cell.score)}</td></tr>
          <tr><td>{nameCT}</td><td>{cell.team3} คิล</td><td /></tr>
        </tbody>
      </table>
    </div>
  );
}

function ZoneTip({ zone, nameT, nameCT }) {
  return (
    <div className="zonemap-tip card">
      <strong>{zone.name}</strong>
      <div className="small muted" style={{ marginBottom: 6 }}>
        ปะทะ {zone.duels} ครั้ง · เปิดไฟต์ที่นี่ {zone.opening.team2 + zone.opening.team3} รอบ
      </div>
      <table className="tip-table">
        <tbody>
          {[['team2', nameT], ['team3', nameCT]].map(([key, label]) => (
            <tr key={key}>
              <td>{label}</td>
              <td>{zone[key].kills} คิล / {zone[key].deaths} ตาย</td>
              <td className={zone[key].score > 0 ? 'pos' : zone[key].score < 0 ? 'neg' : ''}>
                {zone[key].score === null ? '—' : signed(zone[key].score)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {zone.top_weapons?.length > 0 && (
        <div className="small muted" style={{ marginTop: 6 }}>
          อาวุธที่ใช้บ่อย: {zone.top_weapons.map((w) => `${w.weapon} (${w.kills})`).join(', ')}
        </div>
      )}
    </div>
  );
}
