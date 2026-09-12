import React, { useEffect } from "react";
import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider, useQuery, useQueryClient } from "@tanstack/react-query";
import { BrowserRouter, Link, Navigate, Outlet, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { ApiError, auth, UNAUTHORIZED_EVENT } from "./api";
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

  return (
    <div className="usermenu" data-testid="user-menu">
      <span className="muted">{me.data.user.username}</span>
      <button type="button" onClick={logout}>
        ออกจากระบบ
      </button>
    </div>
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
          <span className="dot" /> CS2 SCOUTING
        </Link>
        <nav>
          <Link to="/matches">แมตช์</Link>
          <Link to="/player">สถิติของฉัน</Link>
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
            <Route path="/" element={<Navigate to="/matches" replace />} />
            <Route path="/matches" element={<MatchPage />} />
            <Route path="/matches/:demo/rounds/:n" element={<MatchPage />} />
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
