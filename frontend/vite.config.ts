import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// ตอน dev (npm run dev) Vite เสิร์ฟหน้าเว็บที่ :5173 แล้วส่งต่อ /api /auth /assets ไปให้ API
// เบราว์เซอร์จึงเห็นเป็น origin เดียว คุกกี้ล็อกอิน (SameSite=Lax) ทำงานได้โดยไม่ต้องตั้ง CORS
//   ค่าเริ่มต้น: API ที่รันในเครื่องด้วย python -m uvicorn backend.app:app (พอร์ตปกติของ uvicorn)
//   ใช้ backend ใน Docker แทน: VITE_API_TARGET=http://127.0.0.1:3000 npm run dev  (ผ่าน nginx ของ compose)
// ตอนรันจริงใน Docker หน้าที่นี้เป็นของ nginx (ดู nginx.conf)
const API = process.env.VITE_API_TARGET ?? "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
  build: {
    // ค่าปกติของ Vite คือ "assets" ซึ่งชนกับ /assets/ ของ backend (ภาพเรดาร์) ที่ nginx ส่งต่อไปให้ api
    // ถ้าใช้ชื่อเดิม ไฟล์ JS/CSS ของหน้าเว็บจะถูกส่งไปถาม api แล้วได้ 404 -> หน้าขาวทั้งหน้า
    assetsDir: "_app",
  },
  server: {
    port: 5173,
    proxy: {
      "/api": API,
      "/auth": API,
      "/assets": API,
    },
  },
});
