# research/ — สคริปต์ ML ที่หน้าเว็บใช้ผล

รันจากรากโปรเจกต์เสมอ · อ่านจาก `demos/` `data/` แล้วเขียนผลลง `data/` หรือ `output/`

| ไฟล์ | ทำอะไร | อ่าน → เขียน |
|---|---|---|
| `demoparser.py` | อ่านเดโมทุกไฟล์ รวมการฆ่าเป็นตารางเดียว และเพิ่มฟีเจอร์ role-ready ระดับ event: opening, early, trade, pre/post-plant, site engagement (แคชรายไฟล์ พังกลางทางไม่ต้องเริ่มใหม่) | `demos/reference/**/*.dem` → `data/all_kills.csv` |
| `grid_ml1.py` | unsupervised — MeanShift หาจุดปะทะ + KMeans จัดประเภทช่องกริด · หน้ารอบใช้ผลนี้ (บริบทการตาย + ชั้นซ้อนบนแผนที่) | `data/all_kills.csv` → `output/models/<map>/grid_ml1.json` (+ csv, png) |
| `check_radar.py` | ตรวจค่าปรับเทียบใน `assets/radars.json` — ฉายจุดตายจริงลงภาพเรดาร์แล้วนับ % ที่ตกบนพื้นที่เดินได้ (ค่าที่ถูกได้ 99%+) เพิ่มแมพใหม่ต้องรันตัวนี้ | DB หรือ `data/all_kills.csv` |
| `player_role.py` | unsupervised — แยก KMeans ฝั่ง T/CT คนละโมเดล ตีความ 5 บทบาทเป้าหมาย และเก็บกลุ่ม `Hybrid / Unresolved` แทนการฝืนตั้งชื่อเมื่อหลักฐานไม่พอ | `data/all_kills.csv` (ค่าเริ่มต้น) หรือ DB เฉพาะ `matches.source='reference'` → `output/player_role.json`, `output/player_role_profiles.csv` |

`all_kills.csv` เรียงคอลัมน์เป็น 7 หมวด: Match & Round → Role Signals → Attacker → Victim → Assister / Support → Combat → Technical ส่วนไฟล์ `output/all_kills_readable.xlsx` เป็นเวอร์ชันสำหรับเปิดอ่าน มี filter, freeze pane, สีหัวตารางแยกหมวด และ Data Dictionary ภาษาไทย โดย CSV ยังเป็นแหล่งข้อมูลหลักของสคริปต์และโมเดล

## เทรนโมเดลบทบาทผู้เล่น

```bash
python research/player_role.py --source csv --csv data/all_kills.csv --map de_ancient --output-dir output/models/de_ancient
```

หนึ่งแถวที่ใช้จัดกลุ่มคือผู้เล่นหนึ่งคนในหนึ่งแมตช์ต่อหนึ่งฝั่ง โมเดลฝั่ง T และ CT แยกจากกันโดยสมบูรณ์ และข้อมูลที่ผู้ใช้อัปโหลดจะไม่ถูกนำมาเทรน ชื่ออย่าง `Entry`, `Support`, `Site Anchor` เป็นคำอธิบาย centroid หลังจัดกลุ่ม ไม่ใช่ label ที่ใช้สอนโมเดลหรือคำตัดสินผู้เล่น เมื่อเทรนจาก CSV จะไม่มี grenade throws, movement หรือ planter id: Support จึงใช้ assist/flash-assist, Anchor/Rotator ใช้ callout ของ kill events และ Bomb carrier / Site executor ใช้ site/post-plant events เป็น proxy หากฐานข้อมูล reference พร้อมแล้วจึงค่อยใช้ `--source database` เพื่อใช้ฟีเจอร์ชุดเต็ม

## เพิ่มเดโมแล้วอยากให้บริบทบนหน้ารอบอัปเดต

```bash
python research/demoparser.py      # 1. เดโมในโฟลเดอร์รายแมพ -> data/all_kills.csv
python research/grid_ml1.py --map de_ancient --min-kills 3  # 2. -> output/models/de_ancient/grid_ml1.json
python research/player_role.py --source csv --map de_ancient --output-dir output/models/de_ancient
```

รันสองคำสั่งเทรนท้ายสุดซ้ำตามชื่อแมพที่มีใน CSV; `--min-kills 3` เหมาะกับชุดที่มีเพียง 5 แมตช์ต่อแมพ (ค่าเริ่มต้นคือ 10) อย่าใช้แคชของแมพที่ไม่มีไฟล์ demo ต้นทางมาปะปนใน CSV

API เลือก artifact ตาม `match.map_name` จาก `output/models/<map>/` โดยอัตโนมัติ และยังรองรับไฟล์ legacy ใน `output/` เป็น fallback
ตัวเลือกแมพหน้า Analysis อ่านจาก PostgreSQL: หลังเทรนให้รัน `python -m backend.parser <ไฟล์.dem>` และ `python -m backend.etl_loader output/json/<ชื่อไฟล์>.json` สำหรับเดโมอ้างอิงแต่ละไฟล์ แล้วรัน `python -m backend.etl_loader --mark-reference` เพื่อให้ endpoint ของหน้า Analysis เห็นแมพนั้น (คำสั่งนี้ค้นโฟลเดอร์รายแมพและไม่เปลี่ยน source ของชุดอ้างอิงที่ archive ไปแล้ว)
หากเปลี่ยนชุดอ้างอิงหลักของเทสต์ ให้ก๊อป `grid_ml1.json` กับ `grid_ml1_cells.csv` ของแมพนั้นไปทับใน `backend/tests/fixtures/`
สูตรพิกัดอยู่ที่ `backend/review.py` ที่เดียว — `grid_ml1.py` import ไปใช้ ช่องบนหน้าเว็บจึงตรงกับช่องของโมเดลเสมอ
