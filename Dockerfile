# CS2 Map Zone Analytics
#
#   docker build -t cs2-analytics .
#   docker run --rm -v "${PWD}/output:/app/output" cs2-analytics
#
# คำสั่งข้างบนรัน pipeline/grid_ml.py ได้ทันทีโดยไม่ต้องมีไฟล์ .dem
# เพราะชุดคิลที่ parse แล้ว (data/all_kills.csv) ติดมากับรีโปอยู่แล้ว

FROM python:3.12-slim

# libgomp1 — scikit-learn ต้องใช้ตอนรัน แต่ไม่มีมากับ image แบบ slim
RUN apt-get update \
 && apt-get install -y --no-install-recommends libgomp1 \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ลง library ก่อนคัดลอกโค้ด เพื่อให้ Docker cache เลเยอร์นี้ไว้
# แก้โค้ดแล้ว build ใหม่จึงไม่ต้องรอ pip ลงใหม่ทั้งหมด
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Agg = วาดภาพลงไฟล์โดยไม่ต้องมีจอ (ใน container ไม่มีอยู่แล้ว)
# MPLCONFIGDIR ชี้ไป /tmp กัน matplotlib เตือนว่าเขียน cache ลง HOME ไม่ได้
ENV MPLBACKEND=Agg \
    MPLCONFIGDIR=/tmp/matplotlib \
    PYTHONUNBUFFERED=1

# ผลลัพธ์ลงที่นี่ — mount ออกมาด้วย -v ไม่งั้นไฟล์หายไปพร้อม container
VOLUME ["/app/output"]

CMD ["python", "pipeline/grid_ml.py"]
