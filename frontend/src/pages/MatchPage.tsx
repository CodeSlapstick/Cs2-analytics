import { type ReactNode, useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, Navigate, useNavigate, useParams } from "react-router-dom";
import { api, isBusy, matchesQuery, type Match, type RoundListItem } from "../api";
import { MatchScoreboard } from "../components/MatchScoreboard";
import { MatchSidebar, matchTitle } from "../components/MatchSidebar";
import { RoundView } from "../components/review/RoundView";
import { endReasonLabel, sideLabel } from "../review/format";
import { roundUrl, useViewState, type ViewState } from "../review/urlState";
import { NotFound } from "./NotFound";

type SetView = (patch: Partial<ViewState>) => void;

/**
 * หน้าหลักหน้าเดียวของเว็บ
 *   /matches                                  -> ส่งต่อไปแมตช์ล่าสุด รอบ 1
 *   /matches/{demo_file}/rounds/{round_num}   -> sidebar รายการแมตช์ + แถบรอบ + เนื้อหาของรอบ
 */
export function MatchPage() {
  const { demo, n } = useParams();
  const [view, setView, params] = useViewState();
  const matches = useQuery(matchesQuery);
  const list = matches.data ?? [];

  // /matches เปล่า ๆ -> แมตช์ล่าสุดที่ดูได้ (ยังไม่มีตัวไหนแกะเสร็จ -> เอาตัวล่าสุดไปโชว์ความคืบหน้า)
  if (!demo && matches.data) {
    const latest = pickLatest(list);
    if (latest) return <Navigate to={roundUrl(latest.demo_file, 1, params)} replace />;
  }

  const entry = demo ? list.find((m) => m.demo_file === demo) : undefined;
  const roundNum = Number(n);
  let content: ReactNode;
  if (matches.error) content = <p className="err">โหลดรายการแมตช์ไม่ได้: {(matches.error as Error).message}</p>;
  else if (!matches.data) content = <p className="muted">กำลังโหลด…</p>;
  else if (!demo) content = <EmptyState />;
  else if (!entry) content = <NotFound title="ไม่พบแมตช์นี้" detail={`ไม่มีแมตช์ ${demo} ในระบบ`} />;
  else if (!Number.isInteger(roundNum) || roundNum < 1) content = <NotFound title="ไม่พบรอบนี้" detail={`"${n}" ไม่ใช่เลขรอบ`} />;
  else if (entry.status !== "done") content = <MatchProgress entry={entry} />;
  else content = <MatchBody entry={entry} roundNum={roundNum} view={view} setView={setView} params={params} />;

  return (
    <div className={`match-layout ${view.sidebar ? "" : "sb-collapsed"}`}>
      <MatchSidebar current={demo} collapsed={!view.sidebar} onToggle={() => setView({ sidebar: !view.sidebar })} params={params} />
      <section className="match-main" data-testid="match-main">
        {content}
      </section>
    </div>
  );
}

interface BodyProps {
  entry: Match;
  roundNum: number;
  view: ViewState;
  setView: SetView;
  params: URLSearchParams;
}

/** แมตช์ที่แกะเสร็จแล้ว: หัวแมตช์ + สกอร์บอร์ด (พับได้) + แถบรอบ + เนื้อหาของรอบ */
function MatchBody({ entry, roundNum, view, setView, params }: BodyProps) {
  const navigate = useNavigate();
  const rounds = useQuery({ queryKey: ["review-rounds", entry.demo_file], queryFn: () => api.reviewRounds(entry.demo_file) });
  const list = rounds.data ?? [];
  const idx = list.findIndex((r) => r.round_num === roundNum);
  const go = (to: number) => navigate(roundUrl(entry.demo_file, to, params, ["d"]));

  // ← / → เปลี่ยนรอบ (ไม่ทำงานตอนพิมพ์ในช่อง input)
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return;
      if (e.key === "ArrowLeft" && idx > 0) go(list[idx - 1].round_num);
      if (e.key === "ArrowRight" && idx >= 0 && idx < list.length - 1) go(list[idx + 1].round_num);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  if (rounds.data && idx < 0) {
    return <NotFound title="ไม่พบรอบนี้" detail={`แมตช์นี้มี ${list.length} รอบ ไม่มีรอบที่ ${roundNum}`} />;
  }

  return (
    <>
      <div className="match-head">
        <div>
          <p className="eyebrow">{entry.map_name}</p>
          <h1>{matchTitle(entry)}</h1>
        </div>
        <span className="badge b-ct">CT {entry.ct_rounds}</span>
        <span className="badge b-t">T {entry.t_rounds}</span>
        <span className="muted">
          {entry.rounds} รอบ · {entry.kills} คิล
        </span>
        <button type="button" className="btn-ghost" onClick={() => setView({ board: !view.board })} aria-expanded={view.board}>
          {view.board ? "▾ ซ่อนสกอร์บอร์ด" : "▸ สกอร์บอร์ดทั้งแมตช์"}
        </button>
      </div>
      {view.board && (
        <section className="card board-panel">
          <MatchScoreboard matchId={entry.id} />
        </section>
      )}

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

/** แถบรอบ — จำนวนปุ่มเท่ากับจำนวนรอบจริงของแมตช์ (ไม่ตายตัวที่ 24 เพราะมีทั้งแมตช์สั้นและ overtime) */
function RoundStrip({ demo, rounds, current, idx, go, params }: StripProps) {
  return (
    <nav className="round-strip" data-testid="round-strip" aria-label="เลือกรอบ">
      <button type="button" disabled={idx <= 0} onClick={() => go(rounds[idx - 1].round_num)} title="รอบก่อน (←)">
        ‹
      </button>
      {rounds.map((r) => (
        <Link
          key={r.round_num}
          to={roundUrl(demo, r.round_num, params, ["d"])}
          className={`rbox ${r.winner_side ?? "none"} ${r.round_num === current ? "active" : ""}`}
          title={`รอบ ${r.round_num} · ${sideLabel(r.winner_side)} ชนะ · ${endReasonLabel(r.end_reason)} · ตาย ${r.deaths_count}`}
          aria-current={r.round_num === current ? "page" : undefined}
        >
          {r.round_num}
        </Link>
      ))}
      <button type="button" disabled={idx < 0 || idx >= rounds.length - 1} onClick={() => go(rounds[idx + 1].round_num)} title="รอบถัดไป (→)">
        ›
      </button>
    </nav>
  );
}

function EmptyState() {
  return (
    <div className="empty-state" data-testid="empty-state">
      <h1>ยังไม่มีแมตช์</h1>
      <p className="muted">อัปโหลดไฟล์ .dem ที่แถบซ้าย ระบบจะแกะในเบื้องหลังแล้วเปิดดูได้ที่นี่</p>
    </div>
  );
}

/** แมตช์ที่ยังแกะไม่เสร็จ: แสดงความคืบหน้าในเนื้อหาหลัก (sidebar ยังใช้ได้ตามปกติ และ poll สถานะให้เอง) */
function MatchProgress({ entry }: { entry: Match }) {
  const label = { queued: "รอคิวแกะเดโม", parsing: "กำลังแกะเดโม", error: "แกะเดโมไม่สำเร็จ", done: "" }[entry.status];
  return (
    <div className="progress-state" data-testid="match-progress" data-status={entry.status}>
      <p className="eyebrow">{entry.demo_file}</p>
      <h1>{label}</h1>
      {isBusy(entry.status) ? (
        <>
          <div className="progress-bar">
            <i />
          </div>
          <p className="muted">หน้านี้จะเปิดรอบที่ 1 ให้เองเมื่อแกะเสร็จ — เลือกแมตช์อื่นที่แถบซ้ายระหว่างรอได้</p>
        </>
      ) : (
        <>
          <p className="err">{entry.error_message}</p>
          <p className="muted">อัปโหลดไฟล์เดิมซ้ำที่แถบซ้ายได้เลย (แมตช์ที่พังส่งใหม่ได้โดยไม่ต้องติ๊กโหลดทับ)</p>
        </>
      )}
    </div>
  );
}

/** แมตช์ล่าสุดที่เปิดดูได้ — ถ้ายังไม่มีตัวไหนเสร็จ เอาตัวที่เพิ่งอัปโหลดล่าสุด */
function pickLatest(list: Match[]): Match | undefined {
  const byNewest = [...list].sort((a, b) => b.id - a.id);
  return byNewest.find((m) => m.status === "done") ?? byNewest[0];
}
