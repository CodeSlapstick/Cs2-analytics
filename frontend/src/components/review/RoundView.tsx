import { useQuery } from "@tanstack/react-query";
import { api, ApiError, type RoundDetail } from "../../api";
import { NotFound } from "../../pages/NotFound";
import { clusterColor, endReasonLabel, fmtT, pct, sideLabel } from "../../review/format";
import type { ViewState } from "../../review/urlState";
import { DeathContext, RoundSummary } from "./DeathContext";
import { DeathTimeline } from "./DeathTimeline";
import { MapView } from "./MapView";
import { TeamRoster } from "./TeamRoster";

interface Props {
  demo: string;
  roundNum: number;
  view: ViewState;
  setView: (patch: Partial<ViewState>) => void;
}

/** เนื้อหาของหนึ่งรอบ: รายชื่อทีม / แผนที่ / ไทม์ไลน์ + บริบทจาก grid_ml1 — state ทั้งหมดมาจาก URL */
export function RoundView({ demo, roundNum, view, setView }: Props) {
  const q = useQuery({
    queryKey: ["review-round", demo, roundNum],
    queryFn: () => api.reviewRound(demo, roundNum),
    // ระหว่างโหลดรอบใหม่ของแมตช์เดิม ให้เห็นรอบก่อนไว้ก่อน (ไม่กระพริบ) แต่ห้ามโชว์รอบของแมตช์อื่น
    placeholderData: (prev: RoundDetail | undefined) => (prev && prev.match.demo_file === demo ? prev : undefined),
    retry: (count, err) => !(err instanceof ApiError && err.status === 404) && count < 1,
  });
  const mapName = q.data?.radar?.map;
  const grid = useQuery({
    queryKey: ["review-grid", mapName],
    queryFn: () => api.reviewGrid(mapName!),
    enabled: !!mapName,
    staleTime: Infinity, // ผล grid_ml1 ไม่เปลี่ยนระหว่างใช้งาน
  });

  if (q.isLoading) return <p className="muted">กำลังโหลดรอบ {roundNum}…</p>;
  if (q.error instanceof ApiError && q.error.status === 404) return <NotFound title="ไม่พบรอบนี้" detail={q.error.message} />;
  if (q.error) return <p className="err">โหลดรอบนี้ไม่ได้: {(q.error as Error).message}</p>;
  if (!q.data) return null;

  const d = q.data;
  const overlay = grid.data?.available ? grid.data : undefined;

  return (
    <div className="review" data-testid="round-view">
      <div className="review-head">
        <h2>
          รอบ {d.round.num}
          {d.round.winner_side && <span className={`badge b-${d.round.winner_side} big`}>{sideLabel(d.round.winner_side)} ชนะ</span>}
        </h2>
        <span className="muted">
          {endReasonLabel(d.round.end_reason)}
          {d.round.bomb_planted_t != null && ` · วางบอมบ์ ${fmtT(d.round.bomb_planted_t)}`} · ตาย {d.deaths.length} คน
        </span>
      </div>

      <div className="review-grid">
        <aside>
          <TeamRoster teams={d.teams} highlight={view.player} onHighlight={(p) => setView({ player: p })} />
          {view.player && (
            <button type="button" className="link-btn" onClick={() => setView({ player: null })}>
              ล้างการไฮไลต์
            </button>
          )}
        </aside>

        <section className="map-col">
          <div className="toggles">
            <label>
              <input type="checkbox" checked={view.cells} disabled={!overlay} onChange={(e) => setView({ cells: e.target.checked })} />
              ซ้อนประเภทช่อง (grid_ml1)
            </label>
            <label>
              <input
                type="checkbox"
                checked={view.hotspots}
                disabled={!overlay}
                onChange={(e) => setView({ hotspots: e.target.checked })}
              />
              ซ้อนวง hotspot {overlay?.hotspots?.length ?? ""} จุด
            </label>
          </div>
          {d.radar ? (
            <MapView
              radar={d.radar}
              deaths={d.deaths}
              bomb={d.round.bomb}
              overlay={overlay}
              showCells={view.cells}
              showHotspots={view.hotspots}
              highlight={view.player}
              selected={view.death}
              onSelect={(o) => setView({ death: o })}
            />
          ) : (
            <p className="muted">ยังไม่มีภาพเรดาร์ของแมพ {d.match.map_name}</p>
          )}
          {view.cells && overlay?.clusters && (
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
            highlight={view.player}
            selected={view.death}
            onSelect={(o) => setView({ death: o })}
            bombPlantedT={d.round.bomb_planted_t}
          />
          <RoundSummary summary={d.summary} winner={d.round.winner_side} grid={d.grid} />
          <DeathContext
            deaths={d.deaths}
            grid={d.grid}
            highlight={view.player}
            selected={view.death}
            onSelect={(o) => setView({ death: o })}
          />
        </aside>
      </div>
    </div>
  );
}
