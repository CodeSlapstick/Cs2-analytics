import { useEffect } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Navigate, Outlet, useLocation } from "react-router-dom";
import { ApiError, auth, UNAUTHORIZED_EVENT } from "../api";

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
