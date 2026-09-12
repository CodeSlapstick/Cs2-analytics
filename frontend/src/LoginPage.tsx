import "@fontsource/chakra-petch/600.css";
import "@fontsource/chakra-petch/700.css";
import "@fontsource/anuphan/400.css";
import "@fontsource/anuphan/500.css";
import "@fontsource/anuphan/600.css";
import { type FormEvent, type ReactNode, useId, useState } from "react";
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
  const navigate = useNavigate();
  const qc = useQueryClient();
  const me = useQuery({ queryKey: ["me"], queryFn: auth.me, retry: false });
  const counts = useLiveCounts().data;
  const [mode, setMode] = useState<"login" | "register">("login");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [remember, setRemember] = useState(false);
  const [showPw, setShowPw] = useState(false);
  const [forgotOpen, setForgotOpen] = useState(false);
  const [error, setError] = useState<string | null>(STEAM_ERROR[params.get("err") ?? ""] ?? null);
  const [busy, setBusy] = useState(false);
  const id = useId();
  const ids = { user: `${id}-user`, pw: `${id}-pw`, err: `${id}-err`, forgot: `${id}-forgot`, hint: `${id}-hint` };

  if (me.data) return <Navigate to={next} replace />;

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const res =
        mode === "login"
          ? await auth.login(username, password, remember)
          : await auth.register(username, password, remember);
      qc.setQueryData(["me"], res);
      navigate(next, { replace: true });
    } catch (err) {
      if (err instanceof ApiError && err.status === 401 && mode === "login") {
        setError(`${err.message} — ตรวจตัวสะกดชื่อผู้ใช้อีกครั้ง (ตัวพิมพ์เล็กใหญ่ไม่มีผล) หรือกด “ลืมรหัสผ่าน?” ใต้ช่องรหัสผ่าน`);
      } else {
        setError(err instanceof ApiError ? err.message : "ติดต่อเซิร์ฟเวอร์ไม่ได้ — ตรวจการเชื่อมต่อแล้วลองใหม่อีกครั้ง");
      }
    } finally {
      setBusy(false);
    }
  }

  const invalid = error !== null;
  const describedBy = [invalid && ids.err, mode === "register" && ids.hint].filter(Boolean).join(" ") || undefined;

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
        <form className="login-card" onSubmit={submit} data-testid="login-form">
          <span className="lc-corner tl" aria-hidden="true" />
          <span className="lc-corner tr" aria-hidden="true" />
          <span className="lc-corner bl" aria-hidden="true" />
          <span className="lc-corner br" aria-hidden="true" />

          <div className="lc-head">
            <h1>{mode === "login" ? "ยินดีต้อนรับกลับ, Operator" : "สร้างบัญชี Operator"}</h1>
            <p>{mode === "login" ? "เข้าสู่ระบบเพื่อเปิดรีวิวเดโมของทีม" : "ตั้งชื่อผู้ใช้และรหัสผ่านสำหรับเข้าดูเดโมของทีม"}</p>
          </div>

          <a className="lc-steam" href={`/auth/steam/login?next=${encodeURIComponent(next)}`}>
            <IconSteam />
            <span>เข้าสู่ระบบด้วย Steam</span>
          </a>
          <p className="lc-or">
            <span>หรือใช้ชื่อผู้ใช้ของทีม</span>
          </p>

          <div className="field">
            <label htmlFor={ids.user}>ชื่อผู้ใช้</label>
            <div className={`field-box${invalid ? " bad" : ""}`}>
              <IconUser />
              <input
                id={ids.user}
                name="username"
                autoComplete="username"
                autoCapitalize="none"
                spellCheck={false}
                value={username}
                onChange={(e) => {
                  setUsername(e.target.value);
                  setError(null);
                }}
                aria-invalid={invalid}
                aria-describedby={describedBy}
                required
                autoFocus
              />
            </div>
          </div>

          <div className="field">
            <label htmlFor={ids.pw}>รหัสผ่าน</label>
            <div className={`field-box${invalid ? " bad" : ""}`}>
              <IconLock />
              <input
                id={ids.pw}
                name="password"
                type={showPw ? "text" : "password"}
                autoComplete={mode === "login" ? "current-password" : "new-password"}
                value={password}
                onChange={(e) => {
                  setPassword(e.target.value);
                  setError(null);
                }}
                aria-invalid={invalid}
                aria-describedby={describedBy}
                required
              />
              <button
                type="button"
                className="pw-toggle"
                aria-label={showPw ? "ซ่อนรหัสผ่าน" : "แสดงรหัสผ่าน"}
                aria-pressed={showPw}
                onClick={() => setShowPw((v) => !v)}
              >
                {showPw ? <IconEyeOff /> : <IconEye />}
              </button>
            </div>
            {mode === "login" && (
              <button
                type="button"
                className="lc-link quiet field-foot"
                aria-expanded={forgotOpen}
                aria-controls={ids.forgot}
                onClick={() => setForgotOpen((o) => !o)}
              >
                ลืมรหัสผ่าน?
              </button>
            )}
            {mode === "login" && forgotOpen && (
              <p id={ids.forgot} className="lc-note">
                ระบบนี้ยังไม่มีการรีเซ็ตรหัสผ่านด้วยตัวเอง — ติดต่อผู้ดูแลระบบของทีมให้ตั้งรหัสผ่านใหม่ให้
              </p>
            )}
            {mode === "register" && (
              <p id={ids.hint} className="lc-hint">
                ชื่อผู้ใช้ 3–32 ตัว (a–z 0–9 _ . -) · รหัสผ่านอย่างน้อย 8 ตัว
              </p>
            )}
          </div>

          <label className="lc-check">
            <input type="checkbox" checked={remember} onChange={(e) => setRemember(e.target.checked)} />
            <span>จดจำการเข้าสู่ระบบ 7 วัน</span>
          </label>

          {error && (
            <p id={ids.err} className="lc-error" role="alert">
              <IconAlert />
              <span>{error}</span>
            </p>
          )}

          <button type="submit" className="lc-action" disabled={busy} aria-busy={busy}>
            {busy && <span className="lc-spin" aria-hidden="true" />}
            <span>{busy ? "กำลังตรวจสอบ…" : mode === "login" ? "เข้าสู่ระบบ" : "สมัครและเข้าสู่ระบบ"}</span>
            {!busy && <IconArrow />}
          </button>

          <p className="lc-switch">
            {mode === "login" ? "ยังไม่มีบัญชี?" : "มีบัญชีแล้ว?"}{" "}
            <button
              type="button"
              className="lc-link"
              onClick={() => {
                setMode(mode === "login" ? "register" : "login");
                setError(null);
                setForgotOpen(false);
              }}
            >
              {mode === "login" ? "สมัครสมาชิก" : "เข้าสู่ระบบ"}
            </button>
          </p>
        </form>
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
const IconUser = () => (
  <Icon>
    <circle cx="12" cy="8" r="4" />
    <path d="M4 20c1.6-3.6 4.4-5.4 8-5.4s6.4 1.8 8 5.4" />
  </Icon>
);
const IconLock = () => (
  <Icon>
    <rect x="4.5" y="10.5" width="15" height="10" rx="2" />
    <path d="M8 10.5V7.5a4 4 0 0 1 8 0v3" />
    <path d="M12 14.5v2.5" />
  </Icon>
);
const IconEye = () => (
  <Icon>
    <path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12Z" />
    <circle cx="12" cy="12" r="3" />
  </Icon>
);
const IconEyeOff = () => (
  <Icon>
    <path d="M3 3l18 18" />
    <path d="M10.6 5.6A9.7 9.7 0 0 1 12 5.5c6 0 9.5 6.5 9.5 6.5a17 17 0 0 1-3 3.8M6.3 7.2A16.6 16.6 0 0 0 2.5 12S6 18.5 12 18.5a9 9 0 0 0 4.2-1" />
    <path d="M9.9 9.9a3 3 0 0 0 4.2 4.2" />
  </Icon>
);
const IconAlert = () => (
  <Icon>
    <path d="M12 3.5 22 20.5H2L12 3.5Z" />
    <path d="M12 10v4.5" />
    <path d="M12 17.5v.01" />
  </Icon>
);
const IconArrow = () => (
  <Icon>
    <path d="M4.5 12h15" />
    <path d="M13.5 6l6 6-6 6" />
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
