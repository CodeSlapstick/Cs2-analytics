import { useCallback, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError, matchesQuery, type Match, type MatchStatus } from "./api";
import { matchTitle, mb, num } from "./utils";

// ================================================================================================
// หน้าแมตช์: /matches — อัปโหลด + ค้นหา + กรอง + รายการทั้งหมด
// ================================================================================================
/**
 * งานเดียวของหน้านี้คือ "หาแมตช์ให้เจอ แล้วเข้าไปดู" — เดิมอยู่ใน sidebar ของหน้ารีวิวรอบ
 *
 * ฟอร์มอัปโหลดอยู่หน้าเดียวกับรายการ เพราะอัปเสร็จแถวใหม่โผล่ในรายการทันที เห็นผลของการกระทำตัวเอง
 * ตัวกรองทำฝั่งหน้าเว็บจาก /api/matches ชุดเดิม ไม่มี endpoint ค้นหาแยก — จำนวนแมตช์ระดับหลักร้อย
 * การกรองในเบราว์เซอร์เร็วกว่าและไม่ต้องรอเน็ตทุกครั้งที่พิมพ์
 */
const STATUS_LABEL: Record<MatchStatus, string> = { queued: "รอคิว", parsing: "กำลังแกะ", done: "พร้อม", error: "แกะไม่สำเร็จ" };
const STATUS_ORDER: MatchStatus[] = ["done", "parsing", "queued", "error"];

export function MatchesPage() {
  const matches = useQuery(matchesQuery);
  const rows = useMemo(() => [...(matches.data ?? [])].sort((a, b) => b.id - a.id), [matches.data]);

  const [q, setQ] = useState("");
  const [map, setMap] = useState("");
  const [status, setStatus] = useState("");

  const maps = useMemo(
    () => [...new Set(rows.map((m) => m.map_name).filter((x): x is string => !!x))].sort(),
    [rows],
  );
  const shown = useMemo(() => {
    const needle = q.trim().toLowerCase();
    return rows.filter(
      (m) =>
        (!map || m.map_name === map) &&
        (!status || m.status === status) &&
        (!needle || matchTitle(m).toLowerCase().includes(needle) || m.demo_file.toLowerCase().includes(needle)),
    );
  }, [rows, q, map, status]);

  const filtering = Boolean(q.trim() || map || status);

  return (
    <div className="matches-page" data-testid="matches-page">
      <div className="page-head">
        <p className="eyebrow">แมตช์</p>
        <h1>แมตช์ทั้งหมด</h1>
        <p className="muted">
          {matches.data ? `${num(rows.length)} นัดในระบบ` : "กำลังโหลด…"}
          {filtering && matches.data ? ` · ตรงกับตัวกรอง ${num(shown.length)} นัด` : ""}
        </p>
      </div>

      <UploadBox />

      <section className="card">
        <div className="filters" role="search">
          <label className="f-search">
            <span className="muted small">ค้นหา</span>
            <input
              type="search"
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="ชื่อทีมหรือชื่อไฟล์เดโม"
              data-testid="filter-search"
            />
          </label>
          <label>
            <span className="muted small">แมพ</span>
            <select value={map} onChange={(e) => setMap(e.target.value)} data-testid="filter-map">
              <option value="">ทุกแมพ</option>
              {maps.map((x) => <option key={x} value={x}>{x}</option>)}
            </select>
          </label>
          <label>
            <span className="muted small">สถานะ</span>
            <select value={status} onChange={(e) => setStatus(e.target.value)} data-testid="filter-status">
              <option value="">ทุกสถานะ</option>
              {STATUS_ORDER.filter((s) => rows.some((m) => m.status === s)).map((s) => (
                <option key={s} value={s}>{STATUS_LABEL[s]}</option>
              ))}
            </select>
          </label>
          {filtering && (
            <button type="button" className="btn-ghost" onClick={() => { setQ(""); setMap(""); setStatus(""); }}>
              ล้างตัวกรอง
            </button>
          )}
        </div>

        {matches.isLoading && <p className="muted">กำลังโหลด…</p>}
        {matches.error && <p className="err">โหลดรายการไม่ได้: {(matches.error as Error).message}</p>}
        {matches.data && rows.length === 0 && <p className="muted">ยังไม่มีแมตช์ — อัปโหลดเดโมด้านบน</p>}
        {matches.data && rows.length > 0 && shown.length === 0 && (
          <p className="muted">ไม่มีแมตช์ที่ตรงกับตัวกรอง — ลองล้างตัวกรอง</p>
        )}

        {shown.length > 0 && (
          <div className="tbl-wrap">
            <table className="tbl" data-testid="match-table">
              <thead>
                <tr>
                  <th>แมตช์</th>
                  <th>แมพ</th>
                  <th className="num">สกอร์</th>
                  <th className="num">รอบ</th>
                  <th className="num">คิล</th>
                  <th>สถานะ</th>
                </tr>
              </thead>
              <tbody>
                {shown.map((m) => <MatchRow key={m.id} m={m} />)}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}

function MatchRow({ m }: { m: Match }) {
  const to = `/matches/${encodeURIComponent(m.demo_file)}`;
  return (
    <tr data-testid="match-row" data-demo={m.demo_file}>
      <td>
        <Link to={to} className="row-title" title={m.demo_file}>{matchTitle(m)}</Link>
      </td>
      <td>{m.map_name ?? "—"}</td>
      <td className="num">
        {m.status === "done" ? (
          <><span className="ct">{m.ct_rounds}</span><span className="sep">:</span><span className="t">{m.t_rounds}</span></>
        ) : "—"}
      </td>
      <td className="num">{m.status === "done" ? num(m.rounds) : "—"}</td>
      <td className="num">{m.status === "done" ? num(m.kills) : "—"}</td>
      <td>
        {m.status === "done"
          ? <Link className="btn-sm" to={`${to}/rounds/1`}>รีวิวรอบ →</Link>
          : <Link className={`badge b-${m.status}`} to={to}>{STATUS_LABEL[m.status]}</Link>}
      </td>
    </tr>
  );
}

// ------------------------------------------------------------------ อัปโหลด
interface QueueItem {
  name: string;
  size: number;
  state: "waiting" | "uploading" | "queued" | "failed";
  msg?: string;
}

/** ลากไฟล์ .dem มาวางหรือคลิกเลือก — ส่งทีละไฟล์ ไฟล์หนึ่งพังไม่ลากไฟล์อื่นล้มไปด้วย */
function UploadBox() {
  const qc = useQueryClient();
  const [items, setItems] = useState<QueueItem[]>([]);
  const [force, setForce] = useState(false);
  const [drag, setDrag] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const uploadAll = useCallback(
    async (files: File[]) => {
      setItems((prev) => [...files.map((f) => ({ name: f.name, size: f.size, state: "waiting" as const })), ...prev]);
      const patch = (name: string, p: Partial<QueueItem>) =>
        setItems((prev) => prev.map((it) => (it.name === name && it.state !== "queued" ? { ...it, ...p } : it)));
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

  return (
    <section className="card upload-card">
      <div
        className={`dropzone ${drag ? "drag" : ""}`}
        onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
        onDragLeave={() => setDrag(false)}
        onDrop={(e) => { e.preventDefault(); setDrag(false); onFiles(e.dataTransfer.files); }}
        onClick={() => inputRef.current?.click()}
        onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") inputRef.current?.click(); }}
        role="button"
        tabIndex={0}
      >
        <div className="dz-icon" aria-hidden="true">↑</div>
        <p className="dz-title"><b>อัปโหลดเดโม .dem</b></p>
        <p className="dz-sub">ลากมาวางหรือคลิกเลือก · เลือกได้หลายไฟล์ · ระบบแกะในเบื้องหลัง</p>
        <input
          ref={inputRef}
          type="file"
          accept=".dem"
          multiple
          hidden
          data-testid="file-input"
          onChange={(e) => { onFiles(e.target.files); e.target.value = ""; }}
        />
      </div>
      <label className="check">
        <input type="checkbox" checked={force} onChange={(e) => setForce(e.target.checked)} />
        โหลดทับของเดิม (แมตช์ที่เคยแกะไม่สำเร็จส่งใหม่ได้เลยไม่ต้องติ๊ก)
      </label>

      {items.length > 0 && (
        <ul className="uplist" data-testid="upload-list">
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
    </section>
  );
}
