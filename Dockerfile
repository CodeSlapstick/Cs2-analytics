FROM python:3.12-slim

WORKDIR /app

# คัดลอกรายการ library และสั่งติดตั้ง
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# คัดลอกไฟล์ทั้งหมดในโปรเจกต์เข้าไปใน container
COPY . .

# กำหนดคำสั่งเริ่มต้นให้รัน demo_parser.py
CMD ["python", "demo_parser.py"]
