# research/ — สคริปต์ ML ที่หน้าเว็บใช้ผล

รันจากรากโปรเจกต์เสมอ · อ่านจาก `demos/` `data/` แล้วเขียนผลลง `data/` หรือ `output/`

| ไฟล์ | ทำอะไร | อ่าน → เขียน |
|---|---|---|
| `demoparser.py` | อ่านเดโมทุกไฟล์ รวมการฆ่าเป็นตารางเดียว (แคชรายไฟล์ พังกลางทางไม่ต้องเริ่มใหม่) | `demos/*.dem` → `data/all_kills.csv` |
| `grid_ml1.py` | unsupervised — MeanShift หาจุดปะทะ + KMeans จัดประเภทช่องกริด · หน้ารอบใช้ผลนี้ (บริบทการตาย + ชั้นซ้อนบนแผนที่) | `data/all_kills.csv` → `output/grid_ml1.json` (+ csv, png) |
| `check_radar.py` | ตรวจค่าปรับเทียบใน `assets/radars.json` — ฉายจุดตายจริงลงภาพเรดาร์แล้วนับ % ที่ตกบนพื้นที่เดินได้ (ค่าที่ถูกได้ 99%+) เพิ่มแมพใหม่ต้องรันตัวนี้ | DB หรือ `data/all_kills.csv` |

## เพิ่มเดโมแล้วอยากให้บริบทบนหน้ารอบอัปเดต

```bash
python research/demoparser.py      # 1. เดโม -> data/all_kills.csv
python research/grid_ml1.py        # 2. -> output/grid_ml1.json (api อ่านไฟล์นี้ ไม่ต้องรีสตาร์ต)
```

แล้วก๊อป `output/grid_ml1.json` กับ `output/grid_ml1_cells.csv` ไปทับใน `backend/tests/fixtures/` ด้วย ไม่งั้นเทสต์เทียบช่องจะแดง
สูตรพิกัดอยู่ที่ `backend/review.py` ที่เดียว — `grid_ml1.py` import ไปใช้ ช่องบนหน้าเว็บจึงตรงกับช่องของโมเดลเสมอ
