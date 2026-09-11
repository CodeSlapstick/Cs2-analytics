import type { GridOverlay, ReviewDeath, RoundDetail } from "../../api";
import { clusterColor, fmtT, weaponLabel } from "../../review/format";

interface Props {
  radar: NonNullable<RoundDetail["radar"]>;
  deaths: ReviewDeath[];
  bomb: RoundDetail["round"]["bomb"];
  overlay: GridOverlay | undefined;
  showCells: boolean;
  showHotspots: boolean;
  highlight: string | null; // steamid ที่ถูกกดในรายชื่อ
  selected: number | null; // ลำดับการตายที่ถูกเลือก
  onSelect: (order: number | null) => void;
}

/**
 * แผนที่ของรอบ — วาดเป็น SVG ในพิกัด "พิกเซลของภาพเรดาร์" ที่ backend แปลงมาให้แล้ว (backend/geo.py)
 * frontend ไม่มีสูตรแปลงพิกัดของตัวเอง จุดบนจอจึงตรงกับช่องที่ grid_ml1 ใช้เสมอ
 * มีแค่จุดตอนตาย ไม่มีเส้นทางเดิน/replay (ข้อมูลที่ใช้มีพิกัดแค่ตอนตาย)
 */
export function MapView({ radar, deaths, bomb, overlay, showCells, showHotspots, highlight, selected, onSelect }: Props) {
  const s = radar.size;
  const involved = (d: ReviewDeath) =>
    !highlight || d.victim.steamid === highlight || d.attacker?.steamid === highlight;
  const focus = (d: ReviewDeath) => (selected === null ? involved(d) : selected === d.order);

  return (
    <svg viewBox={`0 0 ${s} ${s}`} className="radar" data-testid="radar-svg" onClick={() => onSelect(null)}>
      <image href={radar.image} x={0} y={0} width={s} height={s} />

      {showCells &&
        overlay?.cells?.map((c) => (
          <rect
            key={`${c.cx}-${c.cy}`}
            x={c.x}
            y={c.y}
            width={c.w}
            height={c.w}
            fill={clusterColor(c.cluster_id)}
            opacity={0.42}
            data-testid="overlay-cell"
          >
            <title>{`ช่อง (${c.cx}, ${c.cy}) · type ${c.cluster_id}`}</title>
          </rect>
        ))}

      {showHotspots &&
        overlay?.hotspots?.map((h) => (
          <g key={h.id} data-testid="overlay-hotspot">
            <circle cx={h.px} cy={h.py} r={h.r} fill="none" stroke="#ffffff" strokeWidth={3} strokeDasharray="10 7" opacity={0.85} />
            <text x={h.px} y={h.py - h.r - 8} textAnchor="middle" className="hs-label">
              #{h.id}
            </text>
          </g>
        ))}

      {bomb?.px && (
        <g transform={`translate(${bomb.px[0]}, ${bomb.px[1]})`} data-testid="bomb-icon">
          <rect x={-15} y={-15} width={30} height={30} rx={6} fill="#dc2626" stroke="#fff" strokeWidth={3} />
          <text textAnchor="middle" dy={6} className="bomb-label">
            C4
          </text>
          <title>{`วางบอมบ์${bomb.site ? ` (${bomb.site})` : ""}`}</title>
        </g>
      )}

      {/* เส้นทิศทางการยิง: จากคนยิงไปคนตาย */}
      {deaths.map(
        (d) =>
          d.attacker_px &&
          d.victim_px && (
            <line
              key={`l${d.order}`}
              x1={d.attacker_px[0]}
              y1={d.attacker_px[1]}
              x2={d.victim_px[0]}
              y2={d.victim_px[1]}
              stroke={d.attacker?.color ?? "#fff"}
              strokeWidth={3}
              opacity={focus(d) ? 0.9 : 0.1}
            />
          ),
      )}
      {deaths.map(
        (d) =>
          d.attacker_px && (
            <circle
              key={`a${d.order}`}
              cx={d.attacker_px[0]}
              cy={d.attacker_px[1]}
              r={7}
              fill={d.attacker?.color ?? "#fff"}
              stroke="#0b1220"
              strokeWidth={2}
              opacity={focus(d) ? 1 : 0.15}
            />
          ),
      )}

      {/* จุดตาย: สีตามคนตาย ขนาดใหญ่ มีเลขลำดับ */}
      {deaths.map(
        (d) =>
          d.victim_px && (
            <g
              key={`v${d.order}`}
              transform={`translate(${d.victim_px[0]}, ${d.victim_px[1]})`}
              className="death-dot"
              opacity={focus(d) ? 1 : 0.22}
              onClick={(e) => {
                e.stopPropagation();
                onSelect(selected === d.order ? null : d.order);
              }}
              data-testid="death-dot"
            >
              <circle r={selected === d.order ? 25 : 20} fill={d.victim.color} stroke={selected === d.order ? "#fff" : "#0b1220"} strokeWidth={4} />
              <text textAnchor="middle" dy={7} className="death-num">
                {d.order}
              </text>
              <title>{`${d.order}. ${fmtT(d.t_round)} ${d.victim.name} ตาย · ${weaponLabel(d.weapon)}${d.attacker ? ` · โดย ${d.attacker.name}` : ""}`}</title>
            </g>
          ),
      )}
    </svg>
  );
}
