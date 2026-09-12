# CS2 Scouting Platform — image ของฝั่ง Python (ใช้ทั้ง api และ worker ใน docker-compose.yml)
#
#   docker build -t cs2-analytics .
#   docker run --rm -v "${PWD}/output:/app/output" cs2-analytics python research/grid_ml1.py   # รันสคริปต์วิจัย
#
# ปกติไม่ต้อง build เอง — docker compose up -d ทำให้หมด

# 3.11 ตามข้อกำหนดของ Sprint 2 (awpy 2.0.2 / demoparser2 0.41.4 มี wheel สำเร็จรูปสำหรับรุ่นนี้)
FROM python:3.11-slim

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

VOLUME ["/app/output", "/app/demos"]

# พอร์ตของ API ภายใน container — compose ไม่เปิดออกมานอกเครื่อง หน้าเว็บ (nginx) ต่อเข้ามาทางเครือข่ายของ compose
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "backend.app:app", "--host", "0.0.0.0", "--port", "8000"]
