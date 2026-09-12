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
import mimetypes
import os
import re
import sys
import urllib.parse
from contextlib import asynccontextmanager
from pathlib import Path

import asyncpg
from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.concurrency import run_in_threadpool  # เอางานหนักที่ไม่ใช่ async ไปรันในเธรดแยก ไม่ให้เซิร์ฟเวอร์ค้าง
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from backend import auth  # ล็อกอิน: hash รหัสผ่าน + JWT ใน httpOnly cookie
from backend.db import (  # noqa: F401  (load_dotenv ทำงานตอน import)
    DATABASE_URL,
    apply_schema,
    create_pool,
    redacted_url,
)
from backend.features import assign_teams, rating2_approx  # ผูกคนกับทีม (Round Review) · Rating 2.0 ประมาณการ
from backend.jobs import QueueUnavailable, enqueue_parse, job_state, queue_health  # คิวงาน parse (Sprint 2)
from backend.review import (
    build_round_detail,
    build_round_list,
    build_round_positions,
    grid_overlay,
    load_grid_model,
    radar_frame,
)

# ---------------------------------------------------------------------------
# ส่วนที่ 1 — ค่าตั้งต้น (CONFIG) อยากแก้อะไรแก้ตรงนี้ที่เดียว
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent   # โฟลเดอร์โปรเจกต์
ASSETS_DIR = ROOT / "assets"                    # ภาพเรดาร์ของแต่ละแมพ + ค่าปรับเทียบพิกัด (radars.json)
DEMOS_DIR = ROOT / "demos"                      # ไฟล์ .dem ที่ผู้ใช้อัปโหลดเข้ามา (ไม่ถูก commit — ดู .gitignore)

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
# ที่อยู่ที่เบราว์เซอร์เห็น (Steam ต้องส่งผู้ใช้กลับมาที่นี่) — ว่าง = เดาจาก Host ของคำขอ ซึ่งถูกต้องเมื่ออยู่หลัง nginx ของ compose
PUBLIC_URL = os.environ.get("PUBLIC_URL", "").rstrip("/")


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
# ส่วนที่ 4 — ล็อกอิน / ออกจากระบบ
# ---------------------------------------------------------------------------
class Credentials(BaseModel):
    username: str
    password: str
    remember: bool = True        # ติ๊ก "จดจำการเข้าสู่ระบบ 7 วัน" — False = คุกกี้หมดเมื่อปิดเบราว์เซอร์


def _logged_in(account, remember: bool = True) -> JSONResponse:
    """ตอบกลับพร้อมติดคุกกี้ JWT — ใช้ร่วมกันทั้งตอนสมัครและตอนล็อกอิน"""
    user = {"id": account["id"], "username": account["username"]}
    response = JSONResponse({"user": user})
    auth.set_auth_cookie(response, auth.create_token(user["id"], user["username"]), persistent=remember)
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
    return _logged_in(row, body.remember)


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
    return _logged_in(row, body.remember)


# ---- ล็อกอินด้วย Steam (OpenID 2.0) — บัญชีที่มาทางนี้ไม่มีรหัสผ่านในระบบเรา (backend/auth.py)
def _safe_next(next_path: str | None) -> str:
    """กัน open redirect: รับเฉพาะ path ในเว็บเรา (ขึ้นต้น / แต่ไม่ใช่ //) — เหมือน safeNext ฝั่งหน้าเว็บ"""
    p = (next_path or "").strip()
    return p if p.startswith("/") and not p.startswith("//") and not p.startswith("/login") else "/matches"


def _public_base(request: Request) -> str:
    """ที่อยู่ที่เบราว์เซอร์เห็น (ต้องมีพอร์ตด้วย ไม่งั้น Steam ส่งผู้ใช้กลับผิดที่) — nginx ส่ง Host จริงมาให้ทาง $http_host"""
    if PUBLIC_URL:
        return PUBLIC_URL
    host = request.headers.get("host") or request.url.netloc
    scheme = (request.headers.get("x-forwarded-proto") or request.url.scheme).split(",")[0].strip()
    return f"{scheme}://{host}"


@app.get("/auth/steam/login")
def auth_steam_login(request: Request, next: str = "/matches"):
    """พาไปล็อกอินที่ Steam แล้วให้ส่งกลับมาที่ /auth/steam/callback (พก next ไปด้วยใน return_to)"""
    base = _public_base(request)
    return_to = f"{base}/auth/steam/callback?next={urllib.parse.quote(_safe_next(next), safe='/')}"
    return RedirectResponse(auth.steam_login_url(return_to, base + "/"))


@app.get("/auth/steam/callback")
async def auth_steam_callback(request: Request, next: str = "/matches", conn: asyncpg.Connection = Depends(db)):
    """Steam ส่งกลับมาที่นี่ — ตรวจกับ Steam ก่อนเสมอ ผ่านแล้วค่อยสร้าง/หาบัญชีแล้วติดคุกกี้ JWT"""
    params = dict(request.query_params)
    steamid = await run_in_threadpool(auth.verify_steam_openid, params)
    if not steamid:
        log("[AUTH] Steam ไม่ยืนยันการล็อกอินนี้")
        return RedirectResponse("/login?err=steam", status_code=303)
    if not auth.steam_id_allowed(steamid):
        log(f"[AUTH] SteamID {steamid} ไม่อยู่ใน STEAM_ALLOWED_IDS")
        return RedirectResponse("/login?err=steam_denied", status_code=303)

    profile = await run_in_threadpool(auth.steam_persona, steamid)
    row = await conn.fetchrow("SELECT id, username FROM accounts WHERE steam_id = $1", int(steamid))
    if row is None:
        # ชื่อจาก Steam อาจชนกับบัญชีที่มีอยู่ — ชนเมื่อไรถอยไปใช้ steam_<id> ซึ่งไม่ซ้ำแน่นอน
        for username in (auth.username_for_steam(profile["name"], steamid), f"steam_{steamid}"):
            try:
                row = await conn.fetchrow("""
                    INSERT INTO accounts (username, password_hash, steam_id, avatar, last_login)
                    VALUES ($1, NULL, $2, $3, now()) RETURNING id, username""",
                    username, int(steamid), profile["avatar"])
                break
            except asyncpg.UniqueViolationError:
                continue
        if row is None:
            return RedirectResponse("/login?err=steam_account", status_code=303)
        log(f"[AUTH] สร้างบัญชีจาก Steam {steamid} -> {row['username']} (id {row['id']})")
    else:
        await conn.execute("UPDATE accounts SET last_login = now(), avatar = COALESCE($2, avatar) WHERE id = $1",
                           row["id"], profile["avatar"])

    response = RedirectResponse(_safe_next(next), status_code=303)
    auth.set_auth_cookie(response, auth.create_token(row["id"], row["username"]), persistent=True)
    return response


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
# ส่วนที่ 5 — API สำหรับหน้าเว็บ (ตอบ JSON) — ทุกอันดึงจาก PostgreSQL
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


# ---------------------------------------------------------------------------
# ส่วนที่ 5.5 — สถิติรายคน (หน้า /player) — อ่านจาก view ใน backend/views.sql
#   /api/players/me/... = คนที่ล็อกอินอยู่ (ต้องล็อกอินด้วย Steam ถึงจะรู้ว่าเป็น SteamID ไหน)
#   ตัวเลขทุกตัวมาจากเดโมที่โหลดเข้าระบบเท่านั้น — ไม่มีข้อมูล = บอกว่าไม่มี ไม่เดาค่าให้
# ---------------------------------------------------------------------------
async def _player_id(conn: asyncpg.Connection, who: str, user: dict) -> int:
    """'me' = SteamID ของบัญชีที่ล็อกอินอยู่ (บัญชีรหัสผ่านล้วนยังไม่มี) · หรือใส่ SteamID64 ตรง ๆ"""
    if who == "me":
        row = await conn.fetchrow("SELECT steam_id FROM accounts WHERE id = $1", user["id"])
        if not row or row["steam_id"] is None:
            raise HTTPException(409, "บัญชีนี้ยังไม่ได้ผูกกับ Steam — ล็อกอินด้วย Steam เพื่อดูสถิติของตัวเอง")
        return int(row["steam_id"])
    if not who.isdigit() or len(who) != 17:
        raise HTTPException(400, "ต้องเป็น SteamID64 (ตัวเลข 17 หลัก) หรือ me")
    return int(who)


@app.get("/api/players/{who}/summary")
async def api_player_summary(who: str, user: dict = Depends(require_login), conn: asyncpg.Connection = Depends(db)):
    """สรุปของผู้เล่นคนเดียว: ภาพรวม + entry แยกฝั่ง + clutch 1v1..1v5 (ทั้งหมดจากเดโมที่โหลดไว้)"""
    steam_id = await _player_id(conn, who, user)
    row = await conn.fetchrow("SELECT * FROM player_stats WHERE steam_id = $1", steam_id)
    if row is None or not row["rounds"]:
        raise HTTPException(404, "ยังไม่มีข้อมูลของผู้เล่นคนนี้ในเดโมที่โหลดไว้")
    totals = await conn.fetchrow("""
        SELECT SUM(damage) AS damage, COUNT(*) FILTER (WHERE kast) AS kast_rounds, COUNT(*) AS rounds,
               SUM(kills) AS kills, SUM(deaths) AS deaths, SUM(assists) AS assists
        FROM player_round_facts WHERE steam_id = $1""", steam_id)
    entry = await conn.fetch("""
        SELECT side,
               COUNT(*) FILTER (WHERE opening_kill)  AS kills,
               COUNT(*) FILTER (WHERE opening_death) AS deaths
        FROM player_rounds WHERE steam_id = $1 GROUP BY side""", steam_id)
    clutches = await conn.fetch("""
        SELECT clutch_vs AS vs, COUNT(*) AS attempts, COUNT(*) FILTER (WHERE clutch_won) AS wins
        FROM player_rounds WHERE steam_id = $1 AND clutch_vs > 0 GROUP BY clutch_vs ORDER BY clutch_vs""", steam_id)
    account = await conn.fetchrow("SELECT username, avatar FROM accounts WHERE steam_id = $1", steam_id)

    by_side = {r["side"]: {"kills": r["kills"], "deaths": r["deaths"]} for r in entry}
    both = {"kills": sum(v["kills"] for v in by_side.values()), "deaths": sum(v["deaths"] for v in by_side.values())}
    return {
        "player": {"steam_id": str(steam_id), "name": row["name"],
                   "avatar": account["avatar"] if account else None,
                   "linked_account": account["username"] if account else None},
        "totals": {k: row[k] for k in ("matches", "rounds", "kills", "deaths", "assists", "headshots",
                                       "kd", "hs_rate", "adr", "kast", "win_rate", "survival_rate", "rating")},
        # Rating 2.0 เป็น "ค่าประมาณ" (สูตรจริงของ HLTV ไม่เปิด) — หน้าเว็บต้องเขียนกำกับไว้เสมอ
        "rating2_approx": rating2_approx(kills=totals["kills"] or 0, deaths=totals["deaths"] or 0,
                                         assists=totals["assists"] or 0, damage=totals["damage"] or 0,
                                         kast_rounds=totals["kast_rounds"], rounds=totals["rounds"]),
        "entry": {"both": both, "t": by_side.get("t", {"kills": 0, "deaths": 0}),
                  "ct": by_side.get("ct", {"kills": 0, "deaths": 0})},
        "clutches": [{"vs": c["vs"], "attempts": c["attempts"], "wins": c["wins"]} for c in clutches],
        "source": {"matches": row["matches"], "label": f"จาก {row['matches']} แมตช์ที่โหลดเข้าระบบ"},
    }


@app.get("/api/players/{who}/matches")
async def api_player_matches(who: str, limit: int = Query(20, ge=1, le=100),
                             user: dict = Depends(require_login), conn: asyncpg.Connection = Depends(db)):
    """แมตช์ล่าสุดของผู้เล่นคนนี้ พร้อมผลแพ้/ชนะและ rating รายแมตช์"""
    steam_id = await _player_id(conn, who, user)
    return rows(await conn.fetch("""
        SELECT match_id, demo_file, map_name, team_a, team_b, imported_at, rounds, rounds_won, result,
               kills, deaths, assists, adr, kast, rating
        FROM player_match_results WHERE steam_id = $1 ORDER BY match_id DESC LIMIT $2""", steam_id, limit))


@app.get("/api/players/{who}/maps")
async def api_player_maps(who: str, user: dict = Depends(require_login), conn: asyncpg.Connection = Depends(db)):
    """รวมรายแมพ: เล่นกี่แมตช์ ชนะกี่แมตช์ rating/ADR เฉลี่ย"""
    steam_id = await _player_id(conn, who, user)
    return rows(await conn.fetch("""
        SELECT map_name, matches, wins, losses, rounds, win_rate, rating, adr
        FROM player_map_stats WHERE steam_id = $1 ORDER BY matches DESC, wins DESC""", steam_id))


@app.get("/api/players/{who}/weapons")
async def api_player_weapons(who: str, limit: int = Query(8, ge=1, le=30),
                             user: dict = Depends(require_login), conn: asyncpg.Connection = Depends(db)):
    """อาวุธที่ใช้ฆ่าบ่อยที่สุด + %หัวของอาวุธนั้น (นับเฉพาะการดวล)"""
    steam_id = await _player_id(conn, who, user)
    return rows(await conn.fetch("""
        SELECT weapon, kills, headshots, hs_rate FROM player_weapon_stats
        WHERE steam_id = $1 ORDER BY kills DESC LIMIT $2""", steam_id, limit))


# ---------------------------------------------------------------------------
# ส่วนที่ 6 — รับไฟล์เดโมจากผู้ใช้
#
#     อัปโหลด -> demos/X.dem -> แถว matches (queued) -> ส่งงานเข้าคิว (backend/jobs.py) -> ตอบ 202 ทันที
#     worker แกะเดโม + โหลดเข้าฐานข้อมูลในเบื้องหลัง หน้าเว็บ poll สถานะที่ /api/matches/{id}/status
# ---------------------------------------------------------------------------
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
    # worker (python -m backend.jobs) หยิบงานไปทำ แล้วหน้าเว็บ poll ที่ /api/matches/{id}/status
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
# ส่วนที่ 7 — Round Review: ไล่ดูทีละรอบว่าใครตายที่ไหนเมื่อไหร่ + บริบทจาก research/grid_ml1.py
#
# คีย์ของแมตช์คือชื่อไฟล์เดโม (ตาม brief)
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
    grenades = await conn.fetch("""
        SELECT g.tick, g.thrower_id, g.side, g.type, g.throw_x, g.throw_y, g.land_x, g.land_y, g.land_tick, g.end_tick,
               p.name AS thrower_name
        FROM grenades g LEFT JOIN players p ON p.steam_id = g.thrower_id
        WHERE g.round_id = $1 ORDER BY g.tick, g.id""", rnd["id"])
    return build_round_detail(match=m, rnd=dict(rnd), roster=roster, in_round=rows(in_round), kills=rows(kills),
                              grenades=rows(grenades), frame=radar_frame(m["map_name"]), model=load_grid_model())


@app.get("/api/review/{demo_file}/rounds/{round_num}/positions")
async def api_review_positions(demo_file: str, round_num: int, _: dict = Depends(require_login),
                               conn: asyncpg.Connection = Depends(db)):
    """ตำแหน่งผู้เล่นรายวินาทีของรอบนี้ (สำหรับโหมดเล่นย้อน) — ~9 KB ต่อรอบ ขอเฉพาะตอนเปิดโหมด"""
    m = await _review_match(conn, demo_file)
    rnd = await conn.fetchrow(
        "SELECT id, round_num, start_tick FROM rounds WHERE match_id = $1 AND round_num = $2", m["id"], round_num)
    if not rnd:
        raise HTTPException(404, f"แมตช์นี้ไม่มีรอบที่ {round_num}")
    pos = await conn.fetch("""
        SELECT tick, steam_id, side, x, y, health, place FROM player_positions
        WHERE match_id = $1 AND round_num = $2 ORDER BY tick, steam_id""", m["id"], round_num)
    return build_round_positions(rows(pos), start_tick=rnd["start_tick"], tickrate=m["tickrate"],
                                 frame=radar_frame(m["map_name"]))
