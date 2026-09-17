import { useEffect, useState } from "react";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import {
  api,
  type DeathCellCount,
  type DeathsOverlay,
  matchesQuery,
  type Match,
  type MatchSource,
  type ReadRound,
  type Readability,
  type ScoreRow,
} from "./api";
import {
  DIFF_FILL,
  DIFF_MIN_DEATHS,
  DEATH_RAMP,
  DIFF_STEPS,
  diffLevel,
  type DiffLevel,
  pct,
  RATIO_RAMP,
  sideLabel,
} from "./utils";

/**
 * หน้าเครื่องมือวิเคราะห์ — สามคำถามเกี่ยวกับแมตช์ของทีมตัวเอง
 *
 *   ทีมเราตายตรงไหน    จุดตายในแมตช์ที่อัปโหลด นับลงกริด 32×32
 *   เทียบกับทีมอาชีพ    ช่องไหนเราตายบ่อยกว่าชุดอ้างอิง (คิดเป็นสัดส่วน)
 *   อ่านทางเราออกไหม   ทายไซต์ที่ทีมจะเข้าจากตำแหน่งที่ยืน แล้วดูว่าอ่านออกเร็วแค่ไหน
 *
 * โมเดล (research/grid_ml1.py, site_ml.py) อยู่หลังบ้านเท่านั้น — หน้าเว็บไม่มีที่ไหนให้ดูผลโมเดลตรง ๆ
 * และไม่มีศัพท์ ML บนหน้าจอ ผู้ใช้เห็นแค่ข้อเท็จจริงจากเดโมกับตัวเลขเทียบ (ตัดสินใจ 2026-09-18)
 *
 * ประเด็นสำคัญ: เดโมที่ผู้ใช้อัปโหลดไม่เคยถูกใช้เทรนโมเดล (คนละโฟลเดอร์ คนละ source ในฐานข้อมูล)
 * หน้านี้จึงเป็นการ "วัดของเราเทียบกับชุดอ้างอิง" ไม่ใช่การเอาข้อมูลตัวเองไปสอนแล้ววัดกับตัวเอง
 */
type Mode = "upload" | "diff" | "read";
type Side = "all" | "ct" | "t";

// ปุ่มโหมดเป็นการ์ดที่มีคำอธิบายสั้น ๆ ในตัว — คนเปิดหน้านี้ครั้งแรกต้องรู้จากปุ่มเลยว่าแต่ละอันตอบคำถามอะไร ไม่ต้องลองกดดู
const MODES: { key: Mode; label: string; hint: string }[] = [
  { key: "upload", label: "ทีมเราตายตรงไหน", hint: "จุดตายจากแมตช์ที่ทีมอัปโหลด" },
  { key: "diff", label: "เทียบกับทีมอาชีพ", hint: "ตรงไหนเราตายบ่อยกว่าทีมอาชีพ" },
  { key: "read", label: "อ่านทางเราออกไหม", hint: "คู่แข่งเดาไซต์ที่เราจะเข้าได้เร็วแค่ไหน" },
];

/** หัวเรื่องเปลี่ยนตามโหมด — คนอ่านต้องรู้ทันทีว่ากำลังดูอะไร ไม่ใช่หัวเดียวกันทุกโหมด */
const MODE_COPY: Record<Mode, { title: string; blurb: string }> = {
  upload: {
    title: "ทีมเราตายตรงไหน",
    blurb: "จุดที่ผู้เล่นในแมตช์ของทีมตาย นับลงช่องเดียวกับชุดเทียบของทีมอาชีพ — เลือกฝั่ง แมตช์ รอบ หรือผู้เล่นได้จากแผงซ้าย",
  },
  diff: {
    title: "เทียบกับทีมอาชีพ",
    blurb: "ตรงไหนที่ทีมเราเสียคนบ่อยกว่าทีมอาชีพ คิดเป็นสัดส่วนของจุดตายทั้งหมด ไม่ใช่จำนวนครั้งดิบ เพราะสองชุดมีจำนวนแมตช์ไม่เท่ากัน",
  },
  read: {
    title: "อ่านทางเราออกไหม",
    blurb: "จากตำแหน่งที่ผู้เล่นฝั่ง T ยืนในแต่ละวินาที เดาได้ตั้งแต่เมื่อไรว่าทีมจะเข้าไซต์ไหน — ยิ่งเดาออกเร็ว คู่แข่งที่ดูเทปก็อ่านทางออกเร็วเท่านั้น",
  },
};
const SIDES: { key: Side; label: string }[] = [
  { key: "all", label: "ทั้งสองฝั่ง" },
  { key: "ct", label: "ตอนเป็น CT" },
  { key: "t", label: "ตอนเป็น T" },
];

export function AnalysisPage() {
  const [mode, setMode] = useState<Mode>("upload");
  const [side, setSide] = useState<Side>("all");
  const [demo, setDemo] = useState<string>(""); // "" = ทุกแมตช์ที่อัปโหลด
  // ชี้เมาส์ที่แถวในตาราง (หรือช่องบนแผนที่) = ไฮไลต์อีกฝั่งให้เห็นทันที — คีย์เดียวกับที่ groupByPlace() ใช้จัดกลุ่ม
  const [hovered, setHovered] = useState<string | null>(null);
  // แผงควบคุมการแสดงผล heatmap — ค่าพวกนี้เป็นแค่การตั้งค่ามุมมอง ไม่ผูกกับ URL หรือรีเซ็ตตอนเปลี่ยนตัวกรองข้อมูล
  const [radius, setRadius] = useState(1);
  const [blur, setBlur] = useState(3.2);
  const [opacity, setOpacity] = useState(1);
  // null = ไม่กรอง (ทุกรอบ/ทุกคน) — ต่างจาก [] ที่แปลว่า "ไม่เลือกเลย" (ปุ่ม "ไม่เอาเลย")
  const [selRounds, setSelRounds] = useState<number[] | null>(null);
  const [selPlayers, setSelPlayers] = useState<string[] | null>(null);
  const matches = useQuery(matchesQuery);

  // แมพที่ดูได้ = แมพที่มีทั้งแมตช์ของเราและชุดอ้างอิง (ไม่งั้นไม่มีอะไรให้เทียบ)
  const done = (matches.data ?? []).filter((m) => m.status === "done" && m.map_name);
  const mapsWith = (s: MatchSource) => new Set(done.filter((m) => m.source === s).map((m) => m.map_name!));
  const refMaps = mapsWith("reference");
  const upMaps = mapsWith("upload");
  const maps = [...refMaps].filter((m) => upMaps.has(m)).sort();
  const [map, setMap] = useState<string>("");
  const activeMap = maps.includes(map) ? map : (maps[0] ?? "");
  const mine = done.filter((m) => m.source === "upload" && m.map_name === activeMap);
  const activeMatch = mine.find((m) => m.demo_file === demo);

  // รอสเตอร์ (ชื่อ + SteamID64) ของแมตช์ที่เลือก — ไว้ทำปุ่มเลือกผู้เล่น เอาจาก endpoint แมตช์เดี่ยวที่มีอยู่แล้ว
  // (ไม่ต้องเพิ่ม endpoint ใหม่) จำนวนรอบทั้งหมดก็มีอยู่แล้วใน match_summary (activeMatch.rounds)
  const roster = useQuery({
    queryKey: ["match-roster", activeMatch?.id],
    queryFn: () => api.match(activeMatch!.id),
    enabled: !!activeMatch,
    staleTime: 5 * 60_000,
  });

  // เจาะจงรอบ/คนได้เฉพาะตอนเลือกแมตช์เดียวแล้ว (เลขรอบไม่มีความหมายข้ามแมตช์) — สลับแมตช์ = ล้างตัวกรองนี้ทิ้ง
  useEffect(() => {
    setSelRounds(null);
    setSelPlayers(null);
  }, [demo]);

  // [] (เลือก "ไม่เอาเลย") ต่างจาก null (ไม่กรอง) — [] แปลว่าต้องไม่แสดงอะไรเลย ไม่ใช่แสดงทุกอย่าง
  // ต้องกันไว้เอง เพราะ API มองพารามิเตอร์ว่างเป็น "ไม่กรอง" (ดู backend/app.py _parse_int_list)
  const noRoundsPicked = selRounds !== null && selRounds.length === 0;
  const noPlayersPicked = selPlayers !== null && selPlayers.length === 0;

  const enabled = !!activeMap && !noRoundsPicked && !noPlayersPicked;
  const upload = useQuery({
    queryKey: ["analysis", activeMap, "upload", side, demo, selRounds, selPlayers],
    queryFn: () => api.analysisDeaths(activeMap, "upload", side, demo || null, selRounds, selPlayers),
    enabled,
    staleTime: 5 * 60_000,
    // เปลี่ยนตัวกรอง (รอบ/คน/ฝั่ง/แมตช์) = queryKey ใหม่ที่ยังไม่เคยแคช — ถ้าไม่กัน isLoading จะ true ชั่วขณะ
    // จนทั้งแผนที่+แผงควบคุมหายวับไปเหลือแค่ข้อความโหลด หน้าเว็บยุบสั้นลงมากจน scroll เด้งขึ้นบนเอง
    placeholderData: keepPreviousData,
  });
  const reference = useQuery({
    queryKey: ["analysis", activeMap, "reference", side],
    queryFn: () => api.analysisDeaths(activeMap, "reference", side),
    enabled: enabled && mode === "diff",
    staleTime: 5 * 60_000,
    placeholderData: keepPreviousData,
  });
  // โหมด "อ่านทางเราออกไหม" ดูได้ทีละแมตช์ — ไม่ได้เลือกไว้ก็ใช้แมตช์แรกของแมพนั้น
  const target = demo || mine[0]?.demo_file || "";
  const readQ = useQuery({
    queryKey: ["readability", target],
    queryFn: () => api.readability(target),
    enabled: mode === "read" && !!target,
    staleTime: 5 * 60_000,
    placeholderData: keepPreviousData,
  });

  // สลับโหมด/แมพ/ฝั่ง/แมตช์ = ชุดข้อมูลเปลี่ยน คีย์ที่ค้างไฮไลต์ไว้จากชุดก่อนหน้าจึงไม่มีความหมายแล้ว
  useEffect(() => setHovered(null), [mode, activeMap, side, demo]);

  if (matches.isLoading) return <p className="muted">กำลังโหลด…</p>;
  if (matches.error) return <p className="err">โหลดรายการแมตช์ไม่ได้: {(matches.error as Error).message}</p>;
  if (maps.length === 0) return <NothingToCompare done={done} />;

  const copy = MODE_COPY[mode];
  const single = upload.data;
  const loading = mode === "read" ? readQ.isLoading : upload.isLoading || (mode === "diff" && reference.isLoading);
  const error = (mode === "read" ? readQ.error : (upload.error ?? reference.error)) as Error | null;
  const rows = mode === "diff" && upload.data && reference.data ? compare(upload.data, reference.data) : [];
  // รวมตามชื่อ callout ครั้งเดียว ใช้ทั้งตาราง (top 8 ที่แย่สุด) และ heatmap ทีละโซน (ทุกโซน) จะได้ไม่มี
  // ทางแยกกันจนตัวเลข/เกณฑ์ไม่ตรงกันระหว่างสองที่
  const diffGroups = mode === "diff" ? groupDiffRows(rows) : [];

  return (
    <div className="analysis" data-testid="analysis-page">
      <header className="an-head">
        <div>
          <h1>{copy.title}</h1>
          <p className="muted">{copy.blurb}</p>
        </div>
      </header>

      <div className="an-controls">
        <div className="mode-tabs" role="group" aria-label="สิ่งที่ดู">
          {MODES.map((m) => (
            <button key={m.key} type="button" className={`mode-tab${mode === m.key ? " on" : ""}`}
              aria-pressed={mode === m.key} onClick={() => setMode(m.key)} data-testid={`mode-${m.key}`}>
              <b>{m.label}</b>
              <small>{m.hint}</small>
            </button>
          ))}
        </div>

        <div className="an-filters">
          <label className="an-select">
            แมพ
            <select value={activeMap} onChange={(e) => setMap(e.target.value)}>
              {maps.map((m) => (
                <option key={m} value={m}>{m}</option>
              ))}
            </select>
          </label>

          <label className="an-select">
            แมตช์ของทีม
            <select value={demo} onChange={(e) => setDemo(e.target.value)}>
              <option value="">ทุกแมตช์ที่อัปโหลด ({mine.length})</option>
              {mine.map((m) => (
                <option key={m.demo_file} value={m.demo_file}>{matchLabel(m)}</option>
              ))}
            </select>
          </label>
        </div>
      </div>

      {error && <p className="err">โหลดข้อมูลไม่ได้: {error.message}</p>}
      {loading && <p className="muted">{mode === "read" ? "กำลังอ่านทีละรอบ…" : "กำลังนับจุดตาย…"}</p>}

      {!loading && !error && mode === "read" && readQ.data && (
        <ReadabilityReport data={readQ.data} demo={target} />
      )}

      {!loading && !error && mode !== "read" && (
        <div className="an-grid">
          {/* แผงนี้อยู่เสมอไม่ว่าจะเลือกรอบ/ผู้เล่นไว้กี่คน — กด "ไม่เอาเลย" แล้วต้องยังเห็นปุ่ม "ทั้งหมด"
              เพื่อย้อนกลับได้ ไม่ใช่ทั้งแผงหายไปพร้อมกับแผนที่จนหาทางกลับไม่เจอ */}
          <HeatmapControls
            side={side} onSide={setSide}
            radius={radius} onRadius={setRadius}
            blur={blur} onBlur={setBlur}
            opacity={opacity} onOpacity={setOpacity}
            demoSelected={!!activeMatch}
            roundsTotal={activeMatch?.rounds ?? 0}
            selRounds={selRounds} onRounds={setSelRounds}
            roster={roster.data?.scoreboard ?? []}
            rosterLoading={roster.isLoading}
            selPlayers={selPlayers} onPlayers={setSelPlayers}
          />

          {noRoundsPicked || noPlayersPicked ? (
            <p className="muted an-empty an-empty-fill" data-testid="analysis-nothing-picked">
              ยังไม่ได้เลือก{noRoundsPicked ? "รอบ" : "ผู้เล่น"}เลยสักคน/รอบ — เลือกอย่างน้อยหนึ่งอย่างในแผงซ้าย
              หรือกด "ทั้งหมด" เพื่อดูภาพรวมอีกครั้ง
            </p>
          ) : (
            <>
              <section className="an-map-col">
                <div className="an-map">
                  {mode === "diff" ? (
                    <DeathMap radar={upload.data!.radar} cells={rows} paint={(r) => diffPaint(r.level)}
                      zoneFill={zoneRatioFill(diffGroups)}
                      highlightKey={hovered} onHoverKey={setHovered} radius={radius} blur={blur} layerOpacity={opacity} />
                  ) : (
                    single && (
                      <DeathMap radar={single.radar} cells={single.cells} paint={continuousFreqPaint(single.cells, side)}
                        highlightKey={hovered} onHoverKey={setHovered} radius={radius} blur={blur} layerOpacity={opacity} />
                    )
                  )}
                </div>
                {mode === "diff" ? <DiffKey /> : <GradientKey cells={single?.cells ?? []} side={side} />}
              </section>

              <aside className="an-side">
                {mode === "diff" ? (
                  <DiffTable groups={diffGroups} upload={upload.data!} reference={reference.data!} hovered={hovered} onHover={setHovered} />
                ) : (
                  <SingleSummary data={single!} hovered={hovered} onHover={setHovered} />
                )}
              </aside>
            </>
          )}
        </div>
      )}
    </div>
  );
}

// ================================================================================================
// แผงควบคุมการแสดงผล heatmap
//
// สองกลุ่ม: "แสดงยังไง" (รัศมี/เบลอ/ความทึบ/ฝั่ง) เป็นการตั้งค่าฝั่งเบราว์เซอร์ล้วน ไม่แตะ backend เลย
// กับ "ข้อมูลไหน" (รอบ/ผู้เล่น) ซึ่งเจาะจงได้เฉพาะหลังเลือกแมตช์เดียวแล้ว (เลขรอบไม่มีความหมายข้ามแมตช์)
// — ประเภทเหตุการณ์ (คิลผู้โจมตี vs ระเบิด) กับตัวกรองทีมยังทำไม่ได้ในรุ่นนี้ เพราะยังไม่มีข้อมูลตำแหน่ง
// ระเบิดผูกกับ endpoint นี้ และการอัปโหลดตอนนี้มีแค่ 1 แมตช์ต่อครั้ง (ทีม = เท่ากับเลือกแมตช์อยู่แล้ว)
// ================================================================================================
interface HeatmapControlsProps {
  side: Side;
  onSide: (s: Side) => void;
  radius: number;
  onRadius: (v: number) => void;
  blur: number;
  onBlur: (v: number) => void;
  opacity: number;
  onOpacity: (v: number) => void;
  demoSelected: boolean;
  roundsTotal: number;
  selRounds: number[] | null;
  onRounds: (r: number[] | null) => void;
  roster: ScoreRow[];
  rosterLoading: boolean;
  selPlayers: string[] | null;
  onPlayers: (p: string[] | null) => void;
}

function HeatmapControls({
  side, onSide, radius, onRadius, blur, onBlur, opacity, onOpacity,
  demoSelected, roundsTotal, selRounds, onRounds, roster, rosterLoading, selPlayers, onPlayers,
}: HeatmapControlsProps) {
  const roundOn = (n: number) => selRounds === null || selRounds.includes(n);
  const toggleRound = (n: number) => {
    const base = selRounds ?? Array.from({ length: roundsTotal }, (_, i) => i + 1);
    onRounds(base.includes(n) ? base.filter((x) => x !== n) : [...base, n].sort((a, b) => a - b));
  };
  const playerOn = (id: string) => selPlayers === null || selPlayers.includes(id);
  const togglePlayer = (id: string) => {
    const base = selPlayers ?? roster.map((p) => p.steam_id);
    onPlayers(base.includes(id) ? base.filter((x) => x !== id) : [...base, id]);
  };

  return (
    <aside className="hm-panel" aria-label="ตั้งค่าการแสดงผล heatmap">
      <div className="hm-field">
        <div className="hm-field-h"><span>ฝั่งของคนที่ตาย</span></div>
        <div className="seg hm-seg" role="group" aria-label="ฝั่งของคนที่ตาย">
          {SIDES.map((s) => (
            <button key={s.key} type="button" className={`seg-btn${side === s.key ? ` ${s.key} on` : ""}`}
              aria-pressed={side === s.key} onClick={() => onSide(s.key)}>
              {s.label}
            </button>
          ))}
        </div>
      </div>

      {!demoSelected ? (
        <p className="muted small hm-note">เลือก "แมตช์ของทีม" แมตช์เดียวด้านบนก่อน ถึงจะเจาะจงรอบหรือผู้เล่นได้</p>
      ) : (
        <>
          <div className="hm-field">
            <div className="hm-field-h">
              <span>รอบ</span>
              <span className="hm-quick">
                <button type="button" className="link-btn" onClick={() => onRounds(null)}>ทั้งหมด</button>
                {" · "}
                <button type="button" className="link-btn" onClick={() => onRounds([])}>ไม่เอาเลย</button>
              </span>
            </div>
            <div className="hm-round-grid" role="group" aria-label="เลือกรอบ">
              {Array.from({ length: roundsTotal }, (_, i) => i + 1).map((n) => (
                <button key={n} type="button" className={`hm-round-btn${roundOn(n) ? " on" : ""}`}
                  aria-pressed={roundOn(n)} onClick={() => toggleRound(n)}>
                  {n}
                </button>
              ))}
            </div>
          </div>

          <div className="hm-field">
            <div className="hm-field-h">
              <span>ผู้เล่น</span>
              <span className="hm-quick">
                <button type="button" className="link-btn" onClick={() => onPlayers(null)}>ทั้งหมด</button>
                {" · "}
                <button type="button" className="link-btn" onClick={() => onPlayers([])}>ไม่เอาเลย</button>
              </span>
            </div>
            {rosterLoading ? (
              <p className="muted small">กำลังโหลดรายชื่อ…</p>
            ) : (
              <div className="hm-pills" role="group" aria-label="เลือกผู้เล่น">
                {roster.map((p) => (
                  <button key={p.steam_id} type="button"
                    className={`hm-pill${playerOn(p.steam_id) ? ` ${p.start_side ?? ""} on` : ""}`}
                    aria-pressed={playerOn(p.steam_id)} onClick={() => togglePlayer(p.steam_id)}>
                    {p.name}
                  </button>
                ))}
              </div>
            )}
          </div>
        </>
      )}

      {/* ปุ่มปรับหน้าตา heatmap พับไว้ — คนส่วนใหญ่ไม่ต้องแตะ และ "รัศมี/เบลอ" ไม่ใช่คำที่โค้ชอยากเห็นก่อนข้อมูล */}
      <details className="hm-adv">
        <summary>ปรับการแสดงผล</summary>
        <div className="hm-field">
          <div className="hm-field-h"><span>รัศมี</span><span className="num muted">{radius.toFixed(1)}×</span></div>
          <input type="range" min={0.5} max={2.5} step={0.1} value={radius}
            onChange={(e) => onRadius(Number(e.target.value))} aria-label="รัศมีของจุดความร้อน" />
        </div>
        <div className="hm-field">
          <div className="hm-field-h"><span>เบลอ</span><span className="num muted">{blur.toFixed(1)}</span></div>
          <input type="range" min={0} max={10} step={0.5} value={blur}
            onChange={(e) => onBlur(Number(e.target.value))} aria-label="ความเบลอเพิ่มเติม" />
        </div>
        <div className="hm-field">
          <div className="hm-field-h"><span>ความทึบ</span><span className="num muted">{Math.round(opacity * 100)}%</span></div>
          <input type="range" min={0.2} max={1} step={0.05} value={opacity}
            onChange={(e) => onOpacity(Number(e.target.value))} aria-label="ความทึบของชั้นสี" />
        </div>
      </details>
    </aside>
  );
}

// ================================================================================================
// "อ่านทางเราออกไหม" — ผลจากโมเดลทายไซต์ (supervised) ที่เทรนจากเดโมทีมอาชีพ
// ================================================================================================
/**
 * โมเดลไม่เคยเห็นแมตช์นี้ ถ้ามันเดาไซต์ที่ทีมจะเข้าได้ตั้งแต่วินาทีต้น ๆ
 * แปลว่าคู่แข่งที่ดูเทปก็อ่านออกเหมือนกัน — "วินาทีที่ถูกอ่านออก" จึงเป็นตัวชี้วัดที่เอาไปแก้ได้จริง
 * ตัวเลขทีมอาชีพวัดแบบ out-of-fold (ทำนายรอบไหนใช้โมเดลที่ไม่เคยเห็นแมตช์นั้น) จึงเอามาเทียบกันได้
 */
function ReadabilityReport({ data, demo }: { data: Readability; demo: string }) {
  if (!data.available) {
    return (
      <div className="an-empty">
        <h2>ยังอ่านแมตช์นี้ไม่ได้</h2>
        <p className="muted">{data.reason}</p>
      </div>
    );
  }
  const s = data.summary!;
  const b = data.benchmark!;
  const ours = s.avg_read_at;
  const pro = b.avg_read_at;
  const gap = ours != null && pro != null ? pro - ours : null;
  const scale = Math.max(ours ?? 0, pro ?? 0, 1);
  const rows = data.rounds_detail ?? [];

  return (
    <div className="read-report" data-testid="readability">
      <section className="rr-hero">
        <div className="rr-stat">
          <span className="rr-label">ทีมเรา ถูกอ่านออกเฉลี่ยวินาทีที่</span>
          <b className="num">{ours ?? "—"}</b>
          <span className="rr-bar"><i style={{ width: `${((ours ?? 0) / scale) * 100}%` }} /></span>
          <span className="muted small">อ่านออก {s.read} จาก {s.rounds} รอบที่วางบอมบ์ · มัธยฐานวินาทีที่ {s.median_read_at ?? "—"}</span>
        </div>
        <div className="rr-stat pro">
          <span className="rr-label">ทีมอาชีพ ถูกอ่านออกเฉลี่ยวินาทีที่</span>
          <b className="num">{pro?.toFixed(1) ?? "—"}</b>
          <span className="rr-bar"><i style={{ width: `${((pro ?? 0) / scale) * 100}%` }} /></span>
          <span className="muted small">จาก {b.rounds} รอบ · มัธยฐานวินาทีที่ {b.median_read_at ?? "—"}</span>
        </div>
      </section>

      {gap != null && (
        <p className="rr-verdict">
          {gap > 0
            ? <>ทีมนี้ถูกอ่านออก<b> เร็วกว่าทีมอาชีพ {gap.toFixed(1)} วินาที</b> — ยิ่งเร็ว ฝ่ายรับยิ่งมีเวลาหมุนไปตั้งรับทัน</>
            : <>ทีมนี้ถูกอ่านออก<b> ช้ากว่าทีมอาชีพ {Math.abs(gap).toFixed(1)} วินาที</b> — ปกปิดทิศทางได้ดีกว่าค่าเฉลี่ยของชุดเทียบ</>}
          {s.avg_lead != null && <> · โดยเฉลี่ยรู้ทางก่อนบอมบ์ลงจริง {s.avg_lead} วินาที</>}
        </p>
      )}

      <h2>ดูทีละรอบ</h2>
      <table className="tbl compact rr-tbl">
        <thead>
          <tr>
            <th>รอบ</th>
            <th>เข้าไซต์</th>
            <th className="num">ถูกอ่านออกวินาทีที่</th>
            <th className="num">ก่อนบอมบ์ลง</th>
            <th>ผลรอบ</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.round_num} className={r.read_at != null && r.read_at <= 8 ? "rr-early" : ""}>
              <td className="num">{r.round_num}</td>
              <td><span className="rr-site">{r.site}</span></td>
              <td className="num">{r.read_at ?? "อ่านไม่ออก"}</td>
              <td className="num">{r.lead != null ? `${r.lead} วิ` : "—"}</td>
              <td>{r.winner_side ? <span className={`side-tag ${r.winner_side}`}>{sideLabel(r.winner_side)} ชนะ</span> : "—"}</td>
              <td>
                <Link className="link-btn" to={roundLink(demo, r)}>ดูรอบนี้</Link>
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <p className="muted small rr-note">
        แถวที่เน้น = ถูกอ่านออกภายใน 8 วินาทีแรก · กด "ดูรอบนี้" แล้วหน้ารอบจะเปิดโหมดเล่นย้อนค้างไว้ที่วินาทีนั้นพอดี
      </p>
      <p className="muted small">{data.note} · เทียบกับ{data.source?.label}</p>
    </div>
  );
}

/** เปิดหน้ารอบในโหมดเล่นย้อน ค้างไว้ที่วินาทีที่โมเดลอ่านออก — เห็นเลยว่าตอนนั้นทุกคนยืนตรงไหน */
const roundLink = (demo: string, r: ReadRound) =>
  `/matches/${encodeURIComponent(demo)}/rounds/${r.round_num}?pb=1${r.read_at != null ? `&t=${r.read_at}` : ""}`;

// ================================================================================================
// รวมช่องที่มีชื่อ callout เดียวกันเป็นแถวเดียว — ใช้ทั้งในตารางและตอนปักป้ายชื่อบนแผนที่
//
// หนึ่งจุดบนแมพ (เช่น "BombsiteA") กินกริด 32x32 หลายช่องเสมอ ถ้าตารางแสดงทีละช่องจะเห็นชื่อ
// เดียวกันซ้ำหลายแถวพร้อมพิกัดที่ต่างกันนิดเดียว อ่านแล้วเหมือนข้อมูลผิดทั้งที่ไม่ผิด — จึงรวมเป็น
// แถวเดียวแล้วบวกจำนวนตาย/สัดส่วนเข้าด้วยกัน ช่องที่ "ไม่มีชื่อเรียก" ไม่ถูกรวม เพราะกระจายอยู่
// คนละที่บนแมพ การเอามารวมกันจะสื่อความหมายผิด (เหมือนบอกว่าหลายจุดคนละที่คือที่เดียวกัน)
//
// คีย์เดียวกันนี้ยังใช้จับคู่ "ชี้เมาส์ที่แถว <-> ไฮไลต์ช่องบนแผนที่" (ข้อ 3) เพราะทั้งตารางกับ
// แผนที่กลุ่มเซลล์แบบเดียวกัน
// ================================================================================================
const cellKey = (c: DeathCellCount) => c.place ?? `@${c.cx},${c.cy}`;

interface PlaceGroup<T extends DeathCellCount> {
  key: string;
  place: string | null;
  cells: T[];
  deaths: number;
  share: number;
}

function groupByPlace<T extends DeathCellCount>(cells: T[]): PlaceGroup<T>[] {
  const out = new Map<string, PlaceGroup<T>>();
  for (const c of cells) {
    const key = cellKey(c);
    let g = out.get(key);
    if (!g) {
      g = { key, place: c.place, cells: [], deaths: 0, share: 0 };
      out.set(key, g);
    }
    g.cells.push(c);
    g.deaths += c.deaths;
    g.share += c.share;
  }
  return [...out.values()];
}

/**
 * ตรงไหนของแมพ — ชื่อ callout ที่เดโมบันทึกไว้ (BombsiteA, Catwalk, …) พร้อมบอกว่ารวมมาจากกี่ช่อง
 * ช่องที่ไม่มีชื่อเรียก ยังบอกพิกัดกำกับไว้เหมือนเดิม เพราะเป็นช่องเดี่ยว ไม่ได้ถูกรวม
 */
function PlaceCell({ place, cells }: { place: string | null; cells: { cx: number; cy: number }[] }) {
  if (place) {
    return (
      <span className="an-place">
        {place}
        {cells.length > 1 && <span className="muted num"> · {cells.length} ช่อง</span>}
      </span>
    );
  }
  return (
    <span className="an-place">
      ไม่มีชื่อเรียก
      <span className="muted num"> {cells[0].cx},{cells[0].cy}</span>
    </span>
  );
}

// ================================================================================================
// เทียบสองชุด
// ================================================================================================
interface DiffRow extends DeathCellCount {
  shareRef: number;
  deathsRef: number;
  level: DiffLevel;
  ratio: number;
}

/** จับคู่ช่องของสองชุด แล้วคิดว่าช่องไหนต่างกันแค่ไหน — เรียงช่องที่เราตายบ่อยกว่ามากสุดไว้บน */
function compare(mine: DeathsOverlay, ref: DeathsOverlay): DiffRow[] {
  const refBy = new Map(ref.cells.map((c) => [`${c.cx},${c.cy}`, c]));
  return mine.cells
    .map((c) => {
      const r = refBy.get(`${c.cx},${c.cy}`);
      const shareRef = r?.share ?? 0;
      return {
        ...c,
        shareRef,
        deathsRef: r?.deaths ?? 0,
        level: diffLevel(c.share, shareRef, c.deaths),
        ratio: shareRef > 0 ? c.share / shareRef : Infinity,
      };
    })
    .sort((a, b) => b.level - a.level || b.deaths - a.deaths);
}

/** รวมแถวเทียบสองชุดตามชื่อ callout แล้วคิด ratio/level ใหม่จากยอดรวม — สูตรเดิมทุกตัว แค่ป้อนเลขที่บวกกันแล้ว */
function groupDiffRows(rows: DiffRow[]) {
  return groupByPlace(rows).map((g) => {
    const shareRef = g.cells.reduce((s, c) => s + c.shareRef, 0);
    const deathsRef = g.cells.reduce((s, c) => s + c.deathsRef, 0);
    const ratio = shareRef > 0 ? g.share / shareRef : Infinity;
    return { ...g, shareRef, deathsRef, ratio, level: diffLevel(g.share, shareRef, g.deaths) };
  });
}

/**
 * ใช้ diffLevel เดิม (เกณฑ์ near/far เดียวกับตาราง) แค่กำหนดว่า "ช่องนี้ชี้เมาส์ได้ไหม" — ไม่ได้ใช้ค่าสี
 * ของ DIFF_FILL แสดงจริงบนแผนที่แล้ว (สลับไปใช้ heatmap ทีละโซนแทน ดู zoneRatioFill) แต่ยังต้องใช้
 * เกณฑ์เดียวกันเพื่อให้ "ช่องที่ hover ได้" ตรงกับ "ช่องที่ต่างกันมากพอจะสรุป" เหมือนเดิม
 */
const diffPaint = (lv: DiffLevel) =>
  lv === 0 ? null : { fill: DIFF_FILL[String(lv) as "-2" | "-1" | "1" | "2"], opacity: 0 };

/**
 * จุดกึ่งกลาง + รัศมีของโซนหนึ่ง จากกลุ่มช่องกริดที่กินชื่อ callout เดียวกัน
 * รัศมีมาจาก "โซนนี้กว้างแค่ไหนจริง ๆ บนแมพ" (ระยะไกลสุดจากจุดกึ่งกลางถึงช่องสมาชิก) ล้วน ๆ
 * ไม่เกี่ยวกับความเข้ม/ตัวเลขกี่เท่าเลย — ความเข้มสื่อผ่านสีอย่างเดียวตามที่ต้องการ
 */
function zoneGeometry(cells: { x: number; y: number; w: number }[]) {
  const cx = cells.reduce((s, c) => s + c.x + c.w / 2, 0) / cells.length;
  const cy = cells.reduce((s, c) => s + c.y + c.w / 2, 0) / cells.length;
  const spread = Math.max(...cells.map((c) => Math.hypot(c.x + c.w / 2 - cx, c.y + c.w / 2 - cy)));
  const w = cells[0]?.w ?? 32;
  return { cx, cy, r: Math.max(w * 1.4, spread + w * 0.9) };
}

/**
 * t=0 ที่ ratio ต่ำกว่าเกณฑ์ near (เท่ากับตารางที่ถือว่า "พอ ๆ กัน") ไล่แบบ log ขึ้นถึง t=1 ที่ maxRatio
 * ของโซนที่แย่สุดในชุดข้อมูลนี้ (ปรับตามข้อมูลจริงแต่ละแมตช์ เหมือนวิธีที่ GradientKey/deathT ใช้อยู่แล้ว)
 * ratio = Infinity (ทีมอาชีพไม่เคยตายช่องนี้เลยสักครั้ง) นับเป็นเข้มสุดตรง ๆ ไม่ต้องเข้าสูตร log
 */
function ratioT(ratio: number, maxRatio: number): number {
  if (ratio < DIFF_STEPS.near) return 0;
  if (ratio === Infinity) return 1;
  const lo = Math.log(DIFF_STEPS.near);
  const hi = Math.log(Math.max(maxRatio, DIFF_STEPS.far));
  return Math.min(1, Math.max(0, (Math.log(ratio) - lo) / (hi - lo)));
}

/**
 * ชั้นสี heatmap ทีละโซน — หนึ่งจุดต่อชื่อ callout หนึ่งชื่อ ใช้ ratio (กี่เท่า) เป็นน้ำหนักอย่างเดียว
 * ข้ามโซนที่ไม่มีชื่อเรียก (คีย์ "@x,y") เพราะไม่ใช่ "โซน" ที่มีความหมายจริง — ยังเห็นได้จากตาราง/
 * hit-rect เดิมอยู่ แค่ไม่ได้จุดสีของตัวเอง — และข้ามโซนที่ตายไม่ถึง DIFF_MIN_DEATHS หรือ t=0 (ต่างกัน
 * ไม่ถึงเกณฑ์) เพื่อให้ "ใกล้ 1×" โปร่งใสจริง ๆ ไม่ใช่แค่จางมาก
 */
function zoneRatioFill(groups: ReturnType<typeof groupDiffRows>) {
  const finite = groups.map((g) => g.ratio).filter((r) => Number.isFinite(r));
  const maxRatio = finite.length ? Math.max(DIFF_STEPS.far, ...finite) : DIFF_STEPS.far;
  return groups
    .filter((g) => g.place != null && g.deaths >= DIFF_MIN_DEATHS)
    .map((g) => {
      const t = ratioT(g.ratio, maxRatio);
      if (t <= 0) return null;
      const geo = zoneGeometry(g.cells);
      return { key: g.key, cx: geo.cx, cy: geo.cy, r: geo.r, fill: mixStops(RATIO_RAMP, t), opacity: 0.4 + t * 0.5 };
    })
    .filter((z): z is { key: string; cx: number; cy: number; r: number; fill: string; opacity: number } => z != null);
}

function DiffKey() {
  const gid = "diff-ratio-grad";
  return (
    <div className="map-key grad-key" aria-label="คำอธิบายสี">
      <span className="muted">สีของแต่ละโซน = ทีมเราตายบ่อยกว่าทีมอาชีพกี่เท่า ยิ่งเข้มยิ่งต่างมาก</span>
      <span className="grad-bar-wrap">
        <span className="grad-num">{DIFF_STEPS.near}×</span>
        <svg className="grad-bar" viewBox="0 0 100 10" preserveAspectRatio="none" aria-hidden="true">
          <defs>
            <linearGradient id={gid} x1="0" y1="0" x2="1" y2="0">
              {RATIO_RAMP.map((c, i) => (
                <stop key={c} offset={`${(i / (RATIO_RAMP.length - 1)) * 100}%`} stopColor={c} />
              ))}
            </linearGradient>
          </defs>
          <rect x="0" y="0" width="100" height="10" fill={`url(#${gid})`} />
        </svg>
        <span className="grad-num">{DIFF_STEPS.far}×+</span>
      </span>
      <span className="muted small key-adv">
        ต่ำกว่า {DIFF_STEPS.near}× หรือทีมเราตายในโซนนั้นไม่ถึง {DIFF_MIN_DEATHS} ครั้ง = ไม่ระบาย
        (ต่างกันไม่ชัดพอจะสรุปอะไรได้)
      </span>
    </div>
  );
}

interface TableHoverProps {
  hovered: string | null;
  onHover: (key: string | null) => void;
}

function DiffTable({ groups, upload, reference, hovered, onHover }:
  { groups: ReturnType<typeof groupDiffRows>; upload: DeathsOverlay; reference: DeathsOverlay } & TableHoverProps) {
  const worst = groups
    .filter((g) => g.level > 0)
    .sort((a, b) => b.level - a.level || b.deaths - a.deaths)
    .slice(0, 8);
  return (
    <>
      <h2>จุดที่ทีมเราตายบ่อยกว่าทีมอาชีพ</h2>
      <p className="muted small">
        {upload.label} · ตาย {upload.deaths} ครั้ง — เทียบกับ {reference.label} · ตาย {reference.deaths} ครั้ง
      </p>
      {worst.length === 0 ? (
        <p className="muted small">
          ยังไม่มีจุดไหนที่ทีมเราตายบ่อยกว่าทีมอาชีพถึง {DIFF_STEPS.near}× และมีจำนวนมากพอจะสรุป —
          อัปโหลดแมตช์เพิ่มแล้วตัวเลขจะชัดขึ้น
        </p>
      ) : (
        <table className="tbl compact an-tbl">
          <thead>
            <tr>
              <th>ตรงไหนของแมพ</th>
              <th className="num">เราตาย</th>
              <th className="num">ของเรา</th>
              <th className="num">ทีมอาชีพ</th>
              <th className="num">ต่างกี่เท่า</th>
            </tr>
          </thead>
          <tbody>
            {worst.map((g) => (
              <tr key={g.key} className={hovered === g.key ? "hl" : ""} tabIndex={0}
                onMouseEnter={() => onHover(g.key)} onMouseLeave={() => onHover(null)}
                onFocus={() => onHover(g.key)} onBlur={() => onHover(null)}>
                <td><PlaceCell place={g.place} cells={g.cells} /></td>
                <td className="num">{g.deaths}</td>
                <td className="num">{pct(g.share)}</td>
                <td className="num">{pct(g.shareRef)}</td>
                <td className="num"><b>{g.ratio === Infinity ? "—" : `${g.ratio.toFixed(1)}×`}</b></td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <p className="muted small an-note">
        "ของเรา" กับ "ทีมอาชีพ" คือสัดส่วนของจุดตายทั้งหมดในชุดนั้น ไม่ใช่จำนวนครั้งดิบ — ทีมอาชีพมี 50 แมตช์
        ถ้าเอาจำนวนครั้งมาเทียบกันตรง ๆ ฝั่งที่มีแมตช์เยอะกว่าก็ตายเยอะกว่าเสมอ ซึ่งไม่ได้บอกอะไร
      </p>
    </>
  );
}

// ================================================================================================
// ดูชุดเดียว — ไล่สีต่อเนื่องตามจำนวนครั้งที่ตาย (ไม่ตัดเป็นขั้นแบบควอนไทล์)
//
// เดิมแบ่งเป็น 5 ขั้นตามควอนไทล์ของข้อมูลชุดนั้น แต่แมตช์ที่อัปโหลดมีน้อย (บ่อยครั้งแค่ 1 แมตช์)
// ทำให้ควอนไทล์ชนกันจนยุบเหลือแค่ 2 ขั้นจริง ๆ (เช่น "1" กับ "ตั้งแต่ 2") — ตาย 2 ครั้งกับ 20 ครั้ง
// เลยได้สีเดียวกัน ทั้งที่ต่างกันมาก จึงเปลี่ยนมาไล่สีต่อเนื่องตามสัดส่วนจริงแทน
// ================================================================================================
function hexToRgb(hex: string): [number, number, number] {
  const n = parseInt(hex.replace("#", ""), 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

/** ผสมสีเชิงเส้นระหว่างสองเฉด ตาม t = 0 (อ่อนสุด) ถึง 1 (เข้มสุด) */
function mixHex(a: string, b: string, t: number): string {
  const pa = hexToRgb(a);
  const pb = hexToRgb(b);
  const m = (i: number) => Math.round(pa[i] + (pb[i] - pa[i]) * t);
  return `rgb(${m(0)}, ${m(1)}, ${m(2)})`;
}

/** ผสมสีไล่ผ่านหลายจุด (ไม่ใช่แค่ปลายสองข้างแบบ mixHex) — t=0 คือสีแรกในลิสต์ t=1 คือสีสุดท้าย */
function mixStops(stops: readonly string[], t: number): string {
  const clamped = Math.min(1, Math.max(0, t));
  const seg = clamped * (stops.length - 1);
  const i = Math.min(stops.length - 2, Math.floor(seg));
  return mixHex(stops[i], stops[i + 1], seg - i);
}

/**
 * ไล่ตาม log1p ไม่ใช่เชิงเส้นตรง ๆ เพราะช่องส่วนใหญ่ตายแค่ 1-3 ครั้ง ถ้าไล่เชิงเส้นตามค่าดิบ
 * ช่องเหล่านั้นจะดูจางเกือบเท่ากันหมด ขณะที่ไม่กี่ช่องที่ตายเยอะกินสเกลไปเกือบทั้งหมด — log1p ให้
 * ความละเอียดกับช่วงตายน้อยมากขึ้น โดยยังแยกช่วงตายเยอะออกจากกันได้อยู่ และไม่มีจุดตัดแบบ percentile
 * clip ที่ทำให้สีกระโดดที่ขอบ (ชุดข้อมูลนี้เล็ก per แมตช์ 1-2 หลักสิบช่อง คำนวณ percentile ได้ไม่นิ่ง)
 */
function deathT(value: number, max: number): number {
  return max > 0 ? Math.log1p(value) / Math.log1p(max) : 0;
}

/** ช่องที่ตายน้อยกว่านี้ไม่ระบายเลย (โปร่งใส) — ข้อมูลน้อยเกินจะสรุปว่าเป็นจุดอ่อนจริง ไม่ใช่ตายเซอร์ไพรส์ครั้งเดียว */
const MIN_PAINTED_DEATHS = 3;

function continuousFreqPaint(cells: DeathCellCount[], side: Side) {
  const max = Math.max(1, ...cells.map((c) => c.deaths));
  const ramp = DEATH_RAMP[side];
  return (c: DeathCellCount) => {
    if (c.deaths < MIN_PAINTED_DEATHS) return null;
    const t = deathT(c.deaths, max);
    return { fill: mixHex(ramp[0], ramp[ramp.length - 1], t), opacity: 0.5 + t * 0.42 };
  };
}

const SIDE_NOTE: Record<Side, string> = {
  all: "รวมทั้งสองฝั่ง",
  ct: "เฉพาะตอนเป็น CT",
  t: "เฉพาะตอนเป็น T",
};

/**
 * คำอธิบายสี — แถบไล่สีต่อเนื่องจริง ๆ (ไม่ใช่สวอตช์แยกขั้น) พร้อมค่าต่ำสุด/สูงสุดกำกับปลายแถบ
 * ขอบแถบคือ MIN_PAINTED_DEATHS ไม่ใช่ 1 เพราะช่องที่ตายน้อยกว่านั้นไม่ถูกระบายเลย แถบจึงต้องตรง
 * กับช่วงค่าที่ระบายจริงบนแผนที่ ไม่ใช่ช่วงค่าทั้งหมดที่มีในข้อมูล
 */
function GradientKey({ cells, side }: { cells: DeathCellCount[]; side: Side }) {
  const max = Math.max(0, ...cells.map((c) => c.deaths));
  const ramp = DEATH_RAMP[side];
  if (max < MIN_PAINTED_DEATHS) {
    return (
      <p className="muted small key-adv" data-testid="grad-key-empty">
        ยังไม่มีช่องไหนตายถึง {MIN_PAINTED_DEATHS} ครั้ง (ตายมากสุด {max} ครั้ง) — ข้อมูลน้อยเกินกว่าจะระบายแผนที่
      </p>
    );
  }
  const gid = `death-grad-${side}`;
  const steps = 10;
  const stops = Array.from({ length: steps + 1 }, (_, i) => {
    const value = MIN_PAINTED_DEATHS + ((max - MIN_PAINTED_DEATHS) * i) / steps;
    return { pos: (i / steps) * 100, color: mixHex(ramp[0], ramp[ramp.length - 1], deathT(value, max)) };
  });
  return (
    <div className="map-key grad-key" aria-label="คำอธิบายสี">
      <span className="muted">จำนวนครั้งที่ตายในช่องนั้น ({SIDE_NOTE[side]}) ยิ่งเข้มยิ่งตายบ่อย</span>
      <span className="grad-bar-wrap">
        <span className="grad-num">{MIN_PAINTED_DEATHS}</span>
        <svg className="grad-bar" viewBox="0 0 100 10" preserveAspectRatio="none" aria-hidden="true">
          <defs>
            <linearGradient id={gid} x1="0" y1="0" x2="1" y2="0">
              {/* ไล่ตามเส้นโค้งเดียวกับที่ใช้ระบายแผนที่จริง (deathT) แถบสีจึงตรงกับสิ่งที่เห็นบนแผนที่เป๊ะ ๆ */}
              {stops.map((s) => (
                <stop key={s.pos} offset={`${s.pos}%`} stopColor={s.color} />
              ))}
            </linearGradient>
          </defs>
          <rect x="0" y="0" width="100" height="10" fill={`url(#${gid})`} />
        </svg>
        <span className="grad-num">{max}</span>
      </span>
      <span className="muted">ครั้ง · ต่ำกว่า {MIN_PAINTED_DEATHS} ครั้งไม่ระบาย</span>
    </div>
  );
}

function SingleSummary({ data, hovered, onHover }: { data: DeathsOverlay } & TableHoverProps) {
  const top = groupByPlace(data.cells).sort((a, b) => b.deaths - a.deaths).slice(0, 8);
  return (
    <>
      <h2>ช่องที่ตายบ่อยที่สุด</h2>
      <p className="muted small">{data.label} · ตายรวม {data.deaths} ครั้ง ใน {data.cells.length} ช่อง</p>
      <table className="tbl compact an-tbl">
        <thead>
          <tr>
            <th>ตรงไหนของแมพ</th>
            <th className="num">ตาย</th>
            <th className="num">สัดส่วน</th>
          </tr>
        </thead>
        <tbody>
          {top.map((g) => (
            <tr key={g.key} className={hovered === g.key ? "hl" : ""} tabIndex={0}
              onMouseEnter={() => onHover(g.key)} onMouseLeave={() => onHover(null)}
              onFocus={() => onHover(g.key)} onBlur={() => onHover(null)}>
              <td><PlaceCell place={g.place} cells={g.cells} /></td>
              <td className="num">{g.deaths}</td>
              <td className="num">{pct(g.share)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}

// ================================================================================================
// แผนที่: ภาพเรดาร์ + ช่องกริด (พิกเซลมาจาก backend เหมือนหน้ารอบ — ไม่มีสูตรพิกัดในหน้าเว็บ)
// ================================================================================================
interface MapProps<T extends DeathCellCount> {
  radar: DeathsOverlay["radar"];
  cells: T[];
  paint: (c: T) => { fill: string; opacity: number } | null;
  /** คีย์ของแถวที่ถูกชี้เมาส์อยู่ในตาราง (จาก groupByPlace) — ช่องที่ตรงกันจะถูกเน้น */
  highlightKey?: string | null;
  /** ชี้เมาส์ที่ช่องบนแผนที่ ก็ให้ไฮไลต์แถวในตารางกลับ (คีย์เดียวกันทั้งสองทาง) */
  onHoverKey?: (key: string | null) => void;
  /** ตัวคูณรัศมีจุดความร้อน (1 = ค่าเริ่มต้น) — ควบคุมจากแผงด้านซ้าย ("รัศมี") */
  radius?: number;
  /** stdDeviation ของเบลอที่ทับอีกชั้นหลังระบายสี — ควบคุมจากแผงด้านซ้าย ("เบลอ") */
  blur?: number;
  /** ความทึบรวมของทั้งชั้นสี คูณกับความทึบต่อจุดที่คำนวณไว้แล้ว — ควบคุมจากแผงด้านซ้าย ("ความทึบ") */
  layerOpacity?: number;
  /**
   * ชั้นสีแบบ "ทีละโซน" (จุดเดียวต่อชื่อ callout หนึ่งชื่อ) แทนชั้นสีทีละช่องกริดที่คำนวณจาก paint() —
   * ใช้ตอนตัวชี้วัดมีความหมายระดับโซน (เช่น "กี่เท่า") ไม่ใช่ระดับช่อง 32×32 เดี่ยว ๆ
   * cells/hit-rect/ป้ายชื่อทุกอย่างยังเหมือนเดิม (ยังใช้ paint() กำหนดว่าช่องไหน hover ได้) —
   * มีพร็อพนี้ให้แค่สลับ "สิ่งที่มองเห็น" ของชั้นสีอย่างเดียว รัศมีของแต่ละจุดยังคูณด้วย radius เหมือนเดิม
   */
  zoneFill?: { key: string; cx: number; cy: number; r: number; fill: string; opacity: number }[];
}

/**
 * ป้ายชื่อที่ติดบนแผนที่ตลอดเวลา จำกัดไว้แค่จุดหลักที่คนใช้แผนที่นี้ต้องอ้างอิงตลอด (บอมบ์ไซต์ · กลางแมพ ·
 * จุดเริ่มของสองฝั่ง) ชื่ออื่น ๆ (Catwalk, Apartments, Shop, …) ยังหาได้จากตาราง "ช่องที่ตายบ่อยที่สุด"
 * และจากการชี้เมาส์ที่ช่องนั้นบนแผนที่ (title tooltip) — ติดป้ายทุกชื่อพร้อมกันแล้วแมพรกจนอ่านไม่ออก
 */
const MAJOR_ZONE_RE = /^(bombsite ?[ab]|mid(dle)?|t ?spawn|ct ?spawn)$/i;

/**
 * จุดกึ่งกลางของแต่ละชื่อ callout ไว้ปักป้ายชื่อบนภาพ — คำนวณครั้งเดียวต่อชื่อ ไม่ใช่ต่อช่อง
 * ข้อจำกัดที่รู้ไว้: ถ้าชื่อเดียวกันกินพื้นที่ที่ไม่ติดกันบนแมพ (พบได้ในบางแมพ) จุดกึ่งกลางที่คำนวณ
 * ได้อาจตกอยู่กึ่งกลางระหว่างสองบริเวณนั้นแทนที่จะอยู่ในบริเวณใดบริเวณหนึ่งพอดี
 */
function placeLabels<T extends DeathCellCount>(cells: T[]) {
  const out: { key: string; place: string; x: number; y: number }[] = [];
  for (const g of groupByPlace(cells)) {
    if (!g.place || !MAJOR_ZONE_RE.test(g.place)) continue;
    const x = g.cells.reduce((s, c) => s + c.x + c.w / 2, 0) / g.cells.length;
    const y = g.cells.reduce((s, c) => s + c.y + c.w / 2, 0) / g.cells.length;
    out.push({ key: g.key, place: g.place, x, y });
  }
  return out;
}

/**
 * ระบายเป็นสองชั้นแยกกัน:
 *   ชั้นสี   — วงกลมถ่วงน้ำหนักที่กึ่งกลางแต่ละช่อง ซ้อนทับกัน แล้วเบลอทั้งกลุ่ม (feGaussianBlur)
 *             ให้ดูเป็น heatmap ต่อเนื่องกลมกลืน ไม่ใช่ตารางสี่เหลี่ยมคมกริบต่อกัน
 *             ปิด pointer-events ไว้ เพราะเบลอแล้วขอบจริงของช่องเพี้ยนไปจากที่ตาเห็น จะชี้/hover ไม่แม่น
 *
 *             ข้อจำกัดที่รู้ไว้: backend ส่งตำแหน่งตายมาเป็นช่องกริด 32×32 ที่รวมแล้ว ไม่ใช่พิกัดจุดตาย
 *             ดิบทีละจุด การระบายนี้จึงเป็นการประมาณด้วยวงกลมถ่วงน้ำหนักที่ศูนย์กลางช่อง ไม่ใช่ KDE จาก
 *             จุดจริงทั้งหมด — ได้ภาพต่อเนื่องเหมือนกัน แต่ความละเอียดจริงยังจำกัดที่ 32×32 ช่องเท่าเดิม
 *   ชั้นรับชี้เมาส์ — โปร่งใส ขอบคมเสมอ ตรงกับพิกัดช่องจริงเป๊ะ ๆ ใช้ทำ hover ↔ ตาราง และ title tooltip
 */
function DeathMap<T extends DeathCellCount>({
  radar, cells, paint, highlightKey, onHoverKey, radius = 1, blur = 3.2, layerOpacity = 1, zoneFill,
}: MapProps<T>) {
  const s = radar.size;
  const labels = placeLabels(cells);
  const painted = cells
    .map((c) => ({ c, p: paint(c) }))
    .filter((x): x is { c: T; p: { fill: string; opacity: number } } => x.p != null)
    // วาดจุดที่เข้มสุดทับบนสุด ไม่งั้นจุดร้อนอาจถูกจุดข้าง ๆ ที่วาดทีหลังบังหรือกลืนสีจนดูจางลง
    .sort((a, b) => a.p.opacity - b.p.opacity);
  // เรียงลำดับเดียวกัน: จุดที่เข้มสุดวาดทับบนสุด
  const zonePainted = zoneFill && [...zoneFill].sort((a, b) => a.opacity - b.opacity);
  return (
    <svg viewBox={`0 0 ${s} ${s}`} className="radar" data-testid="analysis-radar">
      <defs>
        <filter id="cell-blur" x="-40%" y="-40%" width="180%" height="180%">
          <feGaussianBlur stdDeviation={blur} />
        </filter>
      </defs>
      <image href={radar.image} x={0} y={0} width={s} height={s} />

      <g filter="url(#cell-blur)" opacity={layerOpacity} style={{ pointerEvents: "none" }}>
        {zonePainted
          ? zonePainted.map((z) => {
              const active = highlightKey != null && z.key === highlightKey;
              return (
                <circle
                  key={`zone-${z.key}`} cx={z.cx} cy={z.cy} r={z.r * radius}
                  fill={z.fill} opacity={active ? 1 : z.opacity} style={{ transition: "opacity .12s" }}
                />
              );
            })
          : painted.map(({ c, p }) => {
              const active = highlightKey != null && cellKey(c) === highlightKey;
              return (
                <circle
                  key={`fill-${c.cx}-${c.cy}`} cx={c.x + c.w / 2} cy={c.y + c.w / 2} r={c.w * 1.4 * radius}
                  fill={p.fill} opacity={active ? 1 : p.opacity} style={{ transition: "opacity .12s" }}
                />
              );
            })}
      </g>

      {painted.map(({ c }) => {
        const key = cellKey(c);
        const active = highlightKey != null && key === highlightKey;
        return (
          <rect
            key={`hit-${c.cx}-${c.cy}`} x={c.x} y={c.y} width={c.w} height={c.w}
            fill="transparent" stroke={active ? "#ffffff" : "transparent"} strokeWidth={active ? 2.5 : 0}
            onMouseEnter={() => onHoverKey?.(key)} onMouseLeave={() => onHoverKey?.(null)}
            data-testid="analysis-cell" data-active={active || undefined}
          >
            <title>{`${c.place ?? "ไม่มีชื่อเรียก"} (ช่อง ${c.cx}, ${c.cy}) · ตาย ${c.deaths} ครั้ง`}</title>
          </rect>
        );
      })}

      {labels.map((l) => (
        <text
          key={l.key} x={l.x} y={l.y} textAnchor="middle" className="zone-label"
          opacity={highlightKey == null || highlightKey === l.key ? 1 : 0.4}
        >
          {l.place}
        </text>
      ))}
    </svg>
  );
}

/** ยังไม่มีอะไรให้เทียบ — บอกตรง ๆ ว่าขาดอะไร ไม่ใช่หน้าว่าง */
function NothingToCompare({ done }: { done: Match[] }) {
  const uploaded = done.filter((m) => m.source === "upload");
  return (
    <div className="pl-empty" data-testid="analysis-empty">
      <h1>ยังไม่มีแมตช์ให้เทียบ</h1>
      <p className="muted">
        หน้านี้เทียบแมตช์ของทีมกับเดโมทีมอาชีพบนแมพเดียวกัน
        {uploaded.length === 0
          ? " — ยังไม่มีแมตช์ที่อัปโหลดเข้ามาเลย"
          : ` — มีแมตช์ที่อัปโหลด ${uploaded.length} แมตช์ แต่ยังไม่ตรงกับแมพที่มีเดโมทีมอาชีพให้เทียบ (ตอนนี้มีแค่ de_mirage)`}
      </p>
      <Link className="btn-primary" to="/matches">ไปหน้าแมตช์</Link>
    </div>
  );
}


const matchLabel = (m: Match) => (m.team_a && m.team_b ? `${m.team_a} vs ${m.team_b}` : m.demo_file);
