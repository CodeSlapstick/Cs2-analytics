import { useEffect, useState } from "react";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api } from "../api";
import { DeathContext, RoundSummary } from "../components/review/DeathContext";
import { DeathTimeline } from "../components/review/DeathTimeline";
import { MapView } from "../components/review/MapView";
import { TeamRoster } from "../components/review/TeamRoster";
import { clusterColor, endReasonLabel, fmtT, pct, sideLabel } from "../review/format";

/** /matches/:demo/rounds/:n — ไล่ดูทีละรอบว่าใครตายที่ไหนเมื่อไหร่ และตายในพื้นที่แบบไหนตามที่ grid_ml1 จัดกลุ่มไว้ */
export function RoundReviewPage() {
  const { demo = "", n = "1" } = useParams();
  const roundNum = Number(n);
  const navigate = useNavigate();
  const [highlight, setHighlight] = useState<string | null>(null);
  const [selected, setSelected] = useState<number | null>(null);
  const [showCells, setShowCells] = useState(false);
  const [showHotspots, setShowHotspots] = useState(false);

  const list = useQuery({ queryKey: ["review-rounds", demo], queryFn: () => api.reviewRounds(demo), enabled: !!demo });
  const q = useQuery({
    queryKey: ["review-round", demo, roundNum],
    queryFn: () => api.reviewRound(demo, roundNum),
    enabled: !!demo && Number.isFinite(roundNum),
    placeholderData: keepPreviousData,
  });
  const mapName = q.data?.radar?.map;
  const grid = useQuery({
    queryKey: ["review-grid", mapName],
    queryFn: () => api.reviewGrid(mapName!),
    enabled: !!mapName,
    staleTime: Infinity, // ผล grid_ml1 ไม่เปลี่ยนระหว่างใช้งาน
  });

  useEffect(() => setSelected(null), [roundNum]); // เปลี่ยนรอบ = ล้างการเลือกจุดตาย (คงการไฮไลต์คนไว้)

  const rounds = list.data ?? [];
  const idx = rounds.findIndex((r) => r.round_num === roundNum);
  const go = (to: number) => navigate(`/matches/${encodeURIComponent(demo)}/rounds/${to}`);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement) return;
      if (e.key === "ArrowLeft" && idx > 0) go(rounds[idx - 1].round_num);
      if (e.key === "ArrowRight" && idx >= 0 && idx < rounds.length - 1) go(rounds[idx + 1].round_num);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  if (q.isLoading) return <p className="muted">กำลังโหลด…</p>;
  if (q.error) return <p className="err">โหลดรอบนี้ไม่ได้: {(q.error as Error).message}</p>;
  if (!q.data) return null;

  const d = q.data;
  const overlay = grid.data?.available ? grid.data : undefined;
  const title = d.match.team_a && d.match.team_b ? `${d.match.team_a} vs ${d.match.team_b}` : d.match.demo_file;

  return (
    <div className="review">
      <p className="eyebrow">
        <Link to="/">Match Library</Link> · <Link to={`/matches/${d.match.id}`}>{title}</Link> · {d.match.map_name}
      </p>
      <div className="review-head">
        <h1>
          รอบ {d.round.num}
          {d.round.winner_side && (
            <span className={`badge b-${d.round.winner_side} big`}>{sideLabel(d.round.winner_side)} ชนะ</span>
          )}
        </h1>
        <span className="muted">
          {endReasonLabel(d.round.end_reason)}
          {d.round.bomb_planted_t != null && ` · วางบอมบ์ ${fmtT(d.round.bomb_planted_t)}`} · ตาย {d.deaths.length} คน
        </span>
      </div>

      <nav className="round-strip" data-testid="round-strip">
        <button type="button" disabled={idx <= 0} onClick={() => go(rounds[idx - 1].round_num)} title="รอบก่อน (←)">
          ‹
        </button>
        {rounds.map((r) => (
          <Link
            key={r.round_num}
            to={`/matches/${encodeURIComponent(demo)}/rounds/${r.round_num}`}
            className={`rbox ${r.winner_side ?? "none"} ${r.round_num === roundNum ? "active" : ""}`}
            title={`รอบ ${r.round_num} · ${sideLabel(r.winner_side)} ชนะ · ${endReasonLabel(r.end_reason)} · ตาย ${r.deaths_count}`}
          >
            {r.round_num}
          </Link>
        ))}
        <button type="button" disabled={idx < 0 || idx >= rounds.length - 1} onClick={() => go(rounds[idx + 1].round_num)} title="รอบถัดไป (→)">
          ›
        </button>
      </nav>

      <div className="review-grid">
        <aside>
          <TeamRoster teams={d.teams} highlight={highlight} onHighlight={setHighlight} />
          {highlight && (
            <button type="button" className="link-btn" onClick={() => setHighlight(null)}>
              ล้างการไฮไลต์
            </button>
          )}
        </aside>

        <section className="map-col">
          <div className="toggles">
            <label>
              <input type="checkbox" checked={showCells} disabled={!overlay} onChange={(e) => setShowCells(e.target.checked)} />
              ซ้อนประเภทช่อง (grid_ml1)
            </label>
            <label>
              <input type="checkbox" checked={showHotspots} disabled={!overlay} onChange={(e) => setShowHotspots(e.target.checked)} />
              ซ้อนวง hotspot {overlay?.hotspots?.length ?? ""} จุด
            </label>
          </div>
          {d.radar ? (
            <MapView
              radar={d.radar}
              deaths={d.deaths}
              bomb={d.round.bomb}
              overlay={overlay}
              showCells={showCells}
              showHotspots={showHotspots}
              highlight={highlight}
              selected={selected}
              onSelect={setSelected}
            />
          ) : (
            <p className="muted">ยังไม่มีภาพเรดาร์ของแมพ {d.match.map_name}</p>
          )}
          {showCells && overlay?.clusters && (
            <div className="legend">
              {overlay.clusters.map((c) => (
                <span key={c.id}>
                  <i style={{ background: clusterColor(c.id) }} /> type {c.id}: {c.name} · CT ชนะดวล {pct(c.ct_win)}
                </span>
              ))}
              <span className="muted">จาก {overlay.source?.label}</span>
            </div>
          )}
        </section>

        <aside className="breakdown">
          <p className="eyebrow">TIMELINE</p>
          <DeathTimeline
            deaths={d.deaths}
            highlight={highlight}
            selected={selected}
            onSelect={setSelected}
            bombPlantedT={d.round.bomb_planted_t}
          />
          <RoundSummary summary={d.summary} winner={d.round.winner_side} grid={d.grid} />
          <DeathContext deaths={d.deaths} grid={d.grid} highlight={highlight} selected={selected} onSelect={setSelected} />
        </aside>
      </div>
    </div>
  );
}
