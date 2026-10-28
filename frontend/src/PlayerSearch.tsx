import { useEffect, useId, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { playerApi, type PlayerSearchItem } from "./api";
import { useT } from "./i18n";
import unknownAvatar from "./assets/avatar-unknown.jpg";

function useDebouncedValue<T>(value: T, delay: number) {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(value), delay);
    return () => window.clearTimeout(timer);
  }, [delay, value]);
  return debounced;
}

function shortId(id: string) {
  return id.length > 10 ? `…${id.slice(-8)}` : id;
}

function SearchIcon() {
  return <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" aria-hidden="true"><circle cx="11" cy="11" r="6.5" /><path d="m16 16 4 4" /></svg>;
}

function SearchResult({ item, active, id, onOpen, asOption = false }: { item: PlayerSearchItem; active: boolean; id: string; onOpen: () => void; asOption?: boolean }) {
  const { t } = useT();
  return (
    <button type="button" id={id} role={asOption ? "option" : undefined} aria-selected={asOption ? active : undefined} className={`ps-result${active ? " active" : ""}`} onMouseDown={(event) => event.preventDefault()} onClick={onOpen}>
      <img src={item.avatar || unknownAvatar} alt="" referrerPolicy="no-referrer" />
      <span className="ps-result-main"><strong>{item.name}</strong><small>{item.username || `Steam ${shortId(item.steam_id)}`}</small></span>
      <span className="ps-result-meta"><strong>{item.latest_team || t("ไม่ระบุทีม")}</strong><small>{t("{n} แมตช์", { n: item.matches })} · {item.latest_match || t("ไม่มีข้อมูลแมตช์")}</small></span>
    </button>
  );
}

export function PlayerSearch() {
  const { t } = useT();
  const navigate = useNavigate();
  const inputRef = useRef<HTMLInputElement>(null);
  const rootRef = useRef<HTMLDivElement>(null);
  const listId = useId();
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [mobile, setMobile] = useState(false);
  const [active, setActive] = useState(0);
  const debounced = useDebouncedValue(query.trim(), 250);
  const search = useQuery({
    queryKey: ["player-search", debounced, 8],
    queryFn: () => playerApi.search(debounced, 8),
    enabled: debounced.length >= 2,
    staleTime: 60_000,
  });
  const items = search.data?.items ?? [];

  useEffect(() => setActive(0), [debounced]);
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      const typing = target?.matches("input, textarea, select, [contenteditable='true']");
      if ((event.key === "/" && !typing) || (event.key.toLowerCase() === "k" && (event.ctrlKey || event.metaKey))) {
        event.preventDefault(); setMobile(true); setOpen(true); window.setTimeout(() => inputRef.current?.focus(), 0);
      }
    };
    const onPointer = (event: PointerEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    };
    window.addEventListener("keydown", onKey);
    window.addEventListener("pointerdown", onPointer);
    return () => { window.removeEventListener("keydown", onKey); window.removeEventListener("pointerdown", onPointer); };
  }, []);

  function openPlayer(item: PlayerSearchItem) {
    setOpen(false); setMobile(false); setQuery(""); navigate(`/player/${encodeURIComponent(item.steam_id)}`);
  }

  function onInputKeyDown(event: React.KeyboardEvent<HTMLInputElement>) {
    if (event.key === "Escape") { setOpen(false); setMobile(false); inputRef.current?.blur(); return; }
    if (!open || !items.length) return;
    if (event.key === "ArrowDown") { event.preventDefault(); setActive((index) => (index + 1) % items.length); }
    if (event.key === "ArrowUp") { event.preventDefault(); setActive((index) => (index - 1 + items.length) % items.length); }
    if (event.key === "Enter") { event.preventDefault(); openPlayer(items[active]); }
  }

  const showPanel = open && debounced.length >= 2;
  return (
    <div className={`player-search${mobile ? " mobile-open" : ""}`} ref={rootRef}>
      <button className="ps-mobile-trigger" type="button" aria-label={t("ค้นหาผู้เล่น")} onClick={() => { setMobile(true); setOpen(true); window.setTimeout(() => inputRef.current?.focus(), 0); }}><SearchIcon /></button>
      <div className="ps-field">
        <SearchIcon />
        <input ref={inputRef} type="search" value={query} placeholder={t("ค้นหาผู้เล่น…")} aria-label={t("ค้นหาผู้เล่น")}
          role="combobox" aria-autocomplete="list" aria-expanded={showPanel} aria-controls={listId}
          aria-activedescendant={showPanel && items[active] ? `${listId}-${active}` : undefined}
          onFocus={() => setOpen(true)} onChange={(event) => { setQuery(event.target.value); setOpen(true); }} onKeyDown={onInputKeyDown} />
        <kbd aria-hidden="true">/</kbd>
        {mobile && <button type="button" className="ps-close" onClick={() => { setMobile(false); setOpen(false); }}>{t("ปิด")}</button>}
      </div>
      {showPanel && <div className="ps-panel">
        {search.isFetching ? <p role="status">{t("กำลังค้นหา…")}</p>
          : search.isError ? <p role="alert" className="err">{t("ค้นหาผู้เล่นไม่สำเร็จ")}</p>
          : !search.data?.has_players ? <p>{t("ยังไม่มี demo หรือข้อมูลผู้เล่นในระบบ")}</p>
          : items.length === 0 ? <p>{t("ไม่พบผู้เล่น")}</p>
          : <><div className="ps-options" id={listId} role="listbox" aria-label={t("ผลการค้นหาผู้เล่น")}>{items.map((item, index) => <SearchResult key={item.steam_id} item={item} active={index === active} id={`${listId}-${index}`} asOption onOpen={() => openPlayer(item)} />)}</div>
            {(search.data?.total ?? 0) > 8 && <Link className="ps-all" to={`/players?q=${encodeURIComponent(debounced)}`} onClick={() => setOpen(false)}>{t("ดูผลลัพธ์ทั้งหมด")} ({search.data?.total})</Link>}</>}
      </div>}
    </div>
  );
}

export function PlayerSearchPage() {
  const { t } = useT();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const query = params.get("q") ?? "";
  const linking = params.get("link") === "1";
  const [linkingId, setLinkingId] = useState<string | null>(null);
  const [linkError, setLinkError] = useState<string | null>(null);
  const debounced = useDebouncedValue(query.trim(), 250);
  const search = useQuery({ queryKey: ["player-search", debounced, 50], queryFn: () => playerApi.search(debounced, 50), enabled: debounced.length >= 2 });
  return <section className="players-search-page">
    <header><h1>{linking ? t("เลือกและยืนยันผู้เล่นของคุณ") : t("ค้นหาผู้เล่น")}</h1><p className="muted">{t("ค้นหาเฉพาะผู้เล่นจาก demo ที่นำเข้าระบบแล้ว")}{linking ? ` · ${t("ระบบจะไม่เดาจาก nickname")}` : ""}</p></header>
    <label className="players-search-field"><span className="sr-only">{t("ค้นหาผู้เล่น")}</span><SearchIcon /><input autoFocus value={query} placeholder={t("ค้นหาผู้เล่น…")} onChange={(event) => { const next = new URLSearchParams(params); if (event.target.value) next.set("q", event.target.value); else next.delete("q"); setParams(next); }} /></label>
    {linkError && <p className="err" role="alert">{linkError}</p>}
    {debounced.length < 2 ? <p className="muted">{t("พิมพ์อย่างน้อย 2 ตัวอักษร")}</p>
      : search.isLoading ? <p>{t("กำลังค้นหา…")}</p>
      : search.isError ? <p className="err">{t("ค้นหาผู้เล่นไม่สำเร็จ")}</p>
      : !search.data?.has_players ? <p>{t("ยังไม่มี demo หรือข้อมูลผู้เล่นในระบบ")}</p>
      : !search.data.items.length ? <p>{t("ไม่พบผู้เล่น")}</p>
      : <div className="players-search-list">{search.data.items.map((item) => <SearchResult key={item.steam_id} item={item} active={linkingId === item.steam_id} id={`player-${item.steam_id}`} onOpen={async () => {
        if (!linking) { navigate(`/player/${encodeURIComponent(item.steam_id)}`); return; }
        if (!window.confirm(t("ยืนยันว่า {name} (Steam {steam}) คือผู้เล่นของคุณ?", { name: item.name, steam: item.steam_id }))) return;
        try { setLinkError(null); setLinkingId(item.steam_id); await playerApi.linkMe(item.steam_id); navigate("/player"); }
        catch (error) { setLinkError(t((error as Error).message)); setLinkingId(null); }
      }} />)}</div>}
  </section>;
}
