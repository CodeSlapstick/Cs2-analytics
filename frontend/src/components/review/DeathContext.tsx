import type { ReviewDeath, RoundDetail } from "../../api";
import { clusterColor, fmtT, pct, sideLabel } from "../../review/format";

interface Props {
  deaths: ReviewDeath[];
  grid: RoundDetail["grid"];
  highlight: string | null;
  selected: number | null;
  onSelect: (order: number | null) => void;
}

/**
 * บริบทของการตายแต่ละครั้ง จากผล research/grid_ml1.py
 * ตัวเลขทุกตัวมาจากทั้งดาต้าเซ็ต (ทุกแมตช์รวมกัน) ไม่ใช่จากรอบหรือแมตช์นี้
 * ct_win = สัดส่วนที่ฝั่ง CT เป็นฝ่ายชนะการดวลในพื้นที่นั้น
 */
export function DeathContext({ deaths, grid, highlight, selected, onSelect }: Props) {
  return (
    <section className="ctx" data-testid="death-context">
      <p className="eyebrow">บริบทของแต่ละการตาย</p>
      {grid ? (
        <p className="ctx-source">
          ตัวเลขในส่วนนี้มาจาก <b>{grid.source.label}</b> ไม่ใช่สถิติของแมตช์นี้ · "CT ชนะดวล" คือสัดส่วนที่ CT
          เป็นฝ่ายชนะการดวลในพื้นที่นั้น
        </p>
      ) : (
        <p className="muted">ยังไม่มีผล grid_ml1 ของแมพนี้ — แสดงบริบทไม่ได้</p>
      )}
      <ul className="ctx-list">
        {deaths.map((d) => {
          const dim = highlight && d.victim.steamid !== highlight && d.attacker?.steamid !== highlight;
          return (
            <li
              key={d.order}
              className={`${selected === d.order ? "sel" : ""} ${dim ? "dim" : ""}`}
              onClick={() => onSelect(selected === d.order ? null : d.order)}
              data-testid="context-item"
            >
              <div className="ctx-head">
                <span className="tl-num" style={{ background: d.victim.color }}>
                  {d.order}
                </span>
                <b>{d.victim.name}</b> <span className="muted">({sideLabel(d.victim.side)}) · {fmtT(d.t_round)}</span>
                {d.disadvantaged && (
                  <span className="tag-warn">ช่องที่ฝั่งตรงข้ามชนะดวล {pct(d.enemy_win)}</span>
                )}
              </div>
              <ContextText d={d} grid={grid} />
            </li>
          );
        })}
      </ul>
    </section>
  );
}

function ContextText({ d, grid }: { d: ReviewDeath; grid: RoundDetail["grid"] }) {
  if (d.reason === "no_model" || !grid) return <p className="muted small">ยังไม่มีผล grid_ml1 ของแมพนี้</p>;
  if (d.reason === "no_position") return <p className="muted small">ไม่มีพิกัดของการตายครั้งนี้</p>;
  if (d.reason === "insufficient" || !d.cell)
    return (
      <p className="muted small">
        พื้นที่นี้มีข้อมูลไม่พอสรุป — ในดาต้าเซ็ตมีการดวลในช่องนี้น้อยกว่า {grid.min_kills} ครั้ง จึงไม่แสดงตัวเลข
      </p>
    );
  const c = d.cell;
  return (
    <div className="small">
      {!d.is_duel && (
        <p className="muted">ครั้งนี้ไม่ใช่การดวล (ตายจาก C4 / ตกที่สูง / เพื่อนร่วมทีม) ตัวเลขด้านล่างเป็นของการดวลในพื้นที่นี้</p>
      )}
      <p>
        {d.victim.name} ตายในช่องประเภท{" "}
        <span className="ctype" style={{ borderColor: clusterColor(c.cluster_id) }}>
          type {c.cluster_id}: {c.cluster_name}
        </span>{" "}
        ซึ่งทั้งดาต้าเซ็ต {grid.source.matches} แมตช์ CT ชนะดวลในกลุ่มนี้ <b>{pct(c.ct_win)}</b> (เฉลี่ยทั้งแมพ{" "}
        {pct(grid.ct_win_overall)})
      </p>
      {d.hotspot ? (
        <p>
          อยู่ใน hotspot #{d.hotspot.id} ({d.hotspot.place}) คิดเป็น {pct(d.hotspot.share)} ของการดวลทั้งหมด
        </p>
      ) : (
        <p className="muted">ไม่อยู่ใน hotspot ใดใน {grid.source.matches} แมตช์</p>
      )}
    </div>
  );
}

/** สรุปรอบ: ใครตายคนแรก / ฝั่งที่เสียคนแรกแพ้ไหม / ตายในช่องที่ฝั่งตรงข้ามชนะดวลกี่คน */
export function RoundSummary({ summary, winner, grid }: { summary: RoundDetail["summary"]; winner: RoundDetail["round"]["winner_side"]; grid: RoundDetail["grid"] }) {
  const f = summary.first_death;
  return (
    <section className="summary" data-testid="round-summary">
      <p className="eyebrow">สรุปรอบ</p>
      {f ? (
        <p>
          ตายคนแรก: <b>{f.name}</b> ({sideLabel(f.side)}) ที่ {f.place ?? "—"} วินาทีที่ {fmtT(f.t_round)}
          {f.by ? ` โดย ${f.by}` : ""}
        </p>
      ) : (
        <p className="muted">รอบนี้ไม่มีใครตาย</p>
      )}
      {summary.first_death_side_lost !== null && f && (
        <p>
          ฝั่ง {sideLabel(f.side)} เสียคนแรก และ{summary.first_death_side_lost ? "แพ้" : "ชนะ"}รอบนี้ (ผู้ชนะ {sideLabel(winner)})
        </p>
      )}
      {grid ? (
        <p>
          ตายในช่องที่ฝั่งตรงข้ามชนะดวลเกินครึ่ง (ตามดาต้าเซ็ต {grid.source.matches} แมตช์): CT{" "}
          <b>{summary.disadvantaged_deaths.ct}</b> คน · T <b>{summary.disadvantaged_deaths.t}</b> คน
          <span className="muted"> · มีบริบท {summary.deaths_with_context} จาก {summary.duel_deaths} การดวล</span>
        </p>
      ) : null}
    </section>
  );
}
