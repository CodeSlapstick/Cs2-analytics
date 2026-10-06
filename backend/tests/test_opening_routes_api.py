import asyncio

import pytest
from fastapi import HTTPException

from backend.app import api_opening_route


class Connection:
    def __init__(self):
        self.calls = []

    async def fetch(self, sql, *args):
        self.calls.append((sql, args))
        if "FROM matches m JOIN match_players" in sql:
            return [{"id": 1, "demo_file": "2026-01-01_real.dem", "map_name": "de_mirage", "tickrate": 64}]
        return []


def test_side_filter_is_the_player_side_in_each_round():
    conn = Connection()
    result = asyncio.run(api_opening_route(steamid="123", map="de_mirage", side="ct", limit=5, _={}, conn=conn))
    assert result["matches"] == 1
    round_query, args = conn.calls[1]
    assert "pr.side = $3" in round_query
    assert "pr.steam_id = $2" in round_query
    assert args == ([1], 123, "ct")
    assert "pp.tick BETWEEN r.start_tick AND r.start_tick + 30 * m.tickrate" in conn.calls[2][0]


@pytest.mark.parametrize("steamid,side,limit", [("abc", "t", 5), ("123", "both", 5), ("123", "t", 3), (str(2**64), "ct", 0)])
def test_invalid_filters_are_rejected(steamid, side, limit):
    with pytest.raises(HTTPException) as exc:
        asyncio.run(api_opening_route(steamid=steamid, map="de_mirage", side=side, limit=limit, _={}, conn=Connection()))
    assert exc.value.status_code == 422
