import { useCallback, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api, ApiError, isBusy, type Match, type MatchStatus } from "../api";

// รายการไฟล์ที่ผู้ใช้หย่อนเข้ามา — อยู่แค่ในหน้านี้ จบเมื่อรีเฟรช (สถานะจริงอยู่ที่ตารางด้านล่างซึ่งมาจาก DB)
interface QueueItem {
  name: string;
  size: number;
  state: "waiting" | "uploading" | "queued" | "failed";
  msg?: string;
  matchId?: number;
}

const STATUS_LABEL: Record<MatchStatus, string> = {
  queued: "รอคิว",
  parsing: "กำลังแกะ",
  done: "พร้อม",
  error: "พัง",
};

const mb = (n: number) => `${(n / 1024 / 1024).toFixed(1)} MB`;

export function MatchLibrary() {
  const qc = useQueryClient();
  const [items, setItems] = useState<QueueItem[]>([]);
  const [force, setForce] = useState(false);
  const [drag, setDrag] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  // poll ทุก 2 วินาที "เฉพาะตอนที่มีแมตช์ยังไม่เสร็จ" — เสร็จหมดแล้วหยุดถามเซิร์ฟเวอร์เอง
  const matches = useQuery({
    queryKey: ["matches"],
    queryFn: api.matches,
    refetchInterval: (q) => (q.state.data?.some((m) => isBusy(m.status)) ? 2000 : false),
  });

  const uploadAll = useCallback(
    async (files: File[]) => {
      const fresh: QueueItem[] = files.map((f) => ({ name: f.name, size: f.size, state: "waiting" }));
      setItems((prev) => [...fresh, ...prev]);
      const patch = (name: string, p: Partial<QueueItem>) =>
        setItems((prev) => prev.map((it) => (it.name === name && it.state !== "queued" ? { ...it, ...p } : it)));

      // ส่งทีละไฟล์ — ไฟล์หนึ่งพังไม่ลากไฟล์อื่นล้มไปด้วย
      for (const f of files) {
        patch(f.name, { state: "uploading" });
        try {
          const r = await api.upload(f, force);
          patch(f.name, {
            state: "queued",
            matchId: r.match_id,
            msg: r.replaced ? `เข้าคิวแล้ว (เขียนทับแมตช์ #${r.match_id})` : `เข้าคิวแล้ว (แมตช์ #${r.match_id})`,
          });
          qc.invalidateQueries({ queryKey: ["matches"] }); // ให้ตารางเห็นแถว queued ทันที แล้ว poll ต่อเอง
        } catch (e) {
          const msg = e instanceof ApiError ? e.message : String(e);
          patch(f.name, { state: "failed", msg });
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

  const rows = [...(matches.data ?? [])].sort((a, b) => b.id - a.id);
  const busy = rows.filter((m) => isBusy(m.status)).length;

  return (
    <>
      <p className="eyebrow">IMPORT</p>
      <h1>อัปโหลดเดโม</h1>

      <div
        className={`dropzone ${drag ? "drag" : ""}`}
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
        role="button"
        tabIndex={0}
      >
        <div className="dz-icon">↑</div>
        <div className="dz-title">
          ลากไฟล์ <b>.dem</b> มาวางตรงนี้
        </div>
        <div className="dz-sub">หรือคลิกเพื่อเลือกไฟล์ · เลือกหลายไฟล์พร้อมกันได้ · ระบบแกะในเบื้องหลัง ไม่ต้องรอหน้านี้</div>
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
      <label className="check">
        <input type="checkbox" checked={force} onChange={(e) => setForce(e.target.checked)} />
        โหลดทับของเดิม ถ้าแมตช์นี้เคยอยู่ในระบบแล้ว
        <span className="muted"> — ไม่ติ๊ก: ไฟล์ชื่อซ้ำจะถูกปฏิเสธ (ยกเว้นแมตช์ที่เคยพัง ส่งใหม่ได้เลย)</span>
      </label>

      {items.length > 0 && (
        <ul className="uplist" data-testid="upload-list">
          {items.map((it) => (
            <li key={it.name} className={`up-${it.state}`}>
              <span className="q-name">{it.name}</span>
              <span className="q-size">{mb(it.size)}</span>
              <span className="q-state">
                {it.state === "waiting" && "รอส่ง"}
                {it.state === "uploading" && "กำลังส่ง…"}
                {it.state === "queued" && (it.matchId ? <Link to={`/matches/${it.matchId}`}>{it.msg}</Link> : it.msg)}
                {it.state === "failed" && <span className="err">{it.msg}</span>}
              </span>
            </li>
          ))}
        </ul>
      )}

      <section className="card">
        <p className="eyebrow">IN DATABASE</p>
        <h2>
          แมตช์ทั้งหมด <span className="muted">({rows.length} นัด{busy ? ` · กำลังแกะ ${busy}` : ""})</span>
        </h2>
        {matches.isLoading && <p className="muted">กำลังโหลด…</p>}
        {matches.error && <p className="err">โหลดรายการไม่ได้: {String((matches.error as Error).message)}</p>}
        {matches.data && (
          <table className="tbl" data-testid="matches-table">
            <thead>
              <tr>
                <th>#</th>
                <th>ไฟล์</th>
                <th>ทีม</th>
                <th>แมพ</th>
                <th className="num">รอบ</th>
                <th className="num">CT</th>
                <th className="num">T</th>
                <th className="num">คิล</th>
                <th>สถานะ</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {rows.map((m) => (
                <MatchRow key={m.id} m={m} />
              ))}
            </tbody>
          </table>
        )}
      </section>
    </>
  );
}

function MatchRow({ m }: { m: Match }) {
  const teams = m.team_a && m.team_b ? `${m.team_a} vs ${m.team_b}` : "—";
  return (
    <tr className={`st-${m.status}`} data-status={m.status}>
      <td>{m.id}</td>
      <td className="mono">{m.demo_file}</td>
      <td>{teams}</td>
      <td>{m.map_name ?? "—"}</td>
      <td className="num">{m.status === "done" ? m.rounds : "—"}</td>
      <td className="num ct">{m.status === "done" ? m.ct_rounds : ""}</td>
      <td className="num t">{m.status === "done" ? m.t_rounds : ""}</td>
      <td className="num">{m.status === "done" ? m.kills : "—"}</td>
      <td>
        <span className={`badge b-${m.status}`}>{STATUS_LABEL[m.status]}</span>
        {m.status === "error" && m.error_message && (
          <div className="err small" title={m.error_message}>
            {m.error_message.slice(0, 90)}
          </div>
        )}
      </td>
      <td>{m.status === "done" ? <Link to={`/matches/${m.id}`}>ดูสถิติ →</Link> : isBusy(m.status) ? <span className="muted">…</span> : null}</td>
    </tr>
  );
}
