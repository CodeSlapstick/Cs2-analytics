# สร้าง realparser/all_kills_25demos.csv ขึ้นใหม่จากไฟล์ .dem ทั้งหมดใน demos/
# รันจากรากโปรเจกต์:  python realparser/build_kills_csv.py
# ใช้เวลานาน ไฟล์ละ 1-2 นาที — ปกติไม่ต้องรัน เพราะ csv อยู่ใน git แล้ว

import glob
import pandas as pd
from awpy import Demo

# 1. ลิสต์เก็บตารางของทุกเดโม
all_kills = []

# 2. วนลูปอ่านทุกไฟล์ .dem ในโฟลเดอร์ demos
for file in glob.glob("demos/*.dem"):
    print(f"กำลังอ่านไฟล์: {file}")
    
    dem = Demo(file)
    dem.parse()
    
    # แปลง kills เป็น pandas แล้วเก็บเข้าลิสต์
    df = dem.kills.to_pandas()
    all_kills.append(df)

# 3. รวมทุกแมตช์เป็นตารางเดียว แล้วเซฟไฟล์
final_df = pd.concat(all_kills, ignore_index=True)
final_df.to_csv("realparser/all_kills_25demos.csv", index=False)

print("\n=== รวมเสร็จแล้ว 25 แมตช์ ===")
print(final_df.head())