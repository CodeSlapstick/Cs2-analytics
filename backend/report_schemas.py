# -*- coding: utf-8 -*-
"""Public contract for performance reports. Calculations live in the service/insight layers."""
from typing import Literal

from pydantic import BaseModel, Field

SideFilter = Literal["all", "t", "ct"]
ReportType = Literal["coach", "player"]


class ReportHeader(BaseModel):
    match_id: int
    demo_file: str
    report_type: ReportType
    player_id: str | None = None
    player_name: str | None = None
    team_a: str | None = None
    team_b: str | None = None
    map_name: str | None = None
    score_ct: int = 0
    score_t: int = 0
    rounds: int = 0
    match_date: str | None = None
    generated_at: str
    dataset_version: str


class ReportKpi(BaseModel):
    key: str
    label: str
    value: float | int | str | None
    comparison: float | int | str | None = None
    sample_size: int
    status: Literal["good", "watch", "neutral", "unavailable"] = "neutral"
    explanation: str


class Evidence(BaseModel):
    round_num: int | None = None
    time_seconds: float | None = None
    text: str
    viewer_url: str | None = None


class ReportInsight(BaseModel):
    key: str
    title: str
    observation: str
    impact: str
    evidence: list[Evidence] = Field(default_factory=list)
    possible_causes: list[str] = Field(default_factory=list)
    confidence: Literal["low", "medium", "high"]
    recommendation: str
    next_target: str
    sample_size: int


class TurningPoint(BaseModel):
    round_num: int
    winner_side: str | None = None
    buy_type: str | None = None
    event: str
    turning_point: str
    improvement: str
    watch_time_seconds: float | None = None
    viewer_url: str


class SideAnalysis(BaseModel):
    side: Literal["t", "ct"]
    rounds: int
    wins: int
    strengths: list[str] = Field(default_factory=list)
    problems: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    actions: list[str] = Field(default_factory=list)


class EconomyFinding(BaseModel):
    round_num: int
    buy_type: str
    result: str
    impact: str
    recommendation: str


class PlayerReportRow(BaseModel):
    steam_id: str
    name: str
    rounds: int
    kills: int
    deaths: int
    assists: int
    adr: float
    kast: float
    rating: float
    opening_kills: int = 0
    opening_deaths: int = 0
    trade_kills: int = 0
    traded_deaths: int = 0


class TrainingAction(BaseModel):
    title: str
    problem: str
    evidence: str
    method: str
    owner: str
    duration: str
    target: str
    review_after: str


class DataQuality(BaseModel):
    demos: int = 1
    rounds: int
    dataset_version: str
    missing: list[str] = Field(default_factory=list)
    estimated: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ReportResponse(BaseModel):
    header: ReportHeader
    side: SideFilter
    executive_summary: list[str]
    insights: list[ReportInsight]
    kpis: list[ReportKpi]
    turning_points: list[TurningPoint]
    side_analysis: list[SideAnalysis]
    economy: list[EconomyFinding]
    players: list[PlayerReportRow]
    training_plan: list[TrainingAction]
    next_match_goals: list[str]
    data_quality: DataQuality
