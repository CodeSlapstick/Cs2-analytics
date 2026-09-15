import { useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, Navigate, useNavigate, useParams } from "react-router-dom";
import { api, matchesQuery, type Match, type RoundListItem } from "./api";
import { RoundView } from "./RoundView";
import { Breadcrumb, endReasonLabel, matchTitle, NotFound, roundUrl, sideLabel, useViewState } from "./utils";

// ================================================================================================
// หน้ารีวิวรอบ: /matches/{demo_file}/rounds/{n}
// ================================================================================================
/**
 * หน้าที่ของหน้านี้คือ "รอบเดียว ดูให้ละเอียด" — แผนที่ ตารางผู้เล่น ไทม์ไลน์ บริบท
 *
 * URL เป็นตัวเดิมทุกตัวอักษรรวมทั้ง query string เพื่อให้ลิงก์ที่เคยแชร์ไว้เปิดได้เหมือนเดิม
 * (ยกเว้น sb / board ของ sidebar และแผงพับที่ไม่มีแล้ว — param ที่ไม่รู้จักถูกมองข้าม ลิงก์ไม่พัง)
 *
 * เดิมสลับแมตช์ได้ทันทีจาก sidebar การแยกหน้าจึงต้องไม่ทำให้ช้าลง — มี dropdown สลับแมตช์บนหัวหน้า
 */
export function RoundPage() {
  const { demo, n } = useParams();
  const [view, setView, params] = useViewState();
  const matches = useQuery(matchesQuery);
  const list = matches.data ?? [];
  const entry = demo ? list.find((m) => m.demo_file === demo) : undefined;
  const roundNum = Number(n);

  if (matches.error) return <p className="err">โหลดรายการแมตช์ไม่ได้: {(matches.error as Error).message}</p>;
  if (!matches.data) return <p className="muted">กำลังโหลด…</p>;
  if (!entry) return <NotFound title="ไม่พบแมตช์นี้" detail={`ไม่มีแมตช์ ${demo} ในระบบ`} />;
  if (!Number.isInteger(roundNum) || roundNum < 1) {
    return <NotFound title="ไม่พบรอบนี้" detail={`"${n}" ไม่ใช่เลขรอบ`} />;
  }
  // ยังแกะไม่เสร็จก็ยังไม่มีรอบให้ดู — ส่งไปหน้าสรุปแมตช์ที่แสดงความคืบหน้าให้
  if (entry.status !== "done") return <Navigate to={`/matches/${encodeURIComponent(entry.demo_file)}`} replace />;

  return (
    <div className="round-page" data-testid="round-page">
      <Breadcrumb
        items={[
          { label: "แมตช์", to: "/matches" },
          { label: matchTitle(entry), to: `/matches/${encodeURIComponent(entry.demo_file)}` },
          { label: `รอบ ${roundNum}` },
        ]}
      />
      <MatchSwitcher current={entry} all={list} params={params} />
      <RoundBody entry={entry} roundNum={roundNum} view={view} setView={setView} params={params} />
    </div>
  );
}

/**
 * สลับแมตช์โดยไม่ต้องย้อนไปหน้ารายการ — ทดแทน sidebar เดิมด้วยที่ว่างเท่าหนึ่งบรรทัด
 * เปลี่ยนแมตช์แล้วเริ่มที่รอบ 1 และทิ้ง d (การตายที่เลือก) กับ p (ผู้เล่นที่ไฮไลต์) เพราะเป็นคนละชุดผู้เล่น
 */
function MatchSwitcher({ current, all, params }: { current: Match; all: Match[]; params: URLSearchParams }) {
  const navigate = useNavigate();
  const options = all.filter((m) => m.status === "done").sort((a, b) => b.id - a.id);
  return (
    <div className="switcher">
      <label>
        <span className="muted small">แมตช์</span>
        <select
          value={current.demo_file}
          onChange={(e) => navigate(roundUrl(e.target.value, 1, params, ["d", "p"]))}
          data-testid="match-switcher"
        >
          {options.map((m) => (
            <option key={m.id} value={m.demo_file}>
              {matchTitle(m)} · {m.map_name ?? "—"} · {m.ct_rounds}:{m.t_rounds}
            </option>
          ))}
        </select>
      </label>
      <span className="muted small">{current.map_name ?? "—"}</span>
      <Link className="btn-ghost" to={`/matches/${encodeURIComponent(current.demo_file)}`}>
        สรุปทั้งแมตช์
      </Link>
    </div>
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

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return;
      if (e.key === "ArrowLeft" && idx > 0) go(list[idx - 1].round_num);
      if (e.key === "ArrowRight" && idx >= 0 && idx < list.length - 1) go(list[idx + 1].round_num);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  if (rounds.error) return <p className="err">โหลดรายการรอบไม่ได้: {(rounds.error as Error).message}</p>;
  if (rounds.data && idx < 0) {
    return <NotFound title="ไม่พบรอบนี้" detail={`แมตช์นี้มี ${list.length} รอบ ไม่มีรอบที่ ${roundNum}`} />;
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
      <button
        type="button"
        disabled={idx < 0 || idx >= rounds.length - 1}
        onClick={() => go(rounds[idx + 1].round_num)}
        title="รอบถัดไป (→)"
      >
        ›
      </button>
    </nav>
  );
}
