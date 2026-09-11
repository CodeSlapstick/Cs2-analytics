# CS2 Scouting Platform

เว็บวิเคราะห์เดโม Counter-Strike 2 สำหรับโค้ช/ทีม — อัปโหลดไฟล์ `.dem` แล้วระบบแกะในเบื้องหลัง
เปิดดูสถิติของแมตช์นั้นได้ทันทีที่เสร็จ (SP-404 Senior Project · UTCC STECH)

```
เบราว์เซอร์ ──► frontend (React, :3000) ──► api (FastAPI, :8000) ──► PostgreSQL
                                                │  ▲                      ▲
                                        enqueue │  │ status               │ INSERT
                                                ▼  │                      │
                                              Redis ──► worker ── parse_demo(match_id) ── awpy/demoparser2
                                                        │
                                                        └── backend/features  (opening / trade / buy / clutch / KAST)
```

Sprint 1 ตอบว่า "จุดปะทะสำคัญอยู่ตรงไหน ตรงไหนใครได้เปรียบ" ด้วยโมเดลบน Mirage 50 แมตช์ (ดู `research/`)
Sprint 2 เปลี่ยนสิ่งนั้นจากสคริปต์เป็นระบบที่ใช้งานได้จริง end-to-end: **อัปโหลด → parse ในเบื้องหลัง → ดูสถิติ**

---

## เริ่มใช้ในคำสั่งเดียว (Docker)

```bash
cp .env.example .env          # ค่าเริ่มต้นใช้ได้เลย (ถ้าเครื่องมี PostgreSQL อยู่แล้ว ตั้ง POSTGRES_PORT=5433)
docker compose up -d          # db + redis + api + worker + frontend
```

| ที่อยู่ | คืออะไร |
|---|---|
| http://localhost:3000 | หน้าเว็บ Sprint 2 (React) — Match Library + Match Overview |
| http://localhost:8000 | API (Swagger ที่ `/docs`) + หน้าเว็บ Sprint 1 ที่ยังใช้ได้ (`/upload` `/map` `/ml` …) |
| localhost:5432 (หรือ `POSTGRES_PORT`) | PostgreSQL · user/pass `postgres` · db `cs2_analytics` |

`api` รัน `alembic upgrade head` ให้เองตอนสตาร์ต จึงเปิดบนฐานข้อมูลเปล่าได้ทันที และเปิดบนฐานข้อมูลเดิมของ Sprint 1 ได้โดยไม่เสียข้อมูล

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
python -m uvicorn backend.app:app --reload     # API ที่ :8000
python -m backend.worker                       # worker (อีกหน้าต่าง) — บน Windows ใช้ SimpleWorker ให้เอง
cd frontend && npm install && npm run dev      # React ที่ :5173 (proxy /api ไป :8000 ให้)
```

ไม่มี Redis ก็ dev ได้: ตั้ง `QUEUE_BACKEND=thread` ใน `.env` แล้ว api จะรัน parse ใน thread ของตัวเอง (พฤติกรรมที่หน้าเว็บเห็นเหมือนกันทุกอย่าง)

## วิธีเพิ่มเดโม

1. **ผ่านหน้าเว็บ** — เปิด http://localhost:3000 ลากไฟล์ `.dem` ลงกล่อง (เลือกหลายไฟล์ได้)
   แถวจะขึ้นเป็น `รอคิว → กำลังแกะ → พร้อม` เองโดยไม่ต้องรีเฟรช (poll ทุก 2 วินาที) แล้วกด "ดูสถิติ →"
2. **ผ่าน API** — `POST /api/demos` (multipart `file`, `force=1` ถ้าจะโหลดทับ) ตอบ 202 พร้อม `status_url`
3. **ผ่าน CLI** (ไม่ผ่านคิว) — วางไฟล์ใน `demos/` แล้ว
   ```bash
   python -m backend.parser.service demos/X.dem     # -> output/json/X.json
   python backend/etl_loader.py output/json/X.json  # -> PostgreSQL (--force = โหลดทับ + คำนวณฟีเจอร์ใหม่)
   ```

ชื่อไฟล์แบบ `ทีมA-vs-ทีมB-แมพ.dem` จะถูกแกะเป็นชื่อทีมให้ ไฟล์ชื่อซ้ำถูกปฏิเสธ (409) เว้นแต่ติ๊ก "โหลดทับ" หรือแมตช์นั้นเคยพัง
ทุกงานเป็น idempotent: โหลดแมตช์เดิมซ้ำกี่ครั้งก็ได้ข้อมูลชุดเดียว และ `matches.id` ไม่เปลี่ยน

## API

| Method | Path | ใช้ทำอะไร |
|---|---|---|
| POST | `/api/demos` | อัปโหลดเดโม → สร้างแถว `matches` (queued) → เข้าคิว → 202 |
| GET | `/api/matches/{id}/status` | `queued / parsing / done / error` + `error_message` + สถานะงานในคิว |
| GET | `/api/matches` | รายการแมตช์ทั้งหมดพร้อมสรุปและสถานะ |
| GET | `/api/matches/{id}` | สรุป + รายรอบ + สกอร์บอร์ด + ฟีเจอร์ต่อคน (opening / trade / clutch / buy) |
| GET | `/api/health` | DB ต่อได้ไหม คิวยาวแค่ไหน มี worker กี่ตัว |

endpoint อื่น ๆ ของ Sprint 1 (`/api/players` `/api/heatmap` `/api/tactical` `/api/ml/*`) ยังอยู่ครบ — ดู `/docs`
ทุก `/api/*` ต้องล็อกอิน: หน้า React ล็อกอินโหมดทดสอบให้เอง (Sprint 2 ยังไม่มีระบบผู้ใช้ — `ALLOW_DEV_LOGIN=1`)

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
| `matches` | ไฟล์ .dem หนึ่งไฟล์ | `demo_file` (unique) `map_name` `tickrate` `team_a/b` **`status`** `error_message` `job_id` `started_at` `finished_at` |
| `rounds` | รอบหนึ่งของแมตช์ | `match_id` `round_num` `start_tick` (freeze จบ) `bomb_plant_tick` `winner_side` `end_reason` |
| `players` | นักแข่ง (SteamID64) | `steam_id` `name` |
| `match_players` | ใครเล่นในแมตช์ไหน | `match_id` `steam_id` `start_side` `rounds` |
| `player_rounds` (= player_round_stats) | คนหนึ่งในรอบหนึ่ง | `side` `equip_value` `survived` + ฟีเจอร์: `buy_type` `kills` `deaths` `assists` `damage` `opening_kill/death` `trade_kills` `was_traded` `clutch_vs` `clutch_won` `kast` |
| `kills` | การฆ่าหนึ่งครั้ง | `round_id` `tick` `attacker_id` `victim_id` `assister_id` ฝั่ง อาวุธ headshot พิกัดและ callout ของทั้งคู่ |
| `player_positions` | คนหนึ่ง ณ วินาทีหนึ่ง (1 Hz) | `match_id` `round_num` `tick` `steam_id` `side` `x y z` `health` `place` — เฉพาะช่วงที่รอบเล่นและคนยังมีชีวิต |
| `damages` `grenades` `users` | ดาเมจแต่ละครั้ง · ระเบิดแต่ละลูก · ผู้ใช้เว็บ | (จาก Sprint 1) |

view สรุป (`backend/views.sql`): `match_summary` `match_scoreboard` `player_stats` `player_round_facts` `player_clutches` `round_economy`

```bash
alembic upgrade head        # อัปเดตสคีมา (ปลอดภัยบน DB ที่มีข้อมูล)
alembic downgrade -1        # ถอยหนึ่งรุ่น
alembic history
```

`player_positions` เก็บที่ 1 Hz เท่านั้น — เดโมบันทึก 64–128 tick/วินาที ถ้าเก็บทุก tick จะได้ ~2.7 ล้านแถวต่อแมตช์ (`backend/parser/service.py`)

## ทดสอบและ CI

```bash
ruff check .        # lint
pytest              # 28 เทสต์: นิยาม 4 ตัว (doc สังเคราะห์), fixture เดโมจริง 6 รอบ, parser บน .dem จริง
```

test parser ต้องมีไฟล์ `.dem` (100+ MB ไม่อยู่ใน git): ใช้ไฟล์เล็กสุดใน `demos/` หรือตั้ง `CS2_TEST_DEMO=path` — ไม่มีก็ skip
GitHub Actions (`.github/workflows/ci.yml`) รัน ruff · pytest · migration up/down/up บน Postgres จริง · `npm run build`
ตั้ง repository variable `CS2_TEST_DEMO_URL` (ลิงก์ไฟล์เดโม เช่น asset ของ Release) ถ้าอยากให้ CI รัน test parser ด้วย

## โครงโปรเจกต์

```
backend/            FastAPI + worker + parser + feature layer (Python 3.11)
  app.py              API และหน้าเว็บ Sprint 1
  jobs.py             parse_demo(match_id): queued -> parsing -> done | error
  jobqueue.py         คิว RQ/Redis (หรือ thread)     worker.py  โปรเซสที่หยิบงาน
  parser/service.py   .dem -> dict (awpy 2.0.2 / demoparser2 0.41.4 — pin ไว้ เพราะ CS2 อัปเดตแล้ว parser พังบ่อย)
  features/           definitions.py (นิยาม) · compute.py (คำนวณ)
  models.py · alembic/ · views.sql · etl_loader.py · db.py · database.py
  web/                หน้าเว็บ vanilla ของ Sprint 1 (ยังเสิร์ฟที่ :8000 จนกว่าจะย้ายครบใน Sprint 3)
  tests/              pytest + fixtures/sample_match.json
frontend/           React + TypeScript + Vite + TanStack Query (Match Library, Match Overview)
research/           สคริปต์วิเคราะห์/ML ของ Sprint 1 (grid_ml, round_win, …) — ไม่ใช่ส่วนหนึ่งของระบบที่รัน
assets/             ภาพเรดาร์ + radars.json (แหล่งความจริงของค่าปรับเทียบพิกัด)
data/               all_kills.csv ชุดคิล 50 แมตช์ที่สคริปต์วิจัยใช้
demos/ output/      ไฟล์ .dem ที่อัปโหลด · ผล parse (json) — ไม่เข้า git
```

## ปัญหาที่เจอบ่อย

- **พอร์ต 5432 ชน** (มี PostgreSQL ในเครื่อง): ตั้ง `POSTGRES_PORT=5433` ใน `.env` และแก้ `DATABASE_URL` ให้ตรง
- **อัปโหลดแล้ว 503 "ส่งงานเข้าคิวไม่ได้"**: Redis ไม่ได้เปิด — `docker compose up -d redis` หรือใช้ `QUEUE_BACKEND=thread`
- **แถวค้าง `queued` ไม่ขยับ**: ไม่มี worker — `python -m backend.worker` หรือ `docker compose up -d worker` (`/api/health` บอกจำนวน worker)
- **แมตช์ `error`**: ดู `error_message` ในตาราง/หน้าเว็บ ส่งไฟล์ซ้ำได้เลยโดยไม่ต้องติ๊กโหลดทับ
- **เปลี่ยนภาพแมพแล้วแผนที่หาย**: `assets/radars.json` ต้องชี้ไปไฟล์ที่มีจริงและขนาดเดิม (1024×1024)
