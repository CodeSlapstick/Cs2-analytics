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
                                                                                   └── backend/features  (opening / trade / buy / clutch / KAST)
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
รหัสผ่านเก็บเป็น PBKDF2 hash ส่วน session เป็น JWT ในคุกกี้ httpOnly อายุ 7 วัน (`backend/auth.py`) — ตั้ง `SECRET_KEY` ใน `.env` ไว้ ไม่งั้นทุกคนหลุดเมื่อ api รีสตาร์ต
ลืมรหัส dev: `python -m backend.seed_user --reset` (ในเครื่อง) หรือ `docker compose exec api python -m backend.seed_user --reset`

### หน้าเว็บ

หน้าหลักมีหน้าเดียวที่ `/matches/{demo_file}/rounds/{round_num}` เช่น `/matches/Vitality-vs-Legacy-Mirage.dem/rounds/1`

- **sidebar ซ้าย** — ฟอร์มอัปโหลดที่หัวแถบ + รายการแมตช์ทั้งหมด กดแล้วไปรอบ 1 ของแมตช์นั้น ย่อเก็บได้
- **หัวแมตช์** — สกอร์ + ปุ่มเปิดสกอร์บอร์ดทั้งแมตช์ (K/D, ADR, KAST, opening, trade, clutch)
- **แถบรอบ** — เท่าจำนวนรอบจริง กดหรือใช้ปุ่ม ← / → บนคีย์บอร์ด
- **เนื้อหารอบ** — รายชื่อทีม / แผนที่จุดตาย / ไทม์ไลน์ / บริบทจาก grid_ml1

state ทั้งหมดอยู่บน URL (`?sb=0` ย่อ sidebar, `board=1` สกอร์บอร์ด, `cells=1` `hs=1` ชั้นซ้อน, `p=` ผู้เล่นที่ไฮไลต์, `d=` การตายที่เลือก)
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
python -m backend.seed_user                    # dev user
python -m uvicorn backend.app:app --reload     # API
python -m backend.worker                       # worker (อีกหน้าต่าง) — บน Windows ใช้ SimpleWorker ให้เอง
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
   python -m backend.parser.service demos/X.dem     # -> output/json/X.json
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
| GET | `/api/review/grid?map=de_mirage` | ช่องกริดที่จัดกลุ่มแล้ว + วง hotspot เป็นพิกเซล (toggle ซ้อนบนแผนที่) |
| GET | `/api/health` | DB ต่อได้ไหม คิวยาวแค่ไหน มี worker กี่ตัว |

Round Review ใช้ `/api/review/` ไม่ใช่ `/api/matches/` เพราะ `/api/matches/{id}/rounds` เดิมรับเลข id
บริบทของการตายอ่านจาก `output/grid_ml1.json` (cache ในหน่วยความจำ ไม่รันโมเดลตอน request) — ยังไม่เคยรัน `python research/grid_ml1.py` หน้าเว็บจะบอกว่าไม่มีข้อมูล
พิกัดทุกจุดแปลงที่ `backend/geo.py` ที่เดียว (grid_ml1.py import สูตรเดียวกัน) frontend ไม่มีสูตรแปลงพิกัดของตัวเอง

endpoint ของหน้าเว็บ Sprint 1 ที่ลบไปแล้ว (`/api/players` `/api/heatmap` `/api/tactical` `/api/ml/*` …) ยังเก็บไว้สำหรับทำหน้า React ทีหลัง — รายการอยู่ใน `backend/README.md`

## นิยามที่ใช้ทั้งระบบ — `backend/features/definitions.py`

| ฟีเจอร์ | นิยาม |
|---|---|
| opening kill | คิลแรกของรอบหลัง freeze-time จบ (นับเฉพาะการดวล: มีคนยิงและคนละฝั่ง) |
| trade | คนที่ฆ่าเหยื่อ ตายภายใน 5 วินาทีด้วยมือเพื่อนของเหยื่อ |
| buy type | ต่อคน ณ freeze-time จบ: Full ≥ $4000 · Force $2000–4000 · Eco < $2000 · Pistol = รอบ 1 และ 13 |
| clutch | เหลือคนเดียวฝั่งตัวเอง เจอศัตรู ≥ 1 และรอบยังไม่จบ (1v1 นับทั้งสองฝั่ง) |
| ADR / KAST | ดาเมจใส่ศัตรูต่อรอบ · % รอบที่มี Kill / Assist / Survived / Traded |

คำนวณครั้งเดียวตอนโหลด (`backend/features/compute.py`) แล้วเก็บลง `player_rounds` — `features_version` บอกรุ่นนิยาม
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
| `damages` `grenades` | ดาเมจแต่ละครั้ง · ระเบิดแต่ละลูก | (จาก Sprint 1) |
| `users` | ผู้ใช้จาก Steam login เดิม | เลิกใช้แล้ว เก็บตารางไว้ไม่ลบ |

view สรุป (`backend/views.sql`): `match_summary` `match_scoreboard` `player_stats` `player_round_facts` `player_clutches` `round_economy`

```bash
alembic upgrade head        # อัปเดตสคีมา (ปลอดภัยบน DB ที่มีข้อมูล)
alembic downgrade -1        # ถอยหนึ่งรุ่น
alembic history
```

`player_positions` เก็บที่ 1 Hz เท่านั้น — เดโมบันทึก 64–128 tick/วินาที ถ้าเก็บทุก tick จะได้ ~2.7 ล้านแถวต่อแมตช์ (`backend/parser/service.py`)

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
frontend/           หน้าเว็บทั้งหมด — React + TypeScript + Vite + TanStack Query, nginx ใน Docker
  src/pages/          LoginPage · MatchPage (หน้าหลักหน้าเดียว) · NotFound
  src/components/     MatchSidebar · MatchScoreboard · ProtectedRoute · UserMenu · review/ (RoundView, MapView, …)
  src/review/         urlState.ts (state บน URL) · format.ts
backend/            API + worker + parser + feature layer (Python 3.11) — รายละเอียดใน backend/README.md
  app.py              FastAPI: /auth/* /api/* /assets
  auth.py             ล็อกอิน (PBKDF2 + JWT ในคุกกี้ httpOnly) · seed_user.py dev user
  jobs.py             parse_demo(match_id): queued -> parsing -> done | error
  jobqueue.py         คิว RQ/Redis (หรือ thread)     worker.py  โปรเซสที่หยิบงาน
  parser/service.py   .dem -> dict (awpy 2.0.2 / demoparser2 0.41.4 — pin ไว้ เพราะ CS2 อัปเดตแล้ว parser พังบ่อย)
  features/           definitions.py (นิยาม) · compute.py (คำนวณ) · teams.py (ผูกทีม)
  models.py · alembic/ · views.sql · etl_loader.py · db.py · database.py · geo.py · review.py
  tests/              pytest + fixtures/
research/           สคริปต์วิเคราะห์/ML ของ Sprint 1 (grid_ml, grid_ml1, round_win, …) — ไม่ใช่ส่วนหนึ่งของระบบที่รัน
assets/             ภาพเรดาร์ + radars.json (แหล่งความจริงของค่าปรับเทียบพิกัด)
data/               all_kills.csv ชุดคิล 50 แมตช์ที่สคริปต์วิจัยใช้
demos/ output/      ไฟล์ .dem ที่อัปโหลด · ผล parse (json) · ผลของ research — ไม่เข้า git
```

## ปัญหาที่เจอบ่อย

- **พอร์ต 5432 ชน** (มี PostgreSQL ในเครื่อง): ตั้ง `POSTGRES_PORT=5433` ใน `.env` และแก้ `DATABASE_URL` ให้ตรง
- **อัปโหลดแล้ว 503 "ส่งงานเข้าคิวไม่ได้"**: Redis ไม่ได้เปิด — `docker compose up -d redis` หรือใช้ `QUEUE_BACKEND=thread`
- **แถวค้าง `รอคิว` ไม่ขยับ**: ไม่มี worker — `python -m backend.worker` หรือ `docker compose up -d worker` (`/api/health` บอกจำนวน worker)
- **แมตช์ `พัง`**: สาเหตุขึ้นในเนื้อหาหลักเมื่อเปิดแมตช์นั้น ส่งไฟล์ซ้ำได้เลยโดยไม่ต้องติ๊กโหลดทับ
- **ล็อกอินหลุดทุกครั้งที่ api รีสตาร์ต**: ยังไม่ได้ตั้ง `SECRET_KEY` ใน `.env`
- **เปลี่ยนภาพแมพแล้วแผนที่หาย**: `assets/radars.json` ต้องชี้ไปไฟล์ที่มีจริงและขนาดเดิม (1024×1024)
