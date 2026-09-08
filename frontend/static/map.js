let side = "";        // ฝั่งที่กรองอยู่: "" = ทั้งหมด, "ct", "t"
let radar = null;     // ค่าปรับเทียบของแมพที่เลือกอยู่ (null = แมพนี้ยังไม่มีค่าปรับเทียบ)
let radarImg = null;  // ตัวภาพเรดาร์ที่โหลดเสร็จแล้ว
let cells = [];       // ผลการนับรายช่อง เก็บไว้ให้ตอนเอาเมาส์ชี้หยิบไปใช้
let gridN = 32;       // ตอนนี้แบ่งกี่ช่องต่อด้าน


// --------------------------------------------------------------------------
// ส่วนที่ 1 — เริ่มต้น
// --------------------------------------------------------------------------

async function load() {
  await fillMapSelect("mapSelect");                   // เติมรายชื่อแมพจากฐานข้อมูล (fillMapSelect อยู่ใน common.js)

  $("mapSelect").addEventListener("change", draw);    // เปลี่ยนแมพ -> วาดใหม่
  $("gridSize").addEventListener("change", draw);     // เปลี่ยนความละเอียดตาราง -> วาดใหม่
  bindSeg("sideSeg", (v) => { side = v; draw(); });   // ปุ่มสลับ ทั้งหมด/CT/T (bindSeg อยู่ใน common.js)

  bindHover();                                        // ผูกการเอาเมาส์ชี้ช่อง
  await draw();
}


// --------------------------------------------------------------------------
// ส่วนที่ 2 — โหลดข้อมูลแล้ววาด
// --------------------------------------------------------------------------

async function draw() {
  const map = $("mapSelect").value;
  if (!map) return;                                   // ยังไม่มีแมพให้เลือก -> ไม่ต้องทำอะไร

  gridN = Number($("gridSize").value);                // Number(...) = แปลงข้อความ "32" เป็นตัวเลข 32
  await loadRadar(map);                               // เตรียมภาพเรดาร์ก่อน (ถ้าแมพนี้มี)

  const d = await api(`/api/heatmap?map=${map}` + (side ? "&side=" + side : ""));
  // (เงื่อนไข ? ก : ข) = ถ้าเลือกฝั่งไว้ ค่อยต่อ &side= ท้าย URL

  cells = countCells(d.points);                       // นับคนตายรายช่อง
  paint();                                            // วาดภาพ + ตาราง
  drawStats(d, map);                                  // การ์ดตัวเลข + ตารางอันดับ
}

/**
 * โหลดค่าปรับเทียบ + ภาพเรดาร์ของแมพที่เลือก
 * ถ้าแมพนี้ยังไม่มีค่าปรับเทียบใน radars.json จะตั้ง radar = null
 * แล้วโค้ดจะเปลี่ยนไปวาดแบบ "ย่อให้พอดีกรอบ" แทน (ไม่มีภาพพื้นหลัง แต่ยังดูรูปทรงได้)
 */
async function loadRadar(map) {
  if (radar && radar.map === map) return;             // แมพเดิม -> ใช้ภาพที่โหลดไว้แล้ว ไม่ต้องโหลดซ้ำ

  radar = null;
  radarImg = null;
  $("mapNote").textContent = "";

  try {
    radar = await api(`/api/radar?map=${map}`);
  } catch (e) {
    $("mapNote").textContent =
      `แมพ ${map} ยังไม่มีค่าปรับเทียบใน assets/radars.json — วาดตารางแบบย่อพอดีกรอบแทน`;
    return;                                           // ไม่มีค่าปรับเทียบก็ไม่พัง แค่ไม่มีภาพพื้นหลัง
  }

  // โหลดไฟล์ภาพ 
  radarImg = await new Promise((resolve, reject) => {
    const img = new Image();                          // new Image() = สร้าง <img> ในหน่วยความจำ (ไม่ได้แปะบนหน้าเว็บ)
    img.onload = () => resolve(img);                  // onload = "โหลดรูปเสร็จแล้ว" -> ส่งรูปออกไป
    img.onerror = () => reject(new Error("โหลดภาพเรดาร์ไม่ได้"));
    img.src = radar.image;                            // .src = ที่อยู่ของรูป (พอตั้งค่านี้ เบราว์เซอร์เริ่มโหลดทันที)
  }).catch(() => null);                               // โหลดรูปพลาด -> ใช้ null แล้ววาดแบบไม่มีพื้นหลัง
}

// --------------------------------------------------------------------------
// ส่วนที่ 3 — นับคนตายรายช่อง
// --------------------------------------------------------------------------

/** ขนาดผ้าใบ = ขนาดภาพเรดาร์ (ถ้าไม่มีภาพก็ใช้ 1024 ไปก่อน) */
function canvasSize() {
  return radar ? radar.size : 1024;
}

/**
 * แปลงพิกัดเกม -> พิกัดบนผ้าใบ
 * คืนฟังก์ชันออกไป เพราะวิธีแปลงต่างกันตามว่ามีค่าปรับเทียบไหม
 */
function makeConverter(pts) {
  const size = canvasSize();

  if (radar) {
    // สูตรทางการ — จุดจะตกตรงตำแหน่งจริงบนภาพเรดาร์
    return (gx, gy) => [
      (gx - radar.pos_x) / radar.scale,      // pos_x = พิกัดเกมของขอบซ้ายภาพ, scale = 1 พิกเซลเท่ากับกี่หน่วยเกม
      (radar.pos_y - gy) / radar.scale,      // สลับเป็น (pos_y - gy) เพราะแกน y ของเกมกับของภาพกลับด้านกัน
    ];
  }

  // ทางสำรอง: หาขอบเขตของข้อมูลเอง แล้วย่อให้พอดีผ้าใบ
  const xs = pts.map((p) => p.x), ys = pts.map((p) => p.y);
  const minX = Math.min(...xs), maxX = Math.max(...xs);   // ... = "แผ่" array ออกเป็นตัว ๆ ให้ Math.min
  const minY = Math.min(...ys), maxY = Math.max(...ys);
  const pad = 30;
  const sc = Math.min((size - pad * 2) / (maxX - minX || 1),   // || 1 กันหารด้วยศูนย์
                      (size - pad * 2) / (maxY - minY || 1));  // ใช้ตัวเล็กกว่า แผนที่จะได้ไม่ยืดเบี้ยว
  return (gx, gy) => [pad + (gx - minX) * sc, size - pad - (gy - minY) * sc];
}

/**
 * แบ่งภาพเป็นตาราง gridN x gridN ช่อง แล้วนับว่าแต่ละช่องมีคนตายกี่คน
 * คืนออกมาเป็น array ของช่องที่มีคนตายอย่างน้อย 1 คน
 */
function countCells(pts) {
  const size = canvasSize();
  const cell = size / gridN;              // ช่องหนึ่งกว้างกี่พิกเซล เช่น 1024 / 32 = 32
  const toPixel = makeConverter(pts);
  const bucket = new Map();               // Map = ตารางเก็บของแบบ "คีย์ -> ค่า" (คล้าย object แต่ใช้คีย์แบบไหนก็ได้)

  pts.forEach((p) => {                    // forEach = วนทำทีละจุด
    const [px, py] = toPixel(p.x, p.y);   // [px, py] = แกะค่าสองตัวจาก array ที่ฟังก์ชันคืนมา

    const cx = Math.floor(px / cell);     // Math.floor = ปัดลง -> ได้ว่าอยู่ช่องที่เท่าไรในแนวนอน
    const cy = Math.floor(py / cell);     // เช่น px=100, cell=32 -> 100/32 = 3.125 -> ช่องที่ 3
    if (cx < 0 || cy < 0 || cx >= gridN || cy >= gridN) return;   // จุดหลุดนอกภาพ -> ข้ามไป

    const key = cy * gridN + cx;          // ยุบพิกัด 2 มิติให้เป็นเลขตัวเดียว จะได้ใช้เป็นคีย์ได้
    let c = bucket.get(key);
    if (!c) {                             // ยังไม่เคยเจอช่องนี้ -> สร้างใหม่
      c = { cx, cy, n: 0, ct: 0, t: 0, places: {} };
      bucket.set(key, c);
    }
    c.n++;                                          // จำนวนคนตายในช่องนี้ +1
    if (p.side === "ct") c.ct++; else c.t++;        // แยกนับว่าเป็นฝั่งไหน
    if (p.place) c.places[p.place] = (c.places[p.place] || 0) + 1;   // นับชื่อ callout ที่เจอ
  });

  // แปลง Map กลับเป็น array ธรรมดา แล้วหาชื่อ callout ที่พบบ่อยที่สุดของแต่ละช่อง
  return [...bucket.values()].map((c) => ({
    ...c,                                                     // ... = "เทของเดิมทั้งหมดมาใส่"
    place: Object.entries(c.places).sort((a, b) => b[1] - a[1])[0]?.[0] || "-",
    // Object.entries = แปลง {A:5, B:2} เป็น [["A",5], ["B",2]]
    // .sort((a,b) => b[1]-a[1]) = เรียงจากจำนวนมากไปน้อย
    // [0]?.[0] = เอาตัวแรก แล้วเอาชื่อของมัน (?. = ถ้าไม่มีก็อย่าพัง)
  }));
}

// --------------------------------------------------------------------------
// ส่วนที่ 4 — วาดลงผ้าใบ
// --------------------------------------------------------------------------

function paint() {
  const cv = $("heat");                       // ผ้าใบ
  const ctx = cv.getContext("2d");            // getContext("2d") = ขอ "ปากกา" สำหรับวาดรูป 2 มิติ
  const size = canvasSize();

  if (cv.width !== size) { cv.width = size; cv.height = size; }   // ตั้งขนาดผ้าใบให้เท่าภาพ จะได้แปลงพิกัดแบบ 1 ต่อ 1
  ctx.clearRect(0, 0, size, size);            // ลบของเก่าทิ้งทั้งผืน (x, y, กว้าง, สูง)

  // --- ชั้นที่ 1: ภาพเรดาร์ ---
  if (radarImg) {
    ctx.drawImage(radarImg, 0, 0, size, size);   // drawImage(รูป, x, y, กว้าง, สูง)
    ctx.fillStyle = "rgba(5,8,15,.52)";          // ผ้าคลุมดำโปร่ง ๆ ทับภาพ
    ctx.fillRect(0, 0, size, size);              // ถ้าไม่คลุม ภาพเรดาร์จะสว่างจนสีของช่องกลืนหาย
                                                 // แต่ถ้าคลุมเข้มไป ก็จะมองไม่เห็นว่าช่องนั้นอยู่ตรงไหนของแมพ
  } else {
    ctx.fillStyle = "#0a1322";
    ctx.fillRect(0, 0, size, size);
  }

  const cell = size / gridN;

  // --- ชั้นที่ 2: เส้นตาราง ---
  ctx.strokeStyle = "rgba(255,255,255,.05)";  // strokeStyle = สีของ "เส้น" (fillStyle คือสีของ "พื้น")
  ctx.lineWidth = 1;
  ctx.beginPath();                            // เริ่มเขียนเส้นชุดใหม่
  for (let i = 1; i < gridN; i++) {           // let i = 1 -> ข้ามเส้นที่ขอบ วาดแต่เส้นข้างใน
    ctx.moveTo(i * cell, 0); ctx.lineTo(i * cell, size);   // moveTo = ยกปากกาไปวาง, lineTo = ลากเส้นไปหา
    ctx.moveTo(0, i * cell); ctx.lineTo(size, i * cell);
  }
  ctx.stroke();                               // ลากเส้นทั้งหมดที่สั่งไว้ออกมาจริง ๆ

  if (!cells.length) return;

  // --- ชั้นที่ 3: ระบายช่องตามจำนวนคนตาย ---
  const max = Math.max(...cells.map((c) => c.n));   // ช่องที่ตายเยอะสุด = เข้มสุด ที่เหลือเทียบกับมัน

  cells.forEach((c) => {
    ctx.fillStyle = cellColor(c, c.n / max);        // สี = ฝั่ง, ความเข้ม = จำนวนคนตาย
    ctx.fillRect(c.cx * cell, c.cy * cell, cell, cell);   // ระบายสี่เหลี่ยมเต็มช่อง
  });

  // --- ชั้นที่ 4: กรอบเน้นช่องที่ร้อนที่สุด 3 อันดับแรก ---
  const top3 = [...cells].sort((a, b) => b.n - a.n).slice(0, 3);
  // [...cells] = ก๊อป array ก่อนเรียง (ถ้าเรียงตัวจริงเลย ลำดับเดิมจะหายไป)
  ctx.strokeStyle = "rgba(255,255,255,.9)";         // ขาว ใช้ได้กับช่องทั้งสองสี
  ctx.lineWidth = Math.max(2, size / 400);
  top3.forEach((c) => ctx.strokeRect(c.cx * cell, c.cy * cell, cell, cell));   // strokeRect = วาดแค่กรอบ ไม่ระบายข้างใน
}

function cellColor(c, ratio) {
  // กรองฝั่งไว้ -> ใช้สีฝั่งนั้น | ดูทั้งหมด -> ใช้สีของฝั่งที่ตายเยอะกว่าในช่องนั้น
  const isCt = side === "ct" ? true
             : side === "t"  ? false
             : c.ct >= c.t;
  const a = 0.10 + 0.80 * Math.pow(ratio, 0.6);
  // Math.pow(ratio, 0.6) = ยกกำลัง 0.6 (น้อยกว่า 1 = ดันค่าน้อย ๆ ให้สูงขึ้น)
  // ถ้าไม่ทำ ช่องที่ตาย 1-2 คนจะจางจนมองไม่เห็นเลย เพราะช่องร้อนสุดมีเป็นร้อย
  return `rgba(${isCt ? SIDE_RGB.ct : SIDE_RGB.t},${a.toFixed(3)})`;
}

const SIDE_RGB = { ct: "77,139,255", t: "255,122,24" };   // สีประจำฝั่ง เก็บเป็นเลข R,G,B ไว้ใช้กับ rgba()

// --------------------------------------------------------------------------
// ส่วนที่ 5 — การ์ดตัวเลข + ตารางอันดับ
// --------------------------------------------------------------------------

function drawStats(d, map) {
  const max = cells.length ? Math.max(...cells.map((c) => c.n)) : 0;
  const hottest = cells.find((c) => c.n === max);    // find = หาตัวแรกที่ตรงเงื่อนไข

  drawKpis("heatKpis", [
    { k: "จุดที่นับ",      v: fmt(d.count),                s: esc(map) },
    { k: "ช่องที่มีคนตาย", v: fmt(cells.length),           s: `จากทั้งหมด ${fmt(gridN * gridN)} ช่อง` },
    { k: "ช่องที่ตายเยอะที่สุด",  v: fmt(max),                    s: hottest ? esc(hottest.place) : "-" },
    { k: "เฉลี่ยต่อช่อง",   v: cells.length ? (d.count / cells.length).toFixed(1) : "0",
                            s: "เฉพาะช่องที่มีคนตาย" },
  ]);

  drawLegend(max);

  drawTopTable();
}

/**
 * วาดแถบไล่สีใต้แผนที่ ให้สีตรงกับที่ระบายบนช่องจริง ๆ
 * กรองฝั่งไว้ -> แถบเดียว สีของฝั่งนั้น
 * ดูทั้งหมด   -> สองแถบ บอกว่าน้ำเงินคือช่องที่ CT ตายเยอะกว่า ส้มคือ T ตายเยอะกว่า
 */
function drawLegend(max) {
  /** สร้างแถบไล่สีหนึ่งแถบ จากจางไปเข้ม */
  const bar = (rgb) =>
    `<div class="legend-bar" style="background:linear-gradient(90deg,
       rgba(${rgb},.10), rgba(${rgb},.90))"></div>`;

  const rows = side
    ? `<div class="legend">
         <span class="sub">น้อย</span>${bar(SIDE_RGB[side])}<span class="sub">มาก</span>
       </div>`
    : `<div class="legend">
         <span class="sub" style="min-width:96px">CT ตายเยอะกว่า</span>${bar(SIDE_RGB.ct)}
       </div>
       <div class="legend">
         <span class="sub" style="min-width:96px">T ตายเยอะกว่า</span>${bar(SIDE_RGB.t)}
       </div>`;
  // min-width = จองความกว้างป้ายเท่ากันทั้งสองแถว แถบไล่สีจะได้เริ่มตรงกันพอดี

  $("legend").innerHTML = rows +
    `<div class="sub" style="margin-top:6px">ช่องที่เข้มที่สุด = ตาย ${fmt(max)} คน</div>`;
}

/** ตารางอันดับช่องที่อันตรายที่สุด (ฝั่งขวาของหน้า) */
function drawTopTable() {
  const top = [...cells].sort((a, b) => b.n - a.n).slice(0, 10);
  $("topCells").innerHTML = tableHTML(
    ["ตำแหน่ง", "ช่อง", "ตาย", "CT / T"],
    top.map((c) => [
      esc(c.place),
      `<span class="sub">${c.cx},${c.cy}</span>`,
      { n: fmt(c.n) },
      { n: `<span class="tag ct">${c.ct}</span> <span class="tag t">${c.t}</span>` },
    ]));
}

// --------------------------------------------------------------------------
// ส่วนที่ 6 — เอาเมาส์ชี้ช่องแล้วโชว์ตัวเลข
// --------------------------------------------------------------------------

function bindHover() {
  const cv = $("heat");

  cv.addEventListener("mousemove", (e) => {         // mousemove = "เมาส์ขยับอยู่บนผ้าใบ"
    const r = cv.getBoundingClientRect();           // ขนาดและตำแหน่งจริงของผ้าใบบนจอ (หน่วยพิกเซลจอ)
    const size = canvasSize();

    // จอย่อผ้าใบลงมา เลยต้องคูณกลับ ให้ได้พิกัด "ในผ้าใบ"
    const px = (e.clientX - r.left) / r.width * size;    // e.clientX = ตำแหน่งเมาส์บนจอ
    const py = (e.clientY - r.top) / r.height * size;

    const cell = size / gridN;
    const cx = Math.floor(px / cell), cy = Math.floor(py / cell);
    const c = cells.find((q) => q.cx === cx && q.cy === cy);

    if (!c) { $("tip").classList.add("hidden"); return; }   // ชี้โดนช่องที่ไม่มีข้อมูล -> ซ่อนกล่อง

    $("tip").classList.remove("hidden");
    $("tip").innerHTML =
      `<b>${esc(c.place)}</b><br>ตาย ${fmt(c.n)} คน<br>
       <span style="color:var(--ct)">CT ${c.ct}</span> ·
       <span style="color:var(--t)">T ${c.t}</span>`;

    // วางกล่องข้อความไว้ข้างเมาส์ (+14 = เยื้องออกนิดหน่อย จะได้ไม่ทับลูกศรเมาส์)
    $("tip").style.left = (e.clientX - r.left + 14) + "px";
    $("tip").style.top  = (e.clientY - r.top + 14) + "px";
  });

  cv.addEventListener("mouseleave", () => $("tip").classList.add("hidden"));
  // mouseleave = "เมาส์ออกไปจากผ้าใบแล้ว" -> ซ่อนกล่องข้อความ
}


start(load);   