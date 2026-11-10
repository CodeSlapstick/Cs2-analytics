import { type DragEvent as ReactDragEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError, auth, isGuest, matchesQuery, type Match, type MatchStatus } from "@/shared/api";
import { MapThumb, matchTitle, mb, num } from "@/shared/ui/utils";
import { useT } from "@/shared/i18n";

// ================================================================================================
// ================================================================================================
/**
 *
 */
const STATUS_LABEL: Record<MatchStatus, string> = { queued: "รอคิว", parsing: "กำลังแกะ", done: "พร้อม", error: "แกะไม่สำเร็จ" };
export function MatchesPage() {
  const matches = useQuery(matchesQuery);
  const me = useQuery({ queryKey: ["me"], queryFn: auth.me, retry: false, staleTime: 5 * 60_000 });
  const guest = isGuest(me.data?.user);
  const rows = useMemo(() => [...(matches.data ?? [])].sort((a, b) => b.id - a.id), [matches.data]);
  const [q, setQ] = useState("");
  const [map, setMap] = useState("");
  const upload = useUploader();
  const { t, tn } = useT();

  const maps = useMemo(
    () => [...new Set(rows.map((m) => m.map_name).filter((x): x is string => !!x))].sort(),
    [rows],
  );
  const shown = useMemo(() => {
    const needle = q.trim().toLowerCase();
    return rows.filter(
      (m) =>
        (!map || m.map_name === map) &&
        (!needle || matchTitle(m).toLowerCase().includes(needle) || m.demo_file.toLowerCase().includes(needle)),
    );
  }, [rows, q, map]);
  const filtering = Boolean(q.trim() || map);
  const mine = shown;

  return (
    <div className="matches-page" data-testid="matches-page" {...(guest ? {} : upload.dropHandlers)}>
      <div className="page-head head-row">
        <div>
          <h1>{t("แมตช์")}</h1>
          <p className="muted small">
            {matches.data ? t("{n} นัดในระบบ", { n: num(rows.length) }) : t("กำลังโหลด…")}
            {filtering && matches.data ? ` · ${t("ตรงกับที่ค้น {n} นัด", { n: num(shown.length) })}` : ""}
          </p>
        </div>
        {!guest && <>
          <button type="button" className="btn-primary btn-icon" onClick={upload.pick} data-testid="upload-button">
            <IconUpload /> {t("อัปโหลดเดโม")}
          </button>
          <input
            ref={upload.inputRef}
            type="file"
            accept=".dem"
            multiple
            hidden
            data-testid="file-input"
            onChange={(e) => { upload.onFiles(e.target.files); e.target.value = ""; }}
          />
        </>}
      </div>

      {!guest && <UploadQueue items={upload.items} onOverwrite={upload.overwrite} onClear={upload.clearDone} />}

      <div className="filters" role="search">
        <label className="f-search">
          <span className="sr-only">{t("ค้นหาแมตช์")}</span>
          <IconSearch />
          <input
            type="search"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder={t("ค้นหาชื่อทีมหรือชื่อไฟล์")}
            data-testid="filter-search"
          />
        </label>
        {maps.length > 1 && (
          <label>
            <span className="sr-only">{t("แมพ")}</span>
            <select value={map} onChange={(e) => setMap(e.target.value)} data-testid="filter-map">
              <option value="">{t("ทุกแมพ")}</option>
              {maps.map((x) => <option key={x} value={x}>{x}</option>)}
            </select>
          </label>
        )}
        {filtering && (
          <button type="button" className="btn-ghost" onClick={() => { setQ(""); setMap(""); }}>
            {t("ล้าง")}
          </button>
        )}
      </div>

      {matches.isLoading && <p className="muted">{t("กำลังโหลด…")}</p>}
      {matches.error && <p className="err">{t("โหลดรายการไม่ได้: {msg}", { msg: (matches.error as Error).message })}</p>}

      {matches.data && (
        <>
          <section className="card mcard" aria-labelledby="h-mine">
            <div className="card-head">
              <h2 id="h-mine">{t("แมตช์ของทีม")}</h2>
              <span className="muted small">{t("{n} นัด", { n: num(mine.length) })}</span>
            </div>
            {mine.length > 0 ? (
              <MatchList rows={mine} canDelete={!guest} />
            ) : filtering ? (
              <p className="muted small m-empty">{t("ไม่มีแมตช์ของทีมที่ตรงกับที่ค้น")}</p>
            ) : guest ? (
              <p className="muted small m-empty">{t("ยังไม่มีเดโมตัวอย่างที่พร้อมให้ดู")}</p>
            ) : (
              <div className="m-empty">
                <p>{tn("ยังไม่มีแมตช์ของทีม — ลากไฟล์ {dem} มาวางที่หน้านี้ หรือ", { dem: <b>.dem</b> })}</p>
                <button type="button" className="btn-ghost" onClick={upload.pick}>{t("เลือกไฟล์")}</button>
              </div>
            )}
          </section>

          {filtering && shown.length === 0 && (
            <p className="muted">{t("ไม่มีแมตช์ที่ตรงกับ \"{q}\" — ลองคำอื่น หรือกด ล้าง", { q: q.trim() || map })}</p>
          )}
        </>
      )}

      {!guest && upload.dragging && (
        <div className="drop-overlay" aria-hidden="true">
          <div>
            <IconUpload />
            <p>{t("วางไฟล์ .dem เพื่ออัปโหลด")}</p>
          </div>
        </div>
      )}
    </div>
  );
}

function MatchList({ rows, canDelete }: { rows: Match[]; canDelete: boolean }) {
  const { t } = useT();
  const qc = useQueryClient();
  const [confirmId, setConfirmId] = useState<number | null>(null);
  const [deletingId, setDeletingId] = useState<number | null>(null);
  const [deleteError, setDeleteError] = useState("");
  const [cleanupWarning, setCleanupWarning] = useState("");

  const deleteMatch = async (m: Match) => {
    setDeletingId(m.id);
    setDeleteError("");
    try {
      const result = await api.deleteMatch(m.id);
      qc.setQueryData<Match[]>(matchesQuery.queryKey, (current) => current?.filter((row) => row.id !== m.id));
      setConfirmId(null);
      await qc.invalidateQueries();
      if (result.cleanup_failed.length) setCleanupWarning(t("ลบข้อมูลแล้ว แต่ลบไฟล์บางส่วนไม่สำเร็จ"));
    } catch (error) {
      setDeleteError(error instanceof Error ? error.message : t("ลบเดโมไม่สำเร็จ"));
    } finally {
      setDeletingId(null);
    }
  };
  return (
    <ul className="mlist" data-testid="match-table">
      {cleanupWarning && <li className="match-delete-warning err" role="alert">{cleanupWarning}</li>}
      {rows.map((m) => {
        const base = `/matches/${encodeURIComponent(m.demo_file)}`;
        const done = m.status === "done";
        return (
          <li key={m.id}>
            <div className="match-item">
              <Link className="mrow" to={done ? `${base}/rounds/1` : base} data-testid="match-row" data-demo={m.demo_file}
              title={m.demo_file}>
              <MapThumb map={m.map_name} className="m-thumb" />
              <span className="m-title">{matchTitle(m)}</span>
              <span className="m-meta">
                {m.map_name ?? t("ยังไม่รู้แมพ")}
                {done && <> · {t("{n} รอบ", { n: num(m.rounds) })}</>}
              </span>
              {done ? (
                <span className="m-score" aria-label={t("CT {ct} ต่อ T {t}", { ct: m.ct_rounds, t: m.t_rounds })}>
                  <span className="ct">{m.ct_rounds}</span>
                  <span className="sep">:</span>
                  <span className="t">{m.t_rounds}</span>
                </span>
              ) : (
                <span className={`badge b-${m.status}`}>{t(STATUS_LABEL[m.status])}</span>
              )}
              <IconChevron />
              </Link>
              {canDelete && <button type="button" className="match-delete" onClick={() => { setConfirmId(m.id); setDeleteError(""); }}
                disabled={(!done && m.status !== "error") || deletingId !== null}
                title={!done && m.status !== "error" ? t("รอให้แกะเดโมเสร็จก่อนจึงจะลบได้") : undefined}
                aria-label={t("ลบเดโม {name}", { name: m.demo_file })}>
                {t("ลบ")}
              </button>}
            </div>
            {canDelete && confirmId === m.id && (
              <div className="match-delete-confirm" role="group" aria-label={t("ยืนยันลบเดโม")}>
                <span>{t("ลบเดโม {name} และข้อมูลแมตช์ทั้งหมด?", { name: m.demo_file })}</span>
                <button type="button" className="match-delete-confirm-btn" onClick={() => void deleteMatch(m)} disabled={deletingId !== null}>
                  {deletingId === m.id ? t("กำลังลบ…") : t("ยืนยันลบ")}
                </button>
                <button type="button" className="btn-ghost" onClick={() => { setConfirmId(null); setDeleteError(""); }} disabled={deletingId !== null}>{t("ยกเลิก")}</button>
                {deleteError && <span className="err" role="alert">{deleteError}</span>}
              </div>
            )}
          </li>
        );
      })}
    </ul>
  );
}

interface QueueItem {
  name: string;
  size: number;
  file: File;
  state: "waiting" | "uploading" | "queued" | "failed" | "duplicate";
  msg?: string;
}

/**
 */
function useUploader() {
  const qc = useQueryClient();
  const [items, setItems] = useState<QueueItem[]>([]);
  const [dragging, setDragging] = useState(false);
  const depth = useRef(0); // dragenter/leave ยิงซ้ำทุกครั้งที่ผ่านลูก — นับชั้นไว้ไม่ให้แผ่นกระพริบ
  const inputRef = useRef<HTMLInputElement>(null);

  const send = useCallback(
    async (files: File[], force: boolean) => {
      const patch = (name: string, p: Partial<QueueItem>) =>
        setItems((prev) => prev.map((it) => (it.name === name ? { ...it, ...p } : it)));
      for (const f of files) {
        patch(f.name, { state: "uploading", msg: undefined });
        try {
          const r = await api.upload(f, force);
          patch(f.name, { state: "queued", msg: r.replaced ? "โหลดทับแล้ว กำลังรอแกะ" : "เข้าคิวแล้ว กำลังรอแกะ" });
          qc.invalidateQueries({ queryKey: ["matches"] }); // แถวใหม่โผล่ทันที แล้ว poll ต่อเองจนแกะเสร็จ
        } catch (e) {
          const dup = e instanceof ApiError && e.status === 409 && e.message.includes("มีอยู่ในระบบแล้ว");
          patch(f.name, dup
            ? { state: "duplicate", msg: "มีแมตช์นี้ในระบบแล้ว" }
            : { state: "failed", msg: e instanceof ApiError ? e.message : String(e) });
        }
      }
    },
    [qc],
  );
  
 //รับไฟล์ที่ผู้ใช้เลือก กรองชื่อที่ลงท้าย .dem แล้วส่งทีละไฟล์ผ่าน api.upload()
  const onFiles = (list: FileList | null) => {
    if (!list) return;
    const files = Array.from(list).filter((f) => f.name.toLowerCase().endsWith(".dem"));
    if (!files.length) return;
    setItems((prev) => [
      ...files.map((f) => ({ name: f.name, size: f.size, file: f, state: "waiting" as const })),
      ...prev.filter((it) => !files.some((f) => f.name === it.name)),
    ]);
    void send(files, false);
  };

  useEffect(() => () => { depth.current = 0; }, []);

  const hasFiles = (e: ReactDragEvent) => Array.from(e.dataTransfer.types).includes("Files");
  return {
    items,
    dragging,
    inputRef,
    onFiles,
    pick: () => inputRef.current?.click(),
    overwrite: (name: string) => {
      const it = items.find((x) => x.name === name);
      if (it) void send([it.file], true);
    },
    clearDone: () => setItems((prev) => prev.filter((it) => it.state === "uploading" || it.state === "waiting")),
    dropHandlers: {
      onDragEnter: (e: ReactDragEvent) => {
        if (!hasFiles(e)) return;
        depth.current += 1;
        setDragging(true);
      },
      onDragOver: (e: ReactDragEvent) => { if (hasFiles(e)) e.preventDefault(); },
      onDragLeave: () => {
        depth.current = Math.max(0, depth.current - 1);
        if (depth.current === 0) setDragging(false);
      },
      onDrop: (e: ReactDragEvent) => {
        if (!hasFiles(e)) return;
        e.preventDefault();
        depth.current = 0;
        setDragging(false);
        onFiles(e.dataTransfer.files);
      },
    },
  };
}

function UploadQueue({ items, onOverwrite, onClear }: {
  items: QueueItem[];
  onOverwrite: (name: string) => void;
  onClear: () => void;
}) {
  const { t } = useT();
  if (items.length === 0) return null;
  const busy = items.some((it) => it.state === "uploading" || it.state === "waiting");
  return (
    <section className="upqueue" aria-live="polite" data-testid="upload-list">
      <ul className="uplist">
        {items.map((it) => (
          <li key={it.name} className={`up-${it.state}`}>
            <span className="q-name">{it.name}</span>
            <span className={it.state === "failed" ? "err small" : "small muted"}>
              {it.state === "waiting" ? t("รอส่ง") : it.state === "uploading" ? t("กำลังส่ง {size}…", { size: mb(it.size) }) : it.msg && t(it.msg)}
            </span>
            {it.state === "duplicate" && (
              <button type="button" className="btn-sm" onClick={() => onOverwrite(it.name)}>{t("โหลดทับของเดิม")}</button>
            )}
          </li>
        ))}
      </ul>
      {!busy && <button type="button" className="link-btn small" onClick={onClear}>{t("ซ่อนรายการนี้")}</button>}
    </section>
  );
}

function IconUpload() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
      strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false">
      <path d="M12 15V4M7 9l5-5 5 5M5 15v3a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-3" />
    </svg>
  );
}

function IconSearch() {
  return (
    <svg className="f-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
      strokeLinecap="round" aria-hidden="true" focusable="false">
      <circle cx="11" cy="11" r="6.5" />
      <path d="m16 16 4 4" />
    </svg>
  );
}

export function IconChevron() {
  return (
    <svg className="chev" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
      strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false">
      <path d="m9 6 6 6-6 6" />
    </svg>
  );
}
