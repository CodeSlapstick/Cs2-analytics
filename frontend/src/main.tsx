import React, { useEffect, useRef, useState } from "react";
import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider, useQuery, useQueryClient } from "@tanstack/react-query";
import { BrowserRouter, Link, NavLink, Navigate, Outlet, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { ApiError, auth, isGuest, UNAUTHORIZED_EVENT } from "./api";
import { LoginPage } from "./LoginPage";
import { MatchesPage } from "./MatchesPage";
import { MatchPage } from "./MatchPage";
import { RoundPage } from "./RoundPage";
import { PlayerPage } from "./PlayerPage";
import { AnalysisPage } from "./AnalysisPage";
import { OpeningRoutePage } from "./OpeningRoutePage";
import { CoachPage } from "./CoachPage";
import { HeatmapPage } from "./HeatmapPage";
import { EconomyPage } from "./EconomyPage";
import { HomePage } from "./HomePage";
import { NotFound } from "./utils";
import { LangProvider, LangToggle, tr, useT } from "./i18n";
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
  const { t } = useT();
  const me = useQuery({ queryKey: ["me"], queryFn: auth.me, retry: false, staleTime: 5 * 60_000 });

  // API ตัวไหนตอบ 401 (session หมดอายุ) -> ถาม /auth/me ใหม่ แล้ว component นี้จะพาไปหน้า login เอง
  useEffect(() => {
    const onUnauthorized = () => qc.invalidateQueries({ queryKey: ["me"] });
    window.addEventListener(UNAUTHORIZED_EVENT, onUnauthorized);
    return () => window.removeEventListener(UNAUTHORIZED_EVENT, onUnauthorized);
  }, [qc]);

  if (me.isLoading) return <p className="muted">{t("กำลังตรวจสอบการเข้าใช้งาน…")}</p>;
  if (me.error && !(me.error instanceof ApiError && me.error.status === 401)) {
    return <p className="err">{t("ติดต่อเซิร์ฟเวอร์ไม่ได้: {msg}", { msg: t((me.error as Error).message) })}</p>;
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
/**
 * SteamID64 (หรือชื่อสำรอง steam_<id> ที่ backend ตั้งให้ตอนเรียก Steam Web API ไม่ติด — ดู
 * backend/auth.py steam_persona/username_for_steam) เป็นเลข 17 หลักที่ไม่มีใครอ่านออกว่าเป็นใคร
 * ห้ามโผล่ในหน้าเว็บตรง ๆ ไม่ว่าที่ไหน — ถ้าเจอรูปแบบนี้ให้แสดงป้ายกลาง ๆ แทน
 */
const STEAM_ID_FALLBACK = /^(steam_)?\d{15,}$/;
const displayName = (username: string | null | undefined) =>
  username && !STEAM_ID_FALLBACK.test(username) ? username : tr("บัญชี Steam");

/** ปิดเมนูเมื่อคลิกนอกกล่องหรือกด Escape — ใช้ร่วมกันทั้งเมนูผู้ใช้ Steam และผู้เยี่ยมชม */
function useCloseOnOutside<E extends HTMLElement>(open: boolean, onClose: () => void) {
  const ref = useRef<E>(null);
  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) onClose();
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open, onClose]);
  return ref;
}

/**
 * มุมขวาของแถบบน — ปุ่มเดียวที่กดแล้วกางเมนูลงมา (ไม่ใช่ป้าย+ลิงก์+ปุ่มเรียงกันแบบเดิม)
 * เพื่อไม่ให้แถบบนแน่นขึ้นเรื่อย ๆ เวลามีตัวเลือกเพิ่ม และไม่ให้ SteamID โผล่ตรง ๆ ที่ไหนเลย
 */
export function UserMenu() {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const { pathname, search } = useLocation();
  const { t } = useT();
  const me = useQuery({ queryKey: ["me"], queryFn: auth.me, retry: false, staleTime: 5 * 60_000 });
  const [open, setOpen] = useState(false);
  const ref = useCloseOnOutside<HTMLDivElement>(open, () => setOpen(false));
  if (!me.data) return null;
  const user = me.data.user;
  const guest = isGuest(user);
  const name = displayName(user.username);

  async function leave() {
    setOpen(false);
    await auth.logout().catch(() => undefined); // ลบคุกกี้ไม่สำเร็จก็ยังล้างฝั่งหน้าเว็บ
    qc.clear();
    navigate("/login", { replace: true });
  }

  return (
    <div className="usermenu" data-testid="user-menu" data-viewer={guest ? "guest" : "steam"} ref={ref}>
      <button
        type="button"
        className="um-trigger"
        onClick={() => setOpen((o) => !o)}
        aria-haspopup="menu"
        aria-expanded={open}
      >
        {guest ? (
          <span className="pill pill-guest">{t("โหมดเยี่ยมชม")}</span>
        ) : user.avatar ? (
          // รูปโปรไฟล์มาจาก Steam — บัญชีที่ยังไม่มีรูปใช้ตัวอักษรแรกของชื่อที่แสดงแทน ไม่ยืมรูปคนอื่นมาใส่
          <img className="me-avatar" src={user.avatar} alt="" referrerPolicy="no-referrer" />
        ) : (
          <span className="me-avatar ph" aria-hidden="true">{name.slice(0, 1).toUpperCase()}</span>
        )}
        {!guest && <span className="me-name">{name}</span>}
        <span className="um-caret" aria-hidden="true">▾</span>
      </button>

      {open && (
        <div className="um-panel" role="menu">
          {guest ? (
            <>
              <p className="um-note">{t("เข้าชมโดยไม่ได้ล็อกอิน — ข้อมูลที่อัปโหลดจะไม่ผูกกับบัญชีใด")}</p>
              <a
                className="um-item um-item-steam"
                role="menuitem"
                href={`/auth/steam/login?next=${encodeURIComponent(pathname + search)}`}
              >
                {t("ล็อกอินด้วย Steam")}
              </a>
              <button type="button" className="um-item" role="menuitem" onClick={leave}>
                {t("ออก")}
              </button>
            </>
          ) : (
            <>
              <Link className="um-item" role="menuitem" to="/player" onClick={() => setOpen(false)}>
                {t("ดูสถิติของฉัน")}
              </Link>
              <button type="button" className="um-item" role="menuitem" onClick={leave}>
                {t("ออกจากระบบ")}
              </button>
            </>
          )}
        </div>
      )}
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
 * (เคยมีหน้า "ภาพรวม" ที่ / — ตัดออกแล้ว เพราะซ้ำกับตัวเลขที่หน้าแมตช์มีอยู่แล้ว)
 */
const NAV = [
  { to: "/player", label: "สถิติของฉัน", end: false, steamOnly: true },
  { to: "/matches", label: "แมตช์", end: false, steamOnly: false },
  { to: "/analysis", label: "เครื่องมือวิเคราะห์", end: false, steamOnly: false },
  { to: "/opening-route", label: "Opening Route", end: false, steamOnly: false },
  { to: "/coach", label: "Coach", end: false, steamOnly: false },
];

/** โหมดเยี่ยมชมไม่มี "ฉัน" — ไม่ต้องโชว์แท็บที่เปิดแล้วเจอแต่หน้าว่าง และหน้าแรกพาไปหน้าแมตช์แทน */
function useViewerIsGuest() {
  const me = useQuery({ queryKey: ["me"], queryFn: auth.me, retry: false, staleTime: 5 * 60_000 });
  return isGuest(me.data?.user);
}

// เพิ่มรูปไอคอนเป้าเล็ง SVG (ใส่สีส้ม #FF6B00 ตรงๆ ไม่ให้โดน CSS อื่นทับ)
function Mark() {
  return (
    <svg width="30" height="30" viewBox="0 0 32 32" fill="none" aria-hidden="true">
      <path d="M3 10V3h7M22 3h7v7M29 22v7h-7M10 29H3v-7" stroke="#FF6B00" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
      <circle cx="16" cy="16" r="6.5" stroke="#00E5FF" strokeWidth="2" />
      <path d="M16 6.5v5M16 20.5v5M6.5 16h5M20.5 16h5" stroke="#00E5FF" strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}

/** แถบบนของแอป — หน้า /login เต็มจอของตัวเอง ไม่มีแถบนี้ */
function TopBar() {
  const { pathname } = useLocation();
  const guest = useViewerIsGuest();
  const { t } = useT();
  const navRef = useRef<HTMLElement>(null);
  useEffect(() => {
    const nav = navRef.current;
    const active = nav?.querySelector<HTMLElement>("a.active");
    if (nav && active) nav.scrollLeft = active.offsetLeft - nav.offsetLeft - (nav.clientWidth - active.clientWidth) / 2;
  }, [pathname, guest]);
  if (pathname === "/" || pathname === "/login") return null;
  return (
    <header className="topbar">
      <Link className="home-brand" to="/" aria-label="CS2 SCOUTING home">
        <Mark />
        <span>CS2 SCOUTING</span>
      </Link>
      <nav ref={navRef} aria-label={t("เมนูหลัก")}>
        {NAV.filter((n) => !(guest && n.steamOnly)).map((n) => (
          <NavLink key={n.to} to={n.to} end={n.end} className={({ isActive }) => (isActive ? "active" : "")}>
            {t(n.label)}
          </NavLink>
        ))}
      </nav>
      <LangToggle />
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
          <Route path="/" element={<HomePage />} />
          <Route path="/login" element={<LoginPage />} />
          {/* ทุกหน้าที่ดึงข้อมูลต้องมี session ก่อน — ยังไม่มีเด้งไป /login?next=<ที่เดิม> */}
          <Route element={<ProtectedRoute />}>
            {/* หน้าแรก: ผู้ใช้ Steam = สถิติของฉัน · โหมดเยี่ยมชม = แมตช์ (ไม่มี "ฉัน" ให้ดู) */}
            <Route path="/matches" element={<MatchesPage />} />
            <Route path="/matches/:demo" element={<MatchPage />} />
            {/* URL เดิมของหน้ารีวิวรอบ — ลิงก์ที่เคยแชร์ไว้พร้อม query string ต้องเปิดได้เหมือนเดิม */}
            <Route path="/matches/:demo/rounds/:n" element={<RoundPage />} />
            <Route path="/matches/:demo/heatmap" element={<HeatmapPage />} />
            <Route path="/matches/:demo/economy" element={<EconomyPage />} />
            <Route path="/analysis" element={<AnalysisPage />} />
            <Route path="/opening-route" element={<OpeningRoutePage />} />
            <Route path="/coach" element={<CoachPage />} />
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
      <LangProvider>
        <App />
      </LangProvider>
    </QueryClientProvider>
  </React.StrictMode>,
);
