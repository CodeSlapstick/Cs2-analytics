export type ReportType = "coach" | "player";
export type ReportSide = "all" | "t" | "ct";

export interface ReportHeader { match_id: number; demo_file: string; report_type: ReportType; player_id: string | null; player_name: string | null; team_a: string | null; team_b: string | null; map_name: string | null; score_ct: number; score_t: number; rounds: number; match_date: string | null; generated_at: string; dataset_version: string }
export interface ReportKpi { key: string; label: string; value: number | string | null; comparison: number | string | null; sample_size: number; status: "good" | "watch" | "neutral" | "unavailable"; explanation: string }
export interface Evidence { round_num: number | null; time_seconds: number | null; text: string; viewer_url: string | null }
export interface ReportInsight { key: string; title: string; observation: string; impact: string; evidence: Evidence[]; possible_causes: string[]; confidence: "low" | "medium" | "high"; recommendation: string; next_target: string; sample_size: number }
export interface TurningPoint { round_num: number; winner_side: string | null; buy_type: string | null; event: string; turning_point: string; improvement: string; watch_time_seconds: number | null; viewer_url: string }
export interface SideAnalysis { side: "t" | "ct"; rounds: number; wins: number; strengths: string[]; problems: string[]; evidence: string[]; actions: string[] }
export interface EconomyFinding { round_num: number; buy_type: string; result: string; impact: string; recommendation: string }
export interface PlayerReportRow { steam_id: string; name: string; rounds: number; kills: number; deaths: number; assists: number; adr: number; kast: number; rating: number; opening_kills: number; opening_deaths: number; trade_kills: number; traded_deaths: number }
export interface TrainingAction { title: string; problem: string; evidence: string; method: string; owner: string; duration: string; target: string; review_after: string }
export interface DataQuality { demos: number; rounds: number; dataset_version: string; missing: string[]; estimated: string[]; warnings: string[] }
export interface ReportData { header: ReportHeader; side: ReportSide; executive_summary: string[]; insights: ReportInsight[]; kpis: ReportKpi[]; turning_points: TurningPoint[]; side_analysis: SideAnalysis[]; economy: EconomyFinding[]; players: PlayerReportRow[]; training_plan: TrainingAction[]; next_match_goals: string[]; data_quality: DataQuality }
