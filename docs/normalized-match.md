# Normalized Match JSON — สัญญาข้อมูลกลางของระบบ (schema_version 1)

ไฟล์นี้คือ **จุดเชื่อมเดียว** ระหว่าง 3 ส่วนของ pipeline:

```
.dem ──[parser/parse_demo.py]──> normalized JSON ──[backend/src/etl]──> PostgreSQL ──> REST API ──> React
                                        ▲
                     backend/db/seed.js ─┘  (ข้อมูลจำลอง ใช้ schema เดียวกันเป๊ะ)
```

หลักการ: **parser ส่งเฉพาะ "ข้อเท็จจริงดิบ"** (ใครฆ่าใคร ตอน tick ไหน ตรงพิกัดไหน)
ส่วน **สถิติที่ต้องคำนวณ** (opening duel, trade, clutch, ADR, KPI 5 มิติ) คิดที่ชั้น ETL
(`backend/src/etl/derive.js`) ที่เดียว — จะได้ไม่มีสูตรซ้ำสองที่แล้วเพี้ยนกันทีหลัง

---

## โครงสร้าง

```jsonc
{
  "schema_version": 1,
  "match": {
    "external_id": "de_mirage_2025-08-01_a1b2c3d4",  // ต้องไม่ซ้ำ — ใช้กันโหลดซ้ำ (idempotent)
    "map_name": "de_mirage",
    "started_at": "2025-08-01T18:02:11.000Z",         // ISO 8601 (UTC) หรือ null
    "finished_at": "2025-08-01T18:47:52.000Z",
    "tickrate": 64,
    "source": "demo",                                 // "demo" = parse จากไฟล์จริง | "sample" = seed
    "demo_file": "match730_003...dem",                // ชื่อไฟล์ต้นทาง หรือ null
    "server_name": "Valve Matchmaking"                // optional
  },

  // ผู้เล่นทุกคนในแมตช์ — team_number คือ "ทีมตามฝั่งที่เริ่มต้นครึ่งแรก"
  //   2 = ทีมที่เริ่มเป็น T   |   3 = ทีมที่เริ่มเป็น CT
  // (ยึดเลขเดิมของทั้งระบบไว้ เพราะหน้า Match ฝั่ง frontend ใช้ค่านี้อยู่แล้ว)
  "players": [
    { "steam64_id": "76561198000000001", "name": "s1mple", "team_number": 2 }
  ],

  "rounds": [
    {
      "round_number": 1,                 // เริ่มที่ 1
      "winner_team_number": 2,           // 2 หรือ 3 (แปลงจากฝั่ง ct/t เป็น "ทีม" ให้แล้ว)
      "winner_side": "t",                // "t" | "ct" — ฝั่งที่ชนะ ณ รอบนั้น
      "end_reason": "t_win",             // สตริงดิบจาก demo (bomb_exploded, ct_win, …)
      "bomb_planted": false,
      "start_tick": 12800, "freeze_end_tick": 13800,
      "end_tick": 18422,  "official_end_tick": 18742
    }
  ],

  // เหตุการณ์รายรอบ — พิกัดเก็บไว้ทำ heatmap ในสprintถัดไป
  "events": [
    {
      "type": "kill",                    // kill | damage | grenade | bomb
      "round_number": 4,
      "tick": 24011,
      "actor_steam64": "765...01",       // ผู้ยิง / ผู้ขว้าง / ผู้ปลดชนวน (null ได้)
      "victim_steam64": "765...07",
      "assister_steam64": null,
      "weapon": "ak47",
      "headshot": true,
      "damage": 100,                     // kill: hp ที่ทำได้ | damage: dmg_health | grenade: ยูทิลิตี้ดาเมจ
      "actor_x": -1234.5, "actor_y": 880.25, "actor_z": -167.0,
      "victim_x": -980.0, "victim_y": 1122.5, "victim_z": -167.0,
      "meta": { "hitgroup": "head", "noscope": false, "through_smoke": false }
    }
  ]
}
```

### กติกาที่ ETL บังคับ (validate ก่อนเขียน DB)

| กติกา | เหตุผล |
|---|---|
| `match.external_id` ห้ามว่าง และต้องไม่ซ้ำ | โหลดไฟล์เดิมซ้ำต้องได้ผลเท่าเดิม ไม่ใช่ข้อมูลซ้อน |
| `players[].steam64_id` ต้องเป็นตัวเลข 17 หลัก | ตรงกับ validation ของ REST API เดิม |
| `players[].team_number` ต้องเป็น 2 หรือ 3 | สกอร์บอร์ดฝั่ง frontend แบ่งสองฝั่งด้วยค่านี้ |
| `rounds[].round_number` ต้องเรียง 1..N ไม่ข้าม | ใช้คิด opening duel / clutch ตามลำดับรอบ |
| `events[].round_number` ต้องมีอยู่ใน `rounds` | กัน event หลุดจากช่วง warmup/knife round |
| event ที่ steam64 ไม่อยู่ใน `players` | ถูกตัดทิ้งพร้อม warning (bot, ผู้ชม, ผู้เล่นที่ออกกลางคัน) |

### ประเภท event ที่ระบบใช้ตอนนี้

- **kill** — ใช้คิด K/D, HS%, opening duel, trade, clutch, survival
- **damage** — ใช้คิด ADR และ utility damage (`weapon` เป็น hegrenade/molotov/inferno)
- **grenade** — ใช้คิดจำนวนยูทิลิตี้ที่ใช้ (flash/smoke/he/molotov)
- **bomb** — plant/defuse (ยังไม่เข้าสูตร KPI แต่เก็บไว้ก่อนสำหรับ sprint ถัดไป)
