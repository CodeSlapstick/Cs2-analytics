import "@fontsource/chakra-petch/600.css";
import "@fontsource/chakra-petch/700.css";
import "@fontsource/anuphan/400.css";
import "@fontsource/anuphan/500.css";
import "@fontsource/anuphan/600.css";
import { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { LangToggle, useT } from "./i18n";
import { ThemeToggle } from "./theme";

const COPY = {
  th: {
    navAbout: "ระบบช่วยอะไรได้บ้าง",
    navFlow: "เริ่มต้นใช้งาน",
    signIn: "เข้าสู่ระบบ",
    tryNow: "ลองใช้งาน",
    headline: "ดูให้ครบทั้งรอบ\nก่อนสรุปจากจังหวะเดียว",
    lead: "เปลี่ยนเดโม CS2 ให้เป็นภาพรวมทีละรอบ เห็นตำแหน่งผู้เล่น จังหวะปะทะ และ utility ที่กำลังทำงานในแต่ละวินาที",
    note: "อ้างอิงจากเดโมของทีมคุณ · ดูข้อเท็จจริงโดยไม่ตัดสินผู้เล่น",
    stageRound: "รอบ 18 · Mirage",
    stageTime: "00:31 / 00:48",
    stageSample: "รีเพลย์ตัวอย่าง",
    stagePlay: "เล่นรีเพลย์ตัวอย่าง",
    stagePause: "หยุดรีเพลย์ตัวอย่างชั่วคราว",
    stageTimeline: "ไทม์ไลน์รีเพลย์ตัวอย่าง",
    stageEvent: "วางระเบิด",
    stageKill: "Opening duel",
    stageUtility: "Smoke กำลังทำงาน",
    whyTitle: "สกอร์บอกผล\nแผนที่บอกว่าเกิดอะไรขึ้น",
    whyBody: "สกอร์บอร์ดบอกว่าใครชนะ แต่ไม่บอกว่าทีมเสียพื้นที่ตรงไหนก่อน หรือเพื่อนอยู่ใกล้พอจะ trade หรือไม่ CS2 UNTITLED จึงรวมทุกเหตุการณ์ไว้บนแผนที่เดียว ให้โค้ชและผู้เล่นเห็นภาพเดียวกันและทบทวนแต่ละรอบได้เร็วขึ้น",
    f1: "ย้อนดูทุกจังหวะบนแผนที่",
    f1d: "เลื่อน timeline เพื่อดูตำแหน่งผู้เล่น จุดตาย เส้นยิง และ utility ที่กำลังทำงานในขณะนั้น",
    f2: "เห็นพื้นที่ที่ปะทะบ่อย",
    f2d: "ดู heatmap ของทีม แล้วเปรียบเทียบตำแหน่งการตายกับข้อมูลจากทีมอาชีพ",
    f3: "เห็นมากกว่าจำนวนคิลและเดธ",
    f3d: "ดู opening, trade, clutch, ADR, KAST และภาพรวมเศรษฐกิจในแต่ละรอบได้จากเดโมเดียวกัน",
    flowTitle: "จากไฟล์เดโมหนึ่งไฟล์\nสู่การรีวิวร่วมกันทั้งทีม",
    step1: "อัปโหลด .dem",
    step1d: "เลือกไฟล์เดโมของทีม แล้วปล่อยให้ระบบประมวลผลอยู่เบื้องหลัง",
    step2: "เลือกแมตช์และรอบ",
    step2d: "ดูสกอร์บอร์ด ภาพรวมเศรษฐกิจ หรือเลือกเจาะรายละเอียดทีละรอบ",
    step3: "รีวิวรอบไปพร้อมกัน",
    step3d: "เลื่อนเวลา เลือกผู้เล่น แล้วแชร์ลิงก์มุมมองเดียวกันให้ทุกคนในทีม",
    finalTitle: "เข้าใจรอบที่ผ่านมา เพื่อเล่นรอบต่อไปให้ดีขึ้น",
    finalBody: "ลองดูระบบได้ทันทีในโหมดผู้เยี่ยมชม หรือล็อกอินด้วย Steam เพื่อเชื่อมสถิติเข้ากับบัญชีของคุณ",
    finalCta: "ลองใช้งาน CS2 UNTITLED",
    project: "โครงงาน SP-404 · UTCC STECH",
  },
  en: {
    navAbout: "About",
    navFlow: "How it works",
    signIn: "Sign in",
    tryNow: "Explore the system",
    headline: "See the whole round\nbefore judging one moment",
    lead: "Turn a CS2 demo into a round-by-round map story. See where every player was, when the fight happened, and which utility was active at that second.",
    note: "Your team's demo data · facts without grading players",
    stageRound: "Round 18 · Mirage",
    stageTime: "00:31 / 00:48",
    stageSample: "SAMPLE REPLAY",
    stagePlay: "Play sample replay",
    stagePause: "Pause sample replay",
    stageTimeline: "Sample replay timeline",
    stageEvent: "Bomb planted",
    stageKill: "Opening duel",
    stageUtility: "Smoke active",
    whyTitle: "From a scoreboard\nto a shared picture",
    whyBody: "A scoreboard records the result, not which space was lost first or whether a teammate could trade. CS2 UNTITLED puts the events back on one map so coaches and players can review a round together, faster.",
    f1: "Replay player positions",
    f1d: "Scrub second by second with deaths, shot lines, and utility active at that moment.",
    f2: "Read fight patterns",
    f2d: "View your team's death heatmap and compare positional shares with a professional reference set.",
    f3: "Go beyond kills and deaths",
    f3d: "Break down openings, trades, clutches, ADR, KAST, and round economy from the same demo.",
    flowTitle: "One demo becomes\nthe team's review room",
    step1: "Upload a .dem",
    step1d: "Drop in your team's demo while parsing runs in the background.",
    step2: "Pick a match and round",
    step2d: "Open the scoreboard, economy overview, or inspect one round.",
    step3: "Review the same picture",
    step3d: "Scrub time, select a player, and share the exact view by URL.",
    finalTitle: "The next round starts by understanding the last one",
    finalBody: "Explore immediately as a guest, or sign in with Steam to connect stats to your account.",
    finalCta: "Explore CS2 UNTITLED",
    project: "SP-404 Senior Project · UTCC STECH",
  },
} as const;

function Mark() {
  return (
    <svg width="30" height="30" viewBox="0 0 32 32" fill="none" aria-hidden="true">
      <path d="M3 10V3h7M22 3h7v7M29 22v7h-7M10 29H3v-7" stroke="currentColor" strokeWidth="2.5" />
      <circle cx="16" cy="16" r="6.5" stroke="#00E5FF" strokeWidth="2" />
      <path d="M16 6.5v5M16 20.5v5M6.5 16h5M20.5 16h5" stroke="#00E5FF" strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}

function Arrow() {
  return <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 12h13M13 6l6 6-6 6" /></svg>;
}

const PREVIEW_DURATION = 48;
const previewPlayers = [
  { side: "ct", slot: "1", name: "CT-1", from: [31, 72], to: [48, 57], angle: -38, labelX: -12, labelY: -22 },
  { side: "ct", slot: "2", name: "CT-2", from: [28, 78], to: [42, 70], angle: -22, labelX: -45, labelY: 2 },
  { side: "ct", slot: "3", name: "CT-3", from: [34, 79], to: [55, 69], angle: -18, labelX: -38, labelY: 22 },
  { side: "ct", slot: "4", name: "CT-4", from: [32, 83], to: [38, 52], angle: -65, labelX: 25, labelY: 8 },
  { side: "ct", slot: "5", name: "CT-5", from: [30, 86], to: [51, 79], angle: -18, labelX: -24, labelY: 29 },
  { side: "t", slot: "1", name: "T-1", from: [78, 30], to: [62, 47], angle: 142, labelX: -40, labelY: 4 },
  { side: "t", slot: "2", name: "T-2", from: [82, 25], to: [69, 51], angle: 116, labelX: -14, labelY: -26 },
  { side: "t", slot: "3", name: "T-3", from: [80, 33], to: [57, 54], angle: 138, labelX: -46, labelY: 22 },
  { side: "t", slot: "4", name: "T-4", from: [84, 26], to: [73, 62], angle: 107, labelX: -48, labelY: -5 },
  { side: "t", slot: "5", name: "T-5", from: [83, 36], to: [64, 68], angle: 121, labelX: -6, labelY: 35 },
] as const;

const previewEvents: ReadonlyArray<{
  time: number;
  side: "ct" | "t" | "bomb";
  key?: "stageUtility" | "stageKill" | "stageEvent";
  label?: string;
}> = [
  { time: 12, side: "ct", key: "stageUtility" },
  { time: 19, side: "t", key: "stageKill" },
  { time: 31, side: "bomb", key: "stageEvent" },
  { time: 36, side: "ct", label: "Trade kill" },
] as const;

function formatPreviewTime(value: number) {
  return `00:${Math.floor(value).toString().padStart(2, "0")}`;
}

function ReplayPreview({ c }: { c: (typeof COPY)[keyof typeof COPY] }) {
  const rootRef = useRef<HTMLDivElement>(null);
  const [time, setTime] = useState(8);
  const [playing, setPlaying] = useState(true);
  const [visible, setVisible] = useState(true);
  const progress = time / PREVIEW_DURATION;
  const activeEvent = previewEvents.reduce((active, event, index) => time >= event.time ? index : active, 0);
  const events = useMemo(() => previewEvents.map((event) => ({
    ...event,
    label: event.label ?? (event.key ? c[event.key] : ""),
  })), [c]);

  useEffect(() => {
    const node = rootRef.current;
    if (!node) return;
    const observer = new IntersectionObserver(([entry]) => setVisible(entry.isIntersecting), { threshold: 0.15 });
    observer.observe(node);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    if (!playing || !visible) return;
    let frame = 0;
    let previous = performance.now();
    const advance = (now: number) => {
      const elapsed = Math.min((now - previous) / 1000, 0.1);
      previous = now;
      setTime((current) => (current + elapsed) % PREVIEW_DURATION);
      frame = requestAnimationFrame(advance);
    };
    frame = requestAnimationFrame(advance);
    return () => cancelAnimationFrame(frame);
  }, [playing, visible]);

  return (
    <div className="home-stage" ref={rootRef} aria-label={c.stageRound}>
      <div className="stage-head"><b>{c.stageRound}</b><span className="stage-live"><i /> {c.stageSample}</span></div>
      <div className="stage-body">
        <div className="stage-map">
          <img src="/assets/maps/de_mirage.png" alt="Mirage radar" draggable={false} />
          {previewPlayers.map(({ side, slot, name, from, to, angle, labelX, labelY }) => {
            const x = from[0] + (to[0] - from[0]) * progress;
            const y = from[1] + (to[1] - from[1]) * progress;
            return (
              <span key={`${side}-${slot}`} className="stage-player-wrap" style={{ left: `${x}%`, top: `${y}%` }}>
                <span className={`stage-player ${side}`} style={{ rotate: `${angle}deg` }}><i />{slot}</span>
                <span className="stage-player-name" style={{ translate: `${labelX}px ${labelY}px` }}>{name}</span>
              </span>
            );
          })}
        </div>
        <ol className="stage-timeline">
          {events.map((event, index) => (
            <li key={event.time} className={index === activeEvent ? "active" : undefined}>
              <time>{formatPreviewTime(event.time)}</time><i className={event.side} />{event.label}
            </li>
          ))}
        </ol>
      </div>
      <div className="stage-controls">
        <button className={`stage-play${playing ? " playing" : ""}`} type="button" onClick={() => setPlaying((value) => !value)} aria-label={playing ? c.stagePause : c.stagePlay}><span /></button>
        <input aria-label={c.stageTimeline} type="range" min="0" max={PREVIEW_DURATION} step="0.1" value={time} onChange={(event) => setTime(Number(event.currentTarget.value))} />
        <b>{formatPreviewTime(time)} / 00:48</b>
      </div>
    </div>
  );
}

export function HomePage() {
  const { lang } = useT();
  const c = COPY[lang];
  return (
    <div className="home-page">
      <header className="home-nav">
        <Link className="home-brand" to="/" aria-label="CS2 UNTITLED home"><Mark /><span>CS2 UNTITLED</span></Link>
        <nav aria-label="Home navigation">
          <a href="#about">{c.navAbout}</a>
          <a href="#workflow">{c.navFlow}</a>
        </nav>
        <div className="home-actions">
          <ThemeToggle />
          <LangToggle className="home-lang" />
          <Link className="home-signin" to="/login">{c.signIn}</Link>
        </div>
      </header>

      <div className="home-content">
        <section className="home-hero">
          <div className="home-hero-copy">
            <h1>{c.headline.split("\n").map((line) => <span key={line}>{line}</span>)}</h1>
            <p>{c.lead}</p>
            <div className="home-hero-actions">
              <Link className="home-primary" to="/login?next=%2Fmatches">{c.tryNow}<Arrow /></Link>
              <span>{c.note}</span>
            </div>
          </div>

          <ReplayPreview c={c} />
        </section>

        <section className="home-proof" id="about">
          <div className="proof-copy"><h2>{c.whyTitle.split("\n").map((line) => <span key={line}>{line}</span>)}</h2><p>{c.whyBody}</p></div>
          <div className="proof-list">
            {[[c.f1, c.f1d], [c.f2, c.f2d], [c.f3, c.f3d]].map(([title, body], i) => (
              <article key={title}><span className={`proof-glyph glyph-${i + 1}`} aria-hidden="true" /><div><h3>{title}</h3><p>{body}</p></div></article>
            ))}
          </div>
        </section>

        <section className="home-workflow" id="workflow">
          <h2>{c.flowTitle.split("\n").map((line) => <span key={line}>{line}</span>)}</h2>
          <ol>
            {[[c.step1, c.step1d], [c.step2, c.step2d], [c.step3, c.step3d]].map(([title, body], i) => (
              <li key={title}><b>{i + 1}</b><div><h3>{title}</h3><p>{body}</p></div></li>
            ))}
          </ol>
        </section>

        <section className="home-close">
          <div><h2>{c.finalTitle}</h2><p>{c.finalBody}</p></div>
          <Link className="home-primary" to="/login?next=%2Fmatches">{c.finalCta}<Arrow /></Link>
        </section>
      </div>
      <footer className="home-footer"><Link className="home-brand" to="/"><Mark /><span>CS2 UNTITLED</span></Link><span>{c.project}</span></footer>
    </div>
  );
}
