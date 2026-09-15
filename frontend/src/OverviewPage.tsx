import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { isBusy, matchesQuery, type Match } from "./api";
import { matchTitle, num } from "./utils";

// ================================================================================================
// หน้าภาพรวม: /
// ================================================================================================
/**
 * หน้าแรกหลังเข้าใช้งาน — ตอบสองคำถามเท่านั้น
 *   1. ระบบมีข้อมูลอะไรอยู่บ้าง
 *   2. จะไปต่อที่ไหน
 *
 * ตัวเลขทุกตัวคำนวณจาก /api/matches ชุดเดียวกับหน้าแมตช์ ไม่มี endpoint สรุปแยก
 * แคชของ TanStack Query จึงใช้ร่วมกัน สลับหน้าไปมาไม่ยิงซ้ำ
 */
export function OverviewPage() {
  const matches = useQuery(matchesQuery);
  const list = matches.data;

  if (matches.error) return <p className="err">โหลดข้อมูลไม่ได้: {(matches.error as Error).message}</p>;
  if (!list) return <p className="muted">กำลังโหลด…</p>;

  const done = list.filter((m) => m.status === "done");
  const totals = {
    matches: list.length,
    done: done.length,
    busy: list.filter((m) => isBusy(m.status)).length,
    failed: list.filter((m) => m.status === "error").length,
    rounds: done.reduce((a, m) => a + m.rounds, 0),
    kills: done.reduce((a, m) => a + m.kills, 0),
    maps: new Set(done.map((m) => m.map_name).filter(Boolean)).size,
  };
  const recent = [...list].sort((a, b) => b.id - a.id).slice(0, 5);

  return (
    <div className="overview" data-testid="overview">
      <div className="page-head">
        <p className="eyebrow">ภาพรวม</p>
        <h1>ข้อมูลในระบบตอนนี้</h1>
        <p className="muted">ตัวเลขทั้งหมดนับจากเดโมที่แกะเสร็จแล้วเท่านั้น — แมตช์ที่ยังอยู่ในคิวไม่ถูกนับ</p>
      </div>

      <ul className="stat-row" aria-label="สรุปตัวเลขรวม">
        <Stat value={num(totals.matches)} label="แมตช์ในระบบ"
          foot={totals.done === totals.matches ? "แกะเสร็จทั้งหมด" : `แกะเสร็จ ${totals.done} นัด`} />
        <Stat value={num(totals.rounds)} label="รอบที่แกะแล้ว" foot={`${totals.maps} แมพ`} />
        <Stat value={num(totals.kills)} label="คิลที่แกะแล้ว"
          foot={totals.rounds ? `เฉลี่ย ${(totals.kills / totals.rounds).toFixed(1)} คิลต่อรอบ` : undefined} />
        <Stat value={num(totals.busy)} label="กำลังแกะ / รอคิว"
          foot={totals.failed ? `${totals.failed} นัดแกะไม่สำเร็จ` : "ไม่มีงานค้าง"} tone={totals.busy ? "busy" : undefined} />
      </ul>

      <div className="ov-grid">
        <section className="card">
          <div className="card-head">
            <h2>แมตช์ล่าสุด</h2>
            <Link className="link-more" to="/matches">ดูทั้งหมด →</Link>
          </div>
          {recent.length === 0 ? (
            <p className="muted">ยังไม่มีแมตช์ในระบบ — <Link to="/matches">อัปโหลดเดโมไฟล์แรก</Link></p>
          ) : (
            <ul className="ov-list">
              {recent.map((m) => <RecentRow key={m.id} m={m} />)}
            </ul>
          )}
        </section>

        <section className="card">
          <div className="card-head">
            <h2>ไปที่</h2>
          </div>
          <ul className="shortcuts">
            <Shortcut to="/matches" title="แมตช์" detail="อัปโหลดเดโม ค้นหา และกรองแมตช์ทั้งหมด" />
            <Shortcut to="/player" title="สถิติของฉัน" detail="K/D, ADR, clutch และผลแยกตามแมพของตัวเอง" />
            {done[0] && (
              <Shortcut
                to={`/matches/${encodeURIComponent(done[0].demo_file)}/rounds/1`}
                title="รีวิวรอบล่าสุด"
                detail={`${matchTitle(done[0])} — เปิดแผนที่และโหมดเล่นย้อน`}
              />
            )}
          </ul>
        </section>
      </div>
    </div>
  );
}

function Stat({ value, label, foot, tone }: { value: string; label: string; foot?: string; tone?: "busy" }) {
  return (
    <li className={`stat${tone ? ` stat-${tone}` : ""}`}>
      <b>{value}</b>
      <span className="stat-label">{label}</span>
      {foot && <span className="stat-foot">{foot}</span>}
    </li>
  );
}

/** แถวแมตช์ในหน้าภาพรวม — แกะเสร็จแล้วพาไปหน้าสรุปแมตช์ ยังไม่เสร็จก็ยังกดเข้าไปดูความคืบหน้าได้ */
function RecentRow({ m }: { m: Match }) {
  return (
    <li>
      <Link to={`/matches/${encodeURIComponent(m.demo_file)}`}>
        <span className="ov-title">{matchTitle(m)}</span>
        <span className="ov-meta">
          {m.map_name ?? "—"}
          {m.status === "done" ? (
            <>
              {" · "}
              <span className="ct">{m.ct_rounds}</span>
              <span className="sep">:</span>
              <span className="t">{m.t_rounds}</span>
              {" · "}
              {num(m.kills)} คิล
            </>
          ) : (
            <span className={`badge b-${m.status}`}>{m.status === "error" ? "แกะไม่สำเร็จ" : "กำลังแกะ"}</span>
          )}
        </span>
      </Link>
    </li>
  );
}

function Shortcut({ to, title, detail }: { to: string; title: string; detail: string }) {
  return (
    <li>
      <Link to={to} className="shortcut">
        <b>{title}</b>
        <span className="muted">{detail}</span>
        <span className="arrow" aria-hidden="true">→</span>
      </Link>
    </li>
  );
}
