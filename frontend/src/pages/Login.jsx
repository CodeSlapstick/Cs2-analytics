import { useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { api } from '../api.js';
import { useAuth } from '../auth-context.js';

const ERRORS = {
  steam_verify_failed: 'ยืนยันตัวตนกับ Steam ไม่สำเร็จ ลองใหม่อีกครั้ง',
  server_error: 'เซิร์ฟเวอร์มีปัญหา ตรวจ log ฝั่ง backend',
};

export default function Login() {
  const [params] = useSearchParams();
  const { refresh } = useAuth();
  const [devId, setDevId] = useState('76561198283431555');
  const [devError, setDevError] = useState(null);
  const err = params.get('error');

  const devLogin = async () => {
    setDevError(null);
    try {
      await api.devLogin(devId.trim());
      await refresh();
    } catch (e) {
      setDevError(e.message);
    }
  };

  return (
    <div className="container">
      <div className="center-box">
        <h1>CS2 Team Analytics</h1>
        <p className="sub">
          เครื่องมือวิเคราะห์สมรรถนะทีม Counter-Strike 2 สำหรับโค้ชและนักวิเคราะห์
        </p>

        {err && <div className="notice error" style={{ marginBottom: 16 }}>{ERRORS[err] || err}</div>}

        <div className="card">
          <h2>เข้าสู่ระบบ</h2>
          <p className="small muted" style={{ marginTop: 0 }}>
            ระบบใช้ Steam OpenID เราไม่เห็นและไม่เก็บรหัสผ่าน Steam ของคุณ
          </p>
          <a className="btn" href="/auth/steam"
             style={{ display: 'block', textAlign: 'center', background: 'var(--gold)',
                      borderColor: 'var(--gold)', color: 'var(--navy-900)', fontWeight: 700 }}>
            เข้าสู่ระบบด้วย Steam
          </a>
        </div>

        <details className="card" style={{ marginTop: 16 }}>
          <summary className="muted small" style={{ cursor: 'pointer' }}>
            โหมดทดสอบ (ใช้ได้เฉพาะตอน development)
          </summary>
          <p className="small muted">
            ใส่ Steam64 ID เพื่อเข้าระบบโดยไม่ผ่าน Steam — ใช้ตอนพัฒนาเท่านั้น
            (ปิดอัตโนมัติเมื่อ NODE_ENV=production)
          </p>
          <p className="small muted">
            ถ้ารัน <span className="mono">npm run db:seed</span> ไว้ ใช้ ID ที่เติมให้แล้วด้านล่างได้เลย
            จะเห็นข้อมูลตัวอย่างครบทุกหน้า
          </p>
          <div className="row">
            <input value={devId} onChange={(e) => setDevId(e.target.value)} placeholder="765611980…" />
            <button onClick={devLogin}>เข้าระบบ</button>
          </div>
          {devError && <p className="small neg" style={{ marginBottom: 0 }}>{devError}</p>}
        </details>
      </div>
    </div>
  );
}
