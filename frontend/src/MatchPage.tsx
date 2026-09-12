import { type ReactNode, useCallback, useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, Navigate, useNavigate, useParams } from "react-router-dom";
import { api, ApiError, isBusy, matchesQuery, type Match, type MatchStatus, type RoundListItem } from "./api";
import { RoundView } from "./RoundView";
import { endReasonLabel, NotFound, roundUrl, sideLabel, useViewState, type ViewState } from "./utils";

// ================================================================================================
// หน้าหลัก: /matches/{demo_file}/rounds/{n}
// ================================================================================================
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

// ================================================================================================
// แถบซ้าย: อัปโหลด + รายการแมตช์
// ================================================================================================
interface QueueItem {
  name: string;
  size: number;
  state: "waiting" | "uploading" | "queued" | "failed";
  msg?: string;
}

const STATUS_LABEL: Record<MatchStatus, string> = { queued: "รอคิว", parsing: "กำลังแกะ", done: "พร้อม", error: "พัง" };
const mb = (n: number) => `${(n / 1024 / 1024).toFixed(1)} MB`;
export const matchTitle = (m: Pick<Match, "team_a" | "team_b" | "demo_file">) =>
  m.team_a && m.team_b ? `${m.team_a} vs ${m.team_b}` : m.demo_file;

interface SidebarProps {
  current: string | undefined; // demo_file ที่เปิดอยู่
  collapsed: boolean;
  onToggle: () => void;
  params: URLSearchParams; // query ปัจจุบัน — ติดไปกับลิงก์ (ยกเว้น p, d ที่ผูกกับแมตช์เดิม)
}

/** แถบซ้าย: ฟอร์มอัปโหลด + รายการแมตช์ทั้งหมด (แทนหน้า Match Library เดิม) ย่อเก็บได้ */
export function MatchSidebar({ current, collapsed, onToggle, params }: SidebarProps) {
  const qc = useQueryClient();
  const matches = useQuery(matchesQuery);
  const [items, setItems] = useState<QueueItem[]>([]);
  const [force, setForce] = useState(false);
  const [drag, setDrag] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const uploadAll = useCallback(
    async (files: File[]) => {
      setItems((prev) => [...files.map((f) => ({ name: f.name, size: f.size, state: "waiting" as const })), ...prev]);
      const patch = (name: string, p: Partial<QueueItem>) =>
        setItems((prev) => prev.map((it) => (it.name === name && it.state !== "queued" ? { ...it, ...p } : it)));
      // ส่งทีละไฟล์ — ไฟล์หนึ่งพังไม่ลากไฟล์อื่นล้มไปด้วย
      for (const f of files) {
        patch(f.name, { state: "uploading" });
        try {
          const r = await api.upload(f, force);
          patch(f.name, { state: "queued", msg: r.replaced ? `เข้าคิวแล้ว (ทับแมตช์ #${r.match_id})` : "เข้าคิวแล้ว" });
          qc.invalidateQueries({ queryKey: ["matches"] }); // แถวใหม่โผล่ทันที แล้ว poll ต่อเองจนแกะเสร็จ
        } catch (e) {
          patch(f.name, { state: "failed", msg: e instanceof ApiError ? e.message : String(e) });
        }
      }
    },
    [force, qc],
  );

  const onFiles = (list: FileList | null) => {
    if (!list) return;
    const files = Array.from(list).filter((f) => f.name.toLowerCase().endsWith(".dem"));
    if (files.length) void uploadAll(files);
  };

  if (collapsed) {
    return (
      <aside className="sidebar collapsed" data-testid="match-sidebar">
        <button type="button" className="sb-toggle" onClick={onToggle} title="แสดงรายการแมตช์" aria-label="แสดงรายการแมตช์">
          ☰
        </button>
      </aside>
    );
  }

  const rows = [...(matches.data ?? [])].sort((a, b) => b.id - a.id);
  return (
    <aside className="sidebar" data-testid="match-sidebar">
      <div className="sb-head">
        <b>แมตช์</b>
        <span className="muted small">{rows.length} นัด</span>
        <button type="button" className="sb-toggle" onClick={onToggle} title="ย่อแถบนี้" aria-label="ย่อแถบรายการแมตช์">
          «
        </button>
      </div>

      <div
        className={`sb-drop ${drag ? "drag" : ""}`}
        onDragOver={(e) => {
          e.preventDefault();
          setDrag(true);
        }}
        onDragLeave={() => setDrag(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDrag(false);
          onFiles(e.dataTransfer.files);
        }}
        onClick={() => inputRef.current?.click()}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") inputRef.current?.click();
        }}
        role="button"
        tabIndex={0}
      >
        <b>↑ อัปโหลดเดโม .dem</b>
        <span>ลากมาวางหรือคลิกเลือก · แกะในเบื้องหลัง</span>
        <input
          ref={inputRef}
          type="file"
          accept=".dem"
          multiple
          hidden
          data-testid="file-input"
          onChange={(e) => {
            onFiles(e.target.files);
            e.target.value = "";
          }}
        />
      </div>
      <label className="sb-force">
        <input type="checkbox" checked={force} onChange={(e) => setForce(e.target.checked)} /> โหลดทับของเดิม
      </label>

      {items.length > 0 && (
        <ul className="sb-uplist" data-testid="upload-list">
          {items.map((it) => (
            <li key={it.name} className={`up-${it.state}`}>
              <span className="q-name">{it.name}</span>
              <span className={it.state === "failed" ? "err small" : "small muted"}>
                {it.state === "waiting" ? "รอส่ง" : it.state === "uploading" ? `กำลังส่ง ${mb(it.size)}…` : it.msg}
              </span>
            </li>
          ))}
        </ul>
      )}

      {matches.isLoading && <p className="muted small">กำลังโหลด…</p>}
      {matches.error && <p className="err small">โหลดรายการไม่ได้: {(matches.error as Error).message}</p>}
      <ul className="sb-list">
        {rows.map((m) => (
          <li key={m.id}>
            <Link
              to={roundUrl(m.demo_file, 1, params, ["d", "p"])}
              className={m.demo_file === current ? "active" : ""}
              data-testid="sidebar-match"
              data-demo={m.demo_file}
              title={m.demo_file}
            >
              <span className="sb-title">{matchTitle(m)}</span>
              <span className="sb-meta">
                {m.map_name ?? "—"}
                {m.status === "done" ? (
                  <>
                    {" · "}
                    <span className="ct">{m.ct_rounds}</span>:<span className="t">{m.t_rounds}</span>
                  </>
                ) : (
                  <span className={`badge b-${m.status}`}>{STATUS_LABEL[m.status]}</span>
                )}
              </span>
            </Link>
          </li>
        ))}
        {matches.data && rows.length === 0 && <li className="muted small">ยังไม่มีแมตช์ — อัปโหลดเดโมด้านบน</li>}
      </ul>
    </aside>
  );
}

// ================================================================================================
// สกอร์บอร์ดทั้งแมตช์ (แผงพับได้)
// ================================================================================================
/** สกอร์บอร์ดทั้งแมตช์ (เดิมอยู่หน้า Match Overview) — เป็นแผงพับได้ในหน้ารอบ */
export function MatchScoreboard({ matchId }: { matchId: number }) {
  const q = useQuery({ queryKey: ["match", matchId], queryFn: () => api.match(matchId) });
  if (q.isLoading) return <p className="muted small">กำลังโหลดสกอร์บอร์ด…</p>;
  if (q.error || !q.data) return <p className="err small">โหลดสกอร์บอร์ดไม่ได้: {(q.error as Error | null)?.message}</p>;

  const features = q.data.features ?? {};
  const hasFeatures = Object.keys(features).length > 0;
  const rows = [...q.data.scoreboard].sort((a, b) => b.rating - a.rating);

  return (
    <div className="scoreboard-wrap" data-testid="scoreboard">
      <table className="tbl compact">
        <thead>
          <tr>
            <th>นักแข่ง</th>
            <th>ฝั่งเริ่ม</th>
            <th className="num">K</th>
            <th className="num">D</th>
            <th className="num">A</th>
            <th className="num">HS%</th>
            <th className="num">ADR</th>
            <th className="num">KAST</th>
            <th className="num" title="เปิดรอบ: คิลแรก / ตายแรก">
              เปิด K/D
            </th>
            <th className="num" title="ฆ่าคนที่เพิ่งฆ่าเพื่อนภายใน 5 วินาที">
              Trade
            </th>
            <th className="num" title="ชนะ / เจอสถานการณ์เหลือคนเดียว">
              Clutch
            </th>
            <th className="num">Rating</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((p) => {
            const f = features[p.steam_id];
            return (
              <tr key={p.steam_id}>
                <td>{p.name}</td>
                <td>{p.start_side ? <span className={`badge b-${p.start_side}`}>{sideLabel(p.start_side)}</span> : "—"}</td>
                <td className="num">{p.kills}</td>
                <td className="num">{p.deaths}</td>
                <td className="num">{p.assists}</td>
                <td className="num">{p.hs_rate.toFixed(0)}%</td>
                <td className="num">{p.adr.toFixed(1)}</td>
                <td className="num">{p.kast.toFixed(0)}%</td>
                <td className="num">{f ? `${f.opening_kills}/${f.opening_deaths}` : "—"}</td>
                <td className="num">{f ? f.trade_kills : "—"}</td>
                <td className="num">{f ? `${f.clutch_wins}/${f.clutch_attempts}` : "—"}</td>
                <td className="num">
                  <b>{p.rating.toFixed(2)}</b>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      {!hasFeatures && <p className="muted small">แมตช์นี้ยังไม่มีฟีเจอร์ opening / trade / clutch — โหลดเดโมซ้ำเพื่อคำนวณ</p>}
    </div>
  );
}
