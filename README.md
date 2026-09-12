# CS2 Scouting Platform

เว็บวิเคราะห์เดโม Counter-Strike 2 สำหรับโค้ช/ทีม — อัปโหลดไฟล์ `.dem` แล้วระบบแกะในเบื้องหลัง
เปิดดูสถิติของแมตช์นั้นได้ทันทีที่เสร็จ (SP-404 Senior Project · UTCC STECH)

```
เบราว์เซอร์ ──► frontend (React + nginx, :3000) ──/api /auth /assets──► api (FastAPI ภายใน Docker) ──► PostgreSQL
                                                                           │  ▲                       ▲
                                                                   enqueue │  │ status                │ INSERT
                                                                           ▼  │                       │
                                                                         Redis ──► worker ── parse_demo(match_id) ── awpy/demoparser2
                                                                                   │
                                                                                   └── backend/features.py  (opening / trade / buy / clutch / KAST)
```

ใช้งานที่เดียวคือหน้าเว็บ — API อยู่หลังหน้าเว็บเสมอ ไม่เปิดพอร์ตของตัวเองออกมานอกเครื่อง

Sprint 1 ตอบว่า "จุดปะทะสำคัญอยู่ตรงไหน ตรงไหนใครได้เปรียบ" ด้วยโมเดลบน Mirage 50 แมตช์ (ดู `research/`)
Sprint 2 เปลี่ยนสิ่งนั้นจากสคริปต์เป็นระบบที่ใช้งานได้จริง end-to-end: **อัปโหลด → parse ในเบื้องหลัง → ดูสถิติ**

---

## เริ่มใช้ในคำสั่งเดียว (Docker)

```bash
cp .env.example .env          # ค่าเริ่มต้นใช้ได้เลย (ถ้าเครื่องมี PostgreSQL อยู่แล้ว ตั้ง POSTGRES_PORT=5433)
docker compose up -d          # db + redis + api + worker + frontend
```

เปิด **http://localhost:3000** แล้วล็อกอิน — ทุกอย่างอยู่ในหน้าเดียว

| ที่อยู่ | คืออะไร |
|---|---|
| http://localhost:3000 | หน้าเว็บ — `/login` แล้วเข้า `/matches/{demo_file}/rounds/{n}` |
| http://localhost:3000/api/docs | Swagger ของ API (ล็อกอินที่หน้าเว็บก่อน คุกกี้ใช้ร่วมกัน) |
| localhost:5432 (หรือ `POSTGRES_PORT`) | PostgreSQL · user/pass `postgres` · db `cs2_analytics` (ต่อ DBeaver ได้) |

`api` รัน `alembic upgrade head` และสร้าง dev user ให้เองตอนสตาร์ต จึงเปิดบนฐานข้อมูลเปล่าได้ทันที และเปิดบนฐานข้อมูลเดิมได้โดยไม่เสียข้อมูล

### ล็อกอิน

เปิดเว็บแล้วจะเด้งไปหน้า `/login` ก่อนเสมอ ใช้ user สำหรับ dev ที่ระบบสร้างให้ตอน api สตาร์ต

| ชื่อผู้ใช้ | รหัสผ่าน |
|---|---|
| `dev` | `cs2dev1234` |

เปลี่ยนได้ที่ `DEV_USERNAME` / `DEV_PASSWORD` ใน `.env` หรือกด "สมัครสมาชิก" ในหน้า login (ปิดได้ด้วย `ALLOW_REGISTER=0`)
หรือกดปุ่ม **เข้าสู่ระบบด้วย Steam** — ล็อกอินผ่าน Steam (OpenID 2.0) ระบบไม่เห็นรหัสผ่าน Steam ของใครเลย
ครั้งแรกจะสร้างบัญชีให้เองจาก SteamID64 (ชื่อ/รูปโปรไฟล์ต้องตั้ง `STEAM_API_KEY` ใน `.env` ไม่ตั้งก็ล็อกอินได้ ชื่อจะเป็น `steam_<SteamID64>`)
**ค่าเริ่มต้นคือใครมีบัญชี Steam ก็เข้าได้** — จำกัดเฉพาะทีมได้ด้วย `STEAM_ALLOWED_IDS=76561198...,76561198...` ใน `.env`
รหัสผ่านเก็บเป็น PBKDF2 hash ส่วน session เป็น JWT ในคุกกี้ httpOnly อายุ 7 วัน (`backend/auth.py`) — ตั้ง `SECRET_KEY` ใน `.env` ไว้ ไม่งั้นทุกคนหลุดเมื่อ api รีสตาร์ต
ลืมรหัส dev: `python -m backend.auth --reset` (ในเครื่อง) หรือ `docker compose exec api python -m backend.auth --reset`

### หน้าเว็บ

หน้าหลักมีหน้าเดียวที่ `/matches/{demo_file}/rounds/{round_num}` เช่น `/matches/Vitality-vs-Legacy-Mirage.dem/rounds/1`

- **sidebar ซ้าย** — ฟอร์มอัปโหลดที่หัวแถบ + รายการแมตช์ทั้งหมด กดแล้วไปรอบ 1 ของแมตช์นั้น ย่อเก็บได้
- **หัวแมตช์** — สกอร์ + ปุ่มเปิดสกอร์บอร์ดทั้งแมตช์ (K/D, ADR, KAST, opening, trade, clutch)
- **แถบรอบ** — เท่าจำนวนรอบจริง กดหรือใช้ปุ่ม ← / → บนคีย์บอร์ด
- **เนื้อหารอบ** — รายชื่อทีม / แผนที่ (ชื่อคนตายใต้วง · ระเบิดทุกลูกพร้อมชื่อคนขว้างและเส้นทางที่ขว้างมา) / ไทม์ไลน์ / บริบทจาก grid_ml1
  กดจุดตาย = แผนที่เหลือเฉพาะระเบิดที่มีผลอยู่ ณ วินาทีนั้น (ควัน/ไฟที่ยังไม่หมด แฟลช/HE ที่เพิ่งแตก) และขึ้นชื่อคนยิง
  ซูมแผนที่ด้วยล้อเมาส์หรือปุ่ม + / − (ลากเพื่อเลื่อนดู · ปุ่ม "เต็มแมพ" กลับมุมมองเดิม) · เปิด/ปิดระเบิดแยกทีละชนิด (สโมค · แฟลช · HE · โมโลตอฟ — decoy ไม่มีเพราะเดโมไม่บันทึกจุดตก)

state ทั้งหมดอยู่บน URL (`?sb=0` ย่อ sidebar, `board=1` สกอร์บอร์ด, `g=smoke,flash` ชนิดระเบิดที่แสดง (`g=none` = ไม่แสดงเลย), `z=2.5` `c=x,y` ซูม/จุดที่มองอยู่บนแผนที่, `cells=1` `hs=1` ชั้นซ้อน, `pb=1` โหมดเล่นย้อน + `t=12.5` วินาทีในรอบที่ดูค้างไว้, `p=` ผู้เล่นที่ไฮไลต์, `d=` การตายที่เลือก)
refresh แล้วอยู่ที่เดิม และแชร์ลิงก์ให้คนอื่นเห็นแบบเดียวกันได้ · `/matches` พาไปแมตช์ล่าสุด · แมตช์/รอบที่ไม่มีจริงขึ้นหน้า 404 ที่มีปุ่มกลับ

```bash
docker compose logs -f api worker     # ดู log
docker compose down                   # ปิด (ข้อมูลยังอยู่ใน volume pgdata)
docker compose down -v                # ปิดแล้วลบข้อมูลทิ้ง
```

## รันในเครื่องตอนพัฒนา

```bash
docker compose up -d db redis                  # ฐานข้อมูล + คิว ใน Docker
pip install -r requirements-dev.txt
alembic upgrade head                           # สร้าง/อัปเดตตาราง
python -m backend.auth                         # dev user
python -m uvicorn backend.app:app --reload     # API
python -m backend.jobs                         # worker (อีกหน้าต่าง) — บน Windows ใช้ SimpleWorker ให้เอง
cd frontend && npm install && npm run dev      # หน้าเว็บที่ http://localhost:5173 (ส่งต่อ /api /auth /assets ไปที่ API ให้)
```

แก้แค่หน้าเว็บ ไม่อยากรัน Python: เปิดทั้งระบบด้วย `docker compose up -d` แล้ว `VITE_API_TARGET=http://127.0.0.1:3000 npm run dev`
ไม่มี Redis ก็ dev ได้: ตั้ง `QUEUE_BACKEND=thread` ใน `.env` แล้ว api จะรัน parse ใน thread ของตัวเอง (พฤติกรรมที่หน้าเว็บเห็นเหมือนกันทุกอย่าง)

## วิธีเพิ่มเดโม

1. **ผ่านหน้าเว็บ** — ลากไฟล์ `.dem` ลงกล่องอัปโหลดที่หัว sidebar (เลือกหลายไฟล์ได้)
   แมตช์ใหม่ขึ้นในรายการเป็น `รอคิว → กำลังแกะ → พร้อม` เองโดยไม่ต้องรีเฟรช (poll ทุก 2 วินาที)
   เปิดแมตช์ที่ยังแกะไม่เสร็จได้ จะเห็นความคืบหน้าแล้วเข้ารอบ 1 ให้เองเมื่อเสร็จ
2. **ผ่าน API** — `POST /api/demos` (multipart `file`, `force=1` ถ้าจะโหลดทับ) ตอบ 202 พร้อม `status_url`
3. **ผ่าน CLI** (ไม่ผ่านคิว) — วางไฟล์ใน `demos/` แล้ว
   ```bash
   python -m backend.parser demos/X.dem              # -> output/json/X.json
   python backend/etl_loader.py output/json/X.json  # -> PostgreSQL (--force = โหลดทับ + คำนวณฟีเจอร์ใหม่)
   ```

ชื่อไฟล์แบบ `ทีมA-vs-ทีมB-แมพ.dem` จะถูกแกะเป็นชื่อทีมให้ ไฟล์ชื่อซ้ำถูกปฏิเสธ (409) เว้นแต่ติ๊ก "โหลดทับ" หรือแมตช์นั้นเคยพัง
ทุกงานเป็น idempotent: โหลดแมตช์เดิมซ้ำกี่ครั้งก็ได้ข้อมูลชุดเดียว และ `matches.id` ไม่เปลี่ยน

## API

ทุก route ใต้ `/api` ต้องล็อกอิน ยกเว้น `/api/health` — ดูทั้งหมดได้ที่ http://localhost:3000/api/docs

| Method | Path | ใช้ทำอะไร |
|---|---|---|
| POST | `/auth/register` · `/auth/login` · `/auth/logout` | สมัคร / ล็อกอิน (ติดคุกกี้ JWT) / ออกจากระบบ |
| GET | `/auth/me` | ใครล็อกอินอยู่ (401 = ยังไม่ล็อกอิน) |
| POST | `/api/demos` | อัปโหลดเดโม → สร้างแถว `matches` (queued) → เข้าคิว → 202 |
| GET | `/api/matches` | รายการแมตช์ทั้งหมดพร้อมสรุปและสถานะ |
| GET | `/api/matches/{id}` | สรุป + รายรอบ + สกอร์บอร์ด + ฟีเจอร์ต่อคน (opening / trade / clutch / buy) |
| GET | `/api/matches/{id}/status` | `queued / parsing / done / error` + `error_message` + สถานะงานในคิว |
| GET | `/api/review/{demo_file}/rounds` | รายรอบ (ผู้ชนะ / จบด้วยอะไร / ตายกี่คน / คนแรกตายวินาทีที่เท่าไหร่) |
| GET | `/api/review/{demo_file}/rounds/{n}` | ทีม / การตายทุกครั้งพร้อมพิกเซลบนเรดาร์ / บริบทจาก grid_ml1 / สรุปรอบ |
| GET | `/api/review/{demo_file}/rounds/{n}/positions` | ตำแหน่งผู้เล่นรายวินาทีของรอบ (โหมดเล่นย้อน) ~9 KB |
| GET | `/api/review/grid?map=de_mirage` | ช่องกริดที่จัดกลุ่มแล้ว + วง hotspot เป็นพิกเซล (toggle ซ้อนบนแผนที่) |
| GET | `/api/players/{me\|steamid64}/summary` | สถิติรายคน: ภาพรวม + entry แยกฝั่ง + clutch 1v1–1v5 + Rating 2.0 (ประมาณการ) |
| GET | `/api/players/{…}/matches` · `/maps` · `/weapons` | แมตช์ล่าสุด (แพ้/ชนะ + rating) · รวมรายแมพ · อาวุธที่ฆ่าบ่อย |
| GET | `/api/health` | DB ต่อได้ไหม คิวยาวแค่ไหน มี worker กี่ตัว |

บริบทของการตายอ่านจาก `output/grid_ml1.json` (cache ในหน่วยความจำ ไม่รันโมเดลตอน request) — ยังไม่เคยรัน `python research/grid_ml1.py` หน้าเว็บจะบอกว่าไม่มีข้อมูล
พิกัดทุกจุดแปลงที่ `backend/review.py` ที่เดียว (grid_ml1.py import สูตรเดียวกัน) frontend ไม่มีสูตรแปลงพิกัดของตัวเอง

มีเฉพาะ endpoint ที่หน้าเว็บเรียกจริง — endpoint ของหน้าเว็บ Sprint 1 (`/api/players` `/api/heatmap` `/api/tactical` `/api/ml/*` …) ลบไปแล้ว ดูย้อนหลังได้ใน git

## นิยามที่ใช้ทั้งระบบ — `backend/features.py`

| ฟีเจอร์ | นิยาม |
|---|---|
| opening kill | คิลแรกของรอบหลัง freeze-time จบ (นับเฉพาะการดวล: มีคนยิงและคนละฝั่ง) |
| trade | คนที่ฆ่าเหยื่อ ตายภายใน 5 วินาทีด้วยมือเพื่อนของเหยื่อ |
| buy type | ต่อคน ณ freeze-time จบ: Full ≥ $4000 · Force $2000–4000 · Eco < $2000 · Pistol = รอบ 1 และ 13 |
| clutch | เหลือคนเดียวฝั่งตัวเอง เจอศัตรู ≥ 1 และรอบยังไม่จบ (1v1 นับทั้งสองฝั่ง) |
| ADR / KAST | ดาเมจใส่ศัตรูต่อรอบ · % รอบที่มี Kill / Assist / Survived / Traded |

คำนวณครั้งเดียวตอนโหลด (`backend/features.py`) แล้วเก็บลง `player_rounds` — `features_version` บอกรุ่นนิยาม
เปลี่ยนนิยามเมื่อไร ขยับเลขนั้นแล้ว `python backend/etl_loader.py --force` เพื่อ backfill

## ฐานข้อมูล (PostgreSQL · SQLAlchemy models ใน `backend/models.py` · migration ใน `backend/alembic/`)

| ตาราง | หนึ่งแถวคือ | คอลัมน์สำคัญ |
|---|---|---|
| `accounts` | บัญชีที่ล็อกอินหน้าเว็บ | `username` (ไม่สนตัวพิมพ์) `password_hash` (PBKDF2) `last_login` |
| `matches` | ไฟล์ .dem หนึ่งไฟล์ | `demo_file` (unique) `map_name` `tickrate` `team_a/b` **`status`** `error_message` `job_id` `started_at` `finished_at` |
| `rounds` | รอบหนึ่งของแมตช์ | `match_id` `round_num` `start_tick` (freeze จบ) `bomb_plant_tick` `bomb_plant_x/y` `bomb_site` `winner_side` `end_reason` |
| `players` | นักแข่ง (SteamID64) | `steam_id` `name` |
| `match_players` | ใครเล่นในแมตช์ไหน | `match_id` `steam_id` `team_clan` (ชื่อทีมคงที่ทั้งแมตช์) `start_side` `rounds` |
| `player_rounds` (= player_round_stats) | คนหนึ่งในรอบหนึ่ง | `side` `equip_value` `survived` + ฟีเจอร์: `buy_type` `kills` `deaths` `assists` `damage` `opening_kill/death` `trade_kills` `was_traded` `clutch_vs` `clutch_won` `kast` |
| `kills` | การฆ่าหนึ่งครั้ง | `round_id` `tick` `attacker_id` `victim_id` `assister_id` ฝั่ง อาวุธ headshot พิกัดและ callout ของทั้งคู่ |
| `player_positions` | คนหนึ่ง ณ วินาทีหนึ่ง (1 Hz) | `match_id` `round_num` `tick` `steam_id` `side` `x y z` `health` `place` — เฉพาะช่วงที่รอบเล่นและคนยังมีชีวิต |
| `grenades` | ระเบิดหนึ่งลูก | `thrower_id` `type` (smoke/flash/he/molotov/decoy) `tick` · `throw_x/y` จุดขว้าง · `land_x/y` `land_tick` จุดตก · `end_tick` ควัน/ไฟหมด |
| `damages` | ดาเมจแต่ละครั้ง | (จาก Sprint 1) |
| `users` | ผู้ใช้จาก Steam login เดิม | เลิกใช้แล้ว เก็บตารางไว้ไม่ลบ |

view สรุป (`backend/views.sql`): `match_summary` `match_scoreboard` `player_stats` `player_round_facts` `player_clutches` `round_economy`

```bash
alembic upgrade head        # อัปเดตสคีมา (ปลอดภัยบน DB ที่มีข้อมูล)
alembic downgrade -1        # ถอยหนึ่งรุ่น
alembic history
```

`player_positions` เก็บที่ 1 Hz เท่านั้น — เดโมบันทึก 64–128 tick/วินาที ถ้าเก็บทุก tick จะได้ ~2.7 ล้านแถวต่อแมตช์ (`backend/parser.py`)

## ทดสอบและ CI

```bash
ruff check .                      # lint
pytest                            # 76 เทสต์: ล็อกอิน/JWT, นิยาม 4 ตัว, ผูกทีมข้ามครึ่ง, สูตรพิกัด = grid_ml1, payload Round Review, parser บน .dem จริง
cd frontend && npm run build      # type-check + build หน้าเว็บ
```

`backend/tests/fixtures/` เก็บ snapshot ของ `output/grid_ml1.json` / `grid_ml1_cells.csv` ที่คำนวณจาก `data/all_kills.csv` ปัจจุบัน
ถ้าเพิ่มเดโมแล้วรัน `research/demoparser.py` + `research/grid_ml1.py` ใหม่ ต้องก๊อปสองไฟล์นั้นเข้า fixtures ด้วย ไม่งั้นเทสต์เทียบช่องจะแดง

test parser ต้องมีไฟล์ `.dem` (100+ MB ไม่อยู่ใน git): ใช้ไฟล์เล็กสุดใน `demos/` หรือตั้ง `CS2_TEST_DEMO=path` — ไม่มีก็ skip
GitHub Actions (`.github/workflows/ci.yml`) รัน ruff · pytest · migration up/down/up บน Postgres จริง · `npm run build`
ตั้ง repository variable `CS2_TEST_DEMO_URL` (ลิงก์ไฟล์เดโม เช่น asset ของ Release) ถ้าอยากให้ CI รัน test parser ด้วย

## โครงโปรเจกต์

```
frontend/src/       หน้าเว็บ — React + TypeScript + Vite + TanStack Query (nginx ใน Docker)
  main.tsx            เส้นทางของหน้า + ต้องล็อกอินก่อน + เมนูผู้ใช้
  LoginPage.tsx       หน้า /login
  MatchPage.tsx       หน้าหลัก: sidebar อัปโหลด/รายการแมตช์ · หัวแมตช์ · สกอร์บอร์ด · แถบรอบ
  RoundView.tsx       เนื้อหาของรอบ: รายชื่อทีม · แผนที่เรดาร์ · ไทม์ไลน์ · บริบทจาก grid_ml1
  api.ts · utils.tsx  เรียก backend · ตัวช่วยจัดรูปแบบ + state บน URL + หน้า 404
backend/            API + worker (Python 3.11)
  app.py              FastAPI: /auth/* /api/* /assets
  auth.py             ล็อกอิน (PBKDF2 + JWT ในคุกกี้ httpOnly) + สร้าง dev user
  jobs.py             คิว RQ/Redis + งาน parse_demo(match_id) + โปรเซส worker
  parser.py           .dem -> dict (awpy 2.0.2 / demoparser2 0.41.4 — pin ไว้ เพราะ CS2 อัปเดตแล้ว parser พังบ่อย)
  etl_loader.py       dict -> PostgreSQL (รันซ้ำได้ ข้อมูลไม่ซ้ำ)
  features.py         นิยาม opening / trade / buy / clutch + ผูกทีม + ตัวคำนวณ
  review.py           ข้อมูลหน้ารอบ + สูตรแปลงพิกัดชุดเดียวของรีโป
  db.py · models.py · views.sql · alembic/     ต่อฐานข้อมูล · ตาราง · view สรุป · migration
  tests/              pytest (auth · features · review · parser) + fixtures/
research/           demoparser.py · grid_ml1.py · check_radar.py — สคริปต์ ML ที่หน้าเว็บใช้ผล (ดู research/README.md)
assets/             ภาพเรดาร์ + radars.json (แหล่งความจริงของค่าปรับเทียบพิกัด)
data/               all_kills.csv ชุดคิล 50 แมตช์ที่ grid_ml1 ใช้
demos/ output/      ไฟล์ .dem ที่อัปโหลด · ผล parse (json) · ผลของ research — ไม่เข้า git
```

## ปัญหาที่เจอบ่อย

- **พอร์ต 5432 ชน** (มี PostgreSQL ในเครื่อง): ตั้ง `POSTGRES_PORT=5433` ใน `.env` และแก้ `DATABASE_URL` ให้ตรง
- **อัปโหลดแล้ว 503 "ส่งงานเข้าคิวไม่ได้"**: Redis ไม่ได้เปิด — `docker compose up -d redis` หรือใช้ `QUEUE_BACKEND=thread`
- **แถวค้าง `รอคิว` ไม่ขยับ**: ไม่มี worker — `python -m backend.jobs` หรือ `docker compose up -d worker` (`/api/health` บอกจำนวน worker)
- **แมตช์ `พัง`**: สาเหตุขึ้นในเนื้อหาหลักเมื่อเปิดแมตช์นั้น ส่งไฟล์ซ้ำได้เลยโดยไม่ต้องติ๊กโหลดทับ
- **ล็อกอินหลุดทุกครั้งที่ api รีสตาร์ต**: ยังไม่ได้ตั้ง `SECRET_KEY` ใน `.env`
- **เปลี่ยนภาพแมพแล้วแผนที่หาย**: `assets/radars.json` ต้องชี้ไปไฟล์ที่มีจริงและขนาดเดิม (1024×1024)
