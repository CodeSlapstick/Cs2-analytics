# -*- coding: utf-8 -*-
"""
web/app.py — "หลังบ้าน" (backend) ของเว็บ CS2 Analytics

เปรียบเทียบง่าย ๆ: ไฟล์นี้คือ "พนักงานหลังเคาน์เตอร์"
  - หน้าเว็บ (frontend) = ลูกค้าที่มายืนหน้าเคาน์เตอร์
  - ไฟล์นี้ = พนักงานที่คอยรับคำสั่ง แล้วส่งของกลับไปให้

หน้าที่ของไฟล์นี้มี 4 อย่าง
  1) ส่งหน้าเว็บ (ไฟล์ .html) ให้เบราว์เซอร์
  2) พาผู้ใช้ไปล็อกอินที่ Steam แล้วรับผลกลับมา
  3) จำว่า "ใครล็อกอินอยู่" ด้วยคุกกี้ (cookie = บัตรคิวที่ติดตัวลูกค้าไว้)
  4) คำนวณสถิติจากไฟล์ CSV แล้วส่งเป็น JSON ให้หน้าเว็บเอาไปวาด

รัน:  python -m uvicorn web.app:app --reload
เปิด: http://localhost:8000
"""

# ---------------------------------------------------------------------------
# ส่วนที่ 0 — ขนเครื่องมือเข้ามาใช้ (import = "หยิบกล่องเครื่องมือมาวางบนโต๊ะ")
# ---------------------------------------------------------------------------
import os                      # os = คุยกับระบบเครื่อง เอาไว้ "อ่านค่าลับ" จาก environment
import re                      # re = ตัวจับรูปแบบข้อความ (regex) ใช้ตรวจว่าเลข Steam หน้าตาถูกไหม
import secrets                 # secrets = เครื่องสุ่มรหัสลับแบบปลอดภัย ใช้สร้างกุญแจเซ็นคุกกี้
import urllib.parse            # urllib.parse = ตัวประกอบ/แกะ URL (ต่อ "?key=value" ให้ถูกไวยากรณ์)
from pathlib import Path       # Path = ตัวจัดการ "ที่อยู่ไฟล์" ใช้แทนการต่อสตริงเครื่องหมาย / เองให้ปวดหัว

import httpx                   # httpx = โทรศัพท์ ใช้ "โทร" ไปถามเว็บอื่น (ที่นี่คือเซิร์ฟเวอร์ Steam)
import pandas as pd            # pandas = โปรแกรมตารางแบบ Excel ในภาษา Python
from fastapi import FastAPI, Request                       # FastAPI = โครงเว็บเซิร์ฟเวอร์, Request = "ซองจดหมาย" ที่ลูกค้าส่งมา
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse  # 3 แบบของ "ของที่ส่งกลับ": ไฟล์ / ข้อมูล JSON / คำสั่งให้เด้งไปหน้าอื่น
from fastapi.staticfiles import StaticFiles                # StaticFiles = คนแจกไฟล์นิ่ง ๆ (css, js, รูป)
from itsdangerous import BadSignature, URLSafeSerializer   # itsdangerous = เครื่อง "เซ็นชื่อ" ข้อมูลในคุกกี้ กันคนปลอมแปลง


# ---------------------------------------------------------------------------
# ส่วนที่ 1 — ค่าตั้งต้น (CONFIG) อยากแก้อะไรแก้ตรงนี้ที่เดียว
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent   # __file__ = ไฟล์นี้ -> .parent = โฟลเดอร์ web -> .parent อีกที = โฟลเดอร์โปรเจกต์
WEB_DIR = ROOT / "web"                          # ที่อยู่ของโฟลเดอร์ web/ (ที่เก็บไฟล์ .html)
STATIC_DIR = WEB_DIR / "static"                 # ที่อยู่ของโฟลเดอร์ web/static/ (ที่เก็บ .css .js)
KILLS_CSV = ROOT / "all_kills_25demos.csv"      # ไฟล์ตารางการฆ่าที่ parse ไว้แล้ว เอามาทำสถิติ


def load_dotenv(path: Path) -> None:
    """อ่านไฟล์ .env (ที่เก็บ "ค่าลับ") แล้วยัดเข้าไปใน environment ของโปรแกรม

    ทำไมต้องมี? เพราะกุญแจ Steam API เป็นความลับ ห้ามเขียนลงโค้ดแล้ว push ขึ้น git
    เลยแยกไปไว้ในไฟล์ .env ที่ไม่ถูกอัปโหลด
    """
    if not path.exists():          # ถ้าไม่มีไฟล์ .env ก็ไม่เป็นไร -> ออกจากฟังก์ชันเงียบ ๆ
        return
    for line in path.read_text(encoding="utf-8").splitlines():   # อ่านไฟล์ทั้งก้อน แล้วหั่นเป็นบรรทัด ๆ
        line = line.strip()                                      # ตัดช่องว่างหัวท้ายบรรทัดทิ้ง
        if not line or line.startswith("#") or "=" not in line:  # ข้ามบรรทัดว่าง / บรรทัดคอมเมนต์ / บรรทัดที่ไม่มีเครื่องหมาย =
            continue
        key, value = line.split("=", 1)                          # หั่นที่ = ตัวแรก ได้ชื่อกับค่า เช่น "STEAM_API_KEY" กับ "ABC123"
        os.environ.setdefault(key.strip(), value.strip().strip('"'))  # setdefault = ใส่ให้ก็ต่อเมื่อยังไม่มีค่าเดิมอยู่


load_dotenv(WEB_DIR / ".env")     # เรียกใช้ฟังก์ชันข้างบนทันที เพื่อโหลดไฟล์ web/.env

STEAM_API_KEY = os.environ.get("STEAM_API_KEY", "")             # กุญแจ Steam ขอฟรีที่ steamcommunity.com/dev/apikey ("" = ยังไม่มี)
BASE_URL = os.environ.get("BASE_URL", "http://localhost:8000")  # ที่อยู่เว็บเรา ใช้บอก Steam ว่า "ล็อกอินเสร็จให้ส่งกลับมาที่นี่"
SECRET_KEY = os.environ.get("SECRET_KEY") or secrets.token_hex(32)  # กุญแจเซ็นคุกกี้ ถ้าไม่ตั้งไว้ = สุ่มใหม่ทุกครั้งที่รัน (ล็อกอินจะหลุดตอนรีสตาร์ต)
ALLOW_DEV_LOGIN = os.environ.get("ALLOW_DEV_LOGIN", "1") == "1"     # "โหมดทดสอบ" ให้พิมพ์เลข Steam เข้าเองได้ โดยไม่ต้องมีกุญแจ API

COOKIE_NAME = "cs2_session"        # ชื่อคุกกี้ (บัตรคิว) ที่เราจะติดให้ผู้ใช้
COOKIE_MAX_AGE = 60 * 60 * 24 * 7  # อายุคุกกี้ = 60วินาที x 60นาที x 24ชม. x 7วัน = 1 สัปดาห์

STEAM_OPENID_URL = "https://steamcommunity.com/openid/login"  # ประตูล็อกอินของ Steam (มาตรฐานชื่อ OpenID 2.0)
STEAM_ID_RE = re.compile(r"^7656119\d{10}$")                  # แบบแผนของ SteamID64: ขึ้นต้น 7656119 แล้วตามด้วยเลข 10 ตัว

signer = URLSafeSerializer(SECRET_KEY, salt="cs2-session")    # สร้าง "ตราประทับ" ไว้เซ็นและตรวจคุกกี้ด้วยกุญแจลับ

app = FastAPI(title="CS2 Analytics")                          # สร้างตัวเว็บเซิร์ฟเวอร์ขึ้นมา 1 ตัว ชื่อ app
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")  # ผูกว่า URL ที่ขึ้นต้นด้วย /static ให้ไปหยิบไฟล์จริงในโฟลเดอร์ static/


# ---------------------------------------------------------------------------
# ส่วนที่ 2 — เรื่องคุกกี้ "ใครล็อกอินอยู่"
# ---------------------------------------------------------------------------
def make_session_cookie(response, user: dict) -> None:
    """เอาข้อมูลผู้ใช้ใส่ซอง เซ็นชื่อกำกับ แล้วแปะเป็นคุกกี้ติดตัวเบราว์เซอร์"""
    token = signer.dumps(user)          # dumps = แปลง dict เป็นข้อความ + เซ็นชื่อต่อท้าย (ถ้ามีคนแอบแก้ข้างใน ลายเซ็นจะไม่ตรง)
    response.set_cookie(
        COOKIE_NAME, token,             # ชื่อคุกกี้ และเนื้อในคุกกี้
        max_age=COOKIE_MAX_AGE,         # อยู่ได้นานแค่ไหน
        httponly=True,                  # True = JavaScript อ่านคุกกี้นี้ไม่ได้ (กันสคริปต์แปลกปลอมขโมย)
        samesite="lax",                 # ส่งคุกกี้เฉพาะตอนอยู่เว็บเรา กันเว็บอื่นยืมใช้
    )


def read_session(request: Request):
    """แกะคุกกี้ออกมาดูว่าเป็นใคร — ถ้าไม่มีหรือถูกปลอม จะคืน None (แปลว่า "ยังไม่ล็อกอิน")"""
    token = request.cookies.get(COOKIE_NAME)   # หยิบคุกกี้ชื่อ cs2_session จากซองจดหมายที่เบราว์เซอร์ส่งมา
    if not token:                              # ไม่มีคุกกี้ = ยังไม่เคยล็อกอิน
        return None
    try:
        return signer.loads(token)             # loads = ตรวจลายเซ็นก่อน ถ้าผ่านค่อยแปลงกลับเป็น dict
    except BadSignature:                       # ลายเซ็นไม่ตรง = มีคนแก้คุกกี้ -> ถือว่าไม่ล็อกอิน
        return None


# ---------------------------------------------------------------------------
# ส่วนที่ 3 — หน้าเว็บ (ส่งไฟล์ .html ให้เบราว์เซอร์)
# ---------------------------------------------------------------------------
@app.get("/")                       # @app.get("/") = "ถ้ามีคนเปิดหน้าแรก ให้เรียกฟังก์ชันข้างล่างนี้"
def page_login():
    """หน้าล็อกอิน"""
    return FileResponse(WEB_DIR / "login.html")   # ส่งไฟล์ login.html กลับไปให้เบราว์เซอร์วาด


@app.get("/main")                   # URL /main = หน้าหลักหลังล็อกอินเสร็จ
def page_main():
    """หน้าหลัก (ถ้ายังไม่ล็อกอิน ฝั่ง JavaScript จะเด้งกลับไปหน้าแรกเอง)"""
    return FileResponse(WEB_DIR / "main.html")


# ---------------------------------------------------------------------------
# ส่วนที่ 4 — ล็อกอินด้วย Steam (OpenID 2.0)
#
# ขั้นตอนเหมือนไปธนาคาร:
#   1. เราพาผู้ใช้เดินไปที่เคาน์เตอร์ Steam            -> /auth/steam/login
#   2. ผู้ใช้กรอกรหัสที่ Steam (เว็บเราไม่เห็นรหัสเลย)
#   3. Steam ส่งผู้ใช้กลับมาพร้อมใบเสร็จ               -> /auth/steam/callback
#   4. เราโทรกลับไปถาม Steam ว่า "ใบเสร็จนี้ของจริงไหม"
#   5. จริง -> ออกบัตรคิว (คุกกี้) แล้วพาไปหน้าหลัก
# ---------------------------------------------------------------------------
@app.get("/auth/steam/login")
def steam_login():
    """ขั้นที่ 1: สร้างลิงก์ไป Steam แล้วสั่งเบราว์เซอร์เด้งไปตามนั้น"""
    params = {
        "openid.ns": "http://specs.openid.net/auth/2.0",           # บอกว่าใช้กติกา OpenID เวอร์ชัน 2.0
        "openid.mode": "checkid_setup",                            # โหมด "ขอให้ผู้ใช้ล็อกอินให้หน่อย"
        "openid.return_to": f"{BASE_URL}/auth/steam/callback",     # เสร็จแล้วส่งกลับมาที่ URL นี้
        "openid.realm": BASE_URL,                                  # ขอบเขตเว็บเรา (Steam เอาไปโชว์ให้ผู้ใช้ดูว่ากำลังล็อกอินให้เว็บไหน)
        "openid.identity": "http://specs.openid.net/auth/2.0/identifier_select",   # "ยังไม่รู้ว่าใคร ให้ผู้ใช้เลือกเอง"
        "openid.claimed_id": "http://specs.openid.net/auth/2.0/identifier_select", # (ต้องใส่คู่กันเสมอ)
    }
    url = f"{STEAM_OPENID_URL}?{urllib.parse.urlencode(params)}"  # urlencode = จับ dict มาต่อเป็น "a=1&b=2" ให้ถูกไวยากรณ์ URL
    return RedirectResponse(url)                                  # ส่งคำสั่ง "เด้งไปหน้านี้" กลับไปให้เบราว์เซอร์


@app.get("/auth/steam/callback")
async def steam_callback(request: Request):
    """ขั้นที่ 3-5: รับผลจาก Steam -> ตรวจว่าของจริง -> ออกคุกกี้ -> เด้งเข้าหน้าหลัก"""
    params = dict(request.query_params)             # หยิบทุกค่าที่ Steam แนบมาท้าย URL มาเก็บเป็น dict
    params["openid.mode"] = "check_authentication"  # เปลี่ยนโหมดเป็น "ช่วยยืนยันหน่อยว่าใบนี้เธอออกเองจริงไหม"

    async with httpx.AsyncClient(timeout=10) as client:   # เปิด "สายโทรศัพท์" รอไม่เกิน 10 วินาที (async = ระหว่างรอ เซิร์ฟเวอร์ไปทำงานอื่นได้)
        reply = await client.post(STEAM_OPENID_URL, data=params)   # โทรถาม Steam โดยส่งข้อมูลทั้งชุดกลับไป

    if "is_valid:true" not in reply.text:        # Steam ตอบมาเป็นข้อความ ถ้าไม่มีคำว่า is_valid:true = ของปลอม
        return RedirectResponse("/?error=steam_verify_failed")     # เด้งกลับหน้าแรกพร้อมบอกว่าพัง

    claimed_id = params.get("openid.claimed_id", "")   # ค่าหน้าตาแบบ https://steamcommunity.com/openid/id/76561198...
    steamid = claimed_id.rsplit("/", 1)[-1]            # rsplit แล้วเอาชิ้นขวาสุด = ตัวเลข SteamID64
    if not STEAM_ID_RE.match(steamid):                 # เช็กว่าหน้าตาเป็น SteamID64 จริง กันข้อมูลเพี้ยน
        return RedirectResponse("/?error=bad_steamid")

    profile = await fetch_steam_profile(steamid)       # ไปขอชื่อกับรูปโปรไฟล์มาโชว์ (ถ้าไม่มีกุญแจ API จะได้ชื่อสำรอง)
    user = {"steamid": steamid, **profile, "mode": "steam"}   # ** = "เทของใน dict profile มารวมในนี้"

    response = RedirectResponse("/main", status_code=303)  # เตรียมคำสั่งเด้งไปหน้าหลัก (303 = "ไปต่อที่นี่ด้วยวิธี GET")
    make_session_cookie(response, user)                    # แปะคุกกี้ติดไปกับคำสั่งเด้งด้วย
    return response


@app.post("/auth/dev-login")
async def dev_login(request: Request):
    """โหมดทดสอบ: พิมพ์เลข Steam64 เข้าเองได้เลย ไม่ต้องมีกุญแจ API (ไว้ตอนพัฒนา/ตอนนำเสนอ)"""
    if not ALLOW_DEV_LOGIN:                       # ถ้าปิดโหมดนี้ไว้ใน .env ก็ไม่ให้ใช้
        return JSONResponse({"error": "dev login ถูกปิดอยู่"}, status_code=403)  # 403 = ห้ามเข้า

    body = await request.json()                     # อ่านข้อมูล JSON ที่หน้าเว็บส่งมา เช่น {"steamid": "7656119..."}
    steamid = str(body.get("steamid", "")).strip()  # หยิบค่า steamid ออกมา ตัดช่องว่างหัวท้าย
    if not STEAM_ID_RE.match(steamid):              # ตรวจรูปแบบก่อนเสมอ อย่าเชื่อสิ่งที่ผู้ใช้พิมพ์
        return JSONResponse({"error": "SteamID64 ต้องเป็นตัวเลข 17 หลักขึ้นต้นด้วย 7656119"}, status_code=400)

    profile = await fetch_steam_profile(steamid)  # ลองขอโปรไฟล์จริงดู (ถ้ามีกุญแจก็ได้ชื่อจริงมาเลย)
    user = {"steamid": steamid, **profile, "mode": "dev"}   # mode="dev" ไว้ให้หน้าเว็บโชว์ป้าย "โหมดทดสอบ"

    response = JSONResponse({"ok": True, "user": user})     # ตอบกลับเป็น JSON ว่าเรียบร้อย
    make_session_cookie(response, user)                     # พร้อมแปะคุกกี้
    return response


@app.post("/auth/logout")
def logout():
    """ออกจากระบบ = ลบคุกกี้ทิ้ง เหมือนคืนบัตรคิว"""
    response = JSONResponse({"ok": True})
    response.delete_cookie(COOKIE_NAME)    # สั่งเบราว์เซอร์ให้ลบคุกกี้ชื่อนี้
    return response


async def fetch_steam_profile(steamid: str) -> dict:
    """ถาม Steam ว่าเลขนี้ชื่ออะไร รูปโปรไฟล์อะไร (ต้องมี STEAM_API_KEY ถึงจะถามได้)"""
    fallback = {                                # ชื่อสำรอง ใช้ตอนถาม Steam ไม่ได้
        "name": f"ผู้เล่น {steamid[-4:]}",       # steamid[-4:] = เอาเลข 4 ตัวท้าย
        "avatar": "",
        "profile_url": f"https://steamcommunity.com/profiles/{steamid}",
    }
    if not STEAM_API_KEY:                       # ไม่มีกุญแจ = ถามไม่ได้ ก็คืนชื่อสำรองไปก่อน
        return fallback

    url = "https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v2/"  # ที่อยู่ API "ขอสรุปโปรไฟล์ผู้เล่น"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            reply = await client.get(url, params={"key": STEAM_API_KEY, "steamids": steamid})  # โทรถามพร้อมแนบกุญแจกับเลขผู้เล่น
        players = reply.json()["response"]["players"]   # แกะ JSON ที่ตอบมา เข้าไปเอา list ของผู้เล่น
        if not players:                                 # list ว่าง = ไม่เจอคนนี้
            return fallback
        p = players[0]                                  # เอาคนแรก (เราถามไปคนเดียว)
        return {
            "name": p.get("personaname", ""),           # ชื่อที่โชว์ในเกม
            "avatar": p.get("avatarfull", ""),          # ลิงก์รูปโปรไฟล์ขนาดใหญ่
            "profile_url": p.get("profileurl", ""),     # ลิงก์หน้าโปรไฟล์ Steam
        }
    except Exception:                                   # เน็ตล่ม / กุญแจผิด / โปรไฟล์ปิด -> อย่าให้เว็บพังทั้งเว็บ
        return fallback


# ---------------------------------------------------------------------------
# ส่วนที่ 5 — API สำหรับให้หน้าเว็บเรียกใช้ (ตอบกลับเป็น JSON)
# ---------------------------------------------------------------------------
@app.get("/api/me")
def api_me(request: Request):
    """หน้าเว็บถามว่า 'ตอนนี้ฉันล็อกอินอยู่ไหม เป็นใคร'"""
    user = read_session(request)                      # แกะคุกกี้ดู
    if not user:
        return JSONResponse({"error": "ยังไม่ได้ล็อกอิน"}, status_code=401)  # 401 = ยังไม่ยืนยันตัวตน
    return {"user": user}


@app.get("/api/config")
def api_config():
    """บอกหน้าเว็บว่าเซิร์ฟเวอร์ตั้งค่าไว้ยังไง (เช่น ต้องซ่อนกล่องโหมดทดสอบไหม)"""
    return {"allow_dev_login": ALLOW_DEV_LOGIN, "has_steam_key": bool(STEAM_API_KEY)}  # bool("") = False, bool("ABC") = True


_stats_cache: dict | None = None   # กล่องเก็บผลคำนวณครั้งแรก (cache) จะได้ไม่ต้องอ่าน CSV เป็นแสนบรรทัดซ้ำ ๆ


@app.get("/api/stats")
def api_stats(request: Request):
    """สรุปสถิติจากไฟล์ all_kills_25demos.csv ส่งให้หน้าหลักเอาไปวาด"""
    global _stats_cache                               # global = ขอแก้ตัวแปรที่อยู่นอกฟังก์ชัน
    if read_session(request) is None:                 # กันคนที่ไม่ได้ล็อกอินมาดึงข้อมูล
        return JSONResponse({"error": "ยังไม่ได้ล็อกอิน"}, status_code=401)

    if _stats_cache is not None:                      # ถ้าเคยคำนวณแล้ว ส่งของเก่าไปเลย เร็วกว่ามาก
        return _stats_cache

    if not KILLS_CSV.exists():                        # ไม่มีไฟล์ CSV ก็บอกไปตรง ๆ
        return JSONResponse({"error": f"ไม่พบไฟล์ {KILLS_CSV.name}"}, status_code=404)

    cols = ["weapon", "headshot", "victim_place", "attacker_side", "round_num"]  # เลือกอ่านแค่ 5 คอลัมน์ที่ใช้จริง (อ่านหมดจะกินแรม)
    df = pd.read_csv(KILLS_CSV, usecols=cols)         # อ่าน CSV เข้ามาเป็นตาราง (DataFrame)

    total = len(df)                                   # len(ตาราง) = จำนวนแถว = จำนวนการฆ่าทั้งหมด
    hs = int(df["headshot"].astype(bool).sum())       # คอลัมน์ True/False บวกกันได้เลย (True=1, False=0) -> จำนวนคิลที่ยิงหัว
    hs_rate = round(hs / total * 100, 1) if total else 0.0   # คิดเป็น % แล้วปัดทศนิยม 1 ตำแหน่ง (มี if กันหารด้วยศูนย์)

    top_weapons = (
        df["weapon"].value_counts()                   # value_counts = นับว่าปืนแต่ละกระบอกโผล่กี่ครั้ง แล้วเรียงมากไปน้อยให้เอง
        .head(8)                                      # เอาแค่ 8 อันดับแรก
        .reset_index()                                # เปลี่ยนจาก "ดัชนี+ค่า" ให้กลายเป็นตาราง 2 คอลัมน์
        .set_axis(["name", "count"], axis=1)          # ตั้งชื่อคอลัมน์ใหม่เป็น name กับ count
        .to_dict("records")                           # แปลงเป็น list ของ dict เช่น [{"name":"ak47","count":900}, ...]
    )
    top_places = (
        df["victim_place"].dropna()                   # dropna = ทิ้งแถวที่ช่องนี้ว่าง
        .value_counts().head(8).reset_index()
        .set_axis(["name", "count"], axis=1).to_dict("records")
    )
    side_counts = df["attacker_side"].value_counts().to_dict()   # นับว่าฝั่ง ct กับ t ใครฆ่าเยอะกว่ากัน

    _stats_cache = {                                  # เก็บผลไว้ในกล่อง cache
        "total_kills": total,
        "headshots": hs,
        "headshot_rate": hs_rate,
        "avg_round": round(float(df["round_num"].mean()), 1),   # mean = ค่าเฉลี่ยเลขรอบ (บอกคร่าว ๆ ว่าแมตช์ยาวแค่ไหน)
        "top_weapons": top_weapons,
        "top_places": top_places,
        "ct_kills": int(side_counts.get("ct", 0)),    # .get(..., 0) = ถ้าไม่มีคีย์นี้ให้ใช้ 0 แทน (กัน error)
        "t_kills": int(side_counts.get("t", 0)),
    }
    return _stats_cache
