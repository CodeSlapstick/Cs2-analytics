import type { ReportSide, ReportType } from "../../types/report";

type Player = { steam_id: string; name: string };
type Props = { type: ReportType; side: ReportSide; playerId: string; players: Player[]; onType(type: ReportType): void; onSide(side: ReportSide): void; onPlayer(id: string): void };

export function ReportFilters({ type, side, playerId, players, onType, onSide, onPlayer }: Props) {
  return <div className="pr-controls">
    <fieldset><legend>ผู้รับรายงาน</legend><label><input type="radio" name="report-audience" checked={type === "coach"} onChange={() => onType("coach")} /> Coach</label><label><input type="radio" name="report-audience" checked={type === "player"} onChange={() => onType("player")} /> Player</label></fieldset>
    <label>ฝั่ง<select value={side} onChange={(e) => onSide(e.target.value as ReportSide)}><option value="all">ทั้งหมด</option><option value="t">T</option><option value="ct">CT</option></select></label>
    {type === "player" && <label className="pr-player-select">ผู้เล่น<select aria-label="ผู้เล่น" value={playerId} onChange={(e) => onPlayer(e.target.value)}>{players.map((p) => <option key={p.steam_id} value={p.steam_id}>{p.name}</option>)}</select></label>}
    <span>4 หน้า A4 · ขาวดำ · มีหมายเลขหน้า</span>
  </div>;
}
