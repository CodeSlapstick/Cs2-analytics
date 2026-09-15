// ตัวอักษรของทั้งแอป: Anuphan (ไทย) สำหรับข้อความ · Chakra Petch สำหรับตัวเลขที่เป็นชื่อ (เลขผู้เล่น เลขรอบ นาฬิกา สกอร์)
import "@fontsource/anuphan/400.css";
import "@fontsource/anuphan/500.css";
import "@fontsource/anuphan/600.css";
import "@fontsource/chakra-petch/600.css";
import "@fontsource/chakra-petch/700.css";
import React, { useEffect } from "react";
import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider, useQuery, useQueryClient } from "@tanstack/react-query";
import { BrowserRouter, Link, Navigate, NavLink, Outlet, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { ApiError, auth, UNAUTHORIZED_EVENT } from "./api";
import { AnalysisPage } from "./AnalysisPage";
import { LoginPage } from "./LoginPage";
import { MatchPage } from "./MatchPage";
import { PlayerPage } from "./PlayerPage";
import { NotFound } from "./utils";
import "./styles.css";

// ================================================================================================
// ต้องล็อกอินก่อน — ครอบทุก route ที่ดึงข้อมูล
// ================================================================================================
/**
 * ครอบทุก route ที่ต้องล็อกอิน — ยังไม่ล็อกอิน (หรือ token หมดอายุระหว่างใช้) เด้งไป /login?next=<ที่เดิม>
 * ล็อกอินเสร็จจะกลับมาหน้าเดิมพร้อม query string ครบ (state ทั้งหมดอยู่บน URL)
 */
export function ProtectedRoute() {
  const location = useLocation();
  const qc = useQueryClient();
  const me = useQuery({ queryKey: ["me"], queryFn: auth.me, retry: false, staleTime: 5 * 60_000 });

  // API ตัวไหนตอบ 401 (token หมดอายุ) -> ถาม /auth/me ใหม่ แล้ว component นี้จะพาไปหน้า login เอง
  useEffect(() => {
    const onUnauthorized = () => qc.invalidateQueries({ queryKey: ["me"] });
    window.addEventListener(UNAUTHORIZED_EVENT, onUnauthorized);
    return () => window.removeEventListener(UNAUTHORIZED_EVENT, onUnauthorized);
  }, [qc]);

  if (me.isLoading) return <p className="muted">กำลังตรวจสอบการเข้าสู่ระบบ…</p>;
  if (me.error && !(me.error instanceof ApiError && me.error.status === 401)) {
    return <p className="err">ติดต่อเซิร์ฟเวอร์ไม่ได้: {(me.error as Error).message}</p>;
  }
  if (!me.data) {
    const next = encodeURIComponent(location.pathname + location.search);
    return <Navigate to={`/login?next=${next}`} replace />;
  }
  return <Outlet />;
}

// ================================================================================================
// มุมขวาบน: ชื่อผู้ใช้ + ออกจากระบบ
// ================================================================================================
/** มุมขวาของแถบบน: ชื่อคนที่ล็อกอิน + ปุ่มออกจากระบบ (ไม่ล็อกอินก็ไม่แสดง) */
export function UserMenu() {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const me = useQuery({ queryKey: ["me"], queryFn: auth.me, retry: false, staleTime: 5 * 60_000 });
  if (!me.data) return null;

  async function logout() {
    await auth.logout().catch(() => undefined); // ลบคุกกี้ไม่สำเร็จก็ยังล้างฝั่งหน้าเว็บ
    qc.clear();
    navigate("/login", { replace: true });
  }

  const { username, guest, avatar } = me.data.user;
  return (
    <div className="usermenu" data-testid="user-menu">
      {guest ? (
        <span className="guest-tag" title="บัญชีผู้เยี่ยมชม — ดูได้ทุกอย่าง อัปโหลดเดโมไม่ได้">ผู้เยี่ยมชม · ดูอย่างเดียว</span>
      ) : (
        <Link to="/player" className="me-link" title="ดูสถิติของฉัน">
          {/* รูปโปรไฟล์มาจาก Steam — บัญชีที่สมัครด้วยชื่อผู้ใช้ไม่มีรูป ใช้ตัวอักษรแรกแทน ไม่ยืมรูปคนอื่นมาใส่ */}
          {avatar ? (
            <img className="me-avatar" src={avatar} alt="" referrerPolicy="no-referrer" />
          ) : (
            <span className="me-avatar ph" aria-hidden="true">{username.slice(0, 1).toUpperCase()}</span>
          )}
          <span className="me-name">{username}</span>
        </Link>
      )}
      <button type="button" onClick={logout}>
        ออกจากระบบ
      </button>
    </div>
  );
}

/** เครื่องหมายของแอป: เป้าเล็งในวงเล็บเหลี่ยม — รูปเดียวกับโลโก้หน้า login แต่เป็นสีหมึกสีเดียว */
function BrandMark() {
  return (
    <svg width="20" height="20" viewBox="0 0 32 32" fill="none" aria-hidden="true" focusable="false">
      <path d="M3 10V3h7M22 3h7v7M29 22v7h-7M10 29H3v-7" stroke="currentColor" strokeWidth="2.5" strokeLinecap="square" />
      <circle cx="16" cy="16" r="6.5" stroke="currentColor" strokeWidth="2" />
      <path d="M16 6.5v5M16 20.5v5M6.5 16h5M20.5 16h5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}

// ================================================================================================
// แอป: แถบบน + เส้นทางของหน้า
// ================================================================================================
// TanStack Query = ตัวจัดการ "ข้อมูลจากเซิร์ฟเวอร์" ทั้งแคช การโหลดซ้ำ และการ poll
const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false } },
});

/** แถบบนของแอป — หน้า /login เต็มจอของตัวเอง ไม่มีแถบนี้ */
function TopBar() {
  const { pathname } = useLocation();
  if (pathname === "/login") return null;
  return (
      <header className="topbar">
        <Link to="/" className="brand">
          <BrandMark /> CS2 SCOUTING
        </Link>
        {/* เรียงตามสิ่งที่ผู้ใช้เปิดบ่อยที่สุดก่อน — สถิติของตัวเองคือหน้าแรกหลังล็อกอิน */}
        <nav>
          <NavLink to="/player">สถิติของฉัน</NavLink>
          <NavLink to="/matches">แมตช์</NavLink>
          <NavLink to="/analysis">เครื่องมือวิเคราะห์</NavLink>
        </nav>
        <UserMenu />
      </header>
  );
}

function App() {
  return (
    <BrowserRouter>
      <TopBar />
      <main className="page">
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          {/* ทุกหน้าที่ดึงข้อมูลต้องล็อกอินก่อน — ยังไม่ล็อกอินเด้งไป /login?next=<ที่เดิม> */}
          <Route element={<ProtectedRoute />}>
            <Route path="/" element={<Navigate to="/player" replace />} />
            <Route path="/matches" element={<MatchPage />} />
            <Route path="/matches/:demo/rounds/:n" element={<MatchPage />} />
            <Route path="/analysis" element={<AnalysisPage />} />
            <Route path="/player" element={<PlayerPage />} />
            <Route path="/player/:steamId" element={<PlayerPage />} />
            <Route path="*" element={<NotFound />} />
          </Route>
        </Routes>
      </main>
    </BrowserRouter>
  );
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  </React.StrictMode>,
);
