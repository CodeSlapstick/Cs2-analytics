# backend/ — เซิร์ฟเวอร์หลังบ้าน + ฐานข้อมูล

FastAPI + PostgreSQL 16 (ผ่าน asyncpg) — เสิร์ฟหน้าเว็บใน `frontend/`, จัดการล็อกอิน Steam
และตอบ `/api/*` จากฐานข้อมูล

```
backend/
  app.py          FastAPI — routes ทั้งหมด
  db.py           จุดเดียวที่ต่อ PostgreSQL (อ่าน DATABASE_URL จาก .env ที่ราก)
  schema.sql      โครงตาราง + view (รันซ้ำได้ ทุกคำสั่งเป็น IF NOT EXISTS)
  load_kills.py   data/all_kills.csv -> DB
```

## รันครั้งแรก

```bash
cp .env.example .env                    # แก้ POSTGRES_PORT=5433 ถ้าเครื่องมี Postgres อยู่แล้ว
docker compose up -d db                 # เปิดฐานข้อมูล (สร้างตารางจาก schema.sql ให้เอง)
python backend/load_kills.py            # โหลดชุดคิล 7,270 แถวเข้า DB (~2 วินาที)
python -m uvicorn backend.app:app --reload
```

เปิด http://localhost:8000 — ยังไม่มีกุญแจ Steam ก็ใช้ปุ่ม "เข้าใช้งานแบบทดสอบ" ได้

หรือรันทุกอย่างใน Docker ไม่ต้องลง Python:

```bash
docker compose up -d                                          # db + api
docker compose run --rm api python backend/load_kills.py      # โหลดข้อมูล
```

## โครงฐานข้อมูล

```
matches ─1:n─ rounds ─1:n─ kills ─n:1─ players   (attacker / victim / assister)
users                                            (คนล็อกอินเว็บ แยกจาก players ที่เป็นนักแข่งในเดโม)
```

| ตาราง | หนึ่งแถวคือ | คอลัมน์สำคัญ |
|---|---|---|
| `matches` | ไฟล์ .dem หนึ่งไฟล์ | `demo_file` (unique กันโหลดซ้ำ), `map_name`, `tickrate`, `team_a/b` |
| `rounds` | รอบหนึ่งของแมตช์ | `winner_side`, `end_reason`, `bomb_plant_tick` (NULL = ไม่ได้วาง) |
| `kills` | การฆ่าหนึ่งครั้ง | ใคร/ที่ไหน/ด้วยอะไร + พิกัด x,y,z ของทั้งคู่ + callout |
| `players` | นักแข่งหนึ่งคน | `steam_id` (BIGINT), `name` ล่าสุดที่เห็น |
| `users` | ผู้ใช้เว็บที่ล็อกอิน | `steamid`, `mode` (`steam` จริง / `dev` ทดสอบ) |

View ที่เตรียมไว้ให้ API ไม่ต้องเขียน SQL ยาว:
`match_summary` (รอบ/คิล/ใครชนะกี่รอบ ต่อแมตช์) และ `player_stats` (K/D/A, HS%, จำนวนแมตช์ ต่อคน)

> **ระวัง SteamID64** — เลข 17 หลักเกินที่ `float64` เก็บได้แม่น ตอนอ่าน csv ต้องบังคับ
> `dtype="Int64"` ไม่งั้น pandas จะเดาเป็น float แล้วเลขท้ายเพี้ยน (load_kills.py ทำไว้แล้ว)

## API

ทุกอันใต้ `/api/` ต้องล็อกอินก่อน (ตอบ 401 ถ้าไม่มีคุกกี้) ยกเว้น `health` กับ `config`

| Endpoint | ได้อะไร |
|---|---|
| `GET /api/health` | DB ต่อได้ไหม มีกี่แมตช์/กี่คิล |
| `GET /api/me` | ใครล็อกอินอยู่ |
| `GET /api/config` | เปิดโหมดทดสอบไหม มีกุญแจ Steam ไหม |
| `GET /api/stats?map=de_mirage` | สรุปภาพรวมให้หน้าหลัก (ไม่ใส่ `map` = ทุกแมพ) |
| `GET /api/matches` | รายชื่อแมตช์ + สรุป |
| `GET /api/matches/{id}` | แมตช์เดียว: รายรอบ + สกอร์บอร์ด |
| `GET /api/players?limit=20&min_matches=3` | นักแข่งเรียงตามคิล |
| `GET /api/players/{steam_id}` | คนเดียว: สถิติ + ปืน + จุดที่ฆ่า/ตายบ่อย |
| `GET /api/heatmap?map=de_mirage&side=ct` | พิกัดคนตายบนแมพ (ระบบเกม — แปลงด้วย `assets/radars.json` ก่อนวาด) |

Swagger UI อยู่ที่ http://localhost:8000/docs กดลองยิงได้เลย (ล็อกอินที่หน้าเว็บก่อน คุกกี้ใช้ร่วมกัน)

## เพิ่มเดโมใหม่

```bash
# วาง .dem ใน demos/ แล้ว
python research/demoparser.py           # -> data/all_kills.csv (อ่านเฉพาะไฟล์ที่ยังไม่เคยอ่าน)
python backend/load_kills.py            # โหลดเฉพาะแมตช์ที่ยังไม่มีใน DB
python backend/load_kills.py --force    # หรือลบทั้งหมดแล้วโหลดใหม่
```

## แก้ schema

แก้ `schema.sql` แล้ว
- เพิ่มตาราง/คอลัมน์/view ใหม่: รีสตาร์ต api ก็พอ (มันรัน schema.sql ทุกครั้งที่สตาร์ต)
- เปลี่ยนคอลัมน์ที่มีอยู่แล้ว: `IF NOT EXISTS` ไม่ช่วย ต้อง `docker compose down -v` แล้วเริ่มใหม่ + โหลดข้อมูลอีกรอบ
