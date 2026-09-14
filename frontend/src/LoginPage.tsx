import "@fontsource/chakra-petch/600.css";
import "@fontsource/chakra-petch/700.css";
import "@fontsource/anuphan/400.css";
import "@fontsource/anuphan/500.css";
import "@fontsource/anuphan/600.css";
import { type ReactNode, useId } from "react";
import { useQuery } from "@tanstack/react-query";
import { Navigate, useSearchParams } from "react-router-dom";
import { auth } from "./api";
// เส้นโครงสีฟ้าที่สกัดจากภาพเรดาร์ de_mirage จริงของเกม (ที่มาฝังอยู่ในไฟล์ PNG)
import radarLines from "./assets/brief-mirage-lines.png";

export const DEFAULT_AFTER_LOGIN = "/matches";

/** ป้องกัน open redirect: รับเฉพาะ path ภายในเว็บเรา (ขึ้นต้น / แต่ไม่ใช่ //) */
export function safeNext(next: string | null): string {
  return next && next.startsWith("/") && !next.startsWith("//") && !next.startsWith("/login") ? next : DEFAULT_AFTER_LOGIN;
}

/** ข้อความเมื่อกลับมาจาก Steam แบบไม่สำเร็จ (/auth/steam/callback เด้งมาที่ /login?err=...) */
const STEAM_ERROR: Record<string, string> = {
  steam: "Steam ไม่ยืนยันการล็อกอินครั้งนี้ — ลองกดเข้าสู่ระบบด้วย Steam ใหม่อีกครั้ง",
  steam_denied: "บัญชี Steam นี้ไม่อยู่ในรายชื่อที่เข้าระบบนี้ได้ — ติดต่อผู้ดูแลระบบของทีม",
  steam_account: "สร้างบัญชีจาก Steam ไม่สำเร็จ — ติดต่อผู้ดูแลระบบของทีม",
};

/** จำนวนแมตช์ / คิลจริงจาก /api/health (ไม่ต้องล็อกอิน) — โหลดไม่ได้ก็ไม่แสดง ไม่เดาตัวเลข */
function useLiveCounts() {
  return useQuery({
    queryKey: ["health-counts"],
    queryFn: async () => {
      const r = await fetch("/api/health");
      const j = await r.json();
      if (!r.ok || !Number.isFinite(j.matches)) throw new Error("health unavailable");
      return { matches: Number(j.matches), kills: Number(j.kills) };
    },
    retry: false,
    staleTime: 60_000,
  });
}

export function LoginPage() {
  const [params] = useSearchParams();
  const next = safeNext(params.get("next"));
  const me = useQuery({ queryKey: ["me"], queryFn: auth.me, retry: false });
  const counts = useLiveCounts().data;
  // ทางเข้าเดียวคือ Steam — หน้านี้จึงไม่มี state อะไรเลย มีแค่ข้อความ error ที่ Steam เด้งกลับมาทาง ?err=
  const error = STEAM_ERROR[params.get("err") ?? ""] ?? null;
  const errId = useId();

  if (me.data) return <Navigate to={next} replace />;

  return (
    <div className="login-shell">
      {/* แผงบรีฟฝั่งซ้าย: เรดาร์ de_mirage จริงจาก assets + ตัวเลขจริงของระบบ */}
      <section className="brief" aria-label="CS2 SCOUTING">
        <div className="brief-radar" aria-hidden="true">
          <img src={radarLines} alt="" draggable={false} />
          <div className="brief-sweep" />
        </div>

        <div className="brief-brand">
          <LogoMark />
          <span>CS2 SCOUTING</span>
        </div>

        <div className="brief-copy">
          <p className="brief-slogan" lang="en">
            Tactical Precision.
            <br />
            <span>Round-by-Round Breakdown.</span>
          </p>
          <p className="brief-lead">
            รีวิวเดโมของทีมทีละรอบบนแผนที่เดียว — ใครตายที่ไหน โดนใคร และใครขว้าง smoke, flash, molotov ในจังหวะนั้น
          </p>
          <ul className="brief-stats" aria-label="ข้อมูลในระบบตอนนี้">
            {counts && (
              <li>
                <b>{counts.matches.toLocaleString("th-TH")}</b>
                <span>แมตช์ในระบบ</span>
              </li>
            )}
            {counts && (
              <li>
                <b>{counts.kills.toLocaleString("th-TH")}</b>
                <span>คิลที่แกะจากเดโมแล้ว</span>
              </li>
            )}
            <li>
              <b lang="en">Mirage · Dust2</b>
              <span>เรดาร์ปรับเทียบพิกัดแล้ว</span>
            </li>
          </ul>
        </div>

        <p className="brief-caption">เรดาร์ de_mirage จากไฟล์ของเกม CS2</p>
      </section>

      <section className="login-side">
        <div className="login-card">
          <span className="lc-corner tl" aria-hidden="true" />
          <span className="lc-corner tr" aria-hidden="true" />
          <span className="lc-corner bl" aria-hidden="true" />
          <span className="lc-corner br" aria-hidden="true" />

          <div className="lc-head">
            <h1>Login</h1>
            <p>Log in with your Steam account to review the team's demo.</p>
          </div>

          {error && (
            <p id={errId} className="lc-error" role="alert">
              <IconAlert />
              <span>{error}</span>
            </p>
          )}

          <a className="lc-steam" href={`/auth/steam/login?next=${encodeURIComponent(next)}`}>
            <IconSteam />
            <span>เข้าสู่ระบบด้วย Steam</span>
          </a>

          <p className="lc-note">
            ต้องเป็นบัญชี Steam ที่อยู่ในรายชื่อของทีม — ถ้าเข้าไม่ได้ ติดต่อผู้ดูแลระบบ
          </p>
        </div>
        <p className="login-foot">SP-404 Senior Project · UTCC STECH</p>
      </section>
    </div>
  );
}

// ------------------------------------------------------------------ ไอคอน (วาดเอง เส้นหนาเท่ากันทุกตัว)
function Icon({ children, size = 20 }: { children: ReactNode; size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.75}
      strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false">
      {children}
    </svg>
  );
}
const IconAlert = () => (
  <Icon>
    <path d="M12 3.5 22 20.5H2L12 3.5Z" />
    <path d="M12 10v4.5" />
    <path d="M12 17.5v.01" />
  </Icon>
);

/** เครื่องหมาย Steam — วาดเป็น path เองให้เส้นเข้าชุดกับไอคอนอื่นในหน้านี้ */
function IconSteam() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" aria-hidden="true" focusable="false">
      <circle cx="12" cy="12" r="9.25" stroke="currentColor" strokeWidth="1.75" />
      <circle cx="15.1" cy="9.1" r="2.9" stroke="currentColor" strokeWidth="1.75" />
      <circle cx="15.1" cy="9.1" r="1" fill="currentColor" />
      <circle cx="8.4" cy="15.2" r="2.5" stroke="currentColor" strokeWidth="1.75" />
      <path d="M10.6 14.1 13 11.2M2.9 12.6l3.2 1.3" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" />
    </svg>
  );
}

/** โลโก้: เป้าเล็งในวงเล็บเหลี่ยม — ภาษาเดียวกับมุมของการ์ดฟอร์ม */
function LogoMark() {
  return (
    <svg width="30" height="30" viewBox="0 0 32 32" fill="none" aria-hidden="true" focusable="false">
      <path d="M3 10V3h7M22 3h7v7M29 22v7h-7M10 29H3v-7" stroke="#FF6B00" strokeWidth="2.5" strokeLinecap="square" />
      <circle cx="16" cy="16" r="6.5" stroke="#00E5FF" strokeWidth="2" />
      <path d="M16 6.5v5M16 20.5v5M6.5 16h5M20.5 16h5" stroke="#00E5FF" strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}
