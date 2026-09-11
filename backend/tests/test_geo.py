# -*- coding: utf-8 -*-
"""สูตรพิกัดใน backend/geo.py ต้องให้ผลเดียวกับ research/grid_ml1.py และจุดที่วาดต้องอยู่บนภาพเรดาร์เสมอ

ใช้ data/all_kills.csv (อยู่ใน git) + snapshot ของ output/grid_ml1.json / grid_ml1_cells.csv ใน fixtures/
"""
import json
from collections import Counter
from pathlib import Path

import pandas as pd
import pytest

from backend.geo import cell_rect_world, cells_of, in_frame, nearest_within, radar_frame, world_to_pixel
from backend.review import death_context, parse_grid_model

ROOT = Path(__file__).resolve().parent.parent.parent
FIX = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="module")
def kills() -> pd.DataFrame:
    return pd.read_csv(ROOT / "data" / "all_kills.csv")


@pytest.fixture(scope="module")
def model():
    return parse_grid_model(json.loads((FIX / "grid_ml1.json").read_text(encoding="utf-8")))


@pytest.fixture(scope="module")
def cells_csv() -> pd.DataFrame:
    return pd.read_csv(FIX / "grid_ml1_cells.csv")


@pytest.fixture(scope="module")
def frame():
    return radar_frame("de_mirage")


def duels(df: pd.DataFrame) -> pd.DataFrame:
    """ตัวกรองเดียวกับ grid_ml1.py STEP 4: มีคนยิง และคนละฝั่ง"""
    d = df[df["map_name"] == "de_mirage"]
    return d[d["attacker_side"].notna() & (d["attacker_side"] != d["victim_side"])]


def test_every_death_point_drawn_is_inside_the_radar(kills, frame):
    for who in ("victim", "attacker"):
        d = kills.dropna(subset=[f"{who}_X", f"{who}_Y"])
        assert len(d) > 7000
        outside = [(x, y) for x, y in zip(d[f"{who}_X"], d[f"{who}_Y"], strict=True) if not in_frame(x, y, frame)]
        assert outside == [], f"{who}: {len(outside)} จุดหลุดกรอบเรดาร์"
        for x, y in zip(d[f"{who}_X"], d[f"{who}_Y"], strict=True):
            px, py = world_to_pixel(x, y, frame)
            assert 0 <= px <= frame.size and 0 <= py <= frame.size


def test_pixel_and_extent_agree(frame):
    # มุมบนซ้ายของภาพ = (0, 0), มุมล่างขวา = (size, size)
    assert world_to_pixel(frame.x_left, frame.y_top, frame) == (0, 0)
    assert world_to_pixel(frame.x_right, frame.y_bottom, frame) == (frame.size, frame.size)


def test_cells_reproduce_grid_ml1_duel_counts(kills, cells_csv, model, frame):
    """นับดวลต่อช่องด้วย backend.geo แล้วต้องได้ช่องชุดเดียวกัน จำนวนเท่ากันทุกช่องกับ grid_ml1_cells.csv"""
    d = duels(kills)
    cx, cy = cells_of(d["victim_X"], d["victim_Y"], frame, model.grid_n)
    counts = Counter(zip(cx.tolist(), cy.tolist(), strict=True))
    kept = {c: n for c, n in counts.items() if n >= model.min_kills}
    expected = {(int(r.cx), int(r.cy)): int(r.kills) for r in cells_csv.itertuples()}
    assert kept == expected


def test_lookup_cell_to_cluster_matches_cells_csv_every_row(cells_csv, model, frame):
    for r in cells_csv.itertuples():
        x0, y0, x1, y1 = cell_rect_world(r.cx, r.cy, frame, model.grid_n)
        for x, y in (((x0 + x1) / 2, (y0 + y1) / 2), (x0 + 0.01, y0 + 0.01), (x1 - 0.01, y1 - 0.01)):
            ctx = death_context(x, y, "ct", True, model, frame)
            assert ctx["reason"] is None
            c = ctx["cell"]
            assert (c["cx"], c["cy"]) == (r.cx, r.cy)
            assert c["cluster_id"] == r.cluster
            assert c["cluster_name"] == r.cluster_name
            assert c["cell_ct_win"] == pytest.approx(r.ct_win, abs=1e-3)
            assert c["ct_win"] == model.clusters[r.cluster]["ct_win"]      # ct_win ของ "กลุ่ม" ไม่ใช่ของช่อง


def test_cell_with_too_few_duels_is_not_guessed_from_neighbours(cells_csv, model, frame):
    known = set(zip(cells_csv.cx, cells_csv.cy, strict=True))
    # ช่องที่ไม่มีข้อมูลพอ แต่มีเพื่อนบ้านที่มีข้อมูล — ต้องตอบว่าไม่พอ ไม่ใช่ยืมค่าข้างเคียงมา
    target = next((cx, cy) for cx in range(model.grid_n) for cy in range(model.grid_n)
                  if (cx, cy) not in known and (cx + 1, cy) in known and (cx - 1, cy) in known)
    x0, y0, x1, y1 = cell_rect_world(*target, frame, model.grid_n)
    ctx = death_context((x0 + x1) / 2, (y0 + y1) / 2, "t", True, model, frame)
    assert ctx["cell"] is None and ctx["reason"] == "insufficient" and ctx["disadvantaged"] is None
    assert ctx["cell_xy"] == {"cx": target[0], "cy": target[1]}


def test_hotspot_rule_reproduces_meanshift_membership(kills, model):
    """ยอดที่ใกล้สุดภายใน bandwidth = กฎที่ MeanShift(cluster_all=False) ใช้ — จำนวนดวลต่อ hotspot ต้องตรงกับ json"""
    d = duels(kills)
    centers = [(h["x"], h["y"]) for h in model.hotspots]
    got = Counter(nearest_within(x, y, centers, model.bandwidth) for x, y in zip(d["victim_X"], d["victim_Y"], strict=True))
    for i, h in enumerate(model.hotspots):
        assert got[i] == h["duels"], f"hotspot #{h['id']}"


def test_other_map_has_no_context(model):
    dust2 = radar_frame("de_dust2")
    assert dust2 is not None
    ctx = death_context(0, 0, "ct", True, model, dust2)
    assert ctx["reason"] == "no_model" and ctx["cell"] is None
