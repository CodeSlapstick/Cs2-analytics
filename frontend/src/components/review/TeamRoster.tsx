import type { ReviewTeam } from "../../api";
import { fmtT, sideLabel, weaponLabel } from "../../review/format";

interface Props {
  teams: ReviewTeam[];
  highlight: string | null;
  onHighlight: (steamid: string | null) => void;
}

/** สองกล่องแยกตามทีม (ชื่อทีมคงที่ทั้งแมตช์) — หัวกล่องบอกว่ารอบนี้ทีมนั้นเล่นฝั่งไหน */
export function TeamRoster({ teams, highlight, onHighlight }: Props) {
  return (
    <div className="roster" data-testid="team-roster">
      {teams.map((t) => (
        <div className="team-box" key={t.clan}>
          <div className="team-head">
            <b>{t.clan}</b>
            <span className={`badge b-${t.side_this_round}`}>{sideLabel(t.side_this_round)}</span>
            <span className="muted small">รอบนี้</span>
          </div>
          <ul>
            {t.players.map((p) => (
              <li key={p.steamid} className={highlight === p.steamid ? "on" : highlight ? "dim" : ""}>
                <button
                  type="button"
                  className="pname"
                  onClick={() => onHighlight(highlight === p.steamid ? null : p.steamid)}
                  title="กดเพื่อไฮไลต์เฉพาะเหตุการณ์ของคนนี้"
                >
                  <span className="pdot" style={{ background: p.color }} />
                  {p.name}
                  {p.kills > 0 && <span className="kills">{p.kills} คิล</span>}
                </button>
                <div className="pstat">
                  {p.survived ? (
                    <span className="alive">รอดถึงจบรอบ</span>
                  ) : (
                    <>
                      ตาย {fmtT(p.died_at_t)} · {weaponLabel(p.weapon)}
                      {p.killed_by ? ` · โดย ${p.killed_by}` : ""}
                      {p.death_order ? <span className="muted"> (#{p.death_order})</span> : null}
                    </>
                  )}
                </div>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </div>
  );
}
