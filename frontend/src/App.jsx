import { useEffect, useState } from 'react';
import { Routes, Route, NavLink, Navigate, useLocation } from 'react-router-dom';
import { api } from './api.js';
import { AuthCtx } from './auth-context.js';
import Login from './pages/Login.jsx';
import Dashboard from './pages/Dashboard.jsx';
import Player from './pages/Player.jsx';
import Matches from './pages/Matches.jsx';
import MapAnalytics from './pages/MapAnalytics.jsx';
import Upload from './pages/Upload.jsx';
import { Loading } from './components/ui.jsx';

/**
 * เมนูหลัก — ย้ายจากแถบบนมาเป็นแถบข้างตั้งแต่ Sprint 1
 * เหตุผล: เมนูจะเพิ่มขึ้นอีกหลายหน้าเมื่อ pipeline .dem เสร็จ (heatmap, รายงานรอบ,
 * ประวัติการอัปโหลด) แถบบนแนวนอนจะเริ่มตัดคำและอ่านยากบนจอโน้ตบุ๊ก
 */
const NAV = [
  { to: '/', label: 'แดชบอร์ด', hint: 'ภาพรวมของฉัน', end: true },
  { to: '/matches', label: 'แมตช์', hint: 'แมตช์ที่โหลดเข้าระบบ' },
  { to: '/maps', label: 'วิเคราะห์พื้นที่', hint: 'โซนในแมพจาก ML' },
  { to: '/upload', label: 'อัปโหลด .dem', hint: 'เพิ่มแมตช์เข้าระบบ' },
];

function Sidebar({ user, onLogout, open, onClose }) {
  const cls = ({ isActive }) => (isActive ? 'nav-item active' : 'nav-item');
  return (
    <aside className={open ? 'sidebar open' : 'sidebar'}>
      <div className="brand">
        CS2 <span>Team Analytics</span>
        <div className="brand-sub">SP-404 · UTCC STECH</div>
      </div>

      <nav>
        {NAV.map((item) => (
          <NavLink key={item.to} to={item.to} end={item.end} className={cls} onClick={onClose}>
            <span>{item.label}</span>
            <small>{item.hint}</small>
          </NavLink>
        ))}
      </nav>

      <div className="sidebar-foot">
        <div className="who">
          {user?.avatar_url
            ? <img src={user.avatar_url} alt="" />
            : <div className="avatar-blank">{(user?.display_name || '?').slice(0, 1)}</div>}
          <div className="who-text">
            <div>{user?.display_name}</div>
            <div className="mono small muted">{user?.steam64_id}</div>
          </div>
        </div>
        <button className="ghost" onClick={onLogout}>ออกจากระบบ</button>
      </div>
    </aside>
  );
}

export default function App() {
  const [user, setUser] = useState(null);
  const [ready, setReady] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const location = useLocation();

  const refresh = () =>
    api.me()
      .then((d) => setUser(d.user))
      .catch(() => setUser(null))
      .finally(() => setReady(true));

  useEffect(() => { refresh(); }, []);
  useEffect(() => { setMenuOpen(false); }, [location.pathname]);

  const logout = async () => {
    await api.logout().catch(() => {});
    setUser(null);
  };

  if (!ready) return <Loading text="กำลังตรวจสอบสถานะการเข้าสู่ระบบ…" />;

  if (!user) {
    return (
      <AuthCtx.Provider value={{ user, refresh }}>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="*" element={<Navigate to="/login" replace state={{ from: location }} />} />
        </Routes>
      </AuthCtx.Provider>
    );
  }

  return (
    <AuthCtx.Provider value={{ user, refresh }}>
      <div className="layout">
        <Sidebar user={user} onLogout={logout} open={menuOpen} onClose={() => setMenuOpen(false)} />
        {menuOpen && <div className="scrim" onClick={() => setMenuOpen(false)} />}

        <main className="main">
          {/* ปุ่มเมนูโผล่เฉพาะจอแคบ (แถบข้างซ่อนอยู่) */}
          <button className="menu-btn ghost" onClick={() => setMenuOpen((v) => !v)} aria-label="เมนู">
            ☰ เมนู
          </button>

          <div className="content">
            <Routes>
              <Route path="/" element={<Dashboard />} />
              <Route path="/player/:steam64" element={<Player />} />
              <Route path="/matches" element={<Matches />} />
              <Route path="/maps" element={<MapAnalytics />} />
              <Route path="/upload" element={<Upload />} />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </div>

          <footer className="footer">
            <span>ข้อมูลมาจากไฟล์ .dem ที่โหลดเข้าระบบเอง — ไม่มีการเรียก API วิเคราะห์เกมภายนอก</span>
          </footer>
        </main>
      </div>
    </AuthCtx.Provider>
  );
}
