import { useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { toPng } from "html-to-image";
import {
  api,
  type DeathsOverlay,
  type Match,
  type MatchEconomy,
  type PlayerBehavior,
  type ScoreRow,
  type TeamBuy,
} from "./api";
import { DownloadIcon } from "./icons/download-icon";
import { useT } from "./i18n";

type Props = {
  match?: Match;
  heatmap?: DeathsOverlay;
  behavior?: PlayerBehavior;
  scoreboard?: ScoreRow[];
  side: "all" | "ct" | "t";
  selectedRounds: number[] | null;
  selectedPlayers: string[] | null;
};

const BUY_LABEL: Record<TeamBuy, string> = {
  pistol: "Pistol", eco: "Eco", semi_eco: "Semi-eco", semi_buy: "Semi-buy", full: "Full buy",
};
const BUY_COLOR: Record<TeamBuy, string> = {
  pistol: "#94a3b8", eco: "#b8d8c0", semi_eco: "#79b98a", semi_buy: "#3e9362", full: "#176541",
};

function safeFile(value: string) {
  return value.normalize("NFC").replace(/[^\p{L}\p{N}._-]+/gu, "-").replace(/^-+|-+$/g, "") || "match";
}

function matchName(match: Match) {
  return match.team_a && match.team_b ? `${match.team_a} vs ${match.team_b}` : match.demo_file.replace(/\.dem$/i, "");
}

export function AnalysisReportExport(props: Props) {
  const { t } = useT();
  const reportRef = useRef<HTMLDivElement>(null);
  const [working, setWorking] = useState<"png" | "pdf" | null>(null);
  const [error, setError] = useState(false);
  const economy = useQuery({
    queryKey: ["analysis-report-economy", props.match?.demo_file],
    queryFn: () => api.economy(props.match!.demo_file),
    enabled: !!props.match,
    staleTime: 5 * 60_000,
  });
  const ready = !!props.match && !!props.heatmap && !!props.scoreboard && !economy.isLoading;

  async function renderNode(node: HTMLElement, pixelRatio: number) {
    await document.fonts?.ready;
    return toPng(node, {
      backgroundColor: "#0b0e14",
      cacheBust: true,
      pixelRatio,
      width: node.scrollWidth,
      height: node.scrollHeight,
    });
  }

  async function exportPng() {
    if (!reportRef.current || !props.match || !ready || working) return;
    setWorking("png");
    setError(false);
    try {
      const url = await renderNode(reportRef.current, 1.15);
      download(url, `${safeFile(matchName(props.match))}-full-analysis.png`);
    } catch (cause) {
      console.error("Full analysis PNG export failed", cause);
      setError(true);
    } finally {
      setWorking(null);
    }
  }

  async function exportPdf() {
    if (!reportRef.current || !props.match || !ready || working) return;
    setWorking("pdf");
    setError(false);
    try {
      const { jsPDF } = await import("jspdf");
      const pages = Array.from(reportRef.current.querySelectorAll<HTMLElement>(".match-report-page"));
      const pdf = new jsPDF({ orientation: "portrait", unit: "mm", format: "a4", compress: true });
      for (let index = 0; index < pages.length; index += 1) {
        if (index > 0) pdf.addPage();
        const image = await renderNode(pages[index], 1.35);
        pdf.addImage(image, "PNG", 0, 0, 210, 297, undefined, "FAST");
      }
      pdf.save(`${safeFile(matchName(props.match))}-full-analysis.pdf`);
    } catch (cause) {
      console.error("Full analysis PDF export failed", cause);
      setError(true);
    } finally {
      setWorking(null);
    }
  }

  return (
    <section className="analysis-export" aria-labelledby="analysis-export-title" data-testid="analysis-export">
      <div className="analysis-export-copy">
        <span className="analysis-export-icon"><DownloadIcon /></span>
        <div>
          <h2 id="analysis-export-title">{t("Export รายงานการเล่นฉบับเต็ม")}</h2>
          <p>{t("รวม Heatmap, Economy, Tactic, Player Behavior และสถิติผู้เล่นไว้ในไฟล์เดียว พร้อมใช้ประชุมทีม")}</p>
          {!props.match && <strong>{t("เลือกแมตช์หนึ่งรายการด้านบนเพื่อสร้างรายงาน")}</strong>}
          {props.match && economy.error && <strong className="err">{t("โหลดข้อมูล Economy ไม่สำเร็จ — รายงานส่วนอื่นยังพร้อมส่งออก")}</strong>}
        </div>
      </div>
      <div className="analysis-export-actions">
        <button type="button" className="analysis-export-primary" disabled={!ready || !!working} onClick={() => void exportPng()}>
          <DownloadIcon /> {working === "png" ? t("กำลังสร้าง PNG…") : t("Export Full Report PNG")}
        </button>
        <button type="button" className="analysis-export-pdf" disabled={!ready || !!working} onClick={() => void exportPdf()}>
          {working === "pdf" ? t("กำลังสร้าง PDF…") : t("ดาวน์โหลด PDF หลายหน้า")}
        </button>
        {error && <span className="err small" role="alert">{t("สร้างรายงานไม่สำเร็จ กรุณาลองอีกครั้ง")}</span>}
      </div>

      {props.match && props.heatmap && props.scoreboard && (
        <div className="match-report-host" aria-hidden="true">
          <div ref={reportRef} className="match-report-document">
            <OverviewPage {...props} match={props.match} heatmap={props.heatmap} scoreboard={props.scoreboard} economy={economy.data} />
            <HeatmapPage {...props} match={props.match} heatmap={props.heatmap} />
            <EconomyPage match={props.match} economy={economy.data} />
            <TacticsPage match={props.match} behavior={props.behavior} scoreboard={props.scoreboard} />
          </div>
        </div>
      )}
    </section>
  );
}

function download(url: string, filename: string) {
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
}

function ReportHeader({ match, section, page }: { match: Match; section: string; page: number }) {
  return <header className="mr-header">
    <div><b>CS2 SCOUTING</b><span>{matchName(match)}</span></div>
    <div><strong>{section}</strong><small>{match.map_name?.replace(/^de_/, "") ?? "—"} · {page}/4</small></div>
  </header>;
}

function OverviewPage({ match, heatmap, behavior, scoreboard, economy, side, selectedRounds, selectedPlayers }: Props & { match: Match; heatmap: DeathsOverlay; scoreboard: ScoreRow[]; economy?: MatchEconomy }) {
  const top = [...scoreboard].sort((a, b) => b.rating - a.rating);
  const avgAdr = scoreboard.length ? scoreboard.reduce((sum, p) => sum + p.adr, 0) / scoreboard.length : 0;
  const avgKast = scoreboard.length ? scoreboard.reduce((sum, p) => sum + p.kast, 0) / scoreboard.length : 0;
  const buyRounds = economy?.rounds.filter((round) => Object.values(round.teams).some((team) => team.buy_type === "full")).length ?? 0;
  return <article className="match-report-page mr-overview">
    <ReportHeader match={match} section="MATCH REPORT" page={1} />
    <section className="mr-hero">
      <span>รายงานวิเคราะห์รูปแบบการเล่น</span>
      <h1>{matchName(match)}</h1>
      <p>{match.map_name ?? "—"} · {match.rounds} รอบ · ข้อมูลจากเดโม {match.demo_file}</p>
    </section>
    <section className="mr-stat-band">
      <Stat value={String(match.rounds)} label="รอบทั้งหมด" />
      <Stat value={String(match.kills)} label="คิลในแมตช์" />
      <Stat value={String(heatmap.deaths)} label="จุดตายที่วิเคราะห์" />
      <Stat value={avgAdr.toFixed(1)} label="ADR เฉลี่ย" />
      <Stat value={`${avgKast.toFixed(0)}%`} label="KAST เฉลี่ย" />
    </section>
    <div className="mr-overview-grid">
      <section className="mr-panel">
        <h2>ขอบเขตรายงาน</h2>
        <dl className="mr-facts">
          <div><dt>ฝั่งที่เลือก</dt><dd>{side === "all" ? "CT + T" : side.toUpperCase()}</dd></div>
          <div><dt>รอบ</dt><dd>{selectedRounds?.length ? selectedRounds.join(", ") : "ทุกรอบ"}</dd></div>
          <div><dt>ผู้เล่น</dt><dd>{selectedPlayers?.length ? `${selectedPlayers.length} คน` : "ทุกคน"}</dd></div>
          <div><dt>Full-buy rounds</dt><dd>{buyRounds || "—"}</dd></div>
        </dl>
      </section>
      <section className="mr-panel">
        <h2>ภาพรวมทีม</h2>
        <p className="mr-lead">Heatmap แสดงพื้นที่เสียชีวิตจริง ส่วน Player Behavior เป็นรูปแบบจากโมเดลอ้างอิง ไม่ใช่คะแนนฝีมือหรือบทบาทถาวร</p>
        <div className="mr-role-counts">
          {(behavior?.players ?? []).filter((p) => p.available).slice(0, 6).map((p) => <span key={`${p.steamid}-${p.side}`}><b>{p.name}</b>{p.role ?? "ยังสรุปไม่ได้"} · {p.side.toUpperCase()}</span>)}
        </div>
      </section>
    </div>
    <section className="mr-panel mr-score-preview">
      <h2>ผู้เล่นเด่นตามข้อมูลในแมตช์</h2>
      <div className="mr-top-players">{top.slice(0, 5).map((p, index) => <div key={p.steam_id}><i>{index + 1}</i><b>{p.name}</b><span>{p.kills}K / {p.deaths}D</span><strong>{p.rating.toFixed(2)}</strong></div>)}</div>
    </section>
    <ReportFooter />
  </article>;
}

function Stat({ value, label }: { value: string; label: string }) {
  return <div><b>{value}</b><span>{label}</span></div>;
}

function HeatmapPage({ match, heatmap, side }: Props & { match: Match; heatmap: DeathsOverlay }) {
  const max = Math.max(1, ...heatmap.cells.map((cell) => cell.deaths));
  const top = [...heatmap.cells].sort((a, b) => b.deaths - a.deaths).slice(0, 8);
  const color = side === "ct" ? "79,140,255" : side === "t" ? "255,138,30" : "255,77,94";
  return <article className="match-report-page">
    <ReportHeader match={match} section="DEATH HEATMAP" page={2} />
    <div className="mr-section-intro"><h1>พื้นที่ที่ทีมเสียผู้เล่น</h1><p>วงเข้มหมายถึงมีการเสียชีวิตซ้ำในพื้นที่นั้นมากกว่า · กรองตามค่าที่เลือกก่อน Export</p></div>
    <div className="mr-heat-layout">
      <section className="mr-radar">
        <svg viewBox={`0 0 ${heatmap.radar.size} ${heatmap.radar.size}`}>
          <defs><filter id="mr-blur"><feGaussianBlur stdDeviation="8" /></filter></defs>
          <image href={heatmap.radar.image} width={heatmap.radar.size} height={heatmap.radar.size} />
          <g filter="url(#mr-blur)">{heatmap.cells.filter((cell) => cell.deaths >= 1).map((cell) => <circle key={`${cell.cx}-${cell.cy}`} cx={cell.x + cell.w / 2} cy={cell.y + cell.w / 2} r={cell.w * 1.7} fill={`rgb(${color})`} opacity={0.18 + 0.72 * (cell.deaths / max)} />)}</g>
        </svg>
        <div className="mr-heat-key"><i style={{ background: `linear-gradient(90deg, rgba(${color},.18), rgb(${color}))` }} />น้อย → มาก</div>
      </section>
      <section className="mr-panel mr-hotspots">
        <h2>พื้นที่เสียชีวิตสูงสุด</h2>
        <ol>{top.map((cell) => <li key={`${cell.cx}-${cell.cy}`}><span>{cell.place || `Grid ${cell.cx},${cell.cy}`}</span><b>{cell.deaths} ครั้ง</b><i><em style={{ width: `${Math.max(6, cell.deaths / max * 100)}%` }} /></i></li>)}</ol>
        {!top.length && <p>ไม่มีจุดตายในตัวกรองนี้</p>}
      </section>
    </div>
    <section className="mr-callout"><b>ใช้หน้านี้ตอบ:</b> พื้นที่ใดเสียผู้เล่นซ้ำ และควรย้อนดูรอบใดเพื่อหาสาเหตุจาก Replay</section>
    <ReportFooter />
  </article>;
}

function EconomyPage({ match, economy }: { match: Match; economy?: MatchEconomy }) {
  return <article className="match-report-page">
    <ReportHeader match={match} section="ECONOMY" page={3} />
    <div className="mr-section-intro"><h1>รูปแบบการซื้อและความพร้อมของทีม</h1><p>มูลค่าอุปกรณ์และประเภทการซื้ออ้างอิงจากข้อมูลตอนหมดเวลาซื้อของในแต่ละรอบ</p></div>
    {!economy?.rounds.length ? <section className="mr-panel"><h2>ไม่มีข้อมูล Economy</h2><p>เดโมรุ่นนี้ไม่มีข้อมูลมูลค่าอุปกรณ์รายรอบ</p></section> : <>
      <div className="mr-econ-teams">{economy.teams.map((team, index) => <span key={team}><i className={`team-${index}`} />{team}</span>)}</div>
      <section className="mr-panel">
        <h2>การซื้อรายรอบ</h2>
        <div className="mr-round-grid">{economy.rounds.map((round) => <div key={round.round_num}>
          <b>R{round.round_num}</b>
          {economy.teams.map((team) => { const row = round.teams[team]; return <span key={team} style={{ borderLeftColor: row?.buy_type ? BUY_COLOR[row.buy_type] : "#46516a" }}><small>{row?.side?.toUpperCase() ?? "—"}</small>{row?.buy_type ? BUY_LABEL[row.buy_type] : "—"}<em>{row?.equip == null ? "—" : `$${Math.round(row.equip / 100) / 10}K`}</em></span>; })}
          <strong>{round.winner_team ?? "—"}</strong>
        </div>)}</div>
      </section>
      <section className="mr-econ-summary">{economy.teams.map((team) => {
        const rounds = economy.rounds.map((r) => r.teams[team]).filter(Boolean);
        const full = rounds.filter((r) => r.buy_type === "full");
        const won = full.filter((r) => r.won).length;
        return <div className="mr-panel" key={team}><h2>{team}</h2><Stat value={`${full.length ? Math.round(won / full.length * 100) : 0}%`} label={`ชนะเมื่อ Full buy (${won}/${full.length})`} /><p>Eco / Semi-eco {rounds.filter((r) => r.buy_type === "eco" || r.buy_type === "semi_eco").length} รอบ</p></div>;
      })}</section>
    </>}
    <ReportFooter />
  </article>;
}

function TacticsPage({ match, behavior, scoreboard }: { match: Match; behavior?: PlayerBehavior; scoreboard: ScoreRow[] }) {
  return <article className="match-report-page">
    <ReportHeader match={match} section="TACTIC & PLAYER STATS" page={4} />
    <div className="mr-section-intro"><h1>รูปแบบการเล่นและสถิติผู้เล่น</h1><p>รูปแบบแยกตามฝั่งและได้จากกลุ่มพฤติกรรมในชุดอ้างอิง ไม่ใช่คะแนนหรือคำตัดสินผู้เล่น</p></div>
    <section className="mr-behavior-grid">
      {(behavior?.players ?? []).filter((p) => p.available).map((player) => <div className={`mr-behavior side-${player.side}`} key={`${player.steamid}-${player.side}`}>
        <header><div><b>{player.name}</b><span>{player.side.toUpperCase()} · {player.rounds} รอบ</span></div><strong>{player.role ?? "Hybrid / Unresolved"}</strong></header>
        <ul>{(player.signals ?? []).slice(0, 3).map((signal) => <li key={signal.feature}><span>{signalLabel(signal.feature)}</span><b>{signal.direction === "higher" ? "สูงกว่า" : "ต่ำกว่า"}กลุ่มอ้างอิง</b></li>)}</ul>
      </div>)}
      {!behavior?.available && <div className="mr-panel"><h2>Player Behavior ยังไม่พร้อม</h2><p>{behavior?.reason ?? "ข้อมูลไม่พอสำหรับสรุปรูปแบบ"}</p></div>}
    </section>
    <section className="mr-panel mr-score-table">
      <h2>Scoreboard</h2>
      <table><thead><tr><th>ผู้เล่น</th><th>ฝั่งเริ่ม</th><th>K</th><th>D</th><th>A</th><th>HS%</th><th>ADR</th><th>KAST</th><th>Rating</th></tr></thead><tbody>{[...scoreboard].sort((a, b) => b.rating - a.rating).map((p) => <tr key={p.steam_id}><td>{p.name}</td><td>{p.start_side?.toUpperCase() ?? "—"}</td><td>{p.kills}</td><td>{p.deaths}</td><td>{p.assists}</td><td>{p.hs_rate.toFixed(0)}%</td><td>{p.adr.toFixed(1)}</td><td>{p.kast.toFixed(0)}%</td><td><b>{p.rating.toFixed(2)}</b></td></tr>)}</tbody></table>
    </section>
    <section className="mr-callout"><b>แนวทางทบทวนทีม:</b> เทียบรูปแบบ CT/T กับ Heatmap แล้วเปิด Round Review ในรอบที่เกิดซ้ำ เพื่อดูตำแหน่ง Utility และจังหวะเสียผู้เล่นจริง</section>
    <ReportFooter />
  </article>;
}

function signalLabel(feature: string) {
  const labels: Record<string, string> = {
    assists_per_round: "การช่วยต่อรอบ", flash_assists_per_round: "Flash assist", opening_attempt_rate: "การเข้าจังหวะแรก",
    opening_kill_rate: "Opening kill", early_engagement_rate: "การปะทะช่วงต้น", trade_kills_per_round: "Trade kill",
    postplant_kills_per_round: "คิลหลังวางบอมบ์", site_engagement_rate: "การปะทะบริเวณไซต์", avg_kill_time: "เวลาคิลเฉลี่ย",
    place_diversity: "ความหลากหลายของพื้นที่", place_concentration: "ความถี่ในพื้นที่หลัก",
  };
  return labels[feature] ?? feature;
}

function ReportFooter() {
  return <footer className="mr-footer"><span>ข้อมูลจากเดโม · CS2 SCOUTING</span><span>รายงานนี้แสดงข้อเท็จจริงและรูปแบบ ไม่ใช่การตัดสินฝีมือ</span></footer>;
}
