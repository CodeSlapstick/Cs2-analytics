// ==========================================================================
// main.js — "สมอง" ของหน้าหลัก
// หน้าที่: เช็กว่าล็อกอินอยู่จริงไหม -> เอาชื่อมาโชว์ -> ดึงสถิติมาวาดกราฟแท่ง
// ==========================================================================

const $ = (id) => document.getElementById(id);   // ฟังก์ชันย่อ "หยิบชิ้นส่วนตาม id"

/** แปลงตัวเลขให้มีลูกน้ำคั่นหลักพัน เช่น 25341 -> "25,341" อ่านง่ายขึ้นเยอะ */
const fmt = (n) => n.toLocaleString("th-TH");    // toLocaleString = จัดรูปแบบตัวเลขตามภาษาไทย

/**
 * วาด "กราฟแท่งแนวนอน" ลงในกล่องที่กำหนด
 * boxId = id ของกล่องปลายทาง
 * rows  = ข้อมูล เช่น [{name:"ak47", count:900}, ...]
 */
function drawBars(boxId, rows) {
  const box = $(boxId);
  box.innerHTML = "";                                    // ล้างของเก่าทิ้งก่อน จะได้ไม่วาดซ้อนกัน
  if (!rows || rows.length === 0) {                      // ไม่มีข้อมูล -> บอกผู้ใช้แล้วจบ
    box.innerHTML = '<div class="sub">ไม่มีข้อมูล</div>';
    return;
  }

  const max = Math.max(...rows.map((r) => r.count));     // หาค่ามากสุด (... = "แผ่" array ออกเป็นตัว ๆ ให้ Math.max)
                                                         // ค่ามากสุดจะกลายเป็นแท่งเต็ม 100% ที่เหลือเทียบกับมัน

  rows.forEach((r) => {                                  // forEach = วนทำทีละแถว
    const pct = (r.count / max) * 100;                   // สัดส่วนของแถวนี้ เทียบกับแท่งที่ยาวที่สุด

    const row = document.createElement("div");           // createElement = สร้างกล่อง <div> ใหม่ในหน่วยความจำ
    row.className = "bar-row";                           // ใส่คลาสให้ CSS จับไปแต่ง

    row.innerHTML = `
      <div class="bar-top"><span>${r.name}</span><span class="n">${fmt(r.count)}</span></div>
      <div class="bar-bg"><div class="bar-fill" style="width:${pct.toFixed(1)}%"></div></div>
    `;
    // เครื่องหมาย ` ` (backtick) = ข้อความหลายบรรทัดที่แทรกค่าตัวแปรได้ด้วย ${...}
    // toFixed(1) = ปัดเหลือทศนิยม 1 ตำแหน่ง เช่น 63.4%

    box.appendChild(row);                                // appendChild = เอากล่องที่สร้างไว้ ไปแปะจริงบนหน้าเว็บ
  });
}

// --------------------------------------------------------------------------
// ขั้นตอนหลักตอนเปิดหน้า
// --------------------------------------------------------------------------
async function boot() {
  // --- 1) เช็กว่าล็อกอินอยู่ไหม ---
  const meRes = await fetch("/api/me");
  if (!meRes.ok) {                    // ไม่ผ่าน = คุกกี้หมดอายุ / ยังไม่เคยล็อกอิน
    location.href = "/";              // ไล่กลับไปหน้าล็อกอิน
    return;
  }
  const { user } = await meRes.json();  // { user } = ดึงเฉพาะช่องชื่อ user ออกมาจาก object (เรียกว่า destructuring)

  // --- 2) เอาข้อมูลผู้ใช้ไปโชว์บนหน้า ---
  $("userName").textContent = user.name;                    // ชื่อบนแถบบนขวา
  $("helloName").textContent = user.name;                   // ชื่อในประโยคทักทาย
  $("userId").textContent = user.steamid;                   // เลข SteamID64
  if (user.avatar) $("avatar").src = user.avatar;           // .src = ที่อยู่รูป (ใส่ก็ต่อเมื่อมีรูปจริง)
  if (user.mode === "dev") $("modeBadge").classList.remove("hidden");  // โหมดทดสอบ -> เอาคลาสซ่อนออก ป้ายจะโผล่

  // --- 3) ดึงสถิติมาวาด ---
  const statRes = await fetch("/api/stats");
  if (!statRes.ok) return;                 // ดึงไม่ได้ (เช่นไม่มีไฟล์ CSV) ก็ปล่อยให้การ์ดเป็นขีด — ไว้
  const s = await statRes.json();

  $("sTotal").textContent = fmt(s.total_kills);       // จำนวนการฆ่าทั้งหมด
  $("sHs").textContent = fmt(s.headshots);            // จำนวนคิลที่ยิงหัว
  $("sHsRate").textContent = s.headshot_rate + "%";   // + "%" = ต่อเครื่องหมายเปอร์เซ็นต์ท้ายตัวเลข
  $("sRound").textContent = s.avg_round;

  drawBars("weapons", s.top_weapons);                 // กราฟอาวุธยอดฮิต
  drawBars("places", s.top_places);                   // กราฟจุดที่คนตายบ่อย
  drawBars("sides", [                                 // กราฟเทียบสองฝั่ง (สร้าง array เองตรงนี้เลย)
    { name: "CT ฆ่า", count: s.ct_kills },
    { name: "T ฆ่า", count: s.t_kills },
  ]);
}

// --------------------------------------------------------------------------
// ปุ่มออกจากระบบ
// --------------------------------------------------------------------------
$("btnLogout").addEventListener("click", async () => {
  await fetch("/auth/logout", { method: "POST" });   // บอก backend ให้ลบคุกกี้
  location.href = "/";                               // แล้วกลับไปหน้าล็อกอิน
});

boot();   // เริ่มทำงาน
