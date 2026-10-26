import asyncio

from backend.report_export import build_text_report
from backend.report_service import ReportService

RAW = {"match": {"id": 7, "demo_file": "team.dem", "team_a": "Alpha", "team_b": "Bravo", "map_name": "de_mirage", "imported_at": "2026-10-20"},
       "players": [{"steam_id": "1", "name": "One", "rounds": 24, "kills": 20, "deaths": 14, "assists": 5, "adr": 84.2, "kast": 74.0, "rating": 1.18, "opening_kills": 4, "opening_deaths": 3, "trade_kills": 2, "traded_deaths": 5}],
       "rounds": [{"round_num": 1, "winner_side": "ct", "deaths_count": 5, "first_death_t": 38.0, "ct_buy_type": "pistol", "t_buy_type": "pistol"},
                  {"round_num": 2, "winner_side": "t", "deaths_count": 4, "first_death_t": 42.0, "ct_buy_type": "semi_buy", "t_buy_type": "full"}],
       "hotspots": [{"place": "Mid", "deaths": 5}], "benchmark": {"matches": 5, "adr": 78.0, "kast": 70.0}}


class Repo:
    async def load(self, match_id, side, steam_id=None):
        assert match_id == 7
        assert side in ("all", "t", "ct")
        if steam_id is not None:
            assert steam_id == "1"
        return RAW


def test_coach_and_player_reports_share_contract():
    service = ReportService(Repo())
    coach = asyncio.run(service.coach_report(7, "all"))
    player = asyncio.run(service.player_report(7, "1", "ct"))
    assert coach.header.report_type == "coach"
    assert player.header.player_name == "One"
    assert player.side == "ct"
    assert len(coach.next_match_goals) <= 3
    assert "CS2 PLAIN TEXT PERFORMANCE REPORT" in build_text_report(coach)
    assert "สาเหตุที่เป็นไปได้" in build_text_report(player)


def test_low_sample_adds_warning():
    raw = {**RAW, "players": [{**RAW["players"][0], "rounds": 8}]}
    class SmallRepo:
        async def load(self, *_args):
            return raw
    report = asyncio.run(ReportService(SmallRepo()).coach_report(7, "all"))
    assert report.data_quality.warnings
