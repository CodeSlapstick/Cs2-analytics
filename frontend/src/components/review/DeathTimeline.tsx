import type { ReviewDeath } from "../../api";
import { fmtT, sideLabel, weaponLabel } from "../../review/format";

interface Props {
  deaths: ReviewDeath[];
  highlight: string | null;
  selected: number | null;
  onSelect: (order: number | null) => void;
  bombPlantedT: number | null;
}

const involved = (d: ReviewDeath, h: string | null) => !h || d.victim.steamid === h || d.attacker?.steamid === h;

function Who({ p }: { p: ReviewDeath["victim"] }) {
  return (
    <span className="who">
      <span className="pdot" style={{ background: p.color }} />
      {p.name} <span className="muted">({sideLabel(p.side)})</span>
    </span>
  );
}

/** ไล่ตามเวลา: 0:23  Alice (T) ฆ่า Bob (CT) · AK-47 · HS · ระยะ 640u · A Site */
export function DeathTimeline({ deaths, highlight, selected, onSelect, bombPlantedT }: Props) {
  type Item = { t: number; kind: "death"; d: ReviewDeath } | { t: number; kind: "bomb" };
  const items: Item[] = deaths.map((d) => ({ t: d.t_round ?? 0, kind: "death" as const, d }));
  if (bombPlantedT != null) items.push({ t: bombPlantedT, kind: "bomb" });
  items.sort((a, b) => a.t - b.t);

  return (
    <ol className="timeline-list" data-testid="death-timeline">
      {items.map((it) =>
        it.kind === "bomb" ? (
          <li key="bomb" className="tl-bomb">
            <span className="tl-t">{fmtT(it.t)}</span> วางบอมบ์
          </li>
        ) : (
          <li
            key={it.d.order}
            className={`${selected === it.d.order ? "sel" : ""} ${involved(it.d, highlight) ? "" : "dim"}`}
            onClick={() => onSelect(selected === it.d.order ? null : it.d.order)}
          >
            <span className="tl-num" style={{ background: it.d.victim.color }}>
              {it.d.order}
            </span>
            <span className="tl-t">{fmtT(it.d.t_round)}</span>
            <span className="tl-text">
              {it.d.attacker && it.d.is_duel ? (
                <>
                  <Who p={it.d.attacker} /> ฆ่า <Who p={it.d.victim} />
                </>
              ) : it.d.team_kill && it.d.attacker ? (
                <>
                  <Who p={it.d.attacker} /> ยิงเพื่อนร่วมทีม <Who p={it.d.victim} />
                </>
              ) : (
                <>
                  <Who p={it.d.victim} /> ตาย
                </>
              )}
              <span className="tl-meta">
                {" · "}
                {weaponLabel(it.d.weapon)}
                {it.d.headshot && " · HS"}
                {it.d.distance != null && ` · ระยะ ${it.d.distance}u`}
                {it.d.place && ` · ${it.d.place}`}
                {it.d.attacker_blind && " · คนยิงโดนแฟลช"}
                {it.d.thru_smoke && " · ยิงผ่านควัน"}
                {it.d.penetrated > 0 && " · ทะลุกำแพง"}
                {it.d.noscope && " · noscope"}
                {it.d.assister && ` · ช่วย: ${it.d.assister}`}
              </span>
            </span>
          </li>
        ),
      )}
      {deaths.length === 0 && <li className="muted">ไม่มีใครตายในรอบนี้</li>}
    </ol>
  );
}
