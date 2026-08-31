/**
 * หน้าอัปโหลดไฟล์ .dem
 *
 * ก่อนหน้านี้ต้องรัน `python parser/parse_demo.py ... && npm run etl` เองจากคอมมานด์ไลน์
 * ซึ่งโค้ชทำไม่ได้ หน้านี้ยิงไฟล์เข้า POST /api/uploads แล้วตามสถานะจนจบ
 *
 * ทำไมต้องมี progress bar สองท่อน: ท่อนแรกคืออัปโหลดไฟล์ขึ้นเซิร์ฟเวอร์ (รู้เปอร์เซ็นต์
 * ได้จริงเพราะรู้ขนาดไฟล์) ท่อนที่สองคือฝั่งเซิร์ฟเวอร์ parse ซึ่งกินเวลาหลายนาที
 * และไม่รู้เปอร์เซ็นต์ — จึงรายงานเป็น "ขั้นตอนที่กำลังทำ" แทนที่จะแกล้งเดาเป็นตัวเลข
 */
import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { api, uploadDemo } from '../api.js';
import { ErrorBox } from '../components/ui.jsx';

const STAGE_LABEL = {
  queued: 'รอคิว',
  parsing: 'กำลังแปลงไฟล์ .dem',
  loading: 'กำลังโหลดเข้าฐานข้อมูล',
  zones: 'กำลังวิเคราะห์พื้นที่ในแมพ',
  done: 'เสร็จแล้ว',
  failed: 'ล้มเหลว',
};

const MB = (b) => (b === null || b === undefined ? '—' : `${(b / 1024 / 1024).toFixed(1)} MB`);

export default function Upload() {
  const [file, setFile] = useState(null);
  const [tickrate, setTickrate] = useState('');
  const [sent, setSent] = useState(0);
  const [busy, setBusy] = useState(false);
  const [job, setJob] = useState(null);
  const [error, setError] = useState(null);
  const [drag, setDrag] = useState(false);
  const inputRef = useRef(null);
  const pollRef = useRef(null);

  // หยุด poll ตอนออกจากหน้า ไม่งั้นยิงคำขอค้างไว้เรื่อย ๆ
  useEffect(() => () => clearInterval(pollRef.current), []);

  const pick = (f) => {
    if (!f) return;
    if (!f.name.toLowerCase().endsWith('.dem')) {
      setError(new Error('ต้องเป็นไฟล์ .dem เท่านั้น'));
      return;
    }
    setError(null);
    setJob(null);
    setSent(0);
    setFile(f);
  };

  const start = async () => {
    if (!file || busy) return;
    setBusy(true);
    setError(null);
    setSent(0);
    try {
      const created = await uploadDemo(file, {
        tickrate: tickrate ? Number(tickrate) : undefined,
        onProgress: setSent,
      });
      setJob(created);
      poll(created.id);
    } catch (e) {
      setError(e);
      setBusy(false);
    }
  };

  const poll = (jobId) => {
    clearInterval(pollRef.current);
    pollRef.current = setInterval(async () => {
      try {
        const j = await api.uploadJob(jobId);
        setJob(j);
        if (j.stage === 'done' || j.stage === 'failed') {
          clearInterval(pollRef.current);
          setBusy(false);
        }
      } catch (e) {
        clearInterval(pollRef.current);
        setError(e);
        setBusy(false);
      }
    }, 2000);
  };

  const pct = file && sent ? Math.min(100, Math.round((sent / file.size) * 100)) : 0;
  const uploading = busy && !job;

  return (
    <>
      <h1>อัปโหลดไฟล์ .dem</h1>
      <p className="sub">
        ลากไฟล์เดโมของ CS2 มาวาง ระบบจะแปลงเป็นข้อมูลแล้วโหลดเข้าฐานข้อมูลให้เอง
        ไม่ต้องรันคำสั่งเองอีก
      </p>

      <ErrorBox error={error} />

      <div className={`dropzone${drag ? ' over' : ''}`}
           onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
           onDragLeave={() => setDrag(false)}
           onDrop={(e) => { e.preventDefault(); setDrag(false); pick(e.dataTransfer.files?.[0]); }}
           onClick={() => inputRef.current?.click()}>
        <input ref={inputRef} type="file" accept=".dem" hidden
               onChange={(e) => pick(e.target.files?.[0])} />
        {file ? (
          <>
            <strong>{file.name}</strong>
            <div className="small muted">{MB(file.size)}</div>
          </>
        ) : (
          <>
            <strong>ลากไฟล์ .dem มาวางที่นี่</strong>
            <div className="small muted">หรือคลิกเพื่อเลือกไฟล์ · ไฟล์แมตช์เต็มแมพมักอยู่ราว 100–400 MB</div>
          </>
        )}
      </div>

      <div className="card" style={{ marginTop: 16 }}>
        <div className="row" style={{ alignItems: 'flex-end', gap: 12 }}>
          <label style={{ flex: '0 0 200px' }}>
            <div className="small muted">tickrate ของเซิร์ฟเวอร์</div>
            <select value={tickrate} onChange={(e) => setTickrate(e.target.value)} disabled={busy}>
              <option value="">64 (Premier / matchmaking)</option>
              <option value="128">128 (FACEIT บางเซิร์ฟเวอร์)</option>
            </select>
          </label>
          <button className="primary" style={{ flex: '0 0 auto' }} onClick={start} disabled={!file || busy}>
            {busy ? 'กำลังทำงาน…' : 'เริ่มประมวลผล'}
          </button>
        </div>

        {uploading && (
          <div style={{ marginTop: 14 }}>
            <div className="small muted">กำลังอัปโหลด {pct}% ({MB(sent)} / {MB(file.size)})</div>
            <div className="bar"><div className="bar-fill" style={{ width: `${pct}%` }} /></div>
          </div>
        )}

        {job && <JobStatus job={job} />}
      </div>

      <h2>ขั้นตอนที่ระบบทำให้</h2>
      <div className="card small muted">
        <ol style={{ margin: 0, paddingLeft: 20 }}>
          <li>รับไฟล์แล้วเขียนลงดิสก์แบบสตรีม (ไม่อมทั้งไฟล์ไว้ในหน่วยความจำ)</li>
          <li>เรียก <code>parser/parse_demo.py</code> แปลงเป็น normalized JSON — ขั้นนี้นานที่สุด</li>
          <li>โหลด JSON เข้า PostgreSQL ผ่าน ETL ตัวเดียวกับที่ใช้ตอนรันคอมมานด์ไลน์</li>
          <li>แบ่งพื้นที่ในแมพใหม่ด้วย ML ให้รวมแมตช์นี้เข้าไปด้วย (KMeans + DBSCAN)</li>
          <li>ลบไฟล์ .dem ดิบทิ้ง เพราะ JSON เก็บทุกอย่างที่ระบบต้องใช้แล้ว</li>
        </ol>
        <p style={{ marginBottom: 0, marginTop: 10 }}>
          โหลดไฟล์เดิมซ้ำได้ ระบบจะอัปเดตทับแมตช์เดิมแทนที่จะเพิ่มซ้ำ
          (รหัสแมตช์คำนวณจากเนื้อไฟล์ ไม่ใช่ชื่อไฟล์) · การแบ่งพื้นที่ใหม่ทำให้ขอบเขต
          ขยับได้ ตัวเลขที่จดไว้ก่อนหน้าจึงอาจไม่ตรงกับที่เห็นวันนี้ — ไฟล์โซนบันทึกไว้เสมอ
          ว่า fit จากแมตช์ไหนบ้าง ย้อนตรวจได้
        </p>
      </div>
    </>
  );
}

function JobStatus({ job }) {
  const done = job.stage === 'done';
  const failed = job.stage === 'failed';
  return (
    <div style={{ marginTop: 14 }}>
      <div className="row" style={{ gap: 8, alignItems: 'center' }}>
        <span className={`tag ${done ? 'win' : failed ? 'loss' : 'sample'}`}>
          {STAGE_LABEL[job.stage] || job.stage}
        </span>
        <span className="small muted">{job.message}</span>
      </div>

      {!done && !failed && <div className="bar indeterminate"><div className="bar-fill" /></div>}

      {done && job.result && (
        <div className="notice" style={{ marginTop: 10 }}>
          {job.result.replaced ? 'อัปเดตทับแมตช์เดิม' : 'เพิ่มแมตช์ใหม่'} —{' '}
          <strong>{job.result.map_name}</strong> · {job.result.rounds} รอบ ·{' '}
          {job.result.players} ผู้เล่น · {job.result.events} events
          <div className="row" style={{ marginTop: 12 }}>
            {job.result.map_name && job.result.zones_refitted && (
              <Link className="btn primary" style={{ flex: '0 0 auto' }} to="/maps">
                ดูผลวิเคราะห์พื้นที่ของ {job.result.map_name}
              </Link>
            )}
            {job.result.match_id && (
              <Link className="btn" style={{ flex: '0 0 auto' }} to={`/match/${job.result.match_id}`}>
                เปิดสกอร์บอร์ดแมตช์
              </Link>
            )}
          </div>
          {job.result.warnings?.length > 0 && (
            <ul className="small" style={{ marginBottom: 0 }}>
              {job.result.warnings.map((w, i) => <li key={i}>{w}</li>)}
            </ul>
          )}
        </div>
      )}

      {failed && <div className="notice error" style={{ marginTop: 10 }}>{job.error}</div>}
    </div>
  );
}
