import 'dotenv/config';

function required(name, fallback) {
  const v = process.env[name] ?? fallback;
  if (v === undefined || v === '') {
    throw new Error(`ไม่พบค่า env: ${name} — ดูวิธีตั้งค่าใน .env.example`);
  }
  return v;
}

export const config = {
  port: Number(process.env.PORT || 4000),
  isProd: process.env.NODE_ENV === 'production',
  frontendUrl: process.env.FRONTEND_URL || 'http://localhost:5173',
  backendUrl: process.env.BACKEND_URL || 'http://localhost:4000',
  jwtSecret: required('JWT_SECRET', 'dev-only-insecure-secret-change-me'),
  steamApiKey: process.env.STEAM_API_KEY || '',
  cookieName: 'cs2a_token',
  // ว่าง = ใช้ PGlite (Postgres ฝังในโปรเซส) ที่ backend/data/pgdata — ดู src/db.js
  databaseUrl: process.env.DATABASE_URL || '',
  // ที่เก็บไฟล์ของ PGlite — เทสต์ตั้งเป็น 'memory://' เพื่อไม่ให้ไปยุ่งกับข้อมูลที่ dev ใช้อยู่
  pgliteDir: process.env.PGLITE_DIR || 'data/pgdata',
};
