import type { HeatEvent, MatchHeatmap } from "../api";

export type CoachSectionId = "overview" | "scoreboard" | "rounds" | "heatmap" | "economy" | "roles" | "comparison" | "utility" | "moments" | "notes";

export interface CoachExportOptions {
  sections: CoachSectionId[];
  heatmap: {
    event: HeatEvent;
    team: "ours" | "opponent" | "all";
    side: "all" | "ct" | "t";
    roundPreset: "all" | "first" | "second" | "custom";
    customRounds: string;
    players: string[];
    radius: number;
    blur: number;
    opacity: number;
  };
  economy: {
    team: "ours" | "opponent" | "all";
    fromRound: number;
    toRound: number;
    showChart: boolean;
    showBuyTypes: boolean;
    showTable: boolean;
  };
}

export interface CoachHeatmapDocumentData {
  data: MatchHeatmap;
  options: CoachExportOptions["heatmap"];
}
