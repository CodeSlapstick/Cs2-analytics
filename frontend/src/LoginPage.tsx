import "@fontsource/chakra-petch/600.css";
import "@fontsource/chakra-petch/700.css";
import "@fontsource/anuphan/400.css";
import "@fontsource/anuphan/500.css";
import "@fontsource/anuphan/600.css";
import { type ReactNode, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Navigate, useNavigate, useSearchParams } from "react-router-dom";
import { ApiError, auth } from "./api";
// เส้นโครงสีฟ้าที่สกัดจากภาพเรดาร์ de_mirage จริงของเกม (ที่มาฝังอยู่ในไฟล์ PNG)
import radarLines from "./assets/brief-mirage-lines.png";

export const DEFAULT_AFTER_LOGIN = "/matches";

/** ป้องกัน open redirect: รับเฉพาะ path ภายในเว็บเรา (ขึ้นต้น / แต่ไม่ใช่ //) */
export function safeNext(next: string | null): string {
  return next && next.startsWith("/") && !next.startsWith("//") && !next.startsWith("/login") ? next : DEFAULT_AFTER_LOGIN;
}

/** ข้อความเมื่อกลับมาจาก Steam แบบไม่สำเร็จ (/auth/steam/callback เด้งมาที่ /login?err=...) */
/** ช่องทางของโปรเจกต์ — เปิดแท็บใหม่ทุกลิงก์ (rel กัน tabnabbing: หน้าที่เปิดใหม่แก้ที่อยู่หน้าเราไม่ได้) */
const CHANNELS = [
  { name: "X", href: "https://x.com/UntitledCs2", icon: <IconX /> },
  { name: "Discord", href: "https://discord.gg/RKUH2c7MZ", icon: <IconDiscord /> },
];

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

/**
 * หน้าล็อกอิน — เข้าระบบได้ทางเดียวคือ Steam
 *
 * CS2 เล่นผ่าน Steam ผู้ใช้จริงของระบบจึงมีบัญชี Steam อยู่แล้วทุกคน
 * หน้านี้เลยไม่มีฟอร์มชื่อผู้ใช้/รหัสผ่าน ไม่มีสมัครสมาชิก และไม่มีลืมรหัสผ่าน
 * เพราะไม่มีรหัสผ่านให้ลืม — ฝั่ง backend ก็ไม่มี endpoint พวกนี้แล้วเช่นกัน
 */
export function LoginPage() {
  const [params] = useSearchParams();
  const next = safeNext(params.get("next"));
  const navigate = useNavigate();
  const qc = useQueryClient();
  const me = useQuery({ queryKey: ["me"], queryFn: auth.me, retry: false });
  const counts = useLiveCounts().data;
  const [guestErr, setGuestErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  // ข้อผิดพลาดมาจาก query string ที่ Steam เด้งกลับมา หรือจากการกดเข้าชมที่ล้มเหลว
  const error = guestErr ?? STEAM_ERROR[params.get("err") ?? ""] ?? null;

  if (me.data) return <Navigate to={next} replace />;

  /** เข้าชมโดยไม่ล็อกอิน — เซิร์ฟเวอร์ออกคุกกี้ session ให้ แล้วเข้าหน้าที่ตั้งใจจะไปตั้งแต่แรก */
  async function enterAsGuest() {
    setBusy(true);
    setGuestErr(null);
    try {
      const res = await auth.guest();
      qc.setQueryData(["me"], res);
      navigate(next, { replace: true });
    } catch (err) {
      setGuestErr(err instanceof ApiError ? err.message : "เข้าโหมดเยี่ยมชมไม่ได้ — ตรวจการเชื่อมต่อแล้วลองใหม่");
      setBusy(false);
    }
  }

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
        <div className="login-card" data-testid="login-card">
          <span className="lc-corner tl" aria-hidden="true" />
          <span className="lc-corner tr" aria-hidden="true" />
          <span className="lc-corner bl" aria-hidden="true" />
          <span className="lc-corner br" aria-hidden="true" />

          <div className="lc-head">
            <h1>ยินดีต้อนรับ, Operator</h1>
            <p>ล็อกอินด้วย Steam เพื่อผูกสถิติกับบัญชีของคุณ หรือเข้าชมก่อนก็ได้</p>
          </div>

          <a className="lc-steam" href={`/auth/steam/login?next=${encodeURIComponent(next)}`}>
            <IconSteam />
            <span>เข้าสู่ระบบด้วย Steam</span>
          </a>

          <p className="lc-or">
            <span>หรือ</span>
          </p>

          {/* ปุ่มรอง: เส้นขอบไม่ใช่พื้นทึบ เพื่อให้เห็นชัดว่าทางหลักคือ Steam */}
          <button type="button" className="lc-guest" onClick={enterAsGuest} disabled={busy} data-testid="guest-button">
            <IconVisitor />
            <span>{busy ? "กำลังเข้า…" : "เข้าชมโดยไม่ต้องล็อกอิน"}</span>
          </button>

          {error && (
            <p className="lc-error" role="alert">
              <IconAlert />
              <span>{error}</span>
            </p>
          )}

          <p className="lc-note">
            โหมดเยี่ยมชมใช้งานได้ทุกอย่างเหมือนกัน แต่ไม่มีสถิติของตัวเอง เพราะยังไม่ได้ผูกกับบัญชี Steam
            — ล็อกอินภายหลังได้จากแถบบนของทุกหน้า
          </p>
        </div>

        <ul className="channels" aria-label="ช่องทางของโปรเจกต์">
          {CHANNELS.map((c) => (
            <li key={c.name}>
              <a href={c.href} target="_blank" rel="noopener noreferrer">
                {c.icon}
                <span>{c.name}</span>
              </a>
            </li>
          ))}
        </ul>
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

/** ผู้เยี่ยมชม — คนในกรอบเล็ง สื่อว่า "เข้ามาดูได้" โดยไม่ต้องมีบัญชี */
const IconVisitor = () => (
  <Icon size={22}>
    <circle cx="12" cy="9.5" r="3.2" />
    <path d="M5.5 19.5c1.3-3 3.8-4.5 6.5-4.5s5.2 1.5 6.5 4.5" />
    <path d="M3 8V3h5M21 8V3h-5M3 16v5h5M21 16v5h-5" />
  </Icon>
);

/** โลโก้ X — ขีดไขว้ตามรูปแบรนด์ ไม่ใช้ตัวอักษร X เพราะฟอนต์แต่ละเครื่องหน้าตาไม่เหมือนกัน */
function IconX() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
      <path
        fill="currentColor"
        d="M18.9 2.3h3.5l-7.6 8.7 8.9 11.8h-6.9l-5.4-7-6.2 7H1.7l7.9-9L1 2.3h7.1l5 6.6 5.8-6.6Zm-1.2 18.2h1.9L6.4 4.1H4.4l13.3 16.4Z"
      />
    </svg>
  );
}

/** โลโก้ Discord */
function IconDiscord() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
      <path
        fill="currentColor"
        d="M19.3 5.3A16.8 16.8 0 0 0 15.1 4l-.3.6a12.5 12.5 0 0 1 3.7 1.2 12.6 12.6 0 0 0-10.9 0A12.4 12.4 0 0 1 11.3 4.6L11 4a16.8 16.8 0 0 0-4.2 1.3C4.1 9.3 3.4 13.2 3.7 17a16.6 16.6 0 0 0 5.1 2.6l.6-1a10.9 10.9 0 0 1-1.7-.8l.4-.3a11.9 11.9 0 0 0 10 0l.4.3a10.9 10.9 0 0 1-1.7.8l.6 1A16.6 16.6 0 0 0 22.3 17c.4-4.4-.6-8.3-3-11.7ZM9.3 14.7c-1 0-1.8-.9-1.8-2s.8-2 1.8-2 1.8.9 1.8 2-.8 2-1.8 2Zm5.4 0c-1 0-1.8-.9-1.8-2s.8-2 1.8-2 1.8.9 1.8 2-.8 2-1.8 2Z"
      />
    </svg>
  );
}

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
