const $ = (id) => document.getElementById(id);

const msg = $("msg");   // กล่องข้อความแจ้งเตือนใต้ปุ่ม

/** แสดงข้อความให้ผู้ใช้เห็น
 *  text = ข้อความ, kind = "error" (แดง) หรือ "ok" (เขียว) */
function say(text, kind = "error") {
  msg.textContent = text;         // textContent = ใส่ข้อความล้วน 
  msg.className = "msg " + kind;  // className = เปลี่ยนคลาส CSS ของกล่องนี้ -> สีเปลี่ยนตาม
}

async function boot() {
  // fetch = ส่งคำขอไปหาเซิร์ฟเวอร์, await = รอจนกว่าคำตอบจะมาถึงค่อยทำบรรทัดถัดไป
  const me = await fetch("/api/me");
  if (me.ok) {                      // .ok = true เมื่อเซิร์ฟเวอร์ตอบสำเร็จ (สถานะ 200-299)
    location.href = "/upload";    // location.href = "พาเบราว์เซอร์ไปหน้านี้" (เหมือนพิมพ์ URL เอง)
    return;
  }

  const cfg = await (await fetch("/api/config")).json();  // ขอค่าตั้งค่า แล้วแปลงคำตอบเป็น object ด้วย .json()
  if (!cfg.allow_dev_login) {                             // ! = "ไม่" -> ถ้าไม่อนุญาตโหมดทดสอบ
    $("devBox").classList.add("hidden");                  // classList.add("hidden") = ใส่คลาสซ่อน -> CSS สั่ง display:none
    $("devDivider").classList.add("hidden");
  }

  const err = new URLSearchParams(location.search).get("error");  
  if (err) say("ล็อกอิน Steam ไม่สำเร็จ (" + err + ")");
}

// ปุ่ม "เข้าสู่ระบบด้วย Steam"
$("btnSteam").addEventListener("click", () => {
  say("กำลังพาไปหน้า Steam…", "ok");
  location.href = "/auth/steam/login";   // เด้งไป endpoint ของ backend ที่จะพาต่อไปหา Steam
});

$("btnDev").addEventListener("click", async () => {
  const steamid = $("steamid").value.trim();   // .value = สิ่งที่ผู้ใช้พิมพ์ในช่อง, .trim() = ตัดช่องว่างหัวท้าย
  if (!steamid) return say("กรุณาใส่ SteamID64");   

  const res = await fetch("/auth/dev-login", {     // ส่งข้อมูลไปให้ backend
    method: "POST",                                // POST = "ส่งของไปให้" (GET = "ขอของมา")
    headers: { "Content-Type": "application/json" },  // บอกเซิร์ฟเวอร์ว่าของที่ส่งไปเป็นรูปแบบ JSON
    body: JSON.stringify({ steamid }),             // JSON.stringify = แปลง object เป็นข้อความก่อนส่ง
  });

  const data = await res.json();                   // แปลงคำตอบกลับเป็น object
  if (!res.ok) return say(data.error || "เข้าสู่ระบบไม่สำเร็จ");  // || = "ถ้าตัวซ้ายไม่มีค่า ให้ใช้ตัวขวา"

  say("สำเร็จ! กำลังเข้าหน้าหลัก…", "ok");
  location.href = "/upload";
});

boot();   