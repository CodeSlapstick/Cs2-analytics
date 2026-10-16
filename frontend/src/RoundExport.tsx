import { useRef, useState } from "react";
import { toPng } from "html-to-image";
import type { RoundDetail } from "./api";
import { DownloadIcon } from "./icons/download-icon";
import { useT } from "./i18n";
import { endReasonLabel, fmtT, NADE_COLOR, sideLabel, weaponLabel } from "./utils";

export function RoundExportButton({ data }: { data: RoundDetail }) {
  const { t } = useT();
  const reportRef = useRef<HTMLDivElement>(null);
  const [exporting, setExporting] = useState(false);
  const [error, setError] = useState(false);

  async function exportReport() {
    if (!reportRef.current || exporting) return;
    setExporting(true);
    setError(false);
    try {
      await document.fonts?.ready;
      const dataUrl = await toPng(reportRef.current, {
        backgroundColor: "#0b0e14",
        cacheBust: true,
        pixelRatio: 1.5,
        width: 1200,
      });
      const base = data.match.demo_file.replace(/\.dem$/i, "").replace(/[^a-zA-Z0-9._-]+/g, "-");
      const link = document.createElement("a");
      link.href = dataUrl;
      link.download = `${base}-round-${data.round.num}-report.png`;
      link.click();
    } catch {
      setError(true);
    } finally {
      setExporting(false);
    }
  }

  return (
    <>
      <span className="round-export-control">
        <button type="button" className="link-btn round-export-trigger" onClick={() => void exportReport()} disabled={exporting}>
          <DownloadIcon /> {exporting ? t("กำลังสร้าง PNG…") : t("Export สรุปรอบ PNG")}
        </button>
        {error && <span className="err small" role="alert">{t("สร้างไฟล์ PNG ไม่สำเร็จ ลองอีกครั้ง")}</span>}
      </span>
      <div className="round-report-host" aria-hidden="true">
        <div ref={reportRef}><RoundReport data={data} /></div>
      </div>
    </>
  );
}

export function RoundReport({ data }: { data: RoundDetail }) {
  const { t } = useT();
  const matchName = data.match.team_a && data.match.team_b
    ? `${data.match.team_a} vs ${data.match.team_b}`
    : data.match.demo_file;
  const winner = data.round.winner_side ? t("{side} ชนะ", { side: sideLabel(data.round.winner_side) }) : t("ไม่ทราบผล");
  const first = data.summary.first_death;
  const duration = data.round.duration ?? data.round.latest_event_t;

  return (
    <article className="round-report" data-testid="round-report">
      <header className="round-report-head">
        <span className="round-report-mark" aria-hidden="true"><i /><b /></span>
        <div>
          <strong>CS2 SCOUTING</strong>
          <h1>{matchName}</h1>
          <p>{data.match.map_name.replace(/^de_/, "")} · {t("รอบ {n}", { n: data.round.num })} · {endReasonLabel(data.round.end_reason)}</p>
        </div>
        <div className={`round-report-result side-${data.round.winner_side ?? "none"}`}>
          <span>{t("ผลรอบ")}</span><b>{winner}</b>
        </div>
      </header>

      <section className="round-report-stats" aria-label={t("ข้อมูลสำคัญของรอบ")}>
        <p><span>{t("ระยะเวลารอบ")}</span><b>{duration != null ? fmtT(duration) : "—"}</b></p>
        <p><span>{t("ผู้เล่นที่ตาย")}</span><b>{data.deaths.length}</b></p>
        <p><span>Utility</span><b>{data.grenades.length}</b></p>
        <p><span>{t("วางบอมบ์")}</span><b>{data.round.bomb_planted_t != null ? fmtT(data.round.bomb_planted_t) : "—"}</b></p>
        <p><span>{t("การดวล")}</span><b>{data.summary.duel_deaths}</b></p>
      </section>

      <div className="round-report-main">
        <section className="round-report-map" aria-label={t("แผนที่สรุปรอบ")}>
          <h2>{t("ภาพรวมบนแผนที่")}</h2>
          {data.radar ? (
            <svg viewBox={`0 0 ${data.radar.size} ${data.radar.size}`}>
              <image href={data.radar.image} width={data.radar.size} height={data.radar.size} />
              {data.grenades.map((g, i) => g.land_px && (
                <circle key={`nade-${i}`} cx={g.land_px[0]} cy={g.land_px[1]} r={9}
                  fill={NADE_COLOR[g.type] ?? "#fff"} stroke="#0b0e14" strokeWidth={3} />
              ))}
              {data.round.bomb?.px && <g className="round-report-bomb" transform={`translate(${data.round.bomb.px[0]} ${data.round.bomb.px[1]})`}>
                <circle r="17" /><path d="M-7 0h14M0-7v14" />
              </g>}
              {data.deaths.map((death) => death.victim_px && (
                <g key={death.order} className={`round-report-death side-${death.victim.side ?? "none"}`}
                  transform={`translate(${death.victim_px[0]} ${death.victim_px[1]})`}>
                  <circle r="17" /><path d="M-7-7L7 7M7-7L-7 7" /><text y="-24" textAnchor="middle">{death.order}</text>
                </g>
              ))}
            </svg>
          ) : <div className="round-report-map-empty">{t("ไม่มีภาพเรดาร์สำหรับแมพนี้")}</div>}
          <div className="round-report-legend">
            <span><i className="ct" />CT</span><span><i className="t" />T</span><span><i className="bomb" />C4</span>
            <span>{t("วงสีเล็ก = จุดตก Utility · ตัวเลข = ลำดับการตาย")}</span>
          </div>
        </section>

        <aside className="round-report-side">
          <section>
            <h2>{t("ประเด็นสำคัญ")}</h2>
            <ul>
              <li>{first
                ? t("คนแรกที่ตาย: {name} ({side}) เวลา {time} ที่ {place}", {
                    name: first.name, side: sideLabel(first.side), time: fmtT(first.t_round), place: first.place ?? t("ไม่ทราบตำแหน่ง"),
                  })
                : t("ไม่มีข้อมูลการตายในรอบนี้")}</li>
              <li>{t("การตายที่ทีมเสียเปรียบ: CT {ct} · T {tt}", {
                ct: data.summary.disadvantaged_deaths.ct, tt: data.summary.disadvantaged_deaths.t,
              })}</li>
              <li>{data.round.bomb_planted_t != null
                ? t("วางบอมบ์เวลา {time} ที่ไซต์ {site}", { time: fmtT(data.round.bomb_planted_t), site: data.round.bomb?.site ?? "—" })
                : t("รอบนี้ไม่มีการวางบอมบ์")}</li>
            </ul>
          </section>
          <section>
            <h2>{t("รายชื่อผู้เล่น")}</h2>
            {data.teams.map((team) => (
              <div className="round-report-team" key={`${team.clan}-${team.side_this_round}`}>
                <h3><span className={`side-dot ${team.side_this_round}`} />{team.clan || sideLabel(team.side_this_round)}</h3>
                {team.players.map((player) => <p key={player.steamid}>
                  <b>{player.slot ?? "–"}</b><span>{player.name}</span><small>{player.kills}K · {player.survived ? t("รอด") : t("เสียชีวิต")}</small>
                </p>)}
              </div>
            ))}
          </section>
        </aside>
      </div>

      <section className="round-report-timeline">
        <h2>{t("ลำดับการตาย")}</h2>
        {data.deaths.length ? <table><thead><tr>
          <th>#</th><th>{t("เวลา")}</th><th>{t("ผู้เสียชีวิต")}</th><th>{t("ผู้สังหาร")}</th><th>{t("อาวุธ")}</th><th>{t("ตำแหน่ง")}</th>
        </tr></thead><tbody>{data.deaths.map((death) => <tr key={death.order}>
          <td>{death.order}</td><td>{fmtT(death.t_round)}</td><td>{death.victim.name} · {sideLabel(death.victim.side)}</td>
          <td>{death.attacker?.name ?? "—"}</td><td>{weaponLabel(death.weapon)}</td><td>{death.place ?? "—"}</td>
        </tr>)}</tbody></table> : <p>{t("ไม่มีข้อมูลการตายในรอบนี้")}</p>}
      </section>

      <footer><span>{data.match.demo_file}</span><span>{t("ข้อมูลจากเดโม · สร้างโดย CS2 SCOUTING")}</span></footer>
    </article>
  );
}
