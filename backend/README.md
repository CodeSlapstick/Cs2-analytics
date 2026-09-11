# backend/ — API + worker + parser + feature layer

FastAPI (Python 3.11) + PostgreSQL 16 + Redis/RQ — ตอบ `/auth/*` `/api/*` และภาพเรดาร์ `/assets` ให้หน้าเว็บ React ใน `frontend/`
ผู้ใช้ไม่ได้เปิด API ตรง ๆ: ใน Docker nginx ของหน้าเว็บ (http://localhost:3000) ส่ง `/api` `/auth` `/assets` มาที่นี่
และ container ของ API ไม่เปิดพอร์ตออกมานอกเครื่อง

```
backend/
  app.py          FastAPI — routes ทั้งหมด (/auth/*, /api/*, /assets)
  auth.py         ล็อกอิน: รหัสผ่านแบบ PBKDF2 hash + JWT ในคุกกี้ httpOnly
  seed_user.py    สร้าง dev user (dev / cs2dev1234) รันซ้ำได้
  db.py           ต่อ PostgreSQL ด้วย asyncpg (อ่าน DATABASE_URL จาก .env ที่ราก)
  database.py     SQLAlchemy engine (Alembic ใช้)
  models.py       SQLAlchemy models = แหล่งความจริงของสคีมา
  alembic/        migration 0001-0005 (ตารางสร้างด้วย alembic upgrade head)
  views.sql       view สรุปสถิติ — รันซ้ำทุกครั้งที่ api สตาร์ต ไม่แตะข้อมูล
  jobs.py         งาน parse_demo(match_id): queued -> parsing -> done | error
  jobqueue.py     ส่งงานเข้าคิว RQ บน Redis (หรือ thread ตอน dev)   worker.py  โปรเซสที่หยิบงาน
  parser/         .dem -> dict (service.py) ใช้ทั้ง worker และ CLI
  features/       นิยาม opening / trade / buy / clutch (definitions.py) + ตัวคำนวณ (compute.py) + ผูกทีม (teams.py)
  geo.py          สูตรแปลงพิกัดเกม -> ช่องกริด / พิกเซลเรดาร์ ชุดเดียวของรีโป
  review.py       payload หน้า Round Review + อ่าน output/grid_ml1.json (cache ในหน่วยความจำ)
  etl_loader.py   dict/JSON -> PostgreSQL (idempotent)
  tests/          pytest
```

## รันในเครื่อง

```bash
docker compose up -d db redis                  # ฐานข้อมูล + คิวใน Docker
pip install -r requirements-dev.txt
alembic upgrade head                           # สร้าง/อัปเดตตาราง
python -m backend.seed_user                    # dev user: dev / cs2dev1234
python -m uvicorn backend.app:app --reload     # API
python -m backend.worker                       # อีกหน้าต่าง — แกะเดโมที่อัปโหลด
```

แล้วเปิดหน้าเว็บด้วย `cd frontend && npm run dev` (ดู README หลัก) — Swagger ของ API อยู่ที่ `<หน้าเว็บ>/api/docs`
ไม่มี Redis ก็ dev ได้: ตั้ง `QUEUE_BACKEND=thread` ใน `.env`

## ล็อกอิน

| Endpoint | ได้อะไร |
|---|---|
| `POST /auth/register` | สมัครแล้วล็อกอินให้เลย `{username, password}` (ปิดได้ด้วย `ALLOW_REGISTER=0`) |
| `POST /auth/login` | ตรวจรหัสผ่าน ติดคุกกี้ `cs2_token` (JWT httpOnly อายุ 7 วัน) |
| `GET /auth/me` | ใครล็อกอินอยู่ — ยังไม่ล็อกอินตอบ 401 |
| `POST /auth/logout` | ลบคุกกี้ |

ทุก route ใต้ `/api` ต้องล็อกอิน ยกเว้น `/api/health` · ตั้ง `SECRET_KEY` ใน `.env` ไม่งั้นทุกคนหลุดเมื่อ api รีสตาร์ต

## API

| Endpoint | ใช้ที่ไหน |
|---|---|
| `GET /api/health` | docker / monitor — DB ต่อได้ไหม คิวยาวแค่ไหน |
| `GET /api/matches` · `GET /api/matches/{id}` · `GET /api/matches/{id}/status` | sidebar รายการแมตช์ · สกอร์บอร์ด · สถานะการแกะ |
| `POST /api/demos` | อัปโหลดเดโม -> เข้าคิว -> 202 |
| `GET /api/review/{demo_file}/rounds` · `/rounds/{n}` · `GET /api/review/grid?map=` | หน้าหลัก: แถบรอบ · เนื้อหารอบ · ชั้นซ้อนจาก grid_ml1 |

ยังเก็บไว้แต่ยังไม่มีหน้า React เรียก (เป็นของหน้าเว็บ Sprint 1 ที่ลบไปแล้ว ไว้ทำหน้าใหม่ทีหลัง):
`/api/stats` `/api/players` `/api/players/{steam_id}` `/api/heatmap` `/api/radar` `/api/tactical`
`/api/matches/{id}/rounds` `/api/matches/{id}/review` `/api/ml/round-win` `/api/ml/grid` `POST /api/ml/retrain`

## ฐานข้อมูล

ตารางและคอลัมน์อธิบายไว้ใน README หลัก (หัวข้อฐานข้อมูล) · `models.py` ต้องตรงกับ migration ล่าสุดเสมอ

```bash
alembic upgrade head        # อัปเดตสคีมา (ปลอดภัยบน DB ที่มีข้อมูล)
alembic downgrade -1        # ถอยหนึ่งรุ่น
alembic revision -m "..."   # migration ใหม่ (เขียน SQL เองด้วย backend.migrate_util.execute_script)
```

- แก้ view: แก้ `views.sql` แล้วรีสตาร์ต api
- ตาราง/คอลัมน์ใหม่: แก้ `models.py` + เขียน migration คู่กัน แล้ว `alembic upgrade head`

## เพิ่มเดโม

ทางหลักคืออัปโหลดที่ sidebar ของหน้าเว็บ หรือ `POST /api/demos` — worker แกะแล้วเข้าฐานข้อมูลเอง
ทาง CLI (ไม่ผ่านคิว):

```bash
python -m backend.parser.service demos/X.dem     # -> output/json/X.json
python backend/etl_loader.py output/json/X.json  # -> PostgreSQL (--force = โหลดทับ + คำนวณฟีเจอร์ใหม่)
```
