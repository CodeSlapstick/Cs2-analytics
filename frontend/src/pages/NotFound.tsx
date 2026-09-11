import { Link } from "react-router-dom";

/** 404 ที่มีปุ่มกลับ — ใช้ทั้ง path ที่ไม่มีจริง แมตช์ที่ไม่มีในระบบ และเลขรอบที่เกินจำนวนรอบ */
export function NotFound({ title = "ไม่พบหน้านี้", detail }: { title?: string; detail?: string }) {
  return (
    <div className="notfound" data-testid="not-found">
      <p className="eyebrow">404</p>
      <h1>{title}</h1>
      {detail && <p className="muted">{detail}</p>}
      <Link className="btn-primary" to="/matches">
        กลับไปหน้าแมตช์
      </Link>
    </div>
  );
}
