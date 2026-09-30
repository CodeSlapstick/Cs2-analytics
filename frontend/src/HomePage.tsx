import "@fontsource/chakra-petch/600.css";
import "@fontsource/chakra-petch/700.css";
import "@fontsource/anuphan/400.css";
import "@fontsource/anuphan/500.css";
import "@fontsource/anuphan/600.css";
import { Link } from "react-router-dom";
import { LangToggle, useT } from "./i18n";
import radarLines from "./assets/brief-mirage-lines.png";

const COPY = {
  th: {
    navAbout: "รู้จักระบบ",
    navFlow: "วิธีใช้งาน",
    signIn: "เข้าสู่ระบบ",
    tryNow: "ลองดูระบบ",
    headline: "เห็นทั้งรอบ\nก่อนตัดสินหนึ่งจังหวะ",
    lead: "เปลี่ยนไฟล์เดโม CS2 ให้เป็นแผนที่เล่าเรื่องของแต่ละรอบ ดูว่าใครอยู่ตรงไหน การปะทะเกิดเมื่อไร และ utility ใดกำลังทำงานในวินาทีนั้น",
    note: "ข้อมูลจากเดโมของทีมคุณ · แสดงข้อเท็จจริง ไม่ตัดสินผู้เล่น",
    stageRound: "รอบ 18 · Mirage",
    stageTime: "00:31 / 00:48",
    stageEvent: "วางระเบิดแล้ว",
    stageKill: "Opening duel",
    stageUtility: "Smoke ทำงาน",
    whyTitle: "จากสกอร์บอร์ด\nสู่ภาพที่ทีมคุยกันได้",
    whyBody: "สกอร์บอกผลลัพธ์ แต่ไม่ได้บอกว่าพื้นที่ไหนเสียก่อน หรือเพื่อนอยู่ไกลเกิน trade หรือไม่ CS2 SCOUTING วางเหตุการณ์ทั้งหมดกลับลงบนแผนที่เดียว เพื่อให้โค้ชและผู้เล่นทบทวนรอบร่วมกันได้เร็วขึ้น",
    f1: "ย้อนดูตำแหน่งผู้เล่น",
    f1d: "เล่น timeline ทีละวินาที พร้อมจุดตาย เส้นยิง และ utility ที่มีผลในขณะนั้น",
    f2: "อ่านรูปแบบการปะทะ",
    f2d: "ดู heatmap ของทีม และเปรียบเทียบสัดส่วนตำแหน่งการตายกับชุดข้อมูลทีมอาชีพ",
    f3: "สรุปมากกว่าคิลและเดธ",
    f3d: "แยก opening, trade, clutch, ADR, KAST และเศรษฐกิจรายรอบจากเดโมเดียวกัน",
    flowTitle: "หนึ่งไฟล์เดโม\nกลายเป็นห้องรีวิวของทีม",
    step1: "อัปโหลด .dem",
    step1d: "วางไฟล์เดโมของทีม ระบบส่งไปแกะข้อมูลเบื้องหลัง",
    step2: "เลือกแมตช์และรอบ",
    step2d: "เปิดสกอร์บอร์ด ภาพรวมเศรษฐกิจ หรือเจาะทีละรอบ",
    step3: "คุยจากภาพเดียวกัน",
    step3d: "เลื่อนเวลา เลือกผู้เล่น และแชร์ URL ของมุมมองนั้นให้ทีม",
    finalTitle: "รอบต่อไป เริ่มจากเข้าใจรอบที่ผ่านมา",
    finalBody: "เปิดดูระบบในโหมดผู้เยี่ยมชมได้ทันที หรือล็อกอินด้วย Steam เพื่อผูกสถิติกับบัญชีของคุณ",
    finalCta: "เริ่มสำรวจ CS2 SCOUTING",
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
    stageEvent: "Bomb planted",
    stageKill: "Opening duel",
    stageUtility: "Smoke active",
    whyTitle: "From a scoreboard\nto a shared picture",
    whyBody: "A scoreboard records the result, not which space was lost first or whether a teammate could trade. CS2 SCOUTING puts the events back on one map so coaches and players can review a round together, faster.",
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
    finalCta: "Explore CS2 SCOUTING",
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

const players = [
  ["ct", 21, 68, "1"], ["ct", 28, 61, "2"], ["ct", 38, 72, "3"],
  ["t", 68, 30, "1"], ["t", 75, 38, "2"], ["t", 61, 43, "3"],
] as const;

export function HomePage() {
  const { lang } = useT();
  const c = COPY[lang];
  return (
    <div className="home-page">
      <header className="home-nav">
        <Link className="home-brand" to="/" aria-label="CS2 SCOUTING home"><Mark /><span>CS2 SCOUTING</span></Link>
        <nav aria-label="Home navigation">
          <a href="#about">{c.navAbout}</a>
          <a href="#workflow">{c.navFlow}</a>
        </nav>
        <div className="home-actions">
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

          <div className="home-stage" aria-label={c.stageRound}>
            <div className="stage-head"><b>{c.stageRound}</b><span className="stage-live"><i /> LIVE REVIEW</span></div>
            <div className="stage-body">
              <div className="stage-map">
                <img src={radarLines} alt="" draggable={false} />
                <svg className="stage-path" viewBox="0 0 100 100" aria-hidden="true">
                  <path d="M23 67 C36 58 48 49 66 32" /><path d="M31 63 C43 66 55 55 72 39" />
                </svg>
                {players.map(([side, x, y, n]) => <span key={`${side}-${n}`} className={`stage-player ${side}`} style={{ left: `${x}%`, top: `${y}%` }}>{n}</span>)}
                <span className="stage-smoke" style={{ left: "51%", top: "48%" }} />
                <span className="stage-bomb" style={{ left: "70%", top: "33%" }}>B</span>
              </div>
              <ol className="stage-timeline">
                <li><time>00:12</time><i className="ct" />{c.stageUtility}</li>
                <li><time>00:19</time><i className="t" />{c.stageKill}</li>
                <li className="active"><time>00:31</time><i className="bomb" />{c.stageEvent}</li>
                <li><time>00:36</time><i className="ct" />Trade kill</li>
              </ol>
            </div>
            <div className="stage-controls"><span className="stage-play" aria-hidden="true"><span /></span><div><i /></div><b>{c.stageTime}</b></div>
          </div>
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
      <footer className="home-footer"><Link className="home-brand" to="/"><Mark /><span>CS2 SCOUTING</span></Link><span>{c.project}</span></footer>
    </div>
  );
}
