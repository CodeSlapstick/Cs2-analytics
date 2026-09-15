import React, { useEffect } from "react";
import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider, useQuery, useQueryClient } from "@tanstack/react-query";
import { BrowserRouter, Link, NavLink, Navigate, Outlet, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { ApiError, auth, isGuest, UNAUTHORIZED_EVENT } from "./api";
import { LoginPage } from "./LoginPage";
import { OverviewPage } from "./OverviewPage";
import { MatchesPage } from "./MatchesPage";
import { MatchPage } from "./MatchPage";
import { RoundPage } from "./RoundPage";
import { PlayerPage } from "./PlayerPage";
import { AnalysisPage } from "./AnalysisPage";
import { NotFound } from "./utils";
import "./styles.css";

// ================================================================================================
// ต้องมี session ก่อน — ครอบทุก route ที่ดึงข้อมูล
// ================================================================================================
/**
 * ครอบทุก route ที่ต้องมี session — ยังไม่มี (หรือหมดอายุระหว่างใช้) เด้งไป /login?next=<ที่เดิม>
 *
 * "มี session" นับทั้งผู้ใช้ Steam และโหมดเยี่ยมชม — ทั้งสองแบบผ่านด่านนี้เท่ากัน
 * ตัว backend ก็ใช้กฎเดียวกันที่ require_viewer() จุดเดียว
 *
 * เข้ามาแล้วจะกลับมาหน้าเดิมพร้อม query string ครบ (state ทั้งหมดอยู่บน URL)
 */
export function ProtectedRoute() {
  const location = useLocation();
  const qc = useQueryClient();
  const me = useQuery({ queryKey: ["me"], queryFn: auth.me, retry: false, staleTime: 5 * 60_000 });

  // API ตัวไหนตอบ 401 (session หมดอายุ) -> ถาม /auth/me ใหม่ แล้ว component นี้จะพาไปหน้า login เอง
  useEffect(() => {
    const onUnauthorized = () => qc.invalidateQueries({ queryKey: ["me"] });
    window.addEventListener(UNAUTHORIZED_EVENT, onUnauthorized);
    return () => window.removeEventListener(UNAUTHORIZED_EVENT, onUnauthorized);
  }, [qc]);

  if (me.isLoading) return <p className="muted">กำลังตรวจสอบการเข้าใช้งาน…</p>;
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
// มุมขวาบน: ใครกำลังดู + ทางออก
// ================================================================================================
/** มุมขวาของแถบบน — ผู้ใช้ Steam เห็นชื่อ+ออกจากระบบ · โหมดเยี่ยมชมเห็นป้ายบอกสถานะ+ปุ่มล็อกอิน */
export function UserMenu() {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const { pathname, search } = useLocation();
  const me = useQuery({ queryKey: ["me"], queryFn: auth.me, retry: false, staleTime: 5 * 60_000 });
  if (!me.data) return null;
  const user = me.data.user;

  async function leave() {
    await auth.logout().catch(() => undefined); // ลบคุกกี้ไม่สำเร็จก็ยังล้างฝั่งหน้าเว็บ
    qc.clear();
    navigate("/login", { replace: true });
  }

  // โหมดเยี่ยมชม: บอกสถานะให้เห็นชัด และให้ยกระดับเป็นบัญชี Steam ได้จากทุกหน้าโดยไม่เสียที่ที่กำลังดู
  if (isGuest(user)) {
    return (
      <div className="usermenu" data-testid="user-menu" data-viewer="guest">
        <span className="pill pill-guest" title="เข้าชมโดยไม่ได้ล็อกอิน — ข้อมูลที่อัปโหลดจะไม่ผูกกับบัญชีใด">
          โหมดเยี่ยมชม
        </span>
        <a className="btn-steam-sm" href={`/auth/steam/login?next=${encodeURIComponent(pathname + search)}`}>
          ล็อกอินด้วย Steam
        </a>
        <button type="button" className="btn-ghost" onClick={leave}>
          ออก
        </button>
      </div>
    );
  }

  return (
    <div className="usermenu" data-testid="user-menu" data-viewer="steam">
      {/* รูปโปรไฟล์มาจาก Steam — บัญชีที่ยังไม่มีรูปใช้ตัวอักษรแรกของชื่อแทน ไม่ยืมรูปคนอื่นมาใส่ */}
      <Link to="/player" className="me-link" title="ดูสถิติของฉัน">
        {user.avatar ? (
          <img className="me-avatar" src={user.avatar} alt="" referrerPolicy="no-referrer" />
        ) : (
          <span className="me-avatar ph" aria-hidden="true">{(user.username ?? "?").slice(0, 1).toUpperCase()}</span>
        )}
        <span className="me-name">{user.username}</span>
      </Link>
      <button type="button" className="btn-ghost" onClick={leave}>
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

/**
 * หน้าหลักของเว็บ เรียงตามสิ่งที่ผู้ใช้เปิดบ่อยที่สุดก่อน — สถิติของตัวเองคือหน้าแรกหลังล็อกอิน
 * หน้าสรุปแมตช์กับหน้ารีวิวรอบเข้าถึงจาก "แมตช์" จึงไม่มีลิงก์ของตัวเอง
 */
const NAV = [
  { to: "/player", label: "สถิติของฉัน", end: false },
  { to: "/matches", label: "แมตช์", end: false },
  { to: "/analysis", label: "เครื่องมือวิเคราะห์", end: false },
  { to: "/", label: "ภาพรวม", end: true },
];

/** แถบบนของแอป — หน้า /login เต็มจอของตัวเอง ไม่มีแถบนี้ */
function TopBar() {
  const { pathname } = useLocation();
  if (pathname === "/login") return null;
  return (
    <header className="topbar">
      <Link to="/" className="brand">
        <span className="dot" /> CS2 SCOUTING
      </Link>
      <nav aria-label="เมนูหลัก">
        {NAV.map((n) => (
          <NavLink key={n.to} to={n.to} end={n.end} className={({ isActive }) => (isActive ? "active" : "")}>
            {n.label}
          </NavLink>
        ))}
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
          {/* ทุกหน้าที่ดึงข้อมูลต้องมี session ก่อน — ยังไม่มีเด้งไป /login?next=<ที่เดิม> */}
          <Route element={<ProtectedRoute />}>
            <Route path="/" element={<OverviewPage />} />
            <Route path="/matches" element={<MatchesPage />} />
            <Route path="/matches/:demo" element={<MatchPage />} />
            {/* URL เดิมของหน้ารีวิวรอบ — ลิงก์ที่เคยแชร์ไว้พร้อม query string ต้องเปิดได้เหมือนเดิม */}
            <Route path="/matches/:demo/rounds/:n" element={<RoundPage />} />
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
