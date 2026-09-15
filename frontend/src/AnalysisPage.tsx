import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
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
} from "./api";
import {
  DIFF_FILL,
  DIFF_MIN_DEATHS,
  DEATH_RAMP,
  DIFF_STEPS,
  diffLevel,
  type DiffLevel,
  FREQ_ALPHA,
  freqBands,
  freqBreaks,
  freqLevel,
  pct,
  SCREEN,
  sideLabel,
} from "./utils";

/**
 * หน้าเครื่องมือวิเคราะห์ — เทียบ "แมตช์ที่อัปโหลด" กับ "ชุดอ้างอิงที่โมเดลเทรนจากมัน"
 *
 * ประเด็นสำคัญของหน้านี้: เดโมที่ผู้ใช้อัปโหลดไม่เคยถูกใช้เทรนโมเดล (คนละโฟลเดอร์ คนละ source ในฐานข้อมูล)
 * หน้านี้จึงเป็นการ "วัดของเราเทียบกับของที่โมเดลรู้จัก" ไม่ใช่การเอาข้อมูลตัวเองไปสอนโมเดลแล้ววัดกับตัวเอง
 */
type Mode = "diff" | "upload" | "read";
type Side = "all" | "ct" | "t";

const MODES: { key: Mode; label: string; hint: string }[] = [
  { key: "upload", label: "ทีมเราตายตรงไหน", hint: "จุดที่ผู้เล่นตายในแมตช์ของทีมเรา" },
  { key: "diff", label: "เทียบกับทีมอาชีพ", hint: "ช่องไหนทีมเราตายบ่อยกว่าหรือน้อยกว่าทีมอาชีพ" },
  { key: "read", label: "อ่านทางเราออกไหม", hint: "โมเดลเดาไซต์ที่เราจะเข้าได้เร็วแค่ไหน — ยิ่งเร็ว คู่แข่งยิ่งอ่านออกง่าย" },
];
const SIDES: { key: Side; label: string }[] = [
  { key: "all", label: "ทั้งสองฝั่ง" },
  { key: "ct", label: "ตอนเป็น CT" },
  { key: "t", label: "ตอนเป็น T" },
];

export function AnalysisPage() {
  const [mode, setMode] = useState<Mode>("upload");
  const [side, setSide] = useState<Side>("all");
  const [demo, setDemo] = useState<string>(""); // "" = ทุกแมตช์ที่อัปโหลด
  const matches = useQuery(matchesQuery);

  // แมพที่ดูได้ = แมพที่มีทั้งแมตช์ของเราและชุดอ้างอิง (ไม่งั้นไม่มีอะไรให้เทียบ)
  const done = (matches.data ?? []).filter((m) => m.status === "done" && m.map_name);
  const mapsWith = (s: MatchSource) => new Set(done.filter((m) => m.source === s).map((m) => m.map_name!));
  const refMaps = mapsWith("reference");
  const upMaps = mapsWith("upload");
  const maps = [...refMaps].filter((m) => upMaps.has(m)).sort();
  const [map, setMap] = useState<string>("");
  const activeMap = map || maps[0] || "";
  const mine = done.filter((m) => m.source === "upload" && m.map_name === activeMap);

  const enabled = !!activeMap;
  const upload = useQuery({
    queryKey: ["analysis", activeMap, "upload", side, demo],
    queryFn: () => api.analysisDeaths(activeMap, "upload", side, demo || null),
    enabled,
    staleTime: 5 * 60_000,
  });
  const reference = useQuery({
    queryKey: ["analysis", activeMap, "reference", side],
    queryFn: () => api.analysisDeaths(activeMap, "reference", side),
    enabled: enabled && mode === "diff",
    staleTime: 5 * 60_000,
  });
  // โหมด "อ่านทางเราออกไหม" ดูได้ทีละแมตช์ — ไม่ได้เลือกไว้ก็ใช้แมตช์แรกของแมพนั้น
  const target = demo || mine[0]?.demo_file || "";
  const readQ = useQuery({
    queryKey: ["readability", target],
    queryFn: () => api.readability(target),
    enabled: mode === "read" && !!target,
    staleTime: 5 * 60_000,
  });

  if (matches.isLoading) return <p className="muted">กำลังโหลด…</p>;
  if (matches.error) return <p className="err">โหลดรายการแมตช์ไม่ได้: {(matches.error as Error).message}</p>;
  if (maps.length === 0) return <NothingToCompare done={done} />;

  const single = upload.data;
  const loading = mode === "read" ? readQ.isLoading : upload.isLoading || (mode === "diff" && reference.isLoading);
  const error = (mode === "read" ? readQ.error : (upload.error ?? reference.error)) as Error | null;
  const rows = mode === "diff" && upload.data && reference.data ? compare(upload.data, reference.data) : [];

  return (
    <div className="analysis" data-testid="analysis-page">
      <header className="an-head">
        <div>
          <h1>ทีมเราตายตรงไหนบ่อย</h1>
          <p className="muted">
            ดูจุดที่ผู้เล่นในแมตช์ของทีมตาย แล้วเทียบกับเดโมการแข่งของทีมอาชีพ 50 แมตช์บนแมพเดียวกัน
            ว่าตรงไหนเราเสียคนบ่อยกว่าเขา
          </p>
        </div>
      </header>

      <div className="an-controls">
        <div className="seg" role="group" aria-label="สิ่งที่ดู">
          <span className="seg-h">ดู</span>
          {MODES.map((m) => (
            <button key={m.key} type="button" className={`seg-btn${mode === m.key ? " on" : ""}`}
              aria-pressed={mode === m.key} title={m.hint} onClick={() => setMode(m.key)} data-testid={`mode-${m.key}`}>
              {m.label}
            </button>
          ))}
        </div>

        <div className="seg" role="group" aria-label="ฝั่งของคนที่ตาย">
          <span className="seg-h">ฝั่งของคนที่ตาย</span>
          {SIDES.map((s) => (
            <button key={s.key} type="button" className={`seg-btn${side === s.key ? ` ${s.key} on` : ""}`}
              aria-pressed={side === s.key} onClick={() => setSide(s.key)}>
              {s.label}
            </button>
          ))}
        </div>

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

      {error && <p className="err">โหลดข้อมูลไม่ได้: {error.message}</p>}
      {loading && <p className="muted">{mode === "read" ? "กำลังให้โมเดลอ่านทีละรอบ…" : "กำลังนับจุดตาย…"}</p>}

      {!loading && !error && mode === "read" && readQ.data && (
        <ReadabilityReport data={readQ.data} demo={target} />
      )}

      {!loading && !error && mode !== "read" && (
        <div className="an-grid">
          <section className="an-map-col">
            <div className="an-map">
              {mode === "diff" ? (
                <DeathMap radar={upload.data!.radar} cells={rows} paint={(r) => diffPaint(r.level)} />
              ) : (
                single && <DeathMap radar={single.radar} cells={single.cells} paint={freqPaint(single.cells, side)} />
              )}
            </div>
            {mode === "diff" ? <DiffKey /> : <FreqKey cells={single?.cells ?? []} side={side} />}
          </section>

          <aside className="an-side">
            {mode === "diff" ? (
              <DiffTable rows={rows} upload={upload.data!} reference={reference.data!} />
            ) : (
              <SingleSummary data={single!} />
            )}
          </aside>
        </div>
      )}
    </div>
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

const diffPaint = (lv: DiffLevel) =>
  lv === 0 ? null : { fill: DIFF_FILL[String(lv) as "-2" | "-1" | "1" | "2"], opacity: 0.78 };

function DiffKey() {
  return (
    <ul className="map-key" aria-label="คำอธิบายสี">
      <li>
        <span className="ks adv" style={{ background: DIFF_FILL["2"] }} />
        <span className="ks adv" style={{ background: DIFF_FILL["1"] }} />
        ทีมเราตายบ่อยกว่าทีมอาชีพ (ตั้งแต่ {DIFF_STEPS.near}× · ตั้งแต่ {DIFF_STEPS.far}×)
      </li>
      <li>
        <span className="ks adv" style={{ background: DIFF_FILL["-1"] }} />
        <span className="ks adv" style={{ background: DIFF_FILL["-2"] }} />
        ทีมเราตายน้อยกว่า
      </li>
      <li className="key-adv muted">
        ช่องที่ไม่ระบาย = ต่างกันไม่ถึง {DIFF_STEPS.near}× หรือเราตายในช่องนั้นไม่ถึง {DIFF_MIN_DEATHS} ครั้ง
        (น้อยเกินกว่าจะสรุปอะไรได้)
      </li>
    </ul>
  );
}

function DiffTable({ rows, upload, reference }: { rows: DiffRow[]; upload: DeathsOverlay; reference: DeathsOverlay }) {
  const worst = rows.filter((r) => r.level > 0).slice(0, 8);
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
            {worst.map((r) => (
              <tr key={`${r.cx},${r.cy}`}>
                <td><Place cell={r} /></td>
                <td className="num">{r.deaths}</td>
                <td className="num">{pct(r.share)}</td>
                <td className="num">{pct(r.shareRef)}</td>
                <td className="num"><b>{r.ratio === Infinity ? "—" : `${r.ratio.toFixed(1)}×`}</b></td>
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
// ดูชุดเดียว — ใช้ไล่เฉดความถี่ชุดเดียวกับหน้ารอบ
// ================================================================================================
const freqPaint = (cells: DeathCellCount[], side: Side) => {
  const breaks = freqBreaks(cells.map((c) => c.deaths));
  const ramp = DEATH_RAMP[side];
  return (c: DeathCellCount) => {
    const lv = freqLevel(c.deaths, breaks);
    return { fill: ramp[lv], opacity: FREQ_ALPHA + lv * 0.06 };
  };
};

const SIDE_NOTE: Record<Side, string> = {
  all: "รวมทั้งสองฝั่ง",
  ct: "เฉพาะตอนเป็น CT",
  t: "เฉพาะตอนเป็น T",
};

function FreqKey({ cells, side }: { cells: DeathCellCount[]; side: Side }) {
  const bands = freqBands(freqBreaks(cells.map((c) => c.deaths)));
  const ramp = DEATH_RAMP[side];
  return (
    <ul className="map-key" aria-label="คำอธิบายสี">
      <li className="key-adv">
        จำนวนครั้งที่ตายในช่องนั้น ({SIDE_NOTE[side]}) ยิ่งเข้มยิ่งตายบ่อย —
        {bands.map((b) => (
          <span key={b.level} className="key-band">
            <span className="ks adv" style={{ background: ramp[b.level], opacity: FREQ_ALPHA + b.level * 0.06 }} />
            {b.label}
          </span>
        ))}
        ครั้ง
      </li>
    </ul>
  );
}

function SingleSummary({ data }: { data: DeathsOverlay }) {
  const top = [...data.cells].sort((a, b) => b.deaths - a.deaths).slice(0, 8);
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
          {top.map((c) => (
            <tr key={`${c.cx},${c.cy}`}>
              <td><Place cell={c} /></td>
              <td className="num">{c.deaths}</td>
              <td className="num">{pct(c.share)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}

/**
 * ตำแหน่งบนแมพของช่องหนึ่งช่อง — ใช้ชื่อ callout ที่เดโมบันทึกไว้ (BombsiteA, Catwalk, …)
 * เลขช่องยังตามมาด้วยตัวเล็ก เพราะชื่อเดียวกันกินหลายช่อง ต้องแยกออกว่าหมายถึงช่องไหน
 */
function Place({ cell }: { cell: DeathCellCount }) {
  return (
    <span className="an-place">
      {cell.place ?? "ไม่มีชื่อเรียก"}
      <span className="muted num"> {cell.cx},{cell.cy}</span>
    </span>
  );
}

// ================================================================================================
// แผนที่: ภาพเรดาร์ + ช่องกริด (พิกเซลมาจาก backend เหมือนหน้ารอบ — ไม่มีสูตรพิกัดในหน้าเว็บ)
// ================================================================================================
interface MapProps<T extends DeathCellCount> {
  radar: DeathsOverlay["radar"];
  cells: T[];
  paint: (c: T) => { fill: string; opacity: number } | null;
}

function DeathMap<T extends DeathCellCount>({ radar, cells, paint }: MapProps<T>) {
  const s = radar.size;
  return (
    <svg viewBox={`0 0 ${s} ${s}`} className="radar" data-testid="analysis-radar">
      <image href={radar.image} x={0} y={0} width={s} height={s} />
      {cells.map((c) => {
        const p = paint(c);
        return (
          p && (
            <rect key={`${c.cx}-${c.cy}`} x={c.x} y={c.y} width={c.w} height={c.w} fill={p.fill} opacity={p.opacity}
              stroke={SCREEN} strokeWidth={0.5} data-testid="analysis-cell">
              <title>{`${c.place ?? "ไม่มีชื่อเรียก"} (ช่อง ${c.cx}, ${c.cy}) · ตาย ${c.deaths} ครั้ง`}</title>
            </rect>
          )
        );
      })}
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
      <Link className="btn-primary" to="/matches">
        ไปหน้าแมตช์
      </Link>
    </div>
  );
}

const matchLabel = (m: Match) => (m.team_a && m.team_b ? `${m.team_a} vs ${m.team_b}` : m.demo_file);
