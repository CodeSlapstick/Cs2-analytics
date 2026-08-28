# 1. ใช้ระบบปฏิบัติการจำลองที่มี Python 3.12 ติดตั้งมาให้แล้ว
FROM python:3.12-slim

# 2. กำหนดโฟลเดอร์ทำงานหลักข้างในตู้คอนเทนเนอร์
WORKDIR /app

# 3. คัดลอกไฟล์รายชื่อ Library เข้าตู้แล้วสั่งติดตั้ง
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 4. คัดลอกโค้ดและไฟล์เดโมเข้าไปในตู้
COPY demo_parser.py .
COPY faze-vs-spirit-m1-dust2.dem .

# 5. สั่งให้รันโค้ดประมวลผลทันทีที่เปิดเครื่องตู้คอนเทนเนอร์
CMD ["python", "demo_parser.py"]