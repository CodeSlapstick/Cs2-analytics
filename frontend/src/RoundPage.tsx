import { Fragment, useEffect, useRef } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, Navigate, useNavigate, useParams } from "react-router-dom";
import { api, matchesQuery, type Match, type RoundListItem } from "./api";
import { RoundView } from "./RoundView";
import { endReasonLabel, matchTitle, NotFound, roundUrl, sideLabel, useViewState } from "./utils";
import { useT } from "./i18n";

// ================================================================================================
// หน้ารีวิวรอบ: /matches/{demo_file}/rounds/{n}
// ================================================================================================
/**
 * หน้าที่ของหน้านี้คือ "รอบเดียว ดูให้ละเอียด" — แผนที่ ตารางผู้เล่น ไทม์ไลน์
 *
 * URL เป็นตัวเดิมทุกตัวอักษรรวมทั้ง query string เพื่อให้ลิงก์ที่เคยแชร์ไว้เปิดได้เหมือนเดิม
 * (ยกเว้น sb / board ของ sidebar และแผงพับที่ไม่มีแล้ว — param ที่ไม่รู้จักถูกมองข้าม ลิงก์ไม่พัง)
 *
 * เดิมสลับแมตช์ได้ทันทีจาก sidebar การแยกหน้าจึงต้องไม่ทำให้ช้าลง — ชื่อแมตช์บนหัวหน้าเป็นตัวสลับแมตช์ในตัว
 */
export function RoundPage() {
  const { demo, n } = useParams();
  const [view, setView, params] = useViewState();
  const matches = useQuery(matchesQuery);
  const list = matches.data ?? [];
  const entry = demo ? list.find((m) => m.demo_file === demo) : undefined;
  const roundNum = Number(n);
  const { t } = useT();

  if (matches.error) return <p className="err">{t("โหลดรายการแมตช์ไม่ได้: {msg}", { msg: (matches.error as Error).message })}</p>;
  if (!matches.data) return <p className="muted">{t("กำลังโหลด…")}</p>;
  if (!entry) return <NotFound title={t("ไม่พบแมตช์นี้")} detail={t("ไม่มีแมตช์ {demo} ในระบบ", { demo: demo ?? "" })} />;
  if (!Number.isInteger(roundNum) || roundNum < 1) {
    return <NotFound title={t("ไม่พบรอบนี้")} detail={t("\"{n}\" ไม่ใช่เลขรอบ", { n: n ?? "" })} />;
  }
  // ยังแกะไม่เสร็จก็ยังไม่มีรอบให้ดู — ส่งไปหน้าสรุปแมตช์ที่แสดงความคืบหน้าให้
  if (entry.status !== "done") return <Navigate to={`/matches/${encodeURIComponent(entry.demo_file)}`} replace />;

  return (
    <div className="round-page" data-testid="round-page">
      <MatchHeader current={entry} all={list} params={params} />
      <RoundBody entry={entry} roundNum={roundNum} view={view} setView={setView} params={params} />
    </div>
  );
}

/**
 * หัวหน้ารีวิวรอบบรรทัดเดียว: ย้อนกลับ · ชื่อแมตช์ (ซึ่งเป็นตัวสลับแมตช์ในตัว) · สกอร์บอร์ด
 * เดิมเป็นสามบรรทัด (breadcrumb / ป้าย+dropdown+ชื่อแมพลอย ๆ / ปุ่ม) ที่บอกเรื่องเดียวกันซ้ำ
 * เปลี่ยนแมตช์แล้วเริ่มที่รอบ 1 และทิ้ง d (การตายที่เลือก) กับ p (ผู้เล่นที่ไฮไลต์) เพราะเป็นคนละชุดผู้เล่น
 */
function MatchHeader({ current, all, params }: { current: Match; all: Match[]; params: URLSearchParams }) {
  const navigate = useNavigate();
  const { t } = useT();
  const options = all.filter((m) => m.status === "done").sort((a, b) => b.id - a.id);
  const label = (m: Match) => `${matchTitle(m)} · ${m.map_name ?? "—"} · ${m.ct_rounds}:${m.t_rounds}`;
  return (
    <header className="rp-head">
      <Link className="back-link" to="/matches" aria-label={t("กลับไปรายการแมตช์")}>
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
          strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false">
          <path d="m15 6-6 6 6 6" />
        </svg>
        {t("แมตช์")}
      </Link>
      {/* ข้อความที่เห็นคือชื่อแมตช์ปัจจุบัน — select โปร่งใสทับอยู่ข้างบน กดแล้วได้รายการแมตช์ของเบราว์เซอร์เอง
          (select เปล่า ๆ กว้างเท่าชื่อแมตช์ที่ยาวที่สุดในรายการ ลูกศรเลยลอยห่างจากชื่อ) */}
      <h1 className="title-pick">
        <span className="tp-text" aria-hidden="true">{label(current)}</span>
        <select
          value={current.demo_file}
          onChange={(e) => navigate(roundUrl(e.target.value, 1, params, ["d", "p"]))}
          data-testid="match-switcher"
          aria-label={t("แมตช์ที่กำลังดู (เลือกเพื่อสลับแมตช์)")}
        >
          {options.map((m) => (
            <option key={m.id} value={m.demo_file}>{label(m)}</option>
          ))}
        </select>
        <svg className="tp-caret" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor"
          strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false">
          <path d="m6 9 6 6 6-6" />
        </svg>
      </h1>
      <span className="rp-links">
        <Link className="btn-ghost" to={`/matches/${encodeURIComponent(current.demo_file)}/heatmap`}>
          Heatmap
        </Link>
        <Link className="btn-ghost" to={`/matches/${encodeURIComponent(current.demo_file)}/economy`}>
          {t("เศรษฐกิจ")}
        </Link>
        <Link className="btn-ghost" to={`/matches/${encodeURIComponent(current.demo_file)}`}>
          {t("สกอร์บอร์ด")}
        </Link>
      </span>
    </header>
  );
}

interface BodyProps {
  entry: Match;
  roundNum: number;
  view: ReturnType<typeof useViewState>[0];
  setView: ReturnType<typeof useViewState>[1];
  params: URLSearchParams;
}

/** แถบรอบ + เนื้อหาของรอบ — คีย์ ← → เปลี่ยนรอบ (ผูกไว้ที่นี่เพราะเป็นการนำทางระดับหน้า) */
function RoundBody({ entry, roundNum, view, setView, params }: BodyProps) {
  const navigate = useNavigate();
  const rounds = useQuery({ queryKey: ["review-rounds", entry.demo_file], queryFn: () => api.reviewRounds(entry.demo_file) });
  const list = rounds.data ?? [];
  const idx = list.findIndex((r) => r.round_num === roundNum);
  const go = (to: number) => navigate(roundUrl(entry.demo_file, to, params, ["d"]));
  const { t } = useT();

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return;
      if (e.key === "ArrowLeft" && idx > 0) go(list[idx - 1].round_num);
      if (e.key === "ArrowRight" && idx >= 0 && idx < list.length - 1) go(list[idx + 1].round_num);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  if (rounds.error) return <p className="err">{t("โหลดรายการรอบไม่ได้: {msg}", { msg: (rounds.error as Error).message })}</p>;
  if (rounds.data && idx < 0) {
    return <NotFound title={t("ไม่พบรอบนี้")} detail={t("แมตช์นี้มี {count} รอบ ไม่มีรอบที่ {n}", { count: list.length, n: roundNum })} />;
  }

  return (
    <>
      <RoundStrip demo={entry.demo_file} rounds={list} current={roundNum} idx={idx} go={go} params={params} />
      <RoundView demo={entry.demo_file} roundNum={roundNum} view={view} setView={setView} />
    </>
  );
}

interface StripProps {
  demo: string;
  rounds: RoundListItem[];
  current: number;
  idx: number;
  go: (n: number) => void;
  params: URLSearchParams;
}

/**
 * แถบรอบ — จำนวนปุ่มเท่ากับจำนวนรอบจริงของแมตช์ (ไม่ตายตัวที่ 24 เพราะมีทั้งแมตช์สั้นและ overtime)
 * เว้นช่องตรงพักครึ่ง (หลังรอบ 12 และทุก 3 รอบในต่อเวลา) ให้เห็นว่าสลับฝั่งตรงไหน
 * จอแคบเลื่อนข้างได้บรรทัดเดียว แทนการขึ้นสามบรรทัด — รอบที่ดูอยู่เลื่อนเข้ามาในจอเอง
 */
const halfBreakAfter = (n: number) => n === 12 || (n > 24 && (n - 24) % 3 === 0);

function RoundStrip({ demo, rounds, current, idx, go, params }: StripProps) {
  const ref = useRef<HTMLElement>(null);
  const { t } = useT();
  useEffect(() => {
    const box = ref.current;
    const el = box?.querySelector<HTMLElement>('[aria-current="page"]');
    if (!el || !box || box.scrollWidth <= box.clientWidth) return;
    box.scrollTo({ left: el.offsetLeft - box.clientWidth / 2 + el.clientWidth / 2, behavior: "smooth" });
  }, [current, rounds.length]);
  const last = rounds[rounds.length - 1]?.round_num;
  return (
    <nav className="round-strip" data-testid="round-strip" aria-label={t("เลือกรอบ")} ref={ref}>
      <button type="button" disabled={idx <= 0} onClick={() => go(rounds[idx - 1].round_num)} title={t("รอบก่อน (←)")}
        aria-label={t("รอบก่อน")}>
        ‹
      </button>
      {rounds.map((r) => (
        <Fragment key={r.round_num}>
          <Link
            to={roundUrl(demo, r.round_num, params, ["d"])}
            className={`rbox ${r.winner_side ?? "none"} ${r.round_num === current ? "active" : ""}`}
            title={t("รอบ {n} · {side} ชนะ · {reason} · ตาย {deaths}", { n: r.round_num, side: sideLabel(r.winner_side), reason: endReasonLabel(r.end_reason), deaths: r.deaths_count })}
            aria-current={r.round_num === current ? "page" : undefined}
          >
            {r.round_num}
          </Link>
          {halfBreakAfter(r.round_num) && r.round_num !== last && <span className="half-gap" aria-hidden="true" />}
        </Fragment>
      ))}
      <button
        type="button"
        disabled={idx < 0 || idx >= rounds.length - 1}
        onClick={() => go(rounds[idx + 1].round_num)}
        title={t("รอบถัดไป (→)")}
        aria-label={t("รอบถัดไป")}
      >
        ›
      </button>
    </nav>
  );
}
