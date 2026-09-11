# -*- coding: utf-8 -*-
"""
backend/geo.py — แปลงพิกัดในเกม <-> ช่องกริด / พิกเซลบนภาพเรดาร์  (สูตรชุดเดียวของทั้งรีโป)

    from backend.geo import radar_frame, cells_of, cell_of, world_to_pixel
    frame = radar_frame("de_mirage")
    cx, cy = cell_of(x, y, frame, grid_n=32)        # ช่องไหนของกริด (เหมือน research/grid_ml1.py เป๊ะ)
    px, py = world_to_pixel(x, y, frame)            # พิกเซลบนภาพเรดาร์ (มุมบนซ้าย = 0, 0)

ที่มาของสูตร
    ยกมาจาก research/grid_ml1.py (STEP 5) ซึ่งตรวจแล้วว่าถูก — ตอนนี้ grid_ml1.py import จากที่นี่แทน
    ขอบเขตกริดเอาจากภาพเรดาร์ (assets/radars.json) ไม่ใช่จากค่าต่ำสุด-สูงสุดของข้อมูล
    ช่องจึงไม่ขยับเมื่อเพิ่มเดโม และช่องที่ API คำนวณตรงกับช่องใน grid_ml1.json เสมอ

    ห้ามเขียนสูตรแปลงพิกัดที่อื่นอีก — ถ้าต้องการแปลงพิกัด ให้ import จากไฟล์นี้
"""
import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
RADARS_JSON = ROOT / "assets" / "radars.json"


@dataclass(frozen=True)
class RadarFrame:
    """ค่าปรับเทียบภาพเรดาร์ของแมพหนึ่ง (จาก radars.json) + ขอบเขตที่ภาพกินในพิกัดเกม"""
    map_name: str
    image: str      # path ภายใต้ assets/ เช่น "/maps/de_mirage.png"
    size: int       # ภาพเป็นจัตุรัส size x size พิกเซล
    pos_x: float    # พิกัดเกมของมุมบนซ้ายของภาพ
    pos_y: float
    scale: float    # หนึ่งพิกเซล = กี่หน่วยเกม

    @property
    def span(self) -> float:
        """ความกว้างของภาพเป็นหน่วยเกม (1024 พิกเซล x 5.0 = 5120 บน Mirage)"""
        return self.size * self.scale

    @property
    def x_left(self) -> float:
        return self.pos_x

    @property
    def x_right(self) -> float:
        return self.pos_x + self.span

    @property
    def y_top(self) -> float:
        return self.pos_y            # แกน y ในเกมนับขึ้น ขอบบนของภาพจึงเป็นค่ามาก

    @property
    def y_bottom(self) -> float:
        return self.pos_y - self.span

    @property
    def extent(self) -> tuple[float, float, float, float]:
        """(x_left, x_right, y_bottom, y_top) — แบบที่ matplotlib imshow(extent=...) ต้องการ"""
        return (self.x_left, self.x_right, self.y_bottom, self.y_top)

    def cell_size(self, grid_n: int) -> float:
        return self.span / grid_n


def load_radars() -> dict:
    return json.loads(RADARS_JSON.read_text(encoding="utf-8"))


@lru_cache(maxsize=32)
def radar_frame(map_name: str) -> RadarFrame | None:
    """ค่าปรับเทียบของแมพ — None ถ้าแมพนี้ยังไม่มีใน radars.json"""
    r = load_radars().get(map_name)
    if not isinstance(r, dict):
        return None
    return RadarFrame(map_name, r["image"], int(r["size"]), float(r["pos_x"]), float(r["pos_y"]), float(r["scale"]))


def cells_of(xs, ys, frame: RadarFrame, grid_n: int) -> tuple[np.ndarray, np.ndarray]:
    """พิกัดเกม -> ช่องกริด (cx, cy) แบบ vectorized — สูตรเดียวกับ research/grid_ml1.py

    (พิกัด - ขอบ) // ขนาดช่อง = อยู่ช่องที่เท่าไร
    np.clip บีบให้อยู่ในช่วง 0 ถึง grid_n-1 กันจุดที่ตกริมขอบพอดีหลุดออกนอกตาราง
    cy นับจากขอบล่าง (y_bottom) ขึ้นไป — แถว 0 คือแถวล่างสุดของแมพ
    """
    cell = frame.cell_size(grid_n)
    cx = np.clip((np.asarray(xs, dtype=float) - frame.x_left) // cell, 0, grid_n - 1).astype(int)
    cy = np.clip((np.asarray(ys, dtype=float) - frame.y_bottom) // cell, 0, grid_n - 1).astype(int)
    return cx, cy


def cell_of(x: float, y: float, frame: RadarFrame, grid_n: int) -> tuple[int, int]:
    """จุดเดียว — เรียกตัว vectorized ข้างบน เพื่อให้ผลตรงกันทุกทศนิยม ไม่มีสูตรสองชุด"""
    cx, cy = cells_of([x], [y], frame, grid_n)
    return int(cx[0]), int(cy[0])


def cell_rect_world(cx: int, cy: int, frame: RadarFrame, grid_n: int) -> tuple[float, float, float, float]:
    """ขอบของช่องในพิกัดเกม (x0, y0, x1, y1) — y0 คือขอบล่าง"""
    cell = frame.cell_size(grid_n)
    x0 = frame.x_left + cx * cell
    y0 = frame.y_bottom + cy * cell
    return x0, y0, x0 + cell, y0 + cell


def world_to_pixel(x: float, y: float, frame: RadarFrame) -> tuple[float, float]:
    """พิกัดเกม -> พิกเซลบนภาพเรดาร์ (มุมบนซ้ายของภาพ = 0, 0 และ y พิกเซลนับลง)

    ตรงกับ imshow(extent=frame.extent, origin="upper") ที่ grid_ml1.py ใช้วาดรูป
    """
    return (x - frame.pos_x) / frame.scale, (frame.pos_y - y) / frame.scale


def cell_rect_pixel(cx: int, cy: int, frame: RadarFrame, grid_n: int) -> tuple[float, float, float]:
    """มุมบนซ้ายของช่องเป็นพิกเซล + ความกว้างช่องเป็นพิกเซล (x, y, w) — ช่องเป็นจัตุรัส"""
    x0, _, _, y1 = cell_rect_world(cx, cy, frame, grid_n)
    px, py = world_to_pixel(x0, y1, frame)
    return px, py, frame.cell_size(grid_n) / frame.scale


def in_frame(x: float, y: float, frame: RadarFrame) -> bool:
    """จุดนี้อยู่บนภาพเรดาร์ไหม (ถ้าไม่อยู่ วาดแล้วจะหลุดขอบรูป)"""
    return frame.x_left <= x < frame.x_right and frame.y_bottom < y <= frame.y_top


def nearest_within(x: float, y: float, centers: list[tuple[float, float]], radius: float) -> int | None:
    """index ของจุดศูนย์กลางที่ใกล้ที่สุด ถ้าห่างไม่เกิน radius — ไม่งั้น None

    กฎเดียวกับที่ sklearn MeanShift(cluster_all=False) ใช้แปะป้ายจุดตอน grid_ml1 หา hotspot:
    ยอดที่ใกล้ที่สุด และระยะ <= bandwidth  (เกินจากนั้น = ไม่อยู่ใน hotspot ไหน)
    """
    if not centers:
        return None
    c = np.asarray(centers, dtype=float)
    d = np.hypot(c[:, 0] - x, c[:, 1] - y)
    i = int(np.argmin(d))
    return i if d[i] <= radius else None
