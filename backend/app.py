# -*- coding: utf-8 -*-
"""
backend/app.py — "หลังบ้าน" (backend) ของเว็บ CS2 Analytics

เปรียบเทียบง่าย ๆ: ไฟล์นี้คือ "พนักงานหลังเคาน์เตอร์"
  - หน้าเว็บ (frontend/) = ลูกค้าที่มายืนหน้าเคาน์เตอร์
  - ไฟล์นี้ = พนักงานที่คอยรับคำสั่ง ไปหยิบของจากคลัง (PostgreSQL) แล้วส่งกลับไปให้

หน้าที่ของไฟล์นี้มี 3 อย่าง (หน้าเว็บทั้งหมดอยู่ที่ frontend/ — React)
  1) ล็อกอินด้วย username/password (backend/auth.py)
  2) จำว่า "ใครล็อกอินอยู่" ด้วย JWT ในคุกกี้ httpOnly (JavaScript อ่านไม่ได้)
  3) ตอบ /api/* — ดึงสถิติจากฐานข้อมูลแล้วส่งเป็น JSON ให้หน้าเว็บเอาไปวาด

ข้อมูลอยู่ใน PostgreSQL (ตาราง: backend/models.py + Alembic, view: backend/views.sql, โหลดผ่าน /api/demos หรือ backend/etl_loader.py)
ไฟล์นี้ไม่อ่าน csv เองแล้ว — อ่านผ่าน SQL อย่างเดียว จะได้ filter/รวมข้อมูลได้เร็วโดยไม่ต้องโหลดทั้งตารางเข้าแรม

รัน:  python -m uvicorn backend.app:app --reload   (ในเครื่อง — หน้าเว็บ npm run dev ส่งต่อ /api มาที่นี่)
ผู้ใช้ไม่เข้า API ตรง ๆ: เปิดหน้าเว็บ แล้วหน้าเว็บ (หรือ nginx ใน Docker) ส่ง /api /auth /assets มาให้
Swagger: <หน้าเว็บ>/api/docs
"""

# ---------------------------------------------------------------------------
# ส่วนที่ 0 — ขนเครื่องมือเข้ามาใช้
# ---------------------------------------------------------------------------
import json
import mimetypes
import os
import re
import subprocess
import sys
import threading
from contextlib import asynccontextmanager
from pathlib import Path

import asyncpg
from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.concurrency import run_in_threadpool  # เอางานหนักที่ไม่ใช่ async ไปรันในเธรดแยก ไม่ให้เซิร์ฟเวอร์ค้าง
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from backend import auth  # ล็อกอิน: hash รหัสผ่าน + JWT ใน httpOnly cookie
from backend.db import (  # noqa: F401  (load_dotenv ทำงานตอน import)
    DATABASE_URL,
    apply_schema,
    create_pool,
    redacted_url,
)
from backend.features.teams import assign_teams  # ผูกคนกับทีม (Round Review)
from backend.geo import radar_frame
from backend.jobqueue import QueueUnavailable, enqueue_parse, job_state, queue_health  # คิวงาน parse (Sprint 2)
from backend.review import build_round_detail, build_round_list, grid_overlay, load_grid_model

# ---------------------------------------------------------------------------
# ส่วนที่ 1 — ค่าตั้งต้น (CONFIG) อยากแก้อะไรแก้ตรงนี้ที่เดียว
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent   # โฟลเดอร์โปรเจกต์
ASSETS_DIR = ROOT / "assets"                    # ภาพเรดาร์ของแต่ละแมพ + ค่าปรับเทียบพิกัด (radars.json)
DEMOS_DIR = ROOT / "demos"                      # ไฟล์ .dem ที่ผู้ใช้อัปโหลดเข้ามา (ไม่ถูก commit — ดู .gitignore)
JSON_DIR = ROOT / "output" / "json"             # ผลจาก parser ก่อนเข้าฐานข้อมูล เก็บไว้ตรวจย้อนหลังได้

MAX_DEMO_MB = int(os.environ.get("MAX_DEMO_MB", "600"))   # เพดานขนาดไฟล์ที่ยอมรับ กันคนอัปของใหญ่จนดิสก์เต็ม
# ชื่อไฟล์ที่ยอมรับ — อนุญาตเฉพาะตัวอักษร ตัวเลข และ . _ - ( ) เท่านั้น
# สำคัญกว่าที่คิด: ถ้าปล่อยให้มี / หรือ .. ในชื่อ คนอัปจะเขียนไฟล์ทับที่ไหนก็ได้ในเครื่อง (path traversal)
DEMO_NAME_RE = re.compile(r"^[A-Za-z0-9._()-]{1,120}\.dem$", re.IGNORECASE)

# คอนโซลของ Windows ดีฟอลต์เป็น cp1252 ซึ่งพิมพ์ภาษาไทยไม่ได้ ถ้าไม่ตั้งบรรทัดนี้
# print() ที่มีข้อความไทยจะโยน UnicodeEncodeError ออกมากลางคัน ทำให้ทั้ง request พัง
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass


def log(msg: str) -> None:
    """พิมพ์ log โดยไม่มีทางทำให้โปรแกรมพังเพราะ encoding ของคอนโซล"""
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        print(msg.encode("ascii", "replace").decode("ascii"), flush=True)


# ค่าจาก .env ที่รากโปรเจกต์ (backend/db.py โหลดเข้า environment ให้แล้วตอน import)
ALLOW_REGISTER = os.environ.get("ALLOW_REGISTER", "1") == "1"   # 1 = ให้สมัครสมาชิกเองได้ที่หน้า /login

SIDE_RE = re.compile(r"^(ct|t)$")


# ---------------------------------------------------------------------------
# ส่วนที่ 2 — เปิด/ปิดฐานข้อมูลพร้อมเซิร์ฟเวอร์
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    """สิ่งที่ทำตอนเซิร์ฟเวอร์เริ่ม (ก่อน yield) และตอนปิด (หลัง yield)"""
    app.state.pool = None
    try:
        app.state.pool = await create_pool()
        async with app.state.pool.acquire() as conn:
            await apply_schema(conn)          # สร้างตารางถ้ายังไม่มี รันซ้ำได้
        log(f"[DB] ต่อ {redacted_url()} สำเร็จ")
    except Exception as e:                    # DB ล่ม/ยังไม่เปิด -> เว็บยังเปิดได้ แต่ /api/* จะตอบ 503
        log(f"[DB] ต่อ {redacted_url()} ไม่ได้: {e}")
        log("[DB] เปิด DB ด้วย: docker compose up -d db")
    yield
    if app.state.pool:
        await app.state.pool.close()


# Swagger อยู่ใต้ /api — หน้าเว็บส่งต่อให้เฉพาะ /api /auth /assets ถ้าอยู่ที่ /docs จะเปิดจากหน้าเว็บไม่ได้
app = FastAPI(title="CS2 Analytics API", lifespan=lifespan,
              docs_url="/api/docs", redoc_url=None, openapi_url="/api/openapi.json")
app.mount("/assets", StaticFiles(directory=ASSETS_DIR), name="assets")  # URL ที่ขึ้นต้นด้วย /assets ให้ไปหยิบไฟล์จริงใน assets/ (ภาพเรดาร์)

# Windows บางเครื่องไม่รู้จักนามสกุล .webp ทำให้ส่งไฟล์ออกไปเป็น application/octet-stream
# บอกชนิดไฟล์ให้ถูกต้องไว้ก่อน เบราว์เซอร์จะได้รู้แน่ ๆ ว่านี่คือรูปภาพ
mimetypes.add_type("image/webp", ".webp")


async def db(request: Request) -> asyncpg.Connection:
    """Dependency: ขอ connection จากบ่อหนึ่งเส้นให้ route นี้ใช้ แล้วคืนอัตโนมัติเมื่อจบ"""
    pool: asyncpg.Pool | None = request.app.state.pool
    if pool is None:
        raise HTTPException(503, "ฐานข้อมูลยังไม่พร้อม — เปิดด้วย docker compose up -d db แล้วรีสตาร์ตเซิร์ฟเวอร์")
    async with pool.acquire() as conn:
        yield conn


# ---------------------------------------------------------------------------
# ส่วนที่ 3 — ใครล็อกอินอยู่: JWT ในคุกกี้ httpOnly (สร้าง/ตรวจที่ backend/auth.py)
# ---------------------------------------------------------------------------
def require_login(request: Request) -> dict:
    """Dependency: route ไหนใส่อันนี้ = ต้องล็อกอินก่อน ไม่งั้นตอบ 401 ทันที — คืน {id, username}"""
    user = auth.user_from_token(request.cookies.get(auth.COOKIE_NAME))
    if not user:
        raise HTTPException(401, "ยังไม่ได้ล็อกอิน หรือ session หมดอายุ")
    return user


# ---------------------------------------------------------------------------
# ส่วนที่ 5 — ล็อกอิน / ออกจากระบบ
# ---------------------------------------------------------------------------
class Credentials(BaseModel):
    username: str
    password: str


def _logged_in(account) -> JSONResponse:
    """ตอบกลับพร้อมติดคุกกี้ JWT — ใช้ร่วมกันทั้งตอนสมัครและตอนล็อกอิน"""
    user = {"id": account["id"], "username": account["username"]}
    response = JSONResponse({"user": user})
    auth.set_auth_cookie(response, auth.create_token(user["id"], user["username"]))
    return response


@app.post("/auth/register")
async def auth_register(body: Credentials, conn: asyncpg.Connection = Depends(db)):
    """สมัครสมาชิกแล้วล็อกอินให้เลย — ปิดได้ด้วย ALLOW_REGISTER=0"""
    if not ALLOW_REGISTER:
        raise HTTPException(403, "ระบบนี้ปิดการสมัครสมาชิก")
    username = body.username.strip()
    if (err := auth.validate_credentials(username, body.password)):
        raise HTTPException(400, err)
    password_hash = await run_in_threadpool(auth.hash_password, body.password)
    try:
        row = await conn.fetchrow("""
            INSERT INTO accounts (username, password_hash, last_login) VALUES ($1, $2, now())
            RETURNING id, username""", username, password_hash)
    except asyncpg.UniqueViolationError:
        raise HTTPException(409, "ชื่อผู้ใช้นี้มีคนใช้แล้ว") from None
    log(f"[AUTH] สมัครสมาชิก {username} (id {row['id']})")
    return _logged_in(row)


@app.post("/auth/login")
async def auth_login(body: Credentials, conn: asyncpg.Connection = Depends(db)):
    """ตรวจรหัสผ่าน ผ่านแล้วติดคุกกี้ JWT — ผิดทั้งชื่อหรือรหัสตอบข้อความเดียวกัน ไม่บอกว่าชื่อนี้มีอยู่ไหม"""
    row = await conn.fetchrow(
        "SELECT id, username, password_hash FROM accounts WHERE lower(username) = lower($1)", body.username.strip())
    if row is None:
        await run_in_threadpool(auth.burn_time_like_verify, body.password)   # เวลาตอบเท่ากับกรณีมีชื่อจริง
        raise HTTPException(401, "ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง")
    if not await run_in_threadpool(auth.verify_password, body.password, row["password_hash"]):
        raise HTTPException(401, "ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง")
    await conn.execute("UPDATE accounts SET last_login = now() WHERE id = $1", row["id"])
    return _logged_in(row)


@app.get("/auth/me")
def auth_me(user: dict = Depends(require_login)):
    """หน้าเว็บถามว่า 'ตอนนี้ฉันล็อกอินอยู่ไหม เป็นใคร' — ยังไม่ล็อกอินตอบ 401"""
    return {"user": user}


@app.post("/auth/logout")
def auth_logout():
    """ลบคุกกี้ = ออกจากระบบ (JWT เป็น stateless ไม่มีอะไรต้องลบในฐานข้อมูล)"""
    response = JSONResponse({"ok": True})
    auth.clear_auth_cookie(response)
    return response


# ---------------------------------------------------------------------------
# ส่วนที่ 6 — API สำหรับหน้าเว็บ (ตอบ JSON) — ทุกอันดึงจาก PostgreSQL
# ---------------------------------------------------------------------------
def rows(records) -> list[dict]:
    """asyncpg คืน Record มาให้ แปลงเป็น dict ธรรมดาเพื่อให้ FastAPI ส่งเป็น JSON ได้"""
    return [dict(r) for r in records]


@app.get("/api/health")
async def api_health(request: Request):
    """เช็คว่า DB ต่อได้ไหม มีข้อมูลเท่าไร — ไม่ต้องล็อกอิน ไว้ให้ docker/monitor ถาม"""
    pool = request.app.state.pool
    if pool is None:
        return JSONResponse({"ok": False, "db": "ยังไม่ได้ต่อ"}, status_code=503)
    try:
        async with pool.acquire() as conn:
            n = await conn.fetchrow(
                "SELECT (SELECT COUNT(*) FROM matches) AS matches, (SELECT COUNT(*) FROM kills) AS kills")
        return {"queue": await run_in_threadpool(queue_health), "ok": True, "db": "ต่อได้", "matches": n["matches"], "kills": n["kills"]}
    except Exception as e:
        return JSONResponse({"ok": False, "db": str(e)}, status_code=503)


@app.get("/api/stats")
async def api_stats(
    map_name: str | None = Query(None, alias="map", pattern=r"^de_[a-z0-9_]+$"),
    _: dict = Depends(require_login),
    conn: asyncpg.Connection = Depends(db),
):
    """สรุปภาพรวมให้หน้าหลัก — ใส่ ?map=de_mirage เพื่อดูเฉพาะแมพ (ไม่ใส่ = ทุกแมพ)

    รูปแบบคำตอบคงเดิมกับตอนที่ยังอ่านจาก csv หน้าเว็บจึงไม่ต้องแก้อะไร
    """
    where = "WHERE m.map_name = $1" if map_name else ""
    args = [map_name] if map_name else []
    base = f"FROM kills k JOIN rounds r ON r.id = k.round_id JOIN matches m ON m.id = r.match_id {where}"

    totals = await conn.fetchrow(f"""
        SELECT COUNT(*)                                          AS total_kills,
               COUNT(*) FILTER (WHERE k.headshot)                AS headshots,
               COUNT(*) FILTER (WHERE k.attacker_side = 'ct')    AS ct_kills,
               COUNT(*) FILTER (WHERE k.attacker_side = 't')     AS t_kills,
               ROUND(AVG(r.round_num)::numeric, 1)               AS avg_round,
               COUNT(DISTINCT m.id)                              AS matches,
               COUNT(DISTINCT r.id)                              AS rounds
        {base}""", *args)
    top_weapons = await conn.fetch(f"""
        SELECT k.weapon AS name, COUNT(*) AS count {base}
        GROUP BY k.weapon ORDER BY count DESC LIMIT 8""", *args)
    top_places = await conn.fetch(f"""
        SELECT k.victim_place AS name, COUNT(*) AS count {base}
        {"AND" if where else "WHERE"} k.victim_place IS NOT NULL
        GROUP BY k.victim_place ORDER BY count DESC LIMIT 8""", *args)

    # KPI ระดับรอบ/คน สำหรับการ์ดบนหน้า Dashboard — มาจาก view player_round_facts (ต้องมี player_rounds)
    # avg_* = ค่าเฉลี่ยต่อคนต่อรอบทั้งชุดข้อมูล ไว้เป็นเส้นอ้างอิงเวลาเทียบนักแข่งคนเดียว
    kpi = await conn.fetchrow(f"""
        SELECT COUNT(DISTINCT f.round_id) FILTER (WHERE r.winner_side = 'ct')                         AS ct_rounds_won,
               COUNT(DISTINCT f.round_id)                                                            AS rounds_with_facts,
               ROUND(AVG(f.damage)::numeric, 1)                                                      AS avg_adr,
               ROUND(100.0 * COUNT(*) FILTER (WHERE f.kast) / GREATEST(COUNT(*), 1), 1)              AS avg_kast
        FROM player_round_facts f JOIN rounds r ON r.id = f.round_id JOIN matches m ON m.id = r.match_id
        {where}""", *args)
    avg_rating = await conn.fetchval("SELECT ROUND(AVG(rating)::numeric, 2) FROM player_stats WHERE rounds >= 20")

    total = totals["total_kills"]
    return {
        "map": map_name,
        "matches": totals["matches"],
        "rounds": totals["rounds"],
        "total_kills": total,
        "headshots": totals["headshots"],
        "headshot_rate": round(totals["headshots"] / total * 100, 1) if total else 0.0,
        "avg_round": float(totals["avg_round"] or 0),
        "ct_kills": totals["ct_kills"],
        "t_kills": totals["t_kills"],
        "top_weapons": rows(top_weapons),
        "top_places": rows(top_places),
        # ใหม่ — เป็น 0/None ถ้ายังไม่ได้โหลด player_rounds (JSON schema_version < 3)
        "ct_round_win_rate": round(100 * kpi["ct_rounds_won"] / kpi["rounds_with_facts"], 1) if kpi["rounds_with_facts"] else None,
        "avg_adr": float(kpi["avg_adr"]) if kpi["avg_adr"] is not None else None,
        "avg_kast": float(kpi["avg_kast"]) if kpi["avg_kast"] is not None else None,
        "avg_rating": float(avg_rating) if avg_rating is not None else None,
    }


@app.get("/api/matches")
async def api_matches(_: dict = Depends(require_login), conn: asyncpg.Connection = Depends(db)):
    """รายชื่อแมตช์ทั้งหมดพร้อมสรุป (จาก view match_summary)"""
    return rows(await conn.fetch("SELECT * FROM match_summary ORDER BY id"))


@app.get("/api/matches/{match_id}")
async def api_match(match_id: int, _: dict = Depends(require_login), conn: asyncpg.Connection = Depends(db)):
    """แมตช์เดียวแบบละเอียด: สรุป + รายรอบ + สกอร์บอร์ดของนักแข่งในแมตช์นั้น"""
    match = await conn.fetchrow("SELECT * FROM match_summary WHERE id = $1", match_id)
    if not match:
        raise HTTPException(404, "ไม่พบแมตช์นี้")
    # รายรอบ + เศรษฐกิจ (มูลค่าอุปกรณ์ทั้งทีมตอน freeze จบ และ buy type) จาก view round_economy
    # LEFT JOIN เพื่อให้แมตช์ที่โหลดจาก JSON รุ่นเก่า (ไม่มี player_rounds) ยังตอบได้ แค่ช่องเศรษฐกิจว่าง
    rounds_ = await conn.fetch("""
        SELECT r.round_num, r.winner_side, r.end_reason,
               r.bomb_plant_tick IS NOT NULL AS bomb_planted,
               COUNT(k.id) AS kills,
               e.ct_equip, e.t_equip, e.ct_buy_type, e.t_buy_type
        FROM rounds r
        LEFT JOIN kills k ON k.round_id = r.id
        LEFT JOIN round_economy e ON e.round_id = r.id
        WHERE r.match_id = $1
        GROUP BY r.id, e.ct_equip, e.t_equip, e.ct_buy_type, e.t_buy_type
        ORDER BY r.round_num""", match_id)
    # สกอร์บอร์ดจาก view match_scoreboard — มี ADR / KAST / rating / ฝั่งที่เริ่ม (= ทีม) มาให้ครบ
    scoreboard = await conn.fetch("""
        SELECT steam_id::text AS steam_id, name, start_side, rounds,
               kills, deaths, assists, headshots, hs_rate, adr, kast, rating
        FROM match_scoreboard WHERE match_id = $1
        ORDER BY rating DESC, kills DESC""", match_id)
    if not scoreboard:                        # แมตช์รุ่นเก่าที่ไม่มี player_rounds — ถอยไปนับจาก kills ตรง ๆ
        scoreboard = await conn.fetch("""
            WITH mk AS (SELECT k.* FROM kills k JOIN rounds r ON r.id = k.round_id WHERE r.match_id = $1),
                 ids AS (SELECT attacker_id AS steam_id FROM mk WHERE attacker_id IS NOT NULL
                         UNION SELECT victim_id FROM mk)
            SELECT p.steam_id::text AS steam_id, p.name,
                   (SELECT COUNT(*) FROM mk WHERE attacker_id = p.steam_id)              AS kills,
                   (SELECT COUNT(*) FROM mk WHERE victim_id   = p.steam_id)              AS deaths,
                   (SELECT COUNT(*) FROM mk WHERE assister_id = p.steam_id)              AS assists,
                   (SELECT COUNT(*) FROM mk WHERE attacker_id = p.steam_id AND headshot) AS headshots
            FROM ids JOIN players p USING (steam_id)
            ORDER BY kills DESC, deaths ASC""", match_id)
    # ฟีเจอร์ต่อคน (backend/features — คำนวณตอนโหลด เก็บใน player_rounds): opening / trade / clutch / buy type
    feats = await conn.fetch("""
        SELECT pr.steam_id::text AS steam_id,
               COUNT(*) FILTER (WHERE pr.opening_kill)       AS opening_kills,
               COUNT(*) FILTER (WHERE pr.opening_death)      AS opening_deaths,
               COALESCE(SUM(pr.trade_kills), 0)              AS trade_kills,
               COUNT(*) FILTER (WHERE pr.was_traded)         AS traded_deaths,
               COUNT(*) FILTER (WHERE pr.clutch_vs > 0)      AS clutch_attempts,
               COUNT(*) FILTER (WHERE pr.clutch_won)         AS clutch_wins,
               COUNT(*) FILTER (WHERE pr.buy_type = 'full')  AS full_buys,
               COUNT(*) FILTER (WHERE pr.buy_type = 'force') AS force_buys,
               COUNT(*) FILTER (WHERE pr.buy_type = 'eco')   AS eco_buys,
               MAX(pr.features_version)                      AS features_version
        FROM player_rounds pr JOIN rounds r ON r.id = pr.round_id
        WHERE r.match_id = $1
        GROUP BY pr.steam_id""", match_id)
    # features_version 0 = แถวจากยุคก่อนมีฟีเจอร์ (ยังไม่ backfill) — ไม่ส่งค่าศูนย์หลอก ๆ ไปให้หน้าเว็บ
    features = {f["steam_id"]: dict(f) for f in feats if f["features_version"]}
    return {"match": dict(match), "rounds": rows(rounds_), "scoreboard": rows(scoreboard), "features": features}


# ---------------------------------------------------------------------------
# ส่วนที่ 5.5 — โมเดลโอกาสชนะรอบ "อ่าน" แมตช์เดียว
#
# ตรรกะกลางใช้ร่วมกันสอง endpoint
#   /api/matches/{id}/rounds   ไทม์ไลน์รายรอบ: P(CT ชนะ) หลังทุกคิล + จังหวะตัดสินรอบ
#   /api/matches/{id}/review   จุดพลาดรายคน: การตายที่แพงที่สุด / ตายฟรี / ดวลในจุดเสียเปรียบ
#
# ทิศทางกลับกับการเทรน: เทรน = เดโมหลายสิบไฟล์ -> ตาราง P(CT ชนะ)
# ที่นี่ = ตาราง -> เดโมไฟล์เดียว จึงใช้กับแมตช์ที่เพิ่งอัปโหลดได้ทันที ไม่ต้องเทรนใหม่
# ---------------------------------------------------------------------------
ROUND_KILLS_SQL = """
    SELECT r.round_num, r.winner_side, r.end_reason, r.start_tick, r.bomb_plant_tick, m.tickrate,
           k.tick, k.attacker_side, k.victim_side, k.weapon, k.headshot, k.attacker_place, k.victim_place,
           k.attacker_id::text AS attacker_id, k.victim_id::text AS victim_id,
           k.victim_x, k.victim_y,
           pa.name AS attacker, pv.name AS victim
    FROM rounds r
    JOIN matches m ON m.id = r.match_id
    LEFT JOIN kills k    ON k.round_id = r.id          -- LEFT ทั้งสาย: รอบที่ไม่มีคิลเลย (หมดเวลา) ต้องยังโผล่
    LEFT JOIN players pa ON pa.steam_id = k.attacker_id
    LEFT JOIN players pv ON pv.steam_id = k.victim_id
    WHERE r.match_id = $1
    ORDER BY r.round_num, k.tick, k.id"""


def load_round_win_model() -> dict:
    """ตาราง P(CT ชนะรอบ) ที่ round_win.py เขียนไว้ — ไม่มีก็บอกวิธีสร้าง"""
    return read_output_json("round_win.json", "python research/round_win.py")


def annotate_rounds(rows_, model: dict) -> list[dict]:
    """ไล่คิลทีละแถว ติดสถานะ "ก่อน" คิล (ใครเหลือกี่คน ระเบิดลงยัง วินาทีที่เท่าไร)
    แล้วเปิดตาราง -> P(CT ชนะ) ก่อนและหลัง  delta = หลัง - ก่อน (มุมมอง CT)
    คิลที่ |delta| มากที่สุดในรอบ = จังหวะที่ตัดสินรอบ
    """
    table, edges, names = model["table"], model["time_edges"], model["time_names"]

    def time_bucket(sec: float) -> str:
        # ใช้ <= ให้ตรงกับ pd.cut (ช่วงปิดขวา) ที่ round_win.py ใช้ตอนเทรน ไม่งั้นวินาทีที่ 20 พอดีจะตกคนละถัง
        for edge, name in zip(edges, names):
            if sec <= edge:
                return name
        return names[-1]

    def p_ct(ct: int, t: int, planted: int, sec: float | None):
        """P(CT ชนะ) จากตาราง — None ถ้าสถานะนี้ไม่มีในตาราง (นอกช่วง 1-5 หรือไม่รู้เวลาเริ่มรอบ)"""
        if sec is None or not (1 <= ct <= 5 and 1 <= t <= 5):
            return None
        return table.get(f"{ct}v{t}|{planted}|{time_bucket(sec)}")

    rounds_out: list[dict] = []
    cur: dict | None = None
    for row in rows_:
        rate = row["tickrate"] or 128
        start = row["start_tick"]
        if cur is None or cur["round_num"] != row["round_num"]:
            plant = row["bomb_plant_tick"]
            cur = {
                "round_num": row["round_num"],
                "winner_side": row["winner_side"],
                "end_reason": row["end_reason"],
                "bomb_plant_sec": round((plant - start) / rate, 1) if plant is not None and start is not None else None,
                "kills": [],
                "_dead_ct": 0, "_dead_t": 0,
            }
            rounds_out.append(cur)
        if row["tick"] is None:
            continue

        sec = round((row["tick"] - start) / rate, 1) if start is not None else None
        planted = int(row["bomb_plant_tick"] is not None and row["tick"] >= row["bomb_plant_tick"])

        # สถานะ "ก่อน" คิลนี้ — นับคนตายจากทุกสาเหตุ (C4 / ตกที่สูง / ทีมคิล) เหมือน round_win.py
        ct_before, t_before = 5 - cur["_dead_ct"], 5 - cur["_dead_t"]
        if row["victim_side"] == "ct":
            cur["_dead_ct"] += 1
        elif row["victim_side"] == "t":
            cur["_dead_t"] += 1
        ct_after, t_after = 5 - cur["_dead_ct"], 5 - cur["_dead_t"]

        p_before = p_ct(ct_before, t_before, planted, sec)
        if ct_after <= 0:
            p_after = 0.0                       # CT หมด = T ชนะแน่
        elif t_after <= 0:
            p_after = None if planted else 1.0  # T หมดแต่ระเบิดลงแล้ว CT ยังต้องกู้ให้ทัน ตารางไม่มีสถานะนี้ ไม่เดา
        else:
            p_after = p_ct(ct_after, t_after, planted, sec)
        delta = round(p_after - p_before, 4) if p_after is not None and p_before is not None else None

        cur["kills"].append({
            "sec": sec,
            "attacker": row["attacker"], "attacker_side": row["attacker_side"], "attacker_place": row["attacker_place"],
            "victim": row["victim"], "victim_side": row["victim_side"], "victim_place": row["victim_place"],
            "attacker_id": row["attacker_id"], "victim_id": row["victim_id"],
            "victim_x": row["victim_x"], "victim_y": row["victim_y"],
            "weapon": row["weapon"], "headshot": row["headshot"],
            "before": f"{ct_before}v{t_before}", "after": f"{ct_after}v{t_after}",
            "planted": planted,
            "p_before": p_before, "p_after": p_after, "delta": delta,
        })

    for r in rounds_out:
        del r["_dead_ct"], r["_dead_t"]
        ks = r["kills"]
        measurable = [i for i, k in enumerate(ks) if k["delta"] is not None]
        r["deciding"] = max(measurable, key=lambda i: abs(ks[i]["delta"])) if measurable else None
        r["p_final"] = next((k["p_after"] for k in reversed(ks) if k["p_after"] is not None), None)
    return rounds_out


def model_info(model: dict, map_name: str) -> dict:
    """ข้อมูลกำกับโมเดลที่หน้าเว็บต้องรู้ — โดยเฉพาะว่าเทรนจากแมพเดียวกับแมตช์นี้ไหม"""
    return {
        "map": model["map"],
        "trained_matches": model["metrics"]["matches"],
        "trained_at": model.get("trained_at"),
        "same_map": model["map"] == map_name,       # ฟีเจอร์คือคนเหลือ/ระเบิด/เวลา ใช้ข้ามแมพได้ แต่ต้องบอกผู้ใช้
        "p_start": model["table"].get(f"5v5|0|{model['time_names'][0]}"),
    }


@app.get("/api/matches/{match_id}/status")
async def api_match_status(match_id: int, _: dict = Depends(require_login), conn: asyncpg.Connection = Depends(db)):
    """สถานะงานแกะเดโมของแมตช์ — หน้าเว็บ poll ตัวนี้จนกว่าจะ done หรือ error

    status        queued -> parsing -> done | error   (worker เป็นคนขยับ)
    error_message สาเหตุตอน error (ทุก error ใน worker ลงที่นี่)
    job           สถานะฝั่งคิว RQ ถ้าถามได้ (queued/started/finished/failed) ไว้ดูว่า worker หยิบไปหรือยัง
    """
    row = await conn.fetchrow("""
        SELECT id, demo_file, status, error_message, job_id, imported_at, started_at, finished_at
        FROM matches WHERE id = $1;
    """, match_id)
    if not row:
        raise HTTPException(404, "ไม่พบแมตช์นี้")
    d = dict(row)
    d["job"] = await run_in_threadpool(job_state, d["job_id"])
    return d


@app.get("/api/matches/{match_id}/rounds")
async def api_match_rounds(match_id: int, _: dict = Depends(require_login), conn: asyncpg.Connection = Depends(db)):
    """ไทม์ไลน์รายรอบ — P(CT ชนะ) หลังทุกคิล และคิลที่ตัดสินรอบ"""
    match = await conn.fetchrow("SELECT * FROM match_summary WHERE id = $1", match_id)
    if not match:
        raise HTTPException(404, "ไม่พบแมตช์นี้")
    model = load_round_win_model()
    rows_ = await conn.fetch(ROUND_KILLS_SQL, match_id)
    return {"match": dict(match), "model": model_info(model, match["map_name"]), "rounds": annotate_rounds(rows_, model)}


# ---- กริด: ช่องไหนบนแมพที่ฝั่งไหนชนะดวล (ใช้ได้เฉพาะแมพที่ grid_ml.py เทรนไว้) ----------
BAD_CELL_P = 0.40      # ถ้าฝั่งเราชนะดวลในช่องนั้นน้อยกว่านี้ = "ดวลในจุดเสียเปรียบ"


def load_grid(map_name: str) -> dict | None:
    """โหลด grid_ml.json + ค่าปรับเทียบเรดาร์ ถ้าโมเดลกริดเป็นของแมพนี้ — ไม่ใช่ก็คืน None (ไม่พัง)"""
    f = ROOT / "output" / "grid_ml.json"
    if not f.exists():
        return None
    g = json.loads(f.read_text(encoding="utf-8"))
    if g.get("map") != map_name:
        return None
    radar = json.loads((ASSETS_DIR / "radars.json").read_text(encoding="utf-8")).get(map_name)
    if not radar:
        return None
    # เรขาคณิตชุดเดียวกับ grid_ml.py: ขอบกริดเอาจากภาพเรดาร์ ไม่ใช่จากข้อมูล
    span = radar["size"] * radar["scale"]
    n = g["grid_n"]
    return {
        "n": n, "cell": span / n,
        "x_left": radar["pos_x"], "y_bottom": radar["pos_y"] - span,
        "cells": {(c["cx"], c["cy"]): c for c in g["cells"]},
        "matches": g["metrics"]["matches"],
    }


def grid_cell(grid: dict | None, x, y) -> dict | None:
    """พิกัดเกม -> ช่องกริด -> ค่าที่โมเดลรู้ (None ถ้าช่องนั้นมีดวลน้อยเกินจะสรุป)"""
    if grid is None or x is None or y is None:
        return None
    cx = int(min(max((x - grid["x_left"]) // grid["cell"], 0), grid["n"] - 1))
    cy = int(min(max((y - grid["y_bottom"]) // grid["cell"], 0), grid["n"] - 1))
    return grid["cells"].get((cx, cy))


@app.get("/api/matches/{match_id}/review")
async def api_match_review(match_id: int, _: dict = Depends(require_login), conn: asyncpg.Connection = Depends(db)):
    """รีวิวรายคน: เราพลาดตรงไหน — สามคำถามที่ข้อมูลตอบได้จริง

    A  การตายที่แพงที่สุด   ทุกครั้งที่ตาย โอกาสชนะรอบของทีมหายไปกี่ % (จากตาราง round_win)
    B  ดวลในจุดเสียเปรียบ   ตายในช่องที่โมเดลกริดบอกว่าฝั่งเราชนะน้อยกว่า 40% (เฉพาะแมพที่มีกริด)
    C  ตายฟรี              opening death ที่เพื่อนไม่เทรดคืนใน 5 วิ / ตายแล้วไม่ถูกเทรด (จาก player_round_facts)

    สิ่งที่ตั้งใจ "ไม่" ตอบ: ทำไมถึงแพ้ดวล (เล็ง/ปืน) — โมเดลไม่ใช้ headshot/weapon ตั้งแต่ต้น
    """
    match = await conn.fetchrow("SELECT * FROM match_summary WHERE id = $1", match_id)
    if not match:
        raise HTTPException(404, "ไม่พบแมตช์นี้")
    model = load_round_win_model()
    rows_ = await conn.fetch(ROUND_KILLS_SQL, match_id)
    rounds_ = annotate_rounds(rows_, model)
    grid = load_grid(match["map_name"])

    # ---- รายชื่อผู้เล่น: จาก scoreboard ถ้ามี (เดโมที่อัปผ่านเว็บ) ไม่มีก็ประกอบจากคิล (แมตช์จาก csv) ----
    players: dict[str, dict] = {}
    for sb in await conn.fetch(
            "SELECT steam_id::text AS steam_id, name, start_side, kills, deaths FROM match_scoreboard WHERE match_id = $1", match_id):
        players[sb["steam_id"]] = {**dict(sb), "side": sb["start_side"]}
    for r in rounds_:
        for k in r["kills"]:
            for pid, name, side in ((k["victim_id"], k["victim"], k["victim_side"]),
                                    (k["attacker_id"], k["attacker"], k["attacker_side"])):
                if pid and pid not in players:
                    players[pid] = {"steam_id": pid, "name": name, "start_side": None, "side": side, "kills": 0, "deaths": 0}
    if not players:
        raise HTTPException(404, "แมตช์นี้ไม่มีคิลให้รีวิว")

    for p in players.values():
        p.update({"cost_total": 0.0, "costly_deaths": [], "bad_cell_deaths": [], "deaths_seen": 0})

    # ---- A + B: ไล่ทุกการตาย ----------------------------------------------------------------
    for r in rounds_:
        for k in r["kills"]:
            p = players.get(k["victim_id"])
            if not p:
                continue
            p["deaths_seen"] += 1
            side = k["victim_side"]
            # delta เป็นมุมมอง CT — แปลงเป็น "ทีมของคนตายเสียไปเท่าไร" (บวก = เสีย)
            cost = None if k["delta"] is None else (-k["delta"] if side == "ct" else k["delta"])
            cell = grid_cell(grid, k["victim_x"], k["victim_y"])
            own_p = None
            if cell is not None and side in ("ct", "t"):
                own_p = cell["pred"] if side == "ct" else 1 - cell["pred"]
            death = {
                "round_num": r["round_num"], "sec": k["sec"], "before": k["before"], "after": k["after"],
                "planted": k["planted"], "killer": k["attacker"], "weapon": k["weapon"],
                "place": k["victim_place"], "cost": None if cost is None else round(cost, 4),
                "cell_place": cell["place"] if cell else None,
                "cell_own_p": None if own_p is None else round(own_p, 3),
                "cell_kills": cell["kills"] if cell else None,
                "round_won": (r["winner_side"] == side) if r["winner_side"] else None,
            }
            if cost is not None:
                p["cost_total"] += cost
                p["costly_deaths"].append(death)
            if own_p is not None and own_p < BAD_CELL_P:
                p["bad_cell_deaths"].append(death)

    # ---- C: จาก view player_round_facts (มีเฉพาะเดโมที่อัปผ่านเว็บ — จาก csv ไม่มี player_rounds) ----
    facts = await conn.fetch("""
        SELECT steam_id::text AS steam_id,
               COUNT(*)                                                AS rounds,
               COUNT(*) FILTER (WHERE opening_death)                   AS opening_deaths,
               COUNT(*) FILTER (WHERE opening_death AND was_traded)    AS opening_traded,
               COUNT(*) FILTER (WHERE deaths > 0)                      AS deaths,
               COUNT(*) FILTER (WHERE deaths > 0 AND NOT was_traded)   AS untraded_deaths,
               COUNT(*) FILTER (WHERE survived)                        AS survived,
               COUNT(*) FILTER (WHERE kast)                            AS kast_rounds,
               COUNT(*) FILTER (WHERE opening_kill)                    AS opening_kills
        FROM player_round_facts WHERE match_id = $1 GROUP BY steam_id""", match_id)
    facts_by = {f["steam_id"]: dict(f) for f in facts}

    out = []
    for p in players.values():
        p["costly_deaths"].sort(key=lambda d: -d["cost"])
        p["costly_deaths"] = p["costly_deaths"][:5]
        p["bad_cell_deaths"].sort(key=lambda d: d["cell_own_p"])
        p["cost_total"] = round(p["cost_total"], 3)
        p["facts"] = facts_by.get(p["steam_id"])
        out.append(p)
    out.sort(key=lambda p: -p["cost_total"])

    return {
        "match": dict(match),
        "model": model_info(model, match["map_name"]),
        "grid": None if grid is None else {"map": match["map_name"], "matches": grid["matches"], "bad_cell_p": BAD_CELL_P},
        "facts_available": bool(facts_by),
        "players": out,
    }


@app.get("/api/players")
async def api_players(
    limit: int = Query(20, ge=1, le=200),
    min_matches: int = Query(1, ge=1),
    _: dict = Depends(require_login),
    conn: asyncpg.Connection = Depends(db),
):
    """นักแข่งเรียงตามคิล (จาก view player_stats) — ?min_matches=3 กรองคนที่เล่นน้อยออก"""
    recs = await conn.fetch("""
        SELECT steam_id::text AS steam_id, name, matches, rounds, kills, deaths, assists, headshots, kd, hs_rate,
               adr, kast, rating, win_rate, opening_rate, trade_rate, util_per_round
        FROM player_stats WHERE matches >= $1
        ORDER BY kills DESC LIMIT $2""", min_matches, limit)
    return rows(recs)


@app.get("/api/players/{steam_id}")
async def api_player(steam_id: int, _: dict = Depends(require_login), conn: asyncpg.Connection = Depends(db)):
    """นักแข่งคนเดียว: สถิติรวม + เรดาร์ 6 แกน + ปืนที่ใช้ + จุดที่ฆ่า/ตายบ่อย"""
    p = await conn.fetchrow("""
        SELECT steam_id::text AS steam_id, name, matches, rounds, kills, deaths, assists, headshots, kd, hs_rate,
               adr, kast, rating, win_rate, survival_rate, opening_kills, opening_deaths, opening_rate,
               trade_kills, trade_rate, traded_rate, util_per_round, clutch_attempts, clutch_wins
        FROM player_stats WHERE steam_id = $1""", steam_id)
    if not p:
        raise HTTPException(404, "ไม่พบนักแข่งคนนี้")
    # เรดาร์ 6 แกน = เปอร์เซ็นไทล์เทียบนักแข่งคนอื่นที่เล่น >= 20 รอบ (0 = ต่ำสุดในกลุ่ม, 100 = สูงสุด)
    #   AIM = ยิงหัว%  ENTRY = เปิดรอบ%  TRD = เทรดคิล/รอบ  UTIL = ระเบิด/รอบ  CLUTCH = ชนะ clutch%  SURV = รอด%
    #   ใช้เปอร์เซ็นไทล์แทนค่าดิบ เพราะแต่ละแกนหน่วยคนละอย่าง ค่าดิบวางบนเรดาร์เดียวกันไม่ได้
    #   clutch ต้องมีอย่างน้อย 3 ครั้งถึงนับ ไม่งั้นคนที่ชนะ 1/1 จะได้ 100% ทันที
    radar = await conn.fetchrow("""
        WITH pool AS (SELECT * FROM player_stats WHERE rounds >= 20),
        ranked AS (
            SELECT steam_id,
                   percent_rank() OVER (ORDER BY hs_rate)        AS aim,
                   percent_rank() OVER (ORDER BY opening_rate)   AS entry,
                   percent_rank() OVER (ORDER BY trade_rate)     AS trade,
                   percent_rank() OVER (ORDER BY util_per_round) AS util,
                   percent_rank() OVER (ORDER BY CASE WHEN clutch_attempts >= 3
                                                     THEN clutch_wins::numeric / clutch_attempts ELSE 0 END) AS clutch,
                   percent_rank() OVER (ORDER BY survival_rate)  AS surv,
                   COUNT(*) OVER ()                              AS pool_size
            FROM pool)
        SELECT * FROM ranked WHERE steam_id = $1""", steam_id)
    weapons = await conn.fetch("""
        SELECT weapon AS name, COUNT(*) AS count FROM kills
        WHERE attacker_id = $1 GROUP BY weapon ORDER BY count DESC LIMIT 8""", steam_id)
    kill_places = await conn.fetch("""
        SELECT attacker_place AS name, COUNT(*) AS count FROM kills
        WHERE attacker_id = $1 AND attacker_place IS NOT NULL
        GROUP BY attacker_place ORDER BY count DESC LIMIT 8""", steam_id)
    death_places = await conn.fetch("""
        SELECT victim_place AS name, COUNT(*) AS count FROM kills
        WHERE victim_id = $1 AND victim_place IS NOT NULL
        GROUP BY victim_place ORDER BY count DESC LIMIT 8""", steam_id)
    return {"player": dict(p),
            # เรดาร์เป็น 0-100 ต่อแกน; None ถ้าคนนี้เล่นไม่ถึง 20 รอบ (ยังไม่อยู่ในกลุ่มเทียบ)
            "radar": ({k: round(float(radar[k]) * 100) for k in ("aim", "entry", "trade", "util", "clutch", "surv")}
                      | {"pool_size": radar["pool_size"], "min_rounds": 20}) if radar else None,
            "weapons": rows(weapons),
            "kill_places": rows(kill_places), "death_places": rows(death_places)}


@app.get("/api/heatmap")
async def api_heatmap(
    map_name: str = Query(..., alias="map", pattern=r"^de_[a-z0-9_]+$"),
    side: str | None = Query(None, pattern=r"^(ct|t)$"),
    _: dict = Depends(require_login),
    conn: asyncpg.Connection = Depends(db),
):
    """พิกัดที่คนตายบนแมพหนึ่ง สำหรับวาด heatmap — ?side=ct เอาเฉพาะคนตายฝั่ง CT

    พิกัดเป็นระบบของเกม หน้าเว็บต้องแปลงด้วย assets/radars.json (pos_x, pos_y, scale) ก่อนวาด
    """
    recs = await conn.fetch("""
        SELECT k.victim_x AS x, k.victim_y AS y, k.victim_side AS side,
               k.weapon, k.headshot, k.victim_place AS place
        FROM kills k JOIN rounds r ON r.id = k.round_id JOIN matches m ON m.id = r.match_id
        WHERE m.map_name = $1 AND k.victim_x IS NOT NULL
          AND ($2::text IS NULL OR k.victim_side = $2)""", map_name, side)
    return {"map": map_name, "side": side, "count": len(recs), "points": rows(recs)}


@app.get("/api/radar")
def api_radar(
    map_name: str = Query(..., alias="map", pattern=r"^de_[a-z0-9_]+$"),
    _: dict = Depends(require_login),
):
    """ค่าปรับเทียบภาพเรดาร์ของแมพ — ไว้ให้หน้าเว็บแปลงพิกัดในเกมเป็นพิกเซลบนภาพ

    ค่าทั้งหมดอ่านจาก assets/radars.json ซึ่งเป็นแหล่งความจริงแหล่งเดียวของทั้งระบบ
    (สคริปต์ฝั่ง Python ก็อ่านไฟล์เดียวกันนี้ ตัวเลขสองฝั่งจึงไม่มีทางเพี้ยนจากกัน)

    สูตรแปลงพิกัด — หน้าเว็บเอาไปใช้ตรง ๆ ได้เลย
        pixel_x = (game_x - pos_x) / scale
        pixel_y = (pos_y - game_y) / scale      <- แกน y กลับด้าน เพราะในเกม y เพิ่มขึ้นด้านบน
                                                   แต่บนภาพ y เพิ่มลงด้านล่าง
    """
    data = json.loads((ASSETS_DIR / "radars.json").read_text(encoding="utf-8"))
    cal = data.get(map_name)
    if not cal:
        raise HTTPException(404, f"ยังไม่มีค่าปรับเทียบเรดาร์ของ {map_name} ใน assets/radars.json")

    return {
        "map": map_name,
        "image": "/assets" + cal["image"],   # cal["image"] เก็บเป็น "/maps/de_mirage.png" -> เติม /assets ข้างหน้าให้เป็น URL จริง
        "size": cal["size"],                 # ภาพเป็นจัตุรัส ด้านละกี่พิกเซล
        "pos_x": cal["pos_x"],               # พิกัดเกมของมุมบนซ้ายของภาพ
        "pos_y": cal["pos_y"],
        "scale": cal["scale"],               # 1 พิกเซล = กี่หน่วยเกม
    }


# ===========================================================================
# ส่วนที่ 6 — วิเคราะห์แท็คติก (Tactical Analysis)
#
# ทุกตัวเลขในนี้คำนวณสด ๆ จากฐานข้อมูล ไม่มีค่าที่พิมพ์ทิ้งไว้เอง
# แนวคิดหลักคือ "การดวลแรกของรอบ" (opening duel) = คิลแรกสุดของรอบนั้น
# เพราะใครชนะการดวลแรก มักลากยาวไปชนะทั้งรอบ
# ===========================================================================

# SQL ก้อนนี้ถูกเอาไปแปะหน้าคำถามทุกข้อในหน้านี้ จึงเขียนไว้ที่เดียว
# DISTINCT ON (k.round_id) + ORDER BY k.round_id, k.tick
#   = "ของแต่ละรอบ เอาแถวเดียว คือแถวที่ tick น้อยที่สุด" -> ได้คิลแรกของรอบ
FIRST_KILL_CTE = """
WITH fk AS (
    SELECT DISTINCT ON (k.round_id)
           k.round_id,
           k.attacker_side,
           k.attacker_place,
           k.victim_place,
           k.tick,
           r.start_tick,
           r.winner_side,
           r.end_reason,
           r.bomb_plant_tick,
           m.tickrate
    FROM kills k
    JOIN rounds  r ON r.id = k.round_id
    JOIN matches m ON m.id = r.match_id
    WHERE m.map_name = $1
    ORDER BY k.round_id, k.tick
)
"""


@app.get("/api/tactical")
async def api_tactical(
    map_name: str = Query(..., alias="map", pattern=r"^de_[a-z0-9_]+$"),
    side: str = Query("t", pattern=r"^(ct|t)$"),        # มองจากมุมของฝั่งไหน
    _: dict = Depends(require_login),
    conn: asyncpg.Connection = Depends(db),
):
    """สรุปแท็คติกของแมพหนึ่ง มองจากมุมฝั่งที่เลือก (ct หรือ t)

    ตอบกลับ 5 ก้อน
      summary  ภาพรวม: กี่รอบ ชนะกี่รอบ ปักระเบิดกี่รอบ เวลาปะทะแรกเฉลี่ย
      opening  การดวลแรกของรอบ แยกตามตำแหน่งที่ยืน
      timing   ปะทะแรกเกิดตอนวินาทีที่เท่าไร แล้วรอบนั้นชนะไหม
      endings  รอบจบด้วยสาเหตุอะไรบ้าง
      bomb     ปักระเบิดแล้วชนะบ่อยกว่าไม่ปักไหม
    """
    # ---- 1) ภาพรวม -------------------------------------------------------
    summary = await conn.fetchrow(f"""
        {FIRST_KILL_CTE}
        SELECT COUNT(*)                                              AS rounds,
               COUNT(*) FILTER (WHERE winner_side = $2)              AS wins,
               COUNT(*) FILTER (WHERE bomb_plant_tick IS NOT NULL)   AS planted,
               ROUND(AVG((tick - start_tick)::numeric / tickrate), 1) AS avg_first_contact
        FROM fk
        WHERE start_tick IS NOT NULL""", map_name, side)
    # (tick - start_tick) / tickrate = จำนวน tick ตั้งแต่เริ่มรอบ หารด้วย tick ต่อวินาที = วินาที
    # FILTER (WHERE ...) = "นับเฉพาะแถวที่เข้าเงื่อนไข" เขียนสั้นกว่าใช้ CASE WHEN

    if not summary or not summary["rounds"]:
        raise HTTPException(404, f"ไม่มีข้อมูลรอบของแมพ {map_name}")

    # ---- 2) การดวลแรก แยกตามตำแหน่ง --------------------------------------
    # ถ้าฝั่งเราเป็นคนยิง -> ตำแหน่งของเราคือ attacker_place
    # ถ้าฝั่งเราเป็นคนโดนยิง -> ตำแหน่งของเราคือ victim_place
    opening = await conn.fetch(f"""
        {FIRST_KILL_CTE}
        SELECT COALESCE(CASE WHEN attacker_side = $2 THEN attacker_place
                             ELSE victim_place END, '(ไม่ทราบ)')     AS place,
               COUNT(*)                                              AS duels,
               COUNT(*) FILTER (WHERE attacker_side = $2)            AS won,
               COUNT(*) FILTER (WHERE winner_side  = $2)             AS round_wins
        FROM fk
        GROUP BY 1
        HAVING COUNT(*) >= 5
        ORDER BY duels DESC
        LIMIT 8""", map_name, side)
    # COALESCE(ก, ข) = ถ้า ก เป็น NULL ให้ใช้ ข แทน
    # HAVING COUNT(*) >= 5 = ตัดตำแหน่งที่เจอไม่ถึง 5 ครั้งทิ้ง เพราะเปอร์เซ็นต์จากข้อมูล 1-2 ครั้งเชื่อไม่ได้

    # ---- 3) ปะทะแรกเกิดตอนวินาทีที่เท่าไร ---------------------------------
    timing = await conn.fetch(f"""
        {FIRST_KILL_CTE}
        SELECT CASE WHEN sec < 20 THEN '0-20 วิ'
                    WHEN sec < 40 THEN '20-40 วิ'
                    WHEN sec < 60 THEN '40-60 วิ'
                    ELSE '60 วิ ขึ้นไป' END                          AS bucket,
               COUNT(*)                                              AS rounds,
               COUNT(*) FILTER (WHERE winner_side = $2)              AS wins
        FROM (SELECT (tick - start_tick)::numeric / tickrate AS sec, winner_side
              FROM fk WHERE start_tick IS NOT NULL) q
        GROUP BY 1
        ORDER BY MIN(sec)""", map_name, side)
    # ORDER BY MIN(sec) = เรียงกลุ่มตามวินาทีที่น้อยที่สุดในกลุ่มนั้น (ไม่งั้นจะเรียงตามตัวอักษรไทยมั่ว)

    # ---- 4) รอบจบด้วยอะไร -------------------------------------------------
    endings = await conn.fetch("""
        SELECT COALESCE(r.end_reason, '(ไม่ทราบ)')      AS reason,
               COUNT(*)                                 AS rounds,
               COUNT(*) FILTER (WHERE r.winner_side = $2) AS wins
        FROM rounds r JOIN matches m ON m.id = r.match_id
        WHERE m.map_name = $1
        GROUP BY 1 ORDER BY rounds DESC""", map_name, side)

    # ---- 5) ปักระเบิดแล้วต่างกันไหม ---------------------------------------
    bomb = await conn.fetch("""
        SELECT CASE WHEN r.bomb_plant_tick IS NOT NULL THEN 'ปักระเบิดแล้ว'
                    ELSE 'ไม่ได้ปัก' END                 AS state,
               COUNT(*)                                 AS rounds,
               COUNT(*) FILTER (WHERE r.winner_side = $2) AS wins
        FROM rounds r JOIN matches m ON m.id = r.match_id
        WHERE m.map_name = $1
        GROUP BY 1 ORDER BY rounds DESC""", map_name, side)

    return {
        "map": map_name,
        "side": side,
        "summary": {
            "rounds": summary["rounds"],
            "wins": summary["wins"],
            "planted": summary["planted"],
            "avg_first_contact": float(summary["avg_first_contact"] or 0),
        },
        "opening": rows(opening),
        "timing": rows(timing),
        "endings": rows(endings),
        "bomb": rows(bomb),
    }


# ===========================================================================
# ส่วนที่ 7 — ผลจากโมเดล ML
#
# เราไม่เทรนโมเดลในเซิร์ฟเวอร์นี้ (ช้าและกินแรม) สคริปต์ใน research/ เทรนเสร็จ
# แล้วเขียนคำตอบทั้งหมดลงไฟล์ json ไว้ให้ เซิร์ฟเวอร์แค่หยิบไฟล์นั้นส่งต่อ
#     python research/round_win.py   ->  output/round_win.json
#     python research/grid_ml.py     ->  output/grid_ml.json
# ===========================================================================

def read_output_json(filename: str, how_to_make: str) -> dict:
    """อ่านไฟล์ json ในโฟลเดอร์ output/ — ถ้ายังไม่มี บอกวิธีสร้างไปเลย"""
    f = ROOT / "output" / filename
    if not f.exists():
        raise HTTPException(404, f"ยังไม่มีไฟล์ output/{filename} — สร้างด้วย: {how_to_make}")
    return json.loads(f.read_text(encoding="utf-8"))   # loads = แปลงข้อความ json ให้เป็น dict


@app.get("/api/ml/round-win")
def api_ml_round_win(_: dict = Depends(require_login)):
    """โมเดลโอกาสชนะรอบ — ตารางเปิดค่า P(CT ชนะ) ของทุกสถานะที่เป็นไปได้

    คีย์ในตารางหน้าตาแบบ "3v2|0|20-40s" = CT เหลือ 3, T เหลือ 2, ยังไม่ปักระเบิด, วินาทีที่ 20-40
    """
    return read_output_json("round_win.json", "python research/round_win.py")


@app.get("/api/ml/grid")
def api_ml_grid(_: dict = Depends(require_login)):
    """โมเดลกริด — แบ่งแมพเป็นช่อง ๆ แล้วทายว่าการดวลในช่องนั้นฝั่งไหนได้เปรียบ

    ตัดฟิลด์หนัก ๆ ออกก่อนส่ง (ภาพ mask กับจุดตายดิบ 7 พันจุด) เพราะหน้าเว็บไม่ได้ใช้
    เหลือแต่คะแนนโมเดลกับค่ารายช่อง ไฟล์จะได้เล็กลงจาก 160 KB เหลือ ~40 KB
    """
    d = read_output_json("grid_ml.json", "python research/grid_ml.py")
    for heavy in ("play_mask", "kills"):
        d.pop(heavy, None)          # .pop(คีย์, None) = ลบคีย์นี้ทิ้ง ถ้าไม่มีก็ไม่ต้องพัง
    d["cells"] = sorted(d["cells"], key=lambda c: -c["kills"])[:40]
    # sorted(..., key=lambda c: -c["kills"]) = เรียงจากช่องที่มีคนตายเยอะสุดไปน้อยสุด (ติดลบ = กลับด้าน)
    # [:40] = เอาแค่ 40 ช่องแรก พอสำหรับโชว์ตาราง
    return d


# ---------------------------------------------------------------------------
# ส่วนที่ 8 — รับไฟล์เดโมจากผู้ใช้
#
# ทางเดินของไฟล์หนึ่งไฟล์ ทำครบจบในคำขอเดียว ไม่มีคิวงานเบื้องหลัง
#     อัปโหลด -> demos/X.dem -> parse_demo() -> output/json/X.json -> INSERT -> ตอบสรุปกลับ
#
# ทำไมถึงทำแบบซิงโครนัส (รอจนเสร็จในคำขอเดียว)
#     parse ใช้เวลาไม่กี่วินาทีต่อไฟล์ และหน้าเว็บส่งทีละไฟล์อยู่แล้ว
#     การใส่คิวงาน (Celery / RQ / Redis) จะเพิ่มบริการที่ต้องดูแลอีกตัวโดยที่ยังไม่จำเป็น
#     ถ้าวันหนึ่งเดโมใหญ่จนคำขอ timeout ให้ย้ายแค่สองบรรทัด parse + load ไปไว้ใน worker
#     ส่วนที่เหลือของ endpoint นี้ไม่ต้องแก้เลย
#
# เส้นทางนี้ใช้ฟังก์ชันตัวเดียวกับ CLI ทั้งคู่ (parse_demo, load_match_json)
# เดโมที่อัปผ่านเว็บกับที่โหลดด้วยมือจึงได้ข้อมูลเหมือนกันเป๊ะ ไม่มีทางเพี้ยนคนละทาง
# ---------------------------------------------------------------------------
class DemoParseError(Exception):
    """แกะเดโมไม่สำเร็จ — ไฟล์ไม่ใช่เดโม CS2 หรือเสียหาย"""


class DemoParserMissing(Exception):
    """เครื่องนี้ยังไม่ได้ติดตั้ง awpy / demoparser2"""


def parse_demo_isolated(path: Path) -> dict:
    """เรียก parse_demo แล้วห่อความผิดพลาด "ทุกชนิด" ให้กลายเป็น Exception ธรรมดา

    ทำไมต้องห่อในฟังก์ชันนี้ ไม่ใช่ห่อด้วย try ที่ endpoint
        demoparser2 ข้างใน awpy เขียนด้วย Rust เจอไฟล์ที่ไม่ใช่เดโมเมื่อไรมันจะ panic
        PyO3 แปลง panic นั้นเป็น pyo3_runtime.PanicException ซึ่งสืบทอดจาก
        BaseException "ตรง ๆ" ไม่ผ่าน Exception  (mro: PanicException -> BaseException -> object)

        ตัวฟังก์ชันนี้ถูกเรียกผ่าน run_in_threadpool คือรันอยู่คนละเธรดกับ event loop
        พอ BaseException ที่ไม่ใช่ Exception ข้ามเธรดกลับมา anyio จะไม่ส่งต่อให้
        โค้ดที่ await อยู่ แต่ยกขึ้นไปเป็น BaseExceptionGroup เหนือ endpoint ขึ้นไปอีกชั้น
        เขียน except BaseException คร่อม await ไว้ก็ไม่มีทางเห็นมัน — กลายเป็น 500 ทุกครั้ง
        และไฟล์ขยะค้างในดิสก์เพราะโค้ดเก็บกวาดไม่ได้ทำงาน

        ดักตั้งแต่ยังอยู่ในเธรดเดียวกันกับที่ panic เกิด จึงเป็นที่เดียวที่ดักได้จริง

    เคสจริงที่เจอ: ไฟล์ขนาด 15 ไบต์ -> PanicException: range end index 16 out of range
    for slice of length 15  (Rust อ่าน header 16 ไบต์จากไฟล์ที่สั้นกว่านั้น)
    """
    try:
        from backend.parser.service import parse_demo
    except ImportError as e:
        raise DemoParserMissing(f"ไม่พบ {e.name}") from None

    try:
        return parse_demo(path)
    except (KeyboardInterrupt, SystemExit):     # สัญญาณสั่งปิดโปรแกรม ต้องปล่อยผ่าน ห้ามกลืน
        raise
    except BaseException as e:
        raise DemoParseError(f"{type(e).__name__}: {e}") from None


def save_upload(file: UploadFile, dest: Path) -> int:
    """เขียนไฟล์ที่อัปโหลดลงดิสก์ทีละก้อน คืนขนาดเป็นไบต์

    อ่านทีละ 1 MB ไม่ใช่ทีเดียวทั้งไฟล์ เพราะเดโมใหญ่หลายร้อยเมกะไบต์
    ถ้าอ่านรวดเดียวจะกินแรมเท่าขนาดไฟล์ อัปพร้อมกันสองคนก็เริ่มเสี่ยงแล้ว

    เขียนลงชื่อ .part ก่อนแล้วค่อยเปลี่ยนชื่อตอนจบ ไฟล์ที่อัปไม่สำเร็จ
    จึงไม่มีทางถูกเข้าใจผิดว่าเป็นเดโมที่สมบูรณ์
    """
    limit = MAX_DEMO_MB * 1024 * 1024
    part = dest.with_suffix(dest.suffix + ".part")
    size = 0
    try:
        with open(part, "wb") as out:
            while chunk := file.file.read(1024 * 1024):
                size += len(chunk)
                if size > limit:
                    raise HTTPException(413, f"ไฟล์ใหญ่เกิน {MAX_DEMO_MB} MB")
                out.write(chunk)
        if size == 0:
            raise HTTPException(400, "ไฟล์ว่าง")
        try:
            part.replace(dest)      # .replace() = เปลี่ยนชื่อทับของเดิมได้ และเป็น atomic บนดิสก์เดียวกัน
        except PermissionError:     # Windows: ไฟล์ปลายทางถูกเปิดอยู่ (เช่น worker กำลังแกะไฟล์เดิม) — ไม่ใช่ 500
            raise HTTPException(409, "ไฟล์ชื่อนี้กำลังถูกใช้งานอยู่ (อาจกำลังถูกแกะ) — รอให้เสร็จแล้วลองใหม่")
        return size
    finally:
        part.unlink(missing_ok=True)   # เหลือ .part ค้างอยู่ = อัปไม่สำเร็จ เก็บกวาดทิ้ง


@app.post("/api/demos")
async def api_upload_demo(
    file: UploadFile = File(..., description="ไฟล์ .dem หนึ่งไฟล์"),
    force: str = Form("0"),                     # "1" = แมตช์นี้เคยโหลดแล้วให้ลบของเดิมทิ้งแล้วโหลดใหม่
    _: dict = Depends(require_login),
    conn: asyncpg.Connection = Depends(db),
):
    """รับเดโมหนึ่งไฟล์ เก็บลงดิสก์ แล้วส่งงานแกะเข้าคิว — ตอบ 202 ทันที ไม่รอแกะ

    ส่งทีละไฟล์ หน้าเว็บเป็นคนวนส่งเองถ้าผู้ใช้ลากมาหลายไฟล์
    ทำแบบนี้เพื่อให้แต่ละไฟล์มีสถานะของตัวเอง ไฟล์หนึ่งพังก็ไม่ลากไฟล์อื่นล้มไปด้วย
    """
    replace = force == "1"

    # ---- 1) ตรวจชื่อไฟล์ก่อนแตะดิสก์ ------------------------------------
    # Path(...).name = ตัดพาธที่ติดมากับชื่อไฟล์ทิ้งให้เหลือแต่ชื่อจริง
    # เบราว์เซอร์ปกติไม่ส่งพาธมาอยู่แล้ว แต่คนที่ยิง API ตรง ๆ ส่งอะไรมาก็ได้
    name = Path(file.filename or "").name
    if not DEMO_NAME_RE.match(name):
        raise HTTPException(400, "รับเฉพาะไฟล์ .dem และชื่อไฟล์ใช้ได้แค่ตัวอักษร ตัวเลข . _ - ( )")

    # ---- 2) เคยโหลดแมตช์นี้ไปแล้วหรือยัง --------------------------------
    # เช็กก่อนแตะดิสก์ — แมตช์ที่เคยพัง (error) ยอมให้ส่งใหม่ได้เลยโดยไม่ต้องติ๊ก "โหลดทับ"
    existing = await conn.fetchrow("SELECT id, status FROM matches WHERE demo_file = $1;", name)
    if existing and not replace and existing["status"] != "error":
        raise HTTPException(409, f"แมตช์ {name} มีอยู่ในระบบแล้ว (Match ID: {existing['id']}, สถานะ {existing['status']}) "
                                 "— ติ๊ก \"โหลดทับของเดิม\" ถ้าต้องการโหลดใหม่")

    # ---- 3) เขียนไฟล์ลงดิสก์ --------------------------------------------
    DEMOS_DIR.mkdir(parents=True, exist_ok=True)
    dem_path = DEMOS_DIR / name
    size = await run_in_threadpool(save_upload, file, dem_path)

    # ---- 4) สร้าง/รีเซ็ตแถว matches เป็น queued แล้วส่งงานเข้าคิว ------------
    # ตัวเซิร์ฟเวอร์ไม่แกะเดโมเองอีกแล้ว (เดโมใหญ่แกะเป็นนาที request จะค้าง)
    # worker (python -m backend.worker) หยิบงานไปทำ แล้วหน้าเว็บ poll ที่ /api/matches/{id}/status
    if existing:
        match_id = existing["id"]     # เก็บ id เดิมไว้ ลิงก์/บุ๊กมาร์กเก่าจะได้ไม่พัง
        await conn.execute("""
            UPDATE matches SET status = 'queued', error_message = NULL, job_id = NULL,
                               started_at = NULL, finished_at = NULL
            WHERE id = $1;
        """, match_id)
    else:
        match_id = await conn.fetchval(
            "INSERT INTO matches (demo_file, status) VALUES ($1, 'queued') RETURNING id;", name)

    try:
        job_id = await run_in_threadpool(enqueue_parse, match_id)
    except QueueUnavailable as e:
        await conn.execute("UPDATE matches SET status = 'error', error_message = $2 WHERE id = $1;", match_id, str(e))
        log(f"[UPLOAD] {name}: {e}")
        raise HTTPException(503, f"รับไฟล์แล้วแต่ส่งงานเข้าคิวไม่ได้ — เปิด Redis ด้วย docker compose up -d redis ({e})")
    await conn.execute("UPDATE matches SET job_id = $2 WHERE id = $1;", match_id, job_id)
    log(f"[UPLOAD] {name} ({size / 1024 / 1024:.1f} MB) -> match {match_id} เข้าคิว job {job_id}")

    # 202 Accepted = รับเรื่องแล้ว แต่ยังทำไม่เสร็จ ไปถามต่อที่ status_url
    return JSONResponse(status_code=202, content={
        "match_id": match_id,
        "demo_file": name,
        "size_mb": round(size / 1024 / 1024, 1),
        "replaced": bool(existing),
        "status": "queued",
        "job_id": job_id,
        "status_url": f"/api/matches/{match_id}/status",
    })


# ---------------------------------------------------------------------------
# ส่วนที่ 9 — สั่งเทรนโมเดลใหม่จากหน้าเว็บ
#
# โมเดลทั้งสองเป็นสคริปต์ที่รันจบในตัว (research/round_win.py, research/grid_ml.py)
# จึงเรียกเป็นโปรเซสลูกด้วย interpreter ตัวเดียวกับเซิร์ฟเวอร์ ไม่ import เข้ามา เพราะ
#   - สคริปต์พวกนั้นมีโค้ดระดับบนสุด import แล้วรันทันที
#   - ใช้ matplotlib / sklearn หนัก แยกโปรเซสแล้วเสร็จก็คืนแรมทั้งหมด พังก็ไม่ลากเซิร์ฟเวอร์ล้ม
#
# --source=db บังคับให้อ่านจาก PostgreSQL = ทุกแมตช์ที่อัปโหลดเข้ามาถูกนับด้วย
# เสร็จแล้วเขียนทับ output/*.json ซึ่ง /api/ml/* อ่านทุกครั้งที่ถูกเรียก หน้าเว็บจึงเห็นผลใหม่ทันที
#
# กันกดซ้ำด้วย lock ตัวเดียว — เทรนพร้อมกันสองรอบจะแย่งกันเขียนไฟล์ผลลัพธ์
# ---------------------------------------------------------------------------
RETRAIN_LOCK = threading.Lock()
RETRAIN_SCRIPTS = ("research/round_win.py", "research/grid_ml.py")


def run_training() -> list[dict]:
    """รันสคริปต์โมเดลทีละตัวจากฐานข้อมูล คืน log ท้าย ๆ ของแต่ละตัว หยุดทันทีที่ตัวไหนล้ม"""
    results = []
    for script in RETRAIN_SCRIPTS:
        proc = subprocess.run(
            [sys.executable, script, "--source=db"],
            cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600,
        )
        results.append({"script": script, "ok": proc.returncode == 0,
                        "log": (proc.stdout + proc.stderr)[-1500:]})
        if proc.returncode != 0:
            break
    return results


@app.post("/api/ml/retrain")
async def api_ml_retrain(_: dict = Depends(require_login)):
    """เทรนโมเดลทั้งสองใหม่จากทุกแมตช์ในฐานข้อมูล แล้วเขียนทับ output/*.json"""
    if not RETRAIN_LOCK.acquire(blocking=False):
        raise HTTPException(409, "กำลังเทรนอยู่ — รอให้รอบก่อนหน้าเสร็จก่อน")
    try:
        results = await run_in_threadpool(run_training)
    finally:
        RETRAIN_LOCK.release()

    failed = next((r for r in results if not r["ok"]), None)
    if failed:
        log(f"[RETRAIN] {failed['script']} ล้มเหลว:\n{failed['log']}")
        raise HTTPException(500, f"{failed['script']} ล้มเหลว — {failed['log'][-400:]}")
    log(f"[RETRAIN] เทรนใหม่สำเร็จ: {', '.join(r['script'] for r in results)}")
    return {"ok": True, "results": results}


# ---------------------------------------------------------------------------
# ส่วนที่ 10 — Round Review: ไล่ดูทีละรอบว่าใครตายที่ไหนเมื่อไหร่ + บริบทจาก research/grid_ml1.py
#
# คีย์ของแมตช์คือชื่อไฟล์เดโม (ตาม brief) — ใช้ prefix /api/review/ เพราะ /api/matches/{match_id}/rounds
# มีอยู่แล้ว (ไทม์ไลน์ของโมเดลโอกาสชนะรอบ) และรับเป็นเลข id
# ข้อมูลกริดอ่านจาก output/grid_ml1.json ที่ cache ไว้ในหน่วยความจำ (backend/review.py) ไม่รันโมเดลตอน request
# ---------------------------------------------------------------------------
async def _review_match(conn: asyncpg.Connection, demo_file: str) -> dict:
    m = await conn.fetchrow("""
        SELECT id, demo_file, map_name, tickrate, team_a, team_b, status FROM matches WHERE demo_file = $1""", demo_file)
    if not m:
        raise HTTPException(404, f"ไม่พบแมตช์ {demo_file}")
    if m["status"] != "done":
        raise HTTPException(409, f"แมตช์ {demo_file} ยังไม่พร้อม (สถานะ {m['status']})")
    return dict(m)


async def _review_roster(conn: asyncpg.Connection, match_id: int) -> list[dict]:
    """ทุกคนในแมตช์ + ทีม — แมตช์ที่โหลดก่อน migration 0004 (team_clan ว่าง) ผูกทีมจาก player_rounds ตอนนี้แทน"""
    rows = await conn.fetch("""
        SELECT mp.steam_id, p.name, mp.team_clan FROM match_players mp JOIN players p USING (steam_id)
        WHERE mp.match_id = $1""", match_id)
    roster = [{"steam_id": r["steam_id"], "name": r["name"], "team": r["team_clan"]} for r in rows]
    if roster and all(r["team"] for r in roster):
        return roster
    pr = await conn.fetch("""
        SELECT pr.steam_id, r.round_num, pr.side, p.name FROM player_rounds pr
        JOIN rounds r ON r.id = pr.round_id JOIN players p USING (steam_id) WHERE r.match_id = $1""", match_id)
    team_of = assign_teams([dict(x) for x in pr])
    names = {x["steam_id"]: x["name"] for x in pr}
    return [{"steam_id": sid, "name": names.get(sid), "team": team} for sid, team in team_of.items()]


@app.get("/api/review/grid")
def api_review_grid(map: str = Query(..., description="เช่น de_mirage"), _: dict = Depends(require_login)):
    """ช่องกริด (จัดกลุ่มแล้ว) + วง hotspot เป็นพิกเซลบนภาพเรดาร์ — ไว้ให้ toggle ซ้อนบนแผนที่"""
    frame = radar_frame(map)
    model = load_grid_model()
    if frame is None or model is None or model.map_name != map:
        return {"available": False, "reason": "ยังไม่มีผล research/grid_ml1.py ของแมพนี้"}
    return grid_overlay(model, frame)


@app.get("/api/review/{demo_file}/rounds")
async def api_review_rounds(demo_file: str, _: dict = Depends(require_login), conn: asyncpg.Connection = Depends(db)):
    """รายรอบของแมตช์: ใครชนะ จบด้วยอะไร ตายกี่คน คนแรกตายวินาทีที่เท่าไหร่"""
    m = await _review_match(conn, demo_file)
    rounds_ = await conn.fetch("""
        SELECT round_num, start_tick, winner_side, end_reason FROM rounds WHERE match_id = $1 ORDER BY round_num""", m["id"])
    agg = await conn.fetch("""
        SELECT r.round_num, COUNT(k.id) AS n, MIN(k.tick) AS first_tick
        FROM rounds r LEFT JOIN kills k ON k.round_id = r.id WHERE r.match_id = $1 GROUP BY r.round_num""", m["id"])
    return build_round_list(rows(rounds_), {a["round_num"]: a["first_tick"] for a in agg if a["first_tick"] is not None},
                            {a["round_num"]: a["n"] for a in agg}, m["tickrate"])


@app.get("/api/review/{demo_file}/rounds/{round_num}")
async def api_review_round(demo_file: str, round_num: int, _: dict = Depends(require_login),
                           conn: asyncpg.Connection = Depends(db)):
    """รอบเดียวแบบละเอียด: ทีม / การตายทุกครั้ง (พิกัด + พิกเซลบนเรดาร์) / บริบทจาก grid_ml1 / สรุปรอบ"""
    m = await _review_match(conn, demo_file)
    rnd = await conn.fetchrow("""
        SELECT id, round_num, start_tick, winner_side, end_reason, bomb_plant_tick, bomb_plant_x, bomb_plant_y, bomb_site
        FROM rounds WHERE match_id = $1 AND round_num = $2""", m["id"], round_num)
    if not rnd:
        raise HTTPException(404, f"แมตช์นี้ไม่มีรอบที่ {round_num}")
    roster = await _review_roster(conn, m["id"])
    in_round = await conn.fetch("SELECT steam_id, side, survived FROM player_rounds WHERE round_id = $1", rnd["id"])
    kills = await conn.fetch("""
        SELECT k.*, pa.name AS attacker_name, pv.name AS victim_name, ps.name AS assister_name
        FROM kills k
        LEFT JOIN players pa ON pa.steam_id = k.attacker_id
        LEFT JOIN players pv ON pv.steam_id = k.victim_id
        LEFT JOIN players ps ON ps.steam_id = k.assister_id
        WHERE k.round_id = $1 ORDER BY k.tick, k.id""", rnd["id"])
    return build_round_detail(match=m, rnd=dict(rnd), roster=roster, in_round=rows(in_round), kills=rows(kills),
                              frame=radar_frame(m["map_name"]), model=load_grid_model())
