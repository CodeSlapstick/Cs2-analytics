# -*- coding: utf-8 -*-
"""ล็อกอิน: hash รหัสผ่าน, JWT ใน httpOnly cookie, dependency require_login และ route ที่เปิดไว้"""
import base64
import json
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlparse

import jwt
import pytest
from fastapi import HTTPException
from fastapi.responses import JSONResponse
from starlette.requests import Request

from backend import auth

FAST = 1_000          # รอบน้อย ๆ ไว้ทดสอบตรรกะ (ความแข็งแรงของ hash ทดสอบแยกข้างล่าง)
SECRET = "s" * 40


def test_hash_verifies_and_salts_differ():
    h1 = auth.hash_password("correct horse", iterations=FAST)
    h2 = auth.hash_password("correct horse", iterations=FAST)
    assert h1 != h2 and h1.startswith("pbkdf2_sha256$1000$")
    assert auth.verify_password("correct horse", h1)
    assert not auth.verify_password("correct horsE", h1)


def test_default_hash_is_strong():
    h = auth.hash_password("password123")
    assert int(h.split("$")[1]) >= 300_000
    assert auth.verify_password("password123", h)


@pytest.mark.parametrize("stored", ["", "plain", "md5$1$a$b", "pbkdf2_sha256$x$a$b", "pbkdf2_sha256$1000$@@$@@", None])
def test_verify_rejects_garbage_without_raising(stored):
    assert auth.verify_password("pw", stored) is False


def test_token_roundtrip():
    t = auth.create_token(7, "alice", secret=SECRET)
    assert auth.user_from_token(t, secret=SECRET) == {"id": 7, "username": "alice"}


def test_expired_tampered_wrong_secret_are_rejected():
    old = auth.create_token(7, "alice", secret=SECRET, now=datetime.now(UTC) - timedelta(days=8))
    assert auth.user_from_token(old, secret=SECRET) is None
    t = auth.create_token(7, "alice", secret=SECRET)
    head, body, sig = t.split(".")
    forged = json.loads(base64.urlsafe_b64decode(body + "=="))
    forged["sub"] = "1"                                   # แอบเปลี่ยนตัวตนแต่คงลายเซ็นเดิม
    forged_body = base64.urlsafe_b64encode(json.dumps(forged).encode()).decode().rstrip("=")
    assert auth.user_from_token(f"{head}.{forged_body}.{sig}", secret=SECRET) is None
    assert auth.user_from_token(t, secret="another-secret-" * 3) is None
    assert auth.user_from_token("", secret=SECRET) is None
    assert auth.user_from_token("not.a.jwt", secret=SECRET) is None


def test_alg_none_and_missing_claims_are_rejected():
    def b64(d):
        return base64.urlsafe_b64encode(json.dumps(d).encode()).decode().rstrip("=")
    exp = int((datetime.now(UTC) + timedelta(days=1)).timestamp())
    unsigned = f"{b64({'alg': 'none', 'typ': 'JWT'})}.{b64({'sub': '1', 'name': 'x', 'exp': exp})}."
    assert auth.user_from_token(unsigned, secret=SECRET) is None
    no_sub = jwt.encode({"name": "x", "exp": exp}, SECRET, algorithm="HS256")
    assert auth.user_from_token(no_sub, secret=SECRET) is None
    no_exp = jwt.encode({"sub": "1", "name": "x"}, SECRET, algorithm="HS256")
    assert auth.user_from_token(no_exp, secret=SECRET) is None


@pytest.mark.parametrize("username,password,ok", [
    ("dev", "cs2dev1234", True), ("a.b-c_d", "12345678", True),
    ("ab", "12345678", False), ("x" * 33, "12345678", False), ("bad name", "12345678", False),
    ("ไทย", "12345678", False), ("dev", "short", False), ("dev", "x" * 300, False), (None, None, False),
])
def test_validate_credentials(username, password, ok):
    assert (auth.validate_credentials(username, password) is None) is ok


def test_cookie_is_httponly_lax_and_clearable():
    r = JSONResponse({})
    auth.set_auth_cookie(r, "tok")
    h = r.headers["set-cookie"].lower()
    assert f"{auth.COOKIE_NAME}=tok" in h and "httponly" in h and "samesite=lax" in h and "path=/" in h
    r2 = JSONResponse({})
    auth.clear_auth_cookie(r2)
    assert "max-age=0" in r2.headers["set-cookie"].lower()


def test_cookie_without_remember_me_is_a_session_cookie():
    """ไม่ติ๊ก "จดจำการเข้าสู่ระบบ" = ไม่มี Max-Age/Expires คุกกี้จึงหายเมื่อปิดเบราว์เซอร์ แต่ยัง httpOnly"""
    r = JSONResponse({})
    auth.set_auth_cookie(r, "tok", persistent=False)
    h = r.headers["set-cookie"].lower()
    assert "httponly" in h and "max-age" not in h and "expires" not in h


def _request(cookie: str | None) -> Request:
    headers = [(b"cookie", cookie.encode())] if cookie else []
    return Request({"type": "http", "method": "GET", "path": "/", "headers": headers})


def test_require_login_uses_the_cookie():
    from backend import app as appmod
    tok = auth.create_token(3, "bob")
    assert appmod.require_login(_request(f"{auth.COOKIE_NAME}={tok}")) == {"id": 3, "username": "bob"}
    for cookie in (None, f"{auth.COOKIE_NAME}=garbage", f"cs2_session={tok}"):
        with pytest.raises(HTTPException) as e:
            appmod.require_login(_request(cookie))
        assert e.value.status_code == 401


def test_auth_routes_are_password_or_steam_only():
    """ล็อกอินมีสองทางเท่านั้น: username/password กับ Steam OpenID — ห้ามมี dev-login ที่พิมพ์ SteamID เข้าเองได้อีก"""
    from backend import app as appmod
    routes = {(m, r.path) for r in appmod.app.routes for m in getattr(r, "methods", ()) or ()}
    for expected in [("POST", "/auth/register"), ("POST", "/auth/login"), ("GET", "/auth/me"), ("POST", "/auth/logout"),
                     ("GET", "/auth/steam/login"), ("GET", "/auth/steam/callback")]:
        assert expected in routes
    paths = {p for _, p in routes}
    assert "/auth/dev-login" not in paths


# ---- ล็อกอินด้วย Steam (ตรวจเฉพาะส่วนที่ไม่ต้องต่อเน็ต) ----------------------------------------
def test_steam_login_url_asks_steam_to_return_to_us():
    url = auth.steam_login_url("http://localhost:3000/auth/steam/callback?next=/matches", "http://localhost:3000/")
    assert url.startswith("https://steamcommunity.com/openid/login?")
    q = parse_qs(urlparse(url).query)
    assert q["openid.mode"] == ["checkid_setup"]
    assert q["openid.return_to"] == ["http://localhost:3000/auth/steam/callback?next=/matches"]
    assert q["openid.realm"] == ["http://localhost:3000/"]
    assert q["openid.identity"] == ["http://specs.openid.net/auth/2.0/identifier_select"]


@pytest.mark.parametrize("claimed", [
    None, "", "7656119801234567",
    "https://steamcommunity.com/openid/id/123",                        # สั้นเกิน
    "https://evil.example.com/openid/id/76561198012345678",            # คนละโดเมน
    "https://steamcommunity.com.evil.example/openid/id/76561198012345678",
    "https://steamcommunity.com/openid/id/76561198012345678/../x",
])
def test_bad_claimed_ids_are_rejected(claimed):
    assert auth.steamid_from_claimed_id(claimed) is None


def test_good_claimed_id_gives_the_steamid():
    assert auth.steamid_from_claimed_id("https://steamcommunity.com/openid/id/76561198012345678") == "76561198012345678"


def test_openid_reply_is_only_trusted_when_steam_says_is_valid(monkeypatch):
    """พารามิเตอร์ที่ปลอมมาเองต้องไม่ผ่าน แม้ claimed_id จะถูกรูปแบบ — ต้องรอคำตอบ is_valid:true จาก Steam"""
    good = {"openid.mode": "id_res", "openid.claimed_id": "https://steamcommunity.com/openid/id/76561198012345678",
            "openid.sig": "x", "other": "ignored"}
    sent = {}

    class FakeResponse:
        def __init__(self, text): self.text = text
        def read(self): return self.text.encode()
        def __enter__(self): return self
        def __exit__(self, *a): return False

    def fake_urlopen(req, timeout=None):
        sent["url"] = req.full_url
        sent["body"] = req.data.decode()
        return FakeResponse(fake_urlopen.answer)

    monkeypatch.setattr(auth.urllib.request, "urlopen", fake_urlopen)
    fake_urlopen.answer = "ns:http://specs.openid.net/auth/2.0\nis_valid:true\n"
    assert auth.verify_steam_openid(dict(good)) == "76561198012345678"
    assert "openid.mode=check_authentication" in sent["body"] and "other" not in sent["body"]
    fake_urlopen.answer = "is_valid:false\n"
    assert auth.verify_steam_openid(dict(good)) is None
    assert auth.verify_steam_openid({**good, "openid.mode": "cancel"}) is None

    def boom(req, timeout=None):
        raise OSError("steam unreachable")

    monkeypatch.setattr(auth.urllib.request, "urlopen", boom)
    assert auth.verify_steam_openid(dict(good)) is None


def test_allowlist_empty_means_everyone(monkeypatch):
    monkeypatch.setattr(auth, "STEAM_ALLOWED_IDS", set())
    assert auth.steam_id_allowed("76561198012345678")
    monkeypatch.setattr(auth, "STEAM_ALLOWED_IDS", {"76561198000000001"})
    assert auth.steam_id_allowed("76561198000000001")
    assert not auth.steam_id_allowed("76561198012345678")


@pytest.mark.parametrize("persona,expected", [
    ("ZywOo", "ZywOo"), ("s1mple.", "s1mple."), ("  dev  ", "dev"),
    ("ลูกทีม", "steam_76561198012345678"),        # ชื่อไทยล้วน -> ไม่เหลือตัวอักษรที่ใช้ได้
    ("a", "steam_76561198012345678"),             # สั้นกว่า 3 ตัว
    ("", "steam_76561198012345678"),
])
def test_username_from_steam_persona(persona, expected):
    assert auth.username_for_steam(persona, "76561198012345678") == expected


def test_steam_persona_without_api_key_does_not_invent_a_name(monkeypatch):
    monkeypatch.setattr(auth, "STEAM_API_KEY", "")
    assert auth.steam_persona("76561198012345678") == {"name": "steam_76561198012345678", "avatar": None}


def _get(headers: list[tuple[bytes, bytes]]) -> Request:
    return Request({"type": "http", "method": "GET", "path": "/auth/steam/login", "query_string": b"",
                    "headers": headers, "scheme": "http", "server": ("api", 8000), "client": ("test", 1)})


def test_public_base_keeps_the_port_the_browser_used():
    """Steam ส่งผู้ใช้กลับมาตาม return_to — พลาดพอร์ตเมื่อไรคือล็อกอินไม่สำเร็จ"""
    from backend import app as appmod
    assert appmod._public_base(_get([(b"host", b"localhost:3000")])) == "http://localhost:3000"
    assert appmod._public_base(_get([(b"host", b"cs2.example.com"), (b"x-forwarded-proto", b"https")])) == "https://cs2.example.com"


def test_public_base_prefers_the_configured_url(monkeypatch):
    from backend import app as appmod
    monkeypatch.setattr(appmod, "PUBLIC_URL", "https://scouting.example.com")
    assert appmod._public_base(_get([(b"host", b"localhost:3000")])) == "https://scouting.example.com"


@pytest.mark.parametrize("given,expected", [
    ("/matches/X.dem/rounds/3", "/matches/X.dem/rounds/3"),
    (None, "/matches"), ("", "/matches"),
    ("//evil.example/steal", "/matches"),          # open redirect
    ("https://evil.example", "/matches"),
    ("/login?next=/matches", "/matches"),          # วนกลับหน้า login
])
def test_safe_next_only_allows_paths_inside_this_site(given, expected):
    from backend import app as appmod
    assert appmod._safe_next(given) == expected

