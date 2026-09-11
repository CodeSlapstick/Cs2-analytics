import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { auth } from "../api";

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
