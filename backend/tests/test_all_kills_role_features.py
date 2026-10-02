# -*- coding: utf-8 -*-
"""Schema and definition tests for role-ready all_kills.csv columns."""
import polars as pl

from research.demoparser import (
    ALL_KILLS_COLUMN_GROUPS,
    ROLE_EVENT_COLUMNS,
    add_role_event_columns,
    order_all_kills_columns,
)


def _row(tick: int, attacker: int, victim: int, attacker_side: str, victim_side: str) -> dict:
    return {
        "demo_file": "ref.dem", "round_num": 1, "tick": tick, "tickrate": 100,
        "round_start_tick": 1000, "bomb_plant_tick": 5000,
        "attacker_steamid": attacker, "victim_steamid": victim,
        "attacker_side": attacker_side, "victim_side": victim_side,
        "attacker_place": "Connector", "victim_place": "BombsiteA",
        "assistedflash": False, "round_winner_side": "t",
    }


def test_role_event_columns_opening_trade_and_phase():
    # T 1 kills CT 2; CT 3 immediately trades T 1; T 4 gets a post-plant kill.
    rows = [
        _row(2000, 1, 2, "t", "ct"),
        _row(2400, 3, 1, "ct", "t"),
        _row(5100, 4, 3, "t", "ct"),
    ]
    out = add_role_event_columns(pl.DataFrame(rows))
    assert set(ROLE_EVENT_COLUMNS) <= set(out.columns)
    assert out["round_kill_order"].to_list() == [1, 2, 3]
    assert out["is_opening_kill"].to_list() == [True, False, False]
    assert out["trade_kill_count"].to_list() == [0, 1, 0]
    assert out["victim_was_traded"].to_list() == [True, False, False]
    assert out["round_phase"].to_list() == ["preplant", "preplant", "postplant"]


def test_role_event_enrichment_is_idempotent():
    source = pl.DataFrame([_row(2000, 1, 2, "t", "ct")])
    once = add_role_event_columns(source)
    twice = add_role_event_columns(once)
    assert once.columns == twice.columns
    assert once.to_dicts() == twice.to_dicts()


def test_all_kills_columns_are_grouped_once_without_data_loss():
    columns = [column for group in ALL_KILLS_COLUMN_GROUPS.values() for column in group]
    assert len(columns) == len(set(columns))
    source = add_role_event_columns(pl.DataFrame([_row(2000, 1, 2, "t", "ct")]))
    source = source.with_columns(pl.lit("kept").alias("future_parser_column"))
    ordered = order_all_kills_columns(source)
    assert ordered.columns[:3] == ["demo_file", "tickrate", "round_num"]
    assert ordered.columns[-1] == "future_parser_column"
    assert ordered.select(source.columns).to_dicts() == source.to_dicts()
