# -*- coding: utf-8 -*-
"""Coordinates repository facts, insight rules and the stable report response."""
from datetime import UTC, datetime

from backend.report_insights import build_insights
from backend.report_repository import ReportRepository
from backend.report_schemas import (
    DataQuality,
    EconomyFinding,
    PlayerReportRow,
    ReportHeader,
    ReportKpi,
    ReportResponse,
    SideAnalysis,
    TrainingAction,
    TurningPoint,
)

DATASET_VERSION = "report-v1"


class ReportService:
    def __init__(self, repository: ReportRepository):
        self.repository = repository

    async def coach_report(self, match_id: int, side: str) -> ReportResponse:
        return self._build(await self.repository.load(match_id, side), "coach", side)

    async def player_report(self, match_id: int, steam_id: str, side: str) -> ReportResponse:
        return self._build(await self.repository.load(match_id, side, steam_id), "player", side)

    def _build(self, raw: dict, report_type: str, side: str) -> ReportResponse:
        match, players, rounds = raw["match"], raw["players"], raw["rounds"]
        total_rounds = max((p["rounds"] for p in players), default=len(rounds))
        score_ct = sum(r["winner_side"] == "ct" for r in rounds)
        score_t = sum(r["winner_side"] == "t" for r in rounds)
        benchmark = raw.get("benchmark") or {}
        def avg(key):
            return round(sum(float(p[key]) for p in players) / len(players), 2) if players else 0
        opening_kills = sum(p["opening_kills"] for p in players)
        opening_deaths = sum(p["opening_deaths"] for p in players)
        deaths = sum(p["deaths"] for p in players)
        traded = sum(p["traded_deaths"] for p in players)
        kpis = [
            ReportKpi(key="adr", label="ADR", value=avg("adr"), comparison=benchmark.get("adr"), sample_size=total_rounds, status=_status(avg("adr"), benchmark.get("adr"), True), explanation="ความเสียหายเฉลี่ยต่อรอบ"),
            ReportKpi(key="kast", label="KAST", value=avg("kast"), comparison=benchmark.get("kast"), sample_size=total_rounds, status=_status(avg("kast"), benchmark.get("kast"), True), explanation="รอบที่มี kill, assist, survival หรือถูก trade"),
            ReportKpi(key="opening", label="Opening duel", value=f"{opening_kills}/{opening_deaths}", sample_size=opening_kills + opening_deaths, status="neutral", explanation="จำนวนครั้งที่ชนะ/แพ้การดวลแรก"),
            ReportKpi(key="trade", label="Deaths ที่ถูก trade", value=round(100 * traded / deaths, 1) if deaths else None, sample_size=deaths, status="neutral" if deaths else "unavailable", explanation="เปอร์เซ็นต์ deaths ที่เพื่อนยิงคืนภายใน 5 วินาที"),
        ]
        insights = build_insights(raw)
        turning = [_turning(match["demo_file"], r, side) for r in sorted(rounds, key=lambda x: -x["deaths_count"])[:5]]
        analyses = [_side_analysis(s, rounds, insights) for s in ("t", "ct") if side in ("all", s)]
        economy = [_economy(r, side) for r in rounds if _buy(r, side) in ("eco", "semi_eco", "semi_buy")][:5]
        training = [_training(i, players[0]["name"] if report_type == "player" and players else "Coach / IGL") for i in insights[:3]]
        missing = []
        if not any(r.get("first_death_t") is not None for r in rounds):
            missing.append("เวลาการเสียชีวิตแรก")
        missing.extend(["Utility damage", "Flash assists", "สถานการณ์ผู้เล่น 5v3 ราย tick"])
        warnings = [] if total_rounds >= 20 else [f"ข้อมูลมีเพียง {total_rounds} รอบ ควรติดตามเพิ่มอีก 4 แมตช์"]
        player = players[0] if report_type == "player" and players else None
        return ReportResponse(
            header=ReportHeader(match_id=match["id"], demo_file=match["demo_file"], report_type=report_type,
                player_id=player["steam_id"] if player else None, player_name=player["name"] if player else None,
                team_a=match.get("team_a"), team_b=match.get("team_b"), map_name=match.get("map_name"),
                score_ct=score_ct, score_t=score_t, rounds=len(rounds), match_date=str(match.get("imported_at") or ""),
                generated_at=datetime.now(UTC).isoformat(), dataset_version=DATASET_VERSION),
            side=side, executive_summary=[f"วิเคราะห์ {total_rounds} รอบจากเดโม {match['demo_file']}"] + [f"{i.title}: {i.observation} ควรทำต่อ: {i.recommendation}" for i in insights[:4]],
            insights=insights, kpis=kpis, turning_points=turning, side_analysis=analyses, economy=economy,
            players=[PlayerReportRow(**p) for p in players], training_plan=training,
            next_match_goals=[i.next_target for i in insights[:3]],
            data_quality=DataQuality(rounds=total_rounds, dataset_version=DATASET_VERSION, missing=missing,
                                     estimated=["Rating เป็นค่าประมาณจากสูตรเดียวกับหน้าสกอร์บอร์ด"], warnings=warnings))


def _status(value, comparison, higher_is_better):
    if comparison is None:
        return "neutral"
    return "good" if (value >= comparison) == higher_is_better else "watch"


def _buy(row, side):
    if side in ("ct", "t"):
        return row.get(f"{side}_buy_type")
    return f"CT {row.get('ct_buy_type') or '—'} / T {row.get('t_buy_type') or '—'}"


def _turning(demo, row, side):
    return TurningPoint(round_num=row["round_num"], winner_side=row["winner_side"], buy_type=_buy(row, side),
        event=f"มีผู้เสียชีวิต {row['deaths_count']} คน", turning_point="การเสียชีวิตแรกเป็นจุดเริ่มเปลี่ยนจำนวนผู้เล่น" if row["first_death_t"] is not None else "ควรเปิดดู timeline เพื่อหาจุดเปลี่ยน",
        improvement="ตรวจ utility และระยะ trade ก่อนจังหวะแรก", watch_time_seconds=row["first_death_t"],
        viewer_url=f"/matches/{demo}/rounds/{row['round_num']}")


def _side_analysis(side, rounds, insights):
    selected = [r for r in rounds if r["winner_side"] in ("t", "ct")]
    wins = sum(r["winner_side"] == side for r in selected)
    return SideAnalysis(side=side, rounds=len(selected), wins=wins,
        strengths=[f"ชนะ {wins} จาก {len(selected)} รอบที่มีผล"], problems=[i.observation for i in insights[:2]],
        evidence=[f"รอบ {r['round_num']} มี {r['deaths_count']} deaths" for r in sorted(selected, key=lambda x: -x["deaths_count"])[:3]],
        actions=[i.recommendation for i in insights[:2]])


def _economy(row, side):
    buy = _buy(row, side)
    return EconomyFinding(round_num=row["round_num"], buy_type=buy or "ไม่ระบุ", result=f"{(row['winner_side'] or '—').upper()} ชนะ",
        impact="การซื้อรอบนี้มีผลต่ออาวุธและ utility ของรอบถัดไป", recommendation="ตรวจว่าผู้เล่นซื้อพร้อมกันและเหลือ utility ตามแผน")


def _training(insight, owner):
    evidence = "; ".join(e.text for e in insight.evidence[:3]) or insight.observation
    return TrainingAction(title=insight.title, problem=insight.observation, evidence=evidence,
        method=insight.recommendation, owner=owner, duration="15–20 นาทีก่อน Scrim", target=insight.next_target,
        review_after="หลังแข่งขันครบ 5 แมตช์")
