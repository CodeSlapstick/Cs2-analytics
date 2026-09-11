# -*- coding: utf-8 -*-
"""
backend/parser/constants.py — ค่าคงที่ที่ parser ใช้ร่วมกับสคริปต์ใน research/

แยกออกมาไฟล์เดียวเพื่อให้ service.py (ตัวจริงที่ระบบใช้) กับ research/demoparser.py
(ตัวสร้าง data/all_kills.csv) ใช้ชุด event/prop เดียวกันเป๊ะ ไม่งั้นวันหนึ่งสองที่จะเริ่มต่างกันเงียบ ๆ
"""

# event ที่ต้องขอจาก demoparser2 — ชุดขั้นต่ำที่ awpy ใช้หาขอบเขตรอบและคิล
EVENTS = [
    "player_death",           # ตัวคิลเอง
    "round_start",            # สี่อันล่างนี้ create_round_df ใช้หาขอบเขตแต่ละรอบ
    "round_freeze_end",
    "round_end",
    "round_officially_ended",
    "bomb_planted",           # ไม่จำเป็นต่อ kills แต่ทำให้คอลัมน์ bomb_plant ในตารางรอบไม่ว่าง
]

# props ของผู้เล่นที่ให้ parser แนบมากับทุก event
#   awpy เปลี่ยนชื่อให้เองตอนอ่าน: team_name -> side, last_place_name -> place
PLAYER_PROPS = ["last_place_name", "X", "Y", "Z", "health", "team_name"]

# ชื่ออาวุธในเดโม -> ชื่อสั้นที่เราใช้ (molotov กับ incendiary คือของเดียวกันคนละฝั่ง)
GRENADE_TYPES = {
    "flashbang": "flash", "smokegrenade": "smoke", "hegrenade": "he",
    "molotov": "molotov", "incgrenade": "molotov", "decoy": "decoy",
}
