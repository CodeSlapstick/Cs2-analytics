// ==========================================================================
// common.js — "กล่องเครื่องมือกลาง" ที่ทุกหน้าใช้ร่วมกัน
//
// ทุกหน้า (overview, matches, players, map, tactical, ml) โหลดไฟล์นี้ก่อน
// แล้วค่อยโหลดไฟล์ของหน้าตัวเอง เช่น
//     <script src="/static/common.js"></script>     <- ไฟล์นี้ (มาก่อน)
//     <script src="/static/players.js"></script>    <- ไฟล์ของหน้านั้น
//
// ของที่อยู่ในนี้ = ของที่ใช้ซ้ำหลายหน้า ถ้าเขียนไว้ทุกหน้าจะแก้ไม่ไหว
//   1) เครื่องมือเล็ก ๆ ($ fmt esc api pct)
//   2) ตัวช่วยวาด (drawBars drawKpis tableHTML barsWithRate)
//   3) แถบเมนูด้านบน (เขียนที่เดียว ทุกหน้าได้เหมือนกันหมด)
//   4) start() — ตัวเริ่มงานของทุกหน้า
// ==========================================================================


// --------------------------------------------------------------------------
// ส่วนที่ 1 — เครื่องมือเล็ก ๆ
// --------------------------------------------------------------------------

const $ = (id) => document.getElementById(id);
// $ = ฟังก์ชันย่อ แปลว่า "ไปหยิบชิ้นส่วนที่มี id นี้มาให้ที"
// document = ทั้งหน้าเว็บ, getElementById = ค้นหาด้วย id

const fmt = (n) => Number(n || 0).toLocaleString("th-TH");
// แปลงตัวเลขให้มีลูกน้ำคั่นหลักพัน: 7270 -> "7,270"
// (n || 0) = ถ้า n เป็นค่าว่าง/undefined ให้ใช้ 0 แทน กันพัง

const esc = (s) => String(s ?? "").replace(/[<>&"]/g, (c) =>
  ({ "<": "&lt;", ">": "&gt;", "&": "&amp;", '"': "&quot;" }[c]));
// esc = "ทำให้ข้อความปลอดภัย" ก่อนเอาไปแปะลงหน้าเว็บ
// ชื่อผู้เล่นมาจากไฟล์เดโม ถ้ามีใครตั้งชื่อเป็น <script> แล้วเราแปะดิบ ๆ
// เบราว์เซอร์จะรันสคริปต์นั้นจริง ๆ (ช่องโหว่ชื่อ XSS)
// บรรทัดนี้เลยแปลง < > & " ให้กลายเป็นตัวหนังสือธรรมดาก่อน
// ?? = "ถ้าเป็น null หรือ undefined ให้ใช้ตัวขวา"

const pct = (a, b) => (b ? Math.round(a / b * 100) + "%" : "—");
// คิดเป็นเปอร์เซ็นต์แล้วทำเป็นข้อความ เช่น "54%"
// (b ? ... : "—") = ถ้าตัวหารเป็น 0 ให้แสดงขีดแทน กันหารด้วยศูนย์

/** ขอข้อมูลจาก backend แล้วแปลงเป็น object ให้เลย */
async function api(path) {
  const res = await fetch(path);          // fetch = ส่งคำขอไปหาเซิร์ฟเวอร์, await = รอคำตอบก่อนทำบรรทัดถัดไป
  if (res.status === 401) {               // 401 = "ยังไม่ได้ล็อกอิน"
    location.href = "/";                  // ไล่กลับไปหน้าล็อกอิน
    throw new Error("ยังไม่ได้ล็อกอิน");   // throw = โยน error ออกไป เพื่อหยุดโค้ดที่เรียกฟังก์ชันนี้
  }
  if (!res.ok) throw new Error(`${path} ตอบกลับ ${res.status}`);   // .ok = true เมื่อสถานะ 200-299
  return res.json();                      // แปลงข้อความ JSON ที่ได้ ให้กลายเป็น object ของ JavaScript
}


// --------------------------------------------------------------------------
// ส่วนที่ 2 — ตัวช่วยวาด
// --------------------------------------------------------------------------

/**
 * วาดกราฟแท่งแนวนอนลงในกล่อง
 * boxId = id ของกล่องปลายทาง
 * rows  = ข้อมูล เช่น [{name:"ak47", count:2580}, ...]
 */
function drawBars(boxId, rows) {
  const box = $(boxId);
  if (!rows || rows.length === 0) {                     // ไม่มีข้อมูล -> บอกผู้ใช้แล้วจบ
    box.innerHTML = '<div class="empty">ไม่มีข้อมูล</div>';
    return;
  }
  const max = Math.max(...rows.map((r) => r.count));    // หาค่ามากสุด (... = "แผ่" array ออกเป็นตัว ๆ ให้ Math.max)
                                                        // ตัวมากสุดจะเป็นแท่งเต็ม 100% ที่เหลือเทียบกับมัน
  box.innerHTML = rows.map((r) => `
    <div class="bar-row">
      <div class="bar-top"><span>${esc(r.name)}</span><span class="n">${fmt(r.count)}</span></div>
      <div class="bar-bg"><div class="bar-fill" style="width:${(r.count / max * 100).toFixed(1)}%"></div></div>
    </div>`).join("");
  // .map(...) = แปลงข้อมูลทุกแถวให้เป็นข้อความ HTML -> ได้ array ของข้อความ
  // .join("")  = เอาข้อความทุกชิ้นมาต่อกันเป็นก้อนเดียว
  // ` ` (backtick) = ข้อความหลายบรรทัดที่แทรกค่าตัวแปรได้ด้วย ${...}
}

/** สร้างการ์ดตัวเลขสรุป (KPI) — items = [{k:"ป้าย", v:"ตัวเลข", s:"คำอธิบาย"}, ...] */
function drawKpis(boxId, items) {
  $(boxId).innerHTML = items.map((it) => `
    <div class="kpi">
      <div class="k">${esc(it.k)}</div>
      <div class="v">${it.v}</div>
      <div class="s">${esc(it.s || "")}</div>
    </div>`).join("");
  // it.v ไม่ผ่าน esc เพราะบางอันเราตั้งใจใส่แท็ก <small> เข้าไปเอง (ข้อความของเราเอง ไม่ใช่ของผู้ใช้)
}

/**
 * สร้างข้อความ HTML ของตาราง
 * head = ["คอลัมน์1", "คอลัมน์2", ...]
 * body = [[ช่อง, ช่อง, ...], ...]   ช่องที่เป็น {n: ค่า} จะถูกจัดชิดขวา
 * opt  = { rowAttr: ฟังก์ชันที่คืนข้อความไปแปะบนแท็ก <tr> } — ใช้ทำแถวที่กดได้
 */
function tableHTML(head, body, opt = {}) {
  if (!body.length) return '<div class="empty">ไม่มีข้อมูล</div>';   // ตารางว่าง -> บอกไปตรง ๆ ดีกว่าโชว์ตารางเปล่า

  const th = head.map((h, i) =>
    `<th class="${typeof body[0]?.[i] === "object" ? "num" : ""}">${esc(h)}</th>`).join("");
  // ดูจากแถวแรกว่าคอลัมน์ไหนเป็นตัวเลข แล้วใส่คลาส num ให้หัวคอลัมน์นั้นชิดขวาตาม
  // body[0]?.[i] — เครื่องหมาย ?. = "ถ้าไม่มีก็อย่าพัง คืน undefined ไปเลย"

  const tr = body.map((row, ri) => `
    <tr ${opt.rowAttr ? opt.rowAttr(ri) : ""}>
      ${row.map((c) => typeof c === "object"
          ? `<td class="num">${c.n}</td>`     // ช่องตัวเลข -> ชิดขวา
          : `<td>${c}</td>`).join("")}
    </tr>`).join("");

  return `<table><thead><tr>${th}</tr></thead><tbody>${tr}</tbody></table>`;
  // thead = ส่วนหัวตาราง, tbody = ส่วนเนื้อตาราง
}

/**
 * กราฟแท่ง + อัตราชนะต่อท้าย (ใช้ในหน้าแท็คติก)
 * list = ข้อมูล, kName/kCount/kWin = ชื่อช่องในข้อมูลที่จะเอามาใช้, unit = หน่วยที่พิมพ์ต่อท้าย
 */
function barsWithRate(list, kName, kCount, kWin, unit) {
  if (!list.length) return '<div class="empty">ไม่มีข้อมูล</div>';
  const max = Math.max(...list.map((r) => r[kCount]));
  return list.map((r) => `
    <div class="bar-row">
      <div class="bar-top">
        <span>${esc(r[kName])}</span>
        <span class="n">${fmt(r[kCount])} ${unit} (ชนะ ${pct(r[kWin], r[kCount])})</span>
      </div>
      <div class="bar-bg"><div class="bar-fill" style="width:${(r[kCount] / max * 100).toFixed(1)}%"></div></div>
    </div>`).join("");
  // r[kName] = หยิบค่าจากช่องที่ชื่อตรงกับตัวแปร kName
  // (เขียนแบบนี้ ฟังก์ชันเดียวใช้ได้กับข้อมูลหลายแบบ ไม่ต้องเขียนซ้ำ)
}

/** ทำป้ายสีบอกสัดส่วน เช่น 73 จาก 167 -> ป้าย "44%" (ส้มถ้าเกินครึ่ง น้ำเงินถ้าต่ำกว่า) */
function badge(part, whole) {
  const p = whole ? Math.round(part / whole * 100) : 0;
  return `<span class="tag ${p >= 50 ? "t" : "ct"}">${p}%</span>`;
}


// --------------------------------------------------------------------------
// ส่วนที่ 3 — แถบเมนูด้านบน
//
// เขียนไว้ที่เดียว ทุกหน้าได้เหมือนกันหมด
// ในไฟล์ HTML ของแต่ละหน้ามีแค่บรรทัดเดียว: <header class="topbar" id="topbar"></header>
// แล้วฟังก์ชันข้างล่างนี้เติมเนื้อในให้
// --------------------------------------------------------------------------

const MENU = [                        // รายชื่อเมนู — เพิ่มหน้าใหม่ก็มาเพิ่มบรรทัดตรงนี้ที่เดียว
  { url: "/overview", name: "ภาพรวม" },
  { url: "/matches",  name: "แมตช์" },
  { url: "/players",  name: "นักแข่ง" },
  { url: "/map",      name: "แผนที่" },
  { url: "/tactical", name: "แท็คติก" },
  { url: "/ml",       name: "โมเดล ML" },
];

/** วาดแถบเมนู แล้วขีดเส้นส้มใต้เมนูของหน้าที่กำลังเปิดอยู่ */
function drawTopbar(user) {
  const here = location.pathname;     // location.pathname = ส่วนที่อยู่หลังชื่อเว็บ เช่น "/players"

  $("topbar").innerHTML = `
    <div class="brand"><span class="dot"></span><span>CS2 ANALYTICS</span></div>
    <nav class="nav">
      ${MENU.map((m) => `<a href="${m.url}" class="${m.url === here ? "active" : ""}">${m.name}</a>`).join("")}
    </nav>
    <div class="user-box">
      <img class="avatar" src="${esc(user.avatar || "")}" alt="รูปโปรไฟล์" />
      <span>${esc(user.name)}</span>
      <button class="btn-mini" id="btnLogout">ออกจากระบบ</button>
    </div>`;
  // m.url === here ? "active" : "" = ถ้าเมนูนี้คือหน้าที่เปิดอยู่ ให้ใส่คลาส active (CSS ขีดเส้นส้มใต้ให้)

  $("btnLogout").addEventListener("click", async () => {   // "ถ้าปุ่มนี้ถูกคลิก ให้ทำสิ่งนี้"
    await fetch("/auth/logout", { method: "POST" });       // POST = "ส่งคำสั่งไปให้" (GET = "ขอของมา")
    location.href = "/";                                   // กลับไปหน้าล็อกอิน
  });
}


// --------------------------------------------------------------------------
// ส่วนที่ 4 — ตัวช่วยอื่นที่ใช้หลายหน้า
// --------------------------------------------------------------------------

/**
 * เติมรายชื่อแมพลงในช่องเลือก
 * selectId = id ของช่องเลือก
 * withAll  = true ถ้าอยากมีตัวเลือก "ทุกแมพ" อยู่บนสุด
 *
 * รายชื่อแมพไม่ได้พิมพ์ทิ้งไว้ แต่อ่านจากแมตช์ที่มีจริงในฐานข้อมูล
 * โหลด demo แมพใหม่เข้ามาเมื่อไร ช่องเลือกก็ขึ้นเองอัตโนมัติ
 */
async function fillMapSelect(selectId, withAll = false) {
  const ms = await api("/api/matches");
  const maps = [...new Set(ms.map((m) => m.map_name))].sort();
  // new Set(...) = กล่องที่เก็บของซ้ำไม่ได้ -> ใช้กรองชื่อแมพที่ซ้ำกันออก
  // [...ของ] = แผ่กลับมาเป็น array ธรรมดา, .sort() = เรียงตามตัวอักษร

  $(selectId).innerHTML =
    (withAll ? '<option value="">ทุกแมพ</option>' : "") +
    maps.map((m) => `<option value="${esc(m)}">${esc(m)}</option>`).join("");
  return maps;
}

/**
 * ผูกปุ่มสลับกลุ่ม (เช่น ทั้งหมด / CT / T) เข้ากับการทำงาน
 * segId    = id ของกล่อง .seg
 * onChange = ฟังก์ชันที่จะถูกเรียกพร้อมค่าที่เลือก
 */
function bindSeg(segId, onChange) {
  $(segId).addEventListener("click", (e) => {         // e = ข้อมูลของเหตุการณ์ (คลิกโดนอะไร)
    const btn = e.target.closest("button");           // closest("button") = ไล่หาปุ่มที่ใกล้ที่สุดจากจุดที่คลิก
    if (!btn) return;                                 // คลิกโดนที่ว่าง -> ไม่ต้องทำอะไร
    $(segId).querySelectorAll("button").forEach((b) => b.classList.remove("on"));  // ถอดไฮไลต์ปุ่มเดิม
    btn.classList.add("on");                          // ไฮไลต์ปุ่มที่เพิ่งกด
    onChange(btn.dataset.side);                       // btn.dataset.side = ค่าใน data-side="..." ของปุ่มนั้น
  });
}

/**
 * ผูกตารางให้กดแถวได้
 * boxId  = id ของกล่องที่มีตารางอยู่
 * onPick = ฟังก์ชันที่จะถูกเรียกพร้อมเลขแถวที่กด
 */
function bindRows(boxId, onPick) {
  $(boxId).querySelectorAll("tr.click").forEach((tr) => {
    tr.addEventListener("click", () => {
      $(boxId).querySelectorAll("tr").forEach((x) => x.classList.remove("sel"));  // ล้างไฮไลต์แถวเดิม
      tr.classList.add("sel");                        // ไฮไลต์แถวที่เพิ่งกด
      onPick(Number(tr.dataset.i));                   // tr.dataset.i = เลขแถวที่เราแปะไว้ตอนสร้างตาราง
    });                                               // Number(...) = แปลงข้อความเป็นตัวเลข
  });
}


// --------------------------------------------------------------------------
// ส่วนที่ 5 — ตัวเริ่มงานของทุกหน้า
//
// ไฟล์ของแต่ละหน้าจบด้วยบรรทัดเดียว:  start(load);
// แปลว่า "เช็กล็อกอิน วาดเมนู แล้วค่อยเรียกฟังก์ชัน load ของหน้านี้"
// --------------------------------------------------------------------------

function start(pageLoad) {
  (async () => {                                      // (async () => {...})() = สร้างฟังก์ชันแล้วเรียกใช้ทันที
    const me = await fetch("/api/me");                //   (ต้องห่อแบบนี้เพราะจะใช้ await ได้ ต้องอยู่ในฟังก์ชัน async)
    if (!me.ok) { location.href = "/"; return; }      // ยังไม่ล็อกอิน -> ไล่กลับหน้าล็อกอิน
    const { user } = await me.json();                 // { user } = ดึงเฉพาะช่อง user ออกมา (เรียกว่า destructuring)

    drawTopbar(user);                                 // วาดแถบเมนู
    await pageLoad();                                 // แล้วค่อยให้หน้านี้โหลดข้อมูลของตัวเอง
  })().catch((e) => {                                 // .catch = "ถ้าเกิด error ระหว่างทาง ให้ทำสิ่งนี้"
    document.querySelector(".wrap").innerHTML =
      `<div class="err">โหลดข้อมูลไม่สำเร็จ: ${esc(e.message)}<br>
       ตรวจว่าฐานข้อมูลเปิดอยู่ไหม — <code>docker compose up -d db</code></div>`;
  });
}
