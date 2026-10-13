"""Foreign-key fallbacks for demo events with incomplete player rosters."""
import asyncio

from backend.etl_loader import (
    _damage_rows,
    _grenade_rows,
    _kill_rows,
    _player_id,
    _position_rows,
    _upsert_referenced_players,
    load_match_doc,
)


class RecordingConnection:
    def __init__(self):
        self.calls = []

    async def executemany(self, sql, rows):
        self.calls.append((sql, rows))

    async def fetch(self, sql, ids):
        self.calls.append((sql, ids))
        return [{"steam_id": steam_id} for steam_id in ids if steam_id != 404]


def test_all_event_players_are_upserted_and_confirmed_before_child_rows():
    conn = RecordingConnection()
    doc = {
        "players": [{"steam_id": 101, "name": "Known"}],
        "kills": [{"attacker_id": 202, "victim_id": 101, "assister_id": 303}],
        "damages": [{"attacker_id": 202, "victim_id": 404}],
        "grenades": [{"thrower_id": 505}],
        "player_rounds": [{"steam_id": 101}],
        "positions": [{"steam_id": 606}],
    }
    known = asyncio.run(_upsert_referenced_players(conn, doc))
    sql, rows = conn.calls[0]
    assert "ON CONFLICT (steam_id) DO NOTHING" in sql
    assert [row[0] for row in rows] == [101, 202, 303, 404, 505, 606]
    assert "SELECT steam_id FROM players" in conn.calls[1][0]
    assert known == {101, 202, 303, 505, 606}


def test_invalid_event_player_ids_use_null_or_skip_required_rows():
    def rid_of(row):
        return 7
    kill = {"tick": 10, "attacker_id": 0, "victim_id": "101", "assister_id": "invalid",
            "victim_side": "ct"}
    assert _kill_rows([kill], rid_of)[0][2:5] == (None, 101, None)
    assert _kill_rows([{**kill, "victim_id": 0}], rid_of) == []
    damage = {"tick": 11, "attacker_id": "invalid", "victim_id": 101, "damage": 20}
    assert _damage_rows([damage], rid_of)[0][2:4] == (None, 101)
    assert _damage_rows([{**damage, "victim_id": None}], rid_of) == []
    assert _damage_rows([{**damage, "attacker_id": 202}], rid_of, {101})[0][2:4] == (None, 101)
    assert _damage_rows([{**damage, "victim_id": 202}], rid_of, {101}) == []
    grenade = {"tick": 12, "thrower_id": 0, "type": "smoke"}
    assert _grenade_rows([grenade], rid_of)[0][2] is None
    assert _position_rows([{"round_num": 1, "tick": 13, "steam_id": 0, "x": 1, "y": 2}], 1, {1: 7}) == []
    position = {"round_num": 1, "tick": 13, "steam_id": 101, "x": 1, "y": 2,
                "yaw": -90.5, "flash_remaining": 1.25}
    assert _position_rows([position], 1, {1: 7}, {101})[0][-2:] == (-90.5, 1.25)
    assert _player_id(2**63) is None


def test_load_registers_orphan_attacker_before_inserting_damage():
    class Connection(RecordingConnection):
        def __init__(self):
            super().__init__()
            self.players = set()

        def transaction(self):
            return self

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return None

        async def execute(self, sql, *_):
            return None

        async def fetchval(self, sql, *_):
            return 7

        async def executemany(self, sql, rows):
            await super().executemany(sql, rows)
            if "INSERT INTO players" in sql:
                self.players.update(row[0] for row in rows)
            if "INSERT INTO damages" in sql:
                assert rows[0][2] == 76561198033024570
                assert rows[0][2] in self.players and rows[0][3] in self.players

        async def fetch(self, sql, ids):
            return [{"steam_id": steam_id} for steam_id in ids if steam_id in self.players]

    doc = {"match": {"demo_file": "test.dem", "tickrate": 128},
           "players": [{"steam_id": 101, "name": "Known"}],
           "rounds": [{"round_num": 1, "start_tick": 0}],
           "damages": [{"round_num": 1, "tick": 10, "attacker_id": 76561198033024570,
                        "victim_id": 101, "damage": 20}]}
    conn = Connection()
    asyncio.run(load_match_doc(conn, doc, match_id=1))
    assert 76561198033024570 in conn.players
