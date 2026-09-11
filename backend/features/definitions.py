# -*- coding: utf-8 -*-
"""
backend/features/definitions.py — นิยามที่ทั้งโค้ดต้องใช้ให้ตรงกัน (แหล่งเดียว ห้ามนิยามซ้ำที่อื่น)

    opening_kill  คิลแรกของรอบหลัง freeze-time จบ
                  นับเฉพาะ "การดวล" (มีคนยิง และคนละฝั่ง) — ตายจาก C4 / ตกที่สูง / ทีมคิล ไม่ใช่การเปิดรอบ
    trade         คนที่ฆ่าเหยื่อ ตายภายใน TRADE_WINDOW_SEC วินาที ด้วยมือเพื่อนของเหยื่อ
                  (เพื่อน = อยู่ฝั่งเดียวกับเหยื่อในรอบนั้น)
    buy_type      มูลค่าอุปกรณ์ "ต่อคน" ตอน freeze-time จบ
                  Full >= BUY_FULL_MIN | Force ระหว่าง BUY_FORCE_MIN ถึง BUY_FULL_MIN | Eco < BUY_FORCE_MIN
                  Pistol = รอบใน PISTOL_ROUNDS เสมอ ไม่ว่าเงินเท่าไร
    clutch        เหลือคนเดียวฝั่งตัวเอง เจอศัตรู >= 1 และรอบยังไม่จบ
                  clutch_vs = จำนวนศัตรูที่ยังอยู่ ณ วินาทีที่เหลือคนเดียว, won = ฝั่งนั้นชนะรอบ
                  1v1 นับเป็น clutch ของทั้งสองฝั่ง
    ADR           ดาเมจที่ทำใส่ศัตรูรวม / จำนวนรอบที่เล่น
    KAST          % ของรอบที่ผู้เล่นทำได้อย่างน้อยหนึ่งอย่าง: Kill, Assist, Survived, Traded

ตัวเลขทุกตัวเป็นค่าตาม brief ของ Sprint 2 — ถ้าเปลี่ยน ให้ขยับ FEATURES_VERSION ด้วย
จะได้รู้ว่าแถวไหนในฐานข้อมูลคำนวณด้วยนิยามรุ่นเก่า (ต้อง backfill ใหม่)
"""
FEATURES_VERSION = 1

TRADE_WINDOW_SEC = 5          # ฆ่าคืนภายในกี่วินาทีถึงนับเป็น trade

BUY_FULL_MIN = 4000           # >= นี้ = full buy   (ต่อคน หน่วยเป็นดอลลาร์ในเกม)
BUY_FORCE_MIN = 2000          # >= นี้แต่ < BUY_FULL_MIN = force buy, ต่ำกว่านี้ = eco
PISTOL_ROUNDS = (1, 13)       # รอบปืนสั้น (MR12: ครึ่งละ 12 รอบ จึงเป็นรอบ 1 กับ 13)

BUY_TYPES = ("pistol", "full", "force", "eco")
SIDES = ("ct", "t")


def buy_type(equip_value: int | None, round_num: int) -> str | None:
    """จัดประเภทการซื้อของผู้เล่นหนึ่งคนในหนึ่งรอบ — None ถ้าไม่รู้มูลค่าอุปกรณ์ (เดโมไม่มีข้อมูล)"""
    if round_num in PISTOL_ROUNDS:
        return "pistol"
    if equip_value is None:
        return None
    if equip_value >= BUY_FULL_MIN:
        return "full"
    if equip_value >= BUY_FORCE_MIN:
        return "force"
    return "eco"


def trade_window_ticks(tickrate: int) -> int:
    """หน้าต่าง trade แปลงเป็น tick ของเดโมนั้น (64 หรือ 128 tick/วินาที)"""
    return TRADE_WINDOW_SEC * int(tickrate)


def is_duel(kill: dict) -> bool:
    """การดวลจริง = มีคนยิง และคนละฝั่งกับคนตาย (ตัด C4 / ตกที่สูง / ทีมคิล)"""
    return bool(kill.get("attacker_id")) and kill.get("attacker_side") in SIDES \
        and kill.get("victim_side") in SIDES and kill["attacker_side"] != kill["victim_side"]


def other_side(side: str) -> str:
    return "t" if side == "ct" else "ct"
