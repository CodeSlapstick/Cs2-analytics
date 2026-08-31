/**
 * ชิ้นส่วน UI เล็ก ๆ ที่ใช้ซ้ำทั้งเว็บ
 * กราฟทั้งหมดย้ายไปอยู่ components/charts.jsx (ECharts) ตั้งแต่ Sprint 1
 */
import { Link } from 'react-router-dom';

export const DIM_LABEL = {
  aim: 'เล็ง (Aim)',
  positioning: 'ตำแหน่ง',
  utility: 'ยูทิลิตี้',
  clutch: 'คลัตช์',
  opening: 'เปิดไฟต์',
};

/** คำอธิบายว่าแต่ละมิติวัดจากอะไร — ใช้เป็น tooltip ให้โค้ชที่เพิ่งเปิดใช้ครั้งแรก */
export const DIM_HINT = {
  aim: 'ดาเมจต่อรอบ (ADR), สัดส่วนเฮดช็อต, คิลต่อรอบ',
  positioning: 'การตายต่อรอบ, อัตรารอดจนจบรอบ, ตายในจุดที่เพื่อนล้างแค้นให้ได้',
  utility: 'ดาเมจจากระเบิดต่อรอบ, แฟลชแอสซิสต์, จำนวนยูทิลิตี้ที่ใช้',
  clutch: 'อัตราชนะเมื่อเหลือคนเดียว (1vX) และความถี่ที่ต้องเจอสถานการณ์นั้น',
  opening: 'อัตราชนะการดวลคู่แรกของรอบ และความถี่ที่กล้าเปิดไฟต์',
};

export function Loading({ text = 'กำลังโหลด…' }) {
  return <div className="spinner">{text}</div>;
}

export function ErrorBox({ error }) {
  if (!error) return null;
  return <div className="notice error">{error.message || String(error)}</div>;
}

/**
 * สถานะ "ยังไม่มีข้อมูล" — ต่างจาก error ตรงที่ระบบทำงานปกติ แค่ยังไม่มีแมตช์ในฐานข้อมูล
 * บอกวิธีแก้ไปเลยว่าต้องทำอะไรต่อ ไม่ใช่ปล่อยหน้าว่าง ๆ
 */
export function EmptyState({ title, children }) {
  return (
    <div className="card empty">
      <h3 style={{ marginBottom: 8 }}>{title}</h3>
      <div className="small muted">{children}</div>
    </div>
  );
}

export function Signed({ value, digits = 2, suffix = '' }) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return <span className="muted">—</span>;
  }
  const n = Number(value);
  const cls = n > 0 ? 'pos' : n < 0 ? 'neg' : '';
  return <span className={cls}>{n > 0 ? '+' : ''}{n.toFixed(digits)}{suffix}</span>;
}

export function Stat({ value, label, hint }) {
  return (
    <div className="card" title={hint || undefined}>
      <div className="stat">{value ?? '—'}</div>
      <div className="stat-label">{label}</div>
    </div>
  );
}

export function Outcome({ value }) {
  const label = { win: 'ชนะ', loss: 'แพ้', tie: 'เสมอ' }[value] || value;
  return <span className={`tag ${value}`}>{label}</span>;
}

/** ป้ายบอกที่มาของข้อมูลแมตช์ — แยกให้ชัดว่านัดไหนมาจากไฟล์ .dem จริง นัดไหนเป็นข้อมูลจำลอง */
export function SourceTag({ source }) {
  if (source === 'demo') return <span className="tag demo">จากไฟล์ .dem</span>;
  return <span className="tag sample">ข้อมูลจำลอง</span>;
}

export const fmtPct = (v, digits = 1) =>
  v === null || v === undefined ? '—' : `${(Number(v) * 100).toFixed(digits)}%`;

export const fmtNum = (v, digits = 2) =>
  v === null || v === undefined ? '—' : Number(v).toFixed(digits);

export const fmtDate = (s) =>
  s ? new Date(s).toLocaleDateString('th-TH', { day: '2-digit', month: 'short', year: '2-digit' }) : '—';

export const fmtDateTime = (s) => (s ? new Date(s).toLocaleString('th-TH') : '—');

export function PlayerLink({ steam64, children }) {
  return <Link to={`/player/${steam64}`}>{children}</Link>;
}
