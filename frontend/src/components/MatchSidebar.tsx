import { useCallback, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api, ApiError, matchesQuery, type Match, type MatchStatus } from "../api";
import { roundUrl } from "../review/urlState";

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

interface Props {
  current: string | undefined; // demo_file ที่เปิดอยู่
  collapsed: boolean;
  onToggle: () => void;
  params: URLSearchParams; // query ปัจจุบัน — ติดไปกับลิงก์ (ยกเว้น p, d ที่ผูกกับแมตช์เดิม)
}

/** แถบซ้าย: ฟอร์มอัปโหลด + รายการแมตช์ทั้งหมด (แทนหน้า Match Library เดิม) ย่อเก็บได้ */
export function MatchSidebar({ current, collapsed, onToggle, params }: Props) {
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
