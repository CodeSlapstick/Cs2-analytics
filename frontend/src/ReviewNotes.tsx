import { type FormEvent, useEffect, useMemo, useState } from "react";
import { fmtT } from "./utils";
import { useT } from "./i18n";

export interface ReviewNote {
  id: string;
  time: number | null;
  text: string;
  createdAt: string;
  updatedAt: string;
}

const STORE_PREFIX = "cs2.review-notes.v1";

export function reviewNotesKey(demo: string, round: number): string {
  return `${STORE_PREFIX}:${encodeURIComponent(demo)}:${round}`;
}

export function readReviewNotes(demo: string, round: number): ReviewNote[] {
  try {
    const value: unknown = JSON.parse(localStorage.getItem(reviewNotesKey(demo, round)) ?? "[]");
    if (!Array.isArray(value)) return [];
    return value.filter((note): note is ReviewNote => Boolean(
      note && typeof note === "object"
      && typeof note.id === "string"
      && (typeof note.time === "number" || note.time === null)
      && typeof note.text === "string"
      && typeof note.createdAt === "string"
      && typeof note.updatedAt === "string",
    ));
  } catch {
    return [];
  }
}

function writeReviewNotes(demo: string, round: number, notes: ReviewNote[]): boolean {
  try {
    localStorage.setItem(reviewNotesKey(demo, round), JSON.stringify(notes));
    return true;
  } catch {
    return false;
  }
}

const newId = () => globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(36).slice(2)}`;

export function ReviewNotes({ demo, round, playbackTime, onSeek }: {
  demo: string;
  round: number;
  playbackTime: number | null;
  onSeek: (time: number) => void;
}) {
  const { t } = useT();
  const [notes, setNotes] = useState<ReviewNote[]>(() => readReviewNotes(demo, round));
  const [draft, setDraft] = useState("");
  const [editing, setEditing] = useState<string | null>(null);
  const [editText, setEditText] = useState("");
  const [storageError, setStorageError] = useState(false);

  useEffect(() => {
    setNotes(readReviewNotes(demo, round));
    setDraft("");
    setEditing(null);
    setStorageError(false);
  }, [demo, round]);

  const ordered = useMemo(() => [...notes].sort((a, b) => {
    if (a.time == null && b.time != null) return -1;
    if (a.time != null && b.time == null) return 1;
    return (a.time ?? 0) - (b.time ?? 0) || a.createdAt.localeCompare(b.createdAt);
  }), [notes]);

  const commit = (next: ReviewNote[]) => {
    setNotes(next);
    setStorageError(!writeReviewNotes(demo, round, next));
  };

  const add = (event: FormEvent) => {
    event.preventDefault();
    const text = draft.trim();
    if (!text) return;
    const now = new Date().toISOString();
    commit([...notes, {
      id: newId(),
      time: playbackTime == null ? null : Math.round(playbackTime * 10) / 10,
      text,
      createdAt: now,
      updatedAt: now,
    }]);
    setDraft("");
  };

  const saveEdit = (id: string) => {
    const text = editText.trim();
    if (!text) return;
    commit(notes.map((note) => note.id === id ? { ...note, text, updatedAt: new Date().toISOString() } : note));
    setEditing(null);
  };

  const remove = (id: string) => {
    if (!window.confirm(t("ลบโน้ตนี้หรือไม่"))) return;
    commit(notes.filter((note) => note.id !== id));
  };

  return (
    <section className="review-notes" aria-labelledby="review-notes-title">
      <div className="rn-head">
        <h3 className="panel-h" id="review-notes-title">{t("โน้ตรีวิว")}</h3>
        <span className="muted small">{t("เก็บไว้ในเบราว์เซอร์นี้")}</span>
      </div>

      <form className="rn-form" onSubmit={add}>
        <label className="sr-only" htmlFor="review-note-draft">{t("เขียนโน้ตสำหรับรอบนี้")}</label>
        <textarea id="review-note-draft" rows={2} maxLength={500} value={draft}
          onChange={(event) => setDraft(event.target.value)}
          placeholder={t("เช่น CT ไม่มีคนช่วยจาก connector")} />
        <div className="rn-form-actions">
          <span className="muted small">
            {playbackTime == null ? t("โน้ตประจำรอบ") : t("แนบเวลาที่ {time}", { time: fmtT(playbackTime) })}
          </span>
          <button type="submit" className="rn-add" disabled={!draft.trim()}>{t("เพิ่มโน้ต")}</button>
        </div>
      </form>

      {storageError && <p className="err small" role="alert">{t("บันทึกโน้ตไม่ได้ โปรดตรวจสอบการตั้งค่าเบราว์เซอร์")}</p>}
      {ordered.length === 0 ? (
        <p className="muted small rn-empty">{t("ยังไม่มีโน้ตในรอบนี้")}</p>
      ) : (
        <ol className="rn-list">
          {ordered.map((note) => (
            <li key={note.id}>
              <div className="rn-note-head">
                {note.time == null ? (
                  <span className="rn-round-label">{t("ทั้งรอบ")}</span>
                ) : (
                  <button type="button" className="rn-time" onClick={() => onSeek(note.time!)}
                    title={t("ไปที่เวลา {time}", { time: fmtT(note.time) })}>
                    {fmtT(note.time)}
                  </button>
                )}
                <span className="rn-note-actions">
                  <button type="button" onClick={() => { setEditing(note.id); setEditText(note.text); }}>{t("แก้ไข")}</button>
                  <button type="button" className="danger" onClick={() => remove(note.id)}>{t("ลบ")}</button>
                </span>
              </div>
              {editing === note.id ? (
                <form className="rn-edit" onSubmit={(event) => { event.preventDefault(); saveEdit(note.id); }}>
                  <label className="sr-only" htmlFor={`review-note-${note.id}`}>{t("แก้ไขโน้ต")}</label>
                  <textarea id={`review-note-${note.id}`} rows={2} maxLength={500} value={editText}
                    onChange={(event) => setEditText(event.target.value)} autoFocus />
                  <div>
                    <button type="button" onClick={() => setEditing(null)}>{t("ยกเลิก")}</button>
                    <button type="submit" disabled={!editText.trim()}>{t("บันทึก")}</button>
                  </div>
                </form>
              ) : <p>{note.text}</p>}
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
