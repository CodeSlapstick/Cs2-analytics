# -*- coding: utf-8 -*-
"""
backend/app.py — "หลังบ้าน" (backend) ของเว็บ CS2 Analytics

เปรียบเทียบง่าย ๆ: ไฟล์นี้คือ "พนักงานหลังเคาน์เตอร์"
  - หน้าเว็บ (frontend/) = ลูกค้าที่มายืนหน้าเคาน์เตอร์
  - ไฟล์นี้ = พนักงานที่คอยรับคำสั่ง ไปหยิบของจากคลัง (PostgreSQL) แล้วส่งกลับไปให้

หน้าที่ของไฟล์นี้มี 4 อย่าง
  1) ส่งหน้าเว็บ (ไฟล์ .html ใน frontend/pages/) ให้เบราว์เซอร์
  2) พาผู้ใช้ไปล็อกอินที่ Steam แล้วรับผลกลับมา
  3) จำว่า "ใครล็อกอินอยู่" ด้วยคุกกี้ (cookie = บัตรคิวที่ติดตัวลูกค้าไว้)
  4) ตอบ /api/* — ดึงสถิติจากฐานข้อมูลแล้วส่งเป็น JSON ให้หน้าเว็บเอาไปวาด

ข้อมูลอยู่ใน PostgreSQL (โครงอยู่ที่ backend/schema.sql โหลดด้วย backend/load_kills.py)
ไฟล์นี้ไม่อ่าน csv เองแล้ว — อ่านผ่าน SQL อย่างเดียว จะได้ filter/รวมข้อมูลได้เร็วโดยไม่ต้องโหลดทั้งตารางเข้าแรม

รัน:  python -m uvicorn backend.app:app --reload
เปิด: http://localhost:8000
"""

# ---------------------------------------------------------------------------
# ส่วนที่ 0 — ขนเครื่องมือเข้ามาใช้
# ---------------------------------------------------------------------------
import os
import re
import secrets
import sys
import urllib.parse
from contextlib import asynccontextmanager
from pathlib import Path

import asyncpg
import httpx                   # httpx = โทรศัพท์ ใช้ "โทร" ไปถามเว็บอื่น (ที่นี่คือเซิร์ฟเวอร์ Steam)
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from itsdangerous import BadSignature, URLSafeSerializer   # เครื่อง "เซ็นชื่อ" ข้อมูลในคุกกี้ กันคนปลอมแปลง

from backend.db import DATABASE_URL, apply_schema, create_pool, redacted_url  # noqa: F401  (load_dotenv ทำงานตอน import)

# ---------------------------------------------------------------------------
# ส่วนที่ 1 — ค่าตั้งต้น (CONFIG) อยากแก้อะไรแก้ตรงนี้ที่เดียว
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent   # โฟลเดอร์โปรเจกต์
FRONTEND = ROOT / "frontend"                    # โฟลเดอร์ของหน้าเว็บทั้งหมด
PAGES_DIR = FRONTEND / "pages"                  # หน้า .html ที่ไฟล์นี้เสิร์ฟให้เบราว์เซอร์
STATIC_DIR = FRONTEND / "static"                # ไฟล์นิ่ง ๆ (.css .js รูป)

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
STEAM_API_KEY = os.environ.get("STEAM_API_KEY", "")             # กุญแจ Steam ขอฟรีที่ steamcommunity.com/dev/apikey ("" = ยังไม่มี)
BASE_URL = os.environ.get("BASE_URL", "http://localhost:8000")  # ที่อยู่เว็บเรา ใช้บอก Steam ว่า "ล็อกอินเสร็จให้ส่งกลับมาที่นี่"
SECRET_KEY = os.environ.get("SECRET_KEY") or secrets.token_hex(32)  # กุญแจเซ็นคุกกี้ ถ้าไม่ตั้งไว้ = สุ่มใหม่ทุกครั้งที่รัน (ล็อกอินจะหลุดตอนรีสตาร์ต)
ALLOW_DEV_LOGIN = os.environ.get("ALLOW_DEV_LOGIN", "1") == "1"     # "โหมดทดสอบ" ให้พิมพ์เลข Steam เข้าเองได้ โดยไม่ต้องมีกุญแจ API

COOKIE_NAME = "cs2_session"        # ชื่อคุกกี้ (บัตรคิว) ที่เราจะติดให้ผู้ใช้
COOKIE_MAX_AGE = 60 * 60 * 24 * 7  # อายุคุกกี้ 1 สัปดาห์

STEAM_OPENID_URL = "https://steamcommunity.com/openid/login"  # ประตูล็อกอินของ Steam (มาตรฐานชื่อ OpenID 2.0)
STEAM_ID_RE = re.compile(r"^7656119\d{10}$")                  # แบบแผนของ SteamID64: ขึ้นต้น 7656119 แล้วตามด้วยเลข 10 ตัว
SIDE_RE = re.compile(r"^(ct|t)$")

signer = URLSafeSerializer(SECRET_KEY, salt="cs2-session")    # "ตราประทับ" ไว้เซ็นและตรวจคุกกี้ด้วยกุญแจลับ


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


app = FastAPI(title="CS2 Analytics API", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")  # URL ที่ขึ้นต้นด้วย /static ให้ไปหยิบไฟล์จริงใน frontend/static/


async def db(request: Request) -> asyncpg.Connection:
    """Dependency: ขอ connection จากบ่อหนึ่งเส้นให้ route นี้ใช้ แล้วคืนอัตโนมัติเมื่อจบ"""
    pool: asyncpg.Pool | None = request.app.state.pool
    if pool is None:
        raise HTTPException(503, "ฐานข้อมูลยังไม่พร้อม — เปิดด้วย docker compose up -d db แล้วรีสตาร์ตเซิร์ฟเวอร์")
    async with pool.acquire() as conn:
        yield conn


# ---------------------------------------------------------------------------
# ส่วนที่ 3 — เรื่องคุกกี้ "ใครล็อกอินอยู่"
# ---------------------------------------------------------------------------
def make_session_cookie(response, user: dict) -> None:
    """เอาข้อมูลผู้ใช้ใส่ซอง เซ็นชื่อกำกับ แล้วแปะเป็นคุกกี้ติดตัวเบราว์เซอร์"""
    token = signer.dumps(user)          # แปลง dict เป็นข้อความ + เซ็นชื่อต่อท้าย (ถ้ามีคนแอบแก้ข้างใน ลายเซ็นจะไม่ตรง)
    response.set_cookie(
        COOKIE_NAME, token,
        max_age=COOKIE_MAX_AGE,
        httponly=True,                  # JavaScript อ่านคุกกี้นี้ไม่ได้ (กันสคริปต์แปลกปลอมขโมย)
        samesite="lax",                 # ส่งคุกกี้เฉพาะตอนอยู่เว็บเรา กันเว็บอื่นยืมใช้
    )


def read_session(request: Request) -> dict | None:
    """แกะคุกกี้ออกมาดูว่าเป็นใคร — ถ้าไม่มีหรือถูกปลอม จะคืน None (แปลว่า "ยังไม่ล็อกอิน")"""
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None
    try:
        return signer.loads(token)             # ตรวจลายเซ็นก่อน ถ้าผ่านค่อยแปลงกลับเป็น dict
    except BadSignature:                       # ลายเซ็นไม่ตรง = มีคนแก้คุกกี้ -> ถือว่าไม่ล็อกอิน
        return None


def require_login(request: Request) -> dict:
    """Dependency: route ไหนใส่อันนี้ = ต้องล็อกอินก่อน ไม่งั้นตอบ 401 ทันที"""
    user = read_session(request)
    if not user:
        raise HTTPException(401, "ยังไม่ได้ล็อกอิน")
    return user


# ---------------------------------------------------------------------------
# ส่วนที่ 4 — ส่งหน้าเว็บ
# ---------------------------------------------------------------------------
@app.get("/")
def page_login():
    """หน้าแรก = หน้าล็อกอิน"""
    return FileResponse(PAGES_DIR / "login.html")


@app.get("/main")
def page_main():
    """หน้าหลักหลังล็อกอิน (ตัว JS ในหน้าจะเช็คเองว่าล็อกอินแล้วหรือยัง)"""
    return FileResponse(PAGES_DIR / "main.html")


# ---------------------------------------------------------------------------
# ส่วนที่ 5 — ล็อกอิน / ออกจากระบบ
# ---------------------------------------------------------------------------
@app.get("/auth/steam/login")
def steam_login():
    """พาผู้ใช้ไปหน้าล็อกอินของ Steam (OpenID 2.0) พร้อมบอกว่าเสร็จแล้วให้ส่งกลับมาที่ /auth/steam/callback"""
    params = {
        "openid.ns": "http://specs.openid.net/auth/2.0",
        "openid.mode": "checkid_setup",
        "openid.return_to": f"{BASE_URL}/auth/steam/callback",
        "openid.realm": BASE_URL,
        "openid.identity": "http://specs.openid.net/auth/2.0/identifier_select",
        "openid.claimed_id": "http://specs.openid.net/auth/2.0/identifier_select",
    }
    return RedirectResponse(f"{STEAM_OPENID_URL}?{urllib.parse.urlencode(params)}")


@app.get("/auth/steam/callback")
async def steam_callback(request: Request, conn: asyncpg.Connection = Depends(db)):
    """Steam ส่งผู้ใช้กลับมาที่นี่ — ต้องถาม Steam ซ้ำอีกรอบว่า "ข้อมูลชุดนี้มาจากคุณจริงไหม" กันคนปลอม URL"""
    params = dict(request.query_params)
    params["openid.mode"] = "check_authentication"      # เปลี่ยนโหมดเป็น "ขอตรวจสอบ" แล้วส่งกลับไปให้ Steam ทั้งชุด
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.post(STEAM_OPENID_URL, data=params)
    if "is_valid:true" not in r.text:
        return JSONResponse({"error": "Steam ไม่ยืนยันการล็อกอินนี้"}, status_code=401)

    claimed = params.get("openid.claimed_id", "")       # หน้าตา https://steamcommunity.com/openid/id/7656119...
    steamid = claimed.rsplit("/", 1)[-1]
    if not STEAM_ID_RE.match(steamid):
        return JSONResponse({"error": "SteamID ที่ได้กลับมาผิดรูปแบบ"}, status_code=400)

    profile = await fetch_steam_profile(steamid)
    user = {"steamid": steamid, **profile, "mode": "steam"}
    await save_user(conn, user)

    response = RedirectResponse("/main", status_code=303)
    make_session_cookie(response, user)
    return response


@app.post("/auth/dev-login")
async def dev_login(request: Request, conn: asyncpg.Connection = Depends(db)):
    """โหมดทดสอบ: พิมพ์เลข Steam64 เข้าเองได้เลย ไม่ต้องมีกุญแจ API (ไว้ตอนพัฒนา/ตอนนำเสนอ)"""
    if not ALLOW_DEV_LOGIN:
        return JSONResponse({"error": "dev login ถูกปิดอยู่"}, status_code=403)

    body = await request.json()
    steamid = str(body.get("steamid", "")).strip()
    if not STEAM_ID_RE.match(steamid):              # ตรวจรูปแบบก่อนเสมอ อย่าเชื่อสิ่งที่ผู้ใช้พิมพ์
        return JSONResponse({"error": "SteamID64 ต้องเป็นตัวเลข 17 หลักขึ้นต้นด้วย 7656119"}, status_code=400)

    profile = await fetch_steam_profile(steamid)
    user = {"steamid": steamid, **profile, "mode": "dev"}   # mode="dev" ไว้ให้หน้าเว็บโชว์ป้าย "โหมดทดสอบ"
    await save_user(conn, user)

    response = JSONResponse({"ok": True, "user": user})
    make_session_cookie(response, user)
    return response


@app.post("/auth/logout")
def logout():
    """ลบคุกกี้ = ออกจากระบบ"""
    response = JSONResponse({"ok": True})
    response.delete_cookie(COOKIE_NAME)
    return response


async def save_user(conn: asyncpg.Connection, user: dict) -> None:
    """จดว่าใครล็อกอินเข้ามาลงตาราง users — เคยมีแล้วก็อัปเดตชื่อ/รูป/เวลาล่าสุด"""
    await conn.execute(
        """
        INSERT INTO users (steamid, name, avatar, profile_url, mode, last_login)
        VALUES ($1, $2, $3, $4, $5, CURRENT_TIMESTAMP)
        ON CONFLICT (steamid) DO UPDATE
        SET name = EXCLUDED.name, avatar = EXCLUDED.avatar, profile_url = EXCLUDED.profile_url,
            mode = EXCLUDED.mode, last_login = CURRENT_TIMESTAMP
        """,
        str(user.get("steamid", "")), str(user.get("name", "")), str(user.get("avatar", "")),
        str(user.get("profile_url", "")), str(user.get("mode", "dev")),
    )
    log(f"[DB] บันทึกผู้ใช้ {user.get('steamid')} ({user.get('mode')})")


async def fetch_steam_profile(steamid: str) -> dict:
    """ขอชื่อ/รูปโปรไฟล์จาก Steam Web API — ถ้าไม่มีกุญแจหรือโทรไม่ติด ใช้ค่าสำรองแทน"""
    fallback = {
        "name": f"ผู้เล่น {steamid[-4:]}",
        "avatar": "",
        "profile_url": f"https://steamcommunity.com/profiles/{steamid}",
    }
    if not STEAM_API_KEY:
        return fallback
    url = "https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v2/"
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            r = await client.get(url, params={"key": STEAM_API_KEY, "steamids": steamid})
        p = r.json()["response"]["players"][0]
        return {"name": p.get("personaname", fallback["name"]),
                "avatar": p.get("avatarfull", ""),
                "profile_url": p.get("profileurl", fallback["profile_url"])}
    except Exception:
        return fallback


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
        return {"ok": True, "db": "ต่อได้", "matches": n["matches"], "kills": n["kills"]}
    except Exception as e:
        return JSONResponse({"ok": False, "db": str(e)}, status_code=503)


@app.get("/api/me")
def api_me(user: dict = Depends(require_login)):
    """หน้าเว็บถามว่า 'ตอนนี้ฉันล็อกอินอยู่ไหม เป็นใคร'"""
    return {"user": user}


@app.get("/api/config")
def api_config():
    """บอกหน้าเว็บว่าเซิร์ฟเวอร์ตั้งค่าไว้ยังไง (เช่น ต้องซ่อนกล่องโหมดทดสอบไหม)"""
    return {"allow_dev_login": ALLOW_DEV_LOGIN, "has_steam_key": bool(STEAM_API_KEY)}


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
    rounds_ = await conn.fetch("""
        SELECT r.round_num, r.winner_side, r.end_reason,
               r.bomb_plant_tick IS NOT NULL AS bomb_planted,
               COUNT(k.id) AS kills
        FROM rounds r LEFT JOIN kills k ON k.round_id = r.id
        WHERE r.match_id = $1
        GROUP BY r.id ORDER BY r.round_num""", match_id)
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
    return {"match": dict(match), "rounds": rows(rounds_), "scoreboard": rows(scoreboard)}


@app.get("/api/players")
async def api_players(
    limit: int = Query(20, ge=1, le=200),
    min_matches: int = Query(1, ge=1),
    _: dict = Depends(require_login),
    conn: asyncpg.Connection = Depends(db),
):
    """นักแข่งเรียงตามคิล (จาก view player_stats) — ?min_matches=3 กรองคนที่เล่นน้อยออก"""
    recs = await conn.fetch("""
        SELECT steam_id::text AS steam_id, name, matches, kills, deaths, assists, headshots, kd, hs_rate
        FROM player_stats WHERE matches >= $1
        ORDER BY kills DESC LIMIT $2""", min_matches, limit)
    return rows(recs)


@app.get("/api/players/{steam_id}")
async def api_player(steam_id: int, _: dict = Depends(require_login), conn: asyncpg.Connection = Depends(db)):
    """นักแข่งคนเดียว: สถิติรวม + ปืนที่ใช้ + จุดที่ฆ่า/ตายบ่อย"""
    p = await conn.fetchrow("""
        SELECT steam_id::text AS steam_id, name, matches, kills, deaths, assists, headshots, kd, hs_rate
        FROM player_stats WHERE steam_id = $1""", steam_id)
    if not p:
        raise HTTPException(404, "ไม่พบนักแข่งคนนี้")
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
    return {"player": dict(p), "weapons": rows(weapons),
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
        SELECT k.victim_x AS x, k.victim_y AS y, k.victim_side AS side, k.weapon, k.headshot
        FROM kills k JOIN rounds r ON r.id = k.round_id JOIN matches m ON m.id = r.match_id
        WHERE m.map_name = $1 AND k.victim_x IS NOT NULL
          AND ($2::text IS NULL OR k.victim_side = $2)""", map_name, side)
    return {"map": map_name, "side": side, "count": len(recs), "points": rows(recs)}
