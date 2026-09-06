// ==========================================================================
// main.js — "สมอง" ของแดชบอร์ด
//
// หน้าเว็บนี้มี 6 หน้าซ้อนอยู่ในไฟล์ HTML เดียว
// (ภาพรวม / แมตช์ / นักแข่ง / แผนที่ / แท็คติก / โมเดล ML)
// ไฟล์นี้ทำ 3 อย่าง
//   1) เช็กว่าล็อกอินอยู่จริงไหม
//   2) สลับว่าจะโชว์หน้าไหน ตามตัวหนังสือหลัง # ใน URL
//   3) ขอข้อมูลจาก backend แล้วเอามาวาดเป็นตาราง/กราฟ/แผนที่
// ==========================================================================


// --------------------------------------------------------------------------
// ส่วนที่ 0 — เครื่องมือเล็ก ๆ ที่ใช้ซ้ำทั้งไฟล์
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
  // .map(...) = แปลงข้อมูลทุกแถวให้เป็นข้อความ HTML  -> ได้ array ของข้อความ
  // .join("")  = เอาข้อความทุกชิ้นมาต่อกันเป็นก้อนเดียว
  // ` ` (backtick) = ข้อความหลายบรรทัดที่แทรกค่าตัวแปรได้ด้วย ${...}
  // toFixed(1) = ปัดเหลือทศนิยม 1 ตำแหน่ง
}

/** สร้างการ์ดตัวเลขสรุป (KPI) — items = [{k:"ป้าย", v:"ตัวเลข", s:"คำอธิบาย"}, ...] */
function drawKpis(boxId, items) {
  $(boxId).innerHTML = items.map((it) => `
    <div class="kpi">
      <div class="k">${esc(it.k)}</div>
      <div class="v">${it.v}</div>
      <div class="s">${esc(it.s || "")}</div>
    </div>`).join("");
  // it.v ไม่ผ่าน esc เพราะบางอันเราตั้งใจใส่แท็ก <small> เข้าไปเอง (เป็นข้อความของเราเอง ไม่ใช่ของผู้ใช้)
}


// --------------------------------------------------------------------------
// ส่วนที่ 1 — ตัวสลับหน้า (router)
// --------------------------------------------------------------------------

const TABS = ["overview", "matches", "players", "map", "tactical", "ml"];   // รายชื่อหน้าทั้งหมดที่มี
const loaded = {};                                        // จำว่าหน้าไหนโหลดข้อมูลไปแล้ว จะได้ไม่ขอซ้ำทุกครั้งที่กดแท็บ

/** เปลี่ยนหน้าไปตามชื่อที่ให้มา */
function showTab(name) {
  if (!TABS.includes(name)) name = "overview";   // ถ้าชื่อแปลก ๆ ให้กลับไปหน้าแรก

  TABS.forEach((t) => {                                        // วนดูทุกหน้า
    $("page-" + t).classList.toggle("on", t === name);         // classList.toggle("on", เงื่อนไข)
                                                               //   เงื่อนไขจริง = ใส่คลาส on (หน้าโผล่)
                                                               //   เงื่อนไขเท็จ = ถอดคลาส on (หน้าซ่อน)
  });

  document.querySelectorAll(".nav a").forEach((a) => {         // querySelectorAll = หยิบทุกชิ้นที่ตรงเงื่อนไข (ที่นี่คือลิงก์ในเมนู)
    a.classList.toggle("active", a.dataset.tab === name);      // a.dataset.tab = ค่าใน data-tab="..." ของลิงก์นั้น
  });                                                          // ลิงก์ที่ตรงกับหน้าปัจจุบันจะได้ขีดส้มใต้

  if (!loaded[name]) {          // หน้านี้ยังไม่เคยโหลดข้อมูล
    loaded[name] = true;        // ปักธงว่าโหลดแล้ว
    LOADERS[name]();            // เรียกฟังก์ชันโหลดข้อมูลของหน้านั้น (ดูตาราง LOADERS ข้างล่าง)
  }
}

window.addEventListener("hashchange", () => showTab(location.hash.slice(1)));
// hashchange = เหตุการณ์ "ตัวหนังสือหลัง # ใน URL เปลี่ยน" (เกิดตอนผู้ใช้กดเมนู)
// location.hash = "#matches" -> .slice(1) = ตัดตัวแรก (#) ทิ้ง เหลือ "matches"


// --------------------------------------------------------------------------
// ส่วนที่ 2 — หน้า "ภาพรวม"
// --------------------------------------------------------------------------

async function loadOverview() {
  const map = $("mapFilter").value;                            // ค่าที่เลือกในช่องกรองแมพ ("" = ทุกแมพ)
  const s = await api("/api/stats" + (map ? "?map=" + map : ""));
  // (เงื่อนไข ? ก : ข) = ถ้าจริงใช้ ก ถ้าเท็จใช้ ข -> เลือกแมพแล้วค่อยต่อ ?map= ท้าย URL

  drawKpis("kpis", [
    { k: "แมตช์",       v: fmt(s.matches),                          s: `${fmt(s.rounds)} รอบ` },
    { k: "คิลทั้งหมด",   v: fmt(s.total_kills),                      s: `เฉลี่ยรอบที่ ${s.avg_round}` },
    { k: "ยิงหัว",       v: `${s.headshot_rate}<small>%</small>`,     s: `${fmt(s.headshots)} ครั้ง` },
    { k: "CT ฆ่า",      v: fmt(s.ct_kills),                          s: pct(s.ct_kills, s.total_kills) },
    { k: "T ฆ่า",       v: fmt(s.t_kills),                           s: pct(s.t_kills, s.total_kills) },
  ]);

  drawBars("wpBars", s.top_weapons);      // กราฟอาวุธ
  drawBars("plBars", s.top_places);       // กราฟจุดที่คนตาย

  const ms = await api("/api/matches");                        // ขอรายการแมตช์ทั้งหมด
  const last5 = ms.slice(-5).reverse();                        // slice(-5) = เอา 5 ตัวท้าย, reverse() = กลับลำดับให้ใหม่สุดอยู่บน
  $("recent").innerHTML = tableHTML(
    ["แมพ", "ทีม", "รอบ", "CT", "T", "คิล"],                    // ชื่อหัวคอลัมน์
    last5.map((m) => [
      esc(m.map_name),
      esc(m.team_a || "-") + " vs " + esc(m.team_b || "-"),     // || "-" = ถ้าไม่มีชื่อทีมให้ใส่ขีดแทน
      { n: m.rounds }, { n: m.ct_rounds }, { n: m.t_rounds }, { n: fmt(m.kills) },
      // {n: ...} = บอกว่าช่องนี้เป็นตัวเลข ให้ชิดขวา (ดูฟังก์ชัน tableHTML)
    ]));
}

/** คิดเป็นเปอร์เซ็นต์แล้วทำเป็นข้อความ เช่น "54%" */
const pct = (a, b) => (b ? Math.round(a / b * 100) + "%" : "—");
// (b ? ... : "—") = ถ้าตัวหารเป็น 0 ให้แสดงขีดแทน กันหารด้วยศูนย์

/**
 * สร้างข้อความ HTML ของตาราง
 * head = ["คอลัมน์1", "คอลัมน์2", ...]
 * body = [[ช่อง, ช่อง, ...], ...]   ช่องที่เป็น {n: ค่า} จะถูกจัดชิดขวา
 * opt  = { rowAttr: ฟังก์ชันที่คืนข้อความไปแปะบนแท็ก <tr> } — ใช้ทำแถวที่กดได้
 */
function tableHTML(head, body, opt = {}) {
  const th = head.map((h, i) =>
    `<th class="${typeof body[0]?.[i] === "object" ? "num" : ""}">${esc(h)}</th>`).join("");
  // ดูจากแถวแรกว่าคอลัมน์ไหนเป็นตัวเลข แล้วใส่คลาส num ให้หัวคอลัมน์นั้นชิดขวาตาม
  // body[0]?.[i] — เครื่องหมาย ?. = "ถ้าไม่มีก็อย่าพัง คืน undefined ไปเลย" (กันกรณีตารางว่าง)

  const tr = body.map((row, ri) => `
    <tr ${opt.rowAttr ? opt.rowAttr(ri) : ""}>
      ${row.map((c) => typeof c === "object"
          ? `<td class="num">${c.n}</td>`     // ช่องตัวเลข -> ชิดขวา
          : `<td>${c}</td>`).join("")}
    </tr>`).join("");

  if (!body.length) return '<div class="empty">ไม่มีข้อมูล</div>';   // ตารางว่าง -> บอกไปตรง ๆ ดีกว่าโชว์ตารางเปล่า
  return `<table><thead><tr>${th}</tr></thead><tbody>${tr}</tbody></table>`;
  // thead = ส่วนหัวตาราง, tbody = ส่วนเนื้อตาราง
}


// --------------------------------------------------------------------------
// ส่วนที่ 3 — หน้า "แมตช์"
// --------------------------------------------------------------------------

let matchList = [];    // let = ตัวแปรที่เปลี่ยนค่าได้ (const เปลี่ยนไม่ได้) — เก็บรายการแมตช์ไว้ใช้ซ้ำ

async function loadMatches() {
  matchList = await api("/api/matches");
  $("matchCount").textContent = `(${matchList.length} นัด)`;   // .length = จำนวนสมาชิกใน array

  $("matchTable").innerHTML = tableHTML(
    ["#", "แมพ", "รอบ", "CT", "T", "คิล"],
    matchList.map((m) => [
      String(m.id), esc(m.map_name),
      { n: m.rounds }, { n: m.ct_rounds }, { n: m.t_rounds }, { n: fmt(m.kills) },
    ]),
    { rowAttr: (i) => `class="click" data-i="${i}"` }   // ทุกแถวกดได้ และจำไว้ว่าเป็นแถวที่เท่าไร
  );

  $("matchTable").querySelectorAll("tr.click").forEach((tr) => {
    tr.addEventListener("click", () => {                       // "ถ้าแถวนี้ถูกคลิก ให้ทำสิ่งนี้"
      $("matchTable").querySelectorAll("tr").forEach((x) => x.classList.remove("sel"));  // ล้างไฮไลต์แถวเดิมก่อน
      tr.classList.add("sel");                                 // ไฮไลต์แถวที่เพิ่งกด
      openMatch(matchList[tr.dataset.i].id);                   // tr.dataset.i = เลขแถวที่เราแปะไว้ตอนสร้าง
    });
  });
}

/** เปิดรายละเอียดของแมตช์หนึ่งนัด */
async function openMatch(id) {
  const box = $("matchDetail");
  box.innerHTML = '<div class="empty">กำลังโหลด…</div>';       // โชว์ "กำลังโหลด" ระหว่างรอ จะได้ไม่เงียบ
  const d = await api("/api/matches/" + id);

  const timeline = d.rounds.map((r) => `
    <div class="rnd ${["ct", "t"].includes(r.winner_side) ? r.winner_side : "na"}"
         title="รอบ ${r.round_num} · ${esc(r.end_reason || "")} · ${r.kills} คิล">
      ${r.round_num}
    </div>`).join("");
  // class="rnd ct" หรือ "rnd t" -> CSS ระบายน้ำเงิน/ส้มตามฝั่งที่ชนะ
  // includes(...) = เช็กว่าค่านี้อยู่ในรายการไหม ถ้าข้อมูลไม่บอกว่าใครชนะ ให้ใช้ "na" (สีเทา) กันหน้าเพี้ยน
  // title="..." = ข้อความที่โผล่มาตอนเอาเมาส์ค้างไว้บนกล่อง

  const sb = tableHTML(
    ["นักแข่ง", "K", "D", "A", "HS"],
    d.scoreboard.map((p) => [
      esc(p.name), { n: p.kills }, { n: p.deaths }, { n: p.assists }, { n: p.headshots },
    ]));

  box.innerHTML = `
    <div class="eyebrow">${esc(d.match.map_name)}</div>
    <h2>แมตช์ #${d.match.id}</h2>
    <div class="sub" style="margin-bottom:14px">
      <span class="tag ct">CT ${d.match.ct_rounds}</span>
      <span class="tag t">T ${d.match.t_rounds}</span>
      · ${d.rounds.length} รอบ · ${fmt(d.match.kills)} คิล
    </div>
    <div class="eyebrow">Round timeline</div>
    <div class="timeline" style="margin:8px 0 18px">${timeline}</div>
    <div class="eyebrow">Scoreboard</div>
    ${sb}`;
}


// --------------------------------------------------------------------------
// ส่วนที่ 4 — หน้า "นักแข่ง"
// --------------------------------------------------------------------------

let playerList = [];

async function loadPlayers() {
  const min = $("minMatches").value || "1";                    // ค่าที่เลือกในช่องกรอง "เล่นอย่างน้อยกี่แมตช์"
                                                               // || "1" = ถ้าช่องว่างด้วยเหตุใดก็ตาม ให้ใช้ 1 (backend ไม่รับค่าว่าง)
  playerList = await api(`/api/players?limit=30&min_matches=${min}`);

  $("playerTable").innerHTML = tableHTML(
    ["นักแข่ง", "แมตช์", "K", "D", "K/D", "HS%"],
    playerList.map((p) => [
      esc(p.name),
      { n: p.matches }, { n: fmt(p.kills) }, { n: fmt(p.deaths) },
      { n: p.kd }, { n: p.hs_rate + "%" },
    ]),
    { rowAttr: (i) => `class="click" data-i="${i}"` }
  );

  $("playerTable").querySelectorAll("tr.click").forEach((tr) => {
    tr.addEventListener("click", () => {
      $("playerTable").querySelectorAll("tr").forEach((x) => x.classList.remove("sel"));
      tr.classList.add("sel");
      openPlayer(playerList[tr.dataset.i].steam_id);
    });
  });
}

/** เปิดรายละเอียดของนักแข่งคนเดียว */
async function openPlayer(steamId) {
  const box = $("playerDetail");
  box.innerHTML = '<div class="empty">กำลังโหลด…</div>';
  const d = await api("/api/players/" + steamId);
  const p = d.player;

  box.innerHTML = `
    <div class="eyebrow">Player</div>
    <h2>${esc(p.name)}</h2>
    <div class="sub" style="margin-bottom:14px">
      ${p.matches} แมตช์ · ${fmt(p.kills)} คิล / ${fmt(p.deaths)} ตาย ·
      K/D <b style="color:var(--orange)">${p.kd}</b> · ยิงหัว ${p.hs_rate}%
    </div>
    <div class="eyebrow">อาวุธที่ใช้</div>
    <div id="pWp" style="margin:8px 0 16px"></div>
    <div class="eyebrow">จุดที่เขาฆ่าคนบ่อย</div>
    <div id="pKill" style="margin:8px 0 16px"></div>
    <div class="eyebrow">จุดที่เขาตายบ่อย</div>
    <div id="pDeath" style="margin-top:8px"></div>`;
  // ต้องสร้างกล่องเปล่า 3 กล่องนี้ลงหน้าเว็บก่อน แล้วค่อยวาดกราฟใส่ (ไม่งั้น drawBars หากล่องไม่เจอ)

  drawBars("pWp", d.weapons);
  drawBars("pKill", d.kill_places);
  drawBars("pDeath", d.death_places);
}


// --------------------------------------------------------------------------
// ส่วนที่ 5 — หน้า "แผนที่" (heatmap จุดที่คนตาย)
// --------------------------------------------------------------------------

let heatSide = "";     // ฝั่งที่กำลังกรองอยู่: "" = ทั้งหมด, "ct", "t"

async function loadMap() {
  const map = $("heatMap").value;
  if (!map) return;                                            // ยังไม่มีแมพให้เลือก -> ไม่ต้องทำอะไร

  const d = await api(`/api/heatmap?map=${map}` + (heatSide ? "&side=" + heatSide : ""));

  const ct = d.points.filter((p) => p.side === "ct").length;    // filter = คัดเฉพาะตัวที่ตรงเงื่อนไข, .length = นับจำนวน
  const hs = d.points.filter((p) => p.headshot).length;

  drawKpis("heatKpis", [
    { k: "จุดที่พล็อต",  v: fmt(d.count),                    s: esc(map) },
    { k: "CT ตาย",     v: fmt(ct),                          s: pct(ct, d.count) },
    { k: "T ตาย",      v: fmt(d.count - ct),                s: pct(d.count - ct, d.count) },
    { k: "โดนยิงหัว",   v: `${pct(hs, d.count)}`,            s: `${fmt(hs)} จุด` },
  ]);

  drawHeat(d.points);
}

/** วาดจุดที่คนตายลงบนผ้าใบ (canvas) */
function drawHeat(pts) {
  const cv = $("heat");                  // ผ้าใบ
  const ctx = cv.getContext("2d");       // getContext("2d") = ขอ "ปากกา" สำหรับวาดรูป 2 มิติ
  ctx.clearRect(0, 0, cv.width, cv.height);   // ลบของเก่าทิ้งทั้งผืน (x, y, กว้าง, สูง)

  if (!pts.length) return;               // ไม่มีจุด -> จบ

  // --- หาขอบเขตของพิกัดในเกม เพื่อย่อ/ขยายให้พอดีผ้าใบ ---
  const xs = pts.map((p) => p.x), ys = pts.map((p) => p.y);
  const minX = Math.min(...xs), maxX = Math.max(...xs);
  const minY = Math.min(...ys), maxY = Math.max(...ys);

  const pad = 40;                                              // เว้นขอบผ้าใบไว้ 40 จุด จะได้ไม่ติดขอบพอดี
  const sx = (cv.width  - pad * 2) / (maxX - minX || 1);       // อัตราย่อ/ขยายแกน X  (|| 1 กันหารด้วยศูนย์)
  const sy = (cv.height - pad * 2) / (maxY - minY || 1);
  const sc = Math.min(sx, sy);                                 // ใช้ตัวที่เล็กกว่า เพื่อให้แผนที่ไม่ยืดเบี้ยว

  pts.forEach((p) => {
    const x = pad + (p.x - minX) * sc;                         // แปลงพิกัดในเกม -> พิกัดบนผ้าใบ
    const y = cv.height - pad - (p.y - minY) * sc;             // แกน Y ต้องกลับหัว เพราะในเกม Y เพิ่มขึ้นด้านบน
                                                               // แต่บนผ้าใบ Y เพิ่มลงล่าง

    const color = p.side === "ct" ? "77,139,255" : "255,122,24";   // CT = น้ำเงิน, T = ส้ม (เก็บเป็นเลข R,G,B)

    const g = ctx.createRadialGradient(x, y, 0, x, y, 16);     // สร้างการไล่สีแบบวงกลม จากจุดกลางออกไปรัศมี 16
    g.addColorStop(0, `rgba(${color},.55)`);                   // ตรงกลางเข้ม
    g.addColorStop(1, `rgba(${color},0)`);                     // ขอบนอกจางหายไป -> ได้ "แสงฟุ้ง" นุ่ม ๆ

    ctx.fillStyle = g;                                         // ตั้งค่าสีที่จะระบาย = การไล่สีที่เพิ่งสร้าง
    ctx.beginPath();                                           // เริ่มวาดรูปใหม่
    ctx.arc(x, y, 16, 0, Math.PI * 2);                         // arc = วาดวงกลม (x, y, รัศมี, มุมเริ่ม, มุมจบ)
                                                               // Math.PI * 2 = 360 องศา = วงกลมเต็มใบ
    ctx.fill();                                                // ระบายสีลงในรูปที่วาด
  });
  // จุดที่ทับกันหลาย ๆ จุดจะสว่างขึ้นเรื่อย ๆ เอง -> ตรงไหนสว่าง = ตรงนั้นคนตายบ่อย
}


// --------------------------------------------------------------------------
// ส่วนที่ 6 — หน้า "แท็คติก"
//
// แนวคิด: "การดวลแรกของรอบ" (opening duel) = คิลแรกสุดของรอบนั้น
// ใครชนะการดวลแรก มักลากยาวไปชนะทั้งรอบ เลยเป็นตัวเลขที่โค้ชดูก่อนเพื่อน
// --------------------------------------------------------------------------

let tacSide = "t";     // มองจากมุมฝั่งไหน ("t" หรือ "ct")

async function loadTactical() {
  const map = $("tacMap").value;
  if (!map) return;                                            // ยังไม่มีแมพให้เลือก -> ไม่ต้องทำอะไร

  const d = await api(`/api/tactical?map=${map}&side=${tacSide}`);
  const S = d.summary;
  const sideName = tacSide.toUpperCase();                      // toUpperCase = เปลี่ยนเป็นตัวพิมพ์ใหญ่ "t" -> "T"

  drawKpis("tacKpis", [
    { k: "รอบทั้งหมด",      v: fmt(S.rounds),                              s: esc(map) },
    { k: `${sideName} ชนะ`, v: pct(S.wins, S.rounds),                      s: `${fmt(S.wins)} รอบ` },
    { k: "รอบที่ปักระเบิด",  v: pct(S.planted, S.rounds),                   s: `${fmt(S.planted)} รอบ` },
    { k: "ปะทะแรกเฉลี่ย",   v: `${S.avg_first_contact}<small> วิ</small>`,  s: "นับจากหมดเวลาซื้อของ" },
  ]);

  // --- ตารางการดวลแรก แยกตามตำแหน่ง ---
  $("tacOpening").innerHTML = tableHTML(
    ["ตำแหน่ง", "ดวล", "ชนะดวล", "ชนะรอบ"],
    d.opening.map((o) => [
      esc(o.place),
      { n: o.duels },
      { n: badge(o.won, o.duels) },          // badge = ทำเป็นป้ายสี ดูง่ายกว่าตัวเลขเปล่า
      { n: badge(o.round_wins, o.duels) },
    ]));

  // --- ปะทะแรกเกิดตอนไหน ---
  // แสดงเป็นกราฟแท่ง (ความยาว = จำนวนรอบ) พร้อมบอกอัตราชนะของช่วงนั้น
  $("tacTiming").innerHTML = barsWithRate(d.timing, "bucket", "rounds", "wins", "รอบ");

  // --- รอบจบด้วยอะไร ---
  // ไม่โชว์อัตราชนะ เพราะสาเหตุการจบบอกผู้ชนะอยู่ในตัวแล้ว (t_killed = T แพ้เสมอ)
  drawBars("tacEndings", d.endings.map((e) => ({ name: reasonTH(e.reason), count: e.rounds })));

  // --- ปักระเบิดแล้วต่างกันแค่ไหน ---
  $("tacBomb").innerHTML = barsWithRate(d.bomb, "state", "rounds", "wins", "รอบ") +
    `<div class="sub" style="margin-top:10px">ตัวเลขในวงเล็บ = อัตราที่ฝั่ง ${sideName} ชนะรอบนั้น</div>`;
}

/** ทำป้ายสีบอกสัดส่วน เช่น 73/167 -> "44%" สีส้มถ้าเกินครึ่ง สีน้ำเงินถ้าต่ำกว่า */
function badge(part, whole) {
  const p = whole ? Math.round(part / whole * 100) : 0;
  return `<span class="tag ${p >= 50 ? "t" : "ct"}">${p}%</span>`;
  // (เงื่อนไข ? ก : ข) = ถ้าจริงใช้ ก ถ้าเท็จใช้ ข
}

/**
 * กราฟแท่ง + อัตราชนะต่อท้าย
 * list = ข้อมูล, kName/kCount/kWin = ชื่อช่องในข้อมูลที่จะเอามาใช้, unit = หน่วยที่จะพิมพ์ต่อท้าย
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
  // r[kName] = หยิบค่าจากช่องที่ชื่อตรงกับตัวแปร kName (เขียนแบบนี้ฟังก์ชันเดียวใช้ได้กับข้อมูลหลายแบบ)
}

/** แปลชื่อสาเหตุการจบรอบเป็นไทย */
function reasonTH(r) {
  return {
    t_killed:      "ฆ่า T หมดทีม",
    ct_killed:     "ฆ่า CT หมดทีม",
    bomb_exploded: "ระเบิดลง",
    bomb_defused:  "กู้ระเบิดสำเร็จ",
    time_ran_out:  "หมดเวลา",
  }[r] || r;
  // {...}[r] = เปิดตารางแปลด้วยคีย์ r, || r = ถ้าไม่มีในตารางก็ใช้ชื่อเดิม
}


// --------------------------------------------------------------------------
// ส่วนที่ 7 — หน้า "โมเดล ML"
//
// เราไม่ได้เทรนโมเดลในหน้าเว็บ สคริปต์ใน pipeline/ เทรนเสร็จแล้วเขียนคำตอบ
// ทุกกรณีลงไฟล์ json ไว้ให้ หน้านี้แค่เปิดตารางดู -> เร็วมากและไม่กินเครื่องผู้ใช้
// --------------------------------------------------------------------------

let rwData = null;    // เก็บตารางโมเดลไว้ จะได้ไม่ต้องขอใหม่ทุกครั้งที่เปลี่ยนช่องเลือก

async function loadMl() {
  // ----- โมเดลโอกาสชนะรอบ -----
  rwData = await api("/api/ml/round-win");
  const M = rwData.metrics;

  drawKpis("rwKpis", [
    { k: "AUC",              v: M.auc.toFixed(3),                s: "1.00 = ทายถูกหมด, 0.50 = เดาสุ่ม" },
    { k: "ดีกว่าเดาสุ่ม",     v: `${M.gain_pct.toFixed(1)}<small>%</small>`, s: `Brier ${M.brier.toFixed(3)} จาก ${M.brier_base.toFixed(3)}` },
    { k: "ข้อมูลที่ใช้เทรน",   v: fmt(M.rounds),                   s: `${fmt(M.rows)} จุดตัดสินใจ · ${M.matches} แมตช์` },
    { k: "CT ชนะโดยรวม",     v: pct(M.ct_win_overall * 100, 100), s: "ค่าตั้งต้นก่อนดูอะไรเลย" },
  ]);

  // เติมตัวเลือก 1-5 คนให้ช่อง "CT เหลือ" กับ "T เหลือ"
  const opts = (label) => [1, 2, 3, 4, 5].map((n) => `<option value="${n}">${label} ${n} คน</option>`).join("");
  $("rwCt").innerHTML = opts("CT เหลือ");
  $("rwT").innerHTML = opts("T เหลือ");
  $("rwCt").value = "5";                                       // ค่าเริ่มต้น = 5v5 (ต้นรอบ)
  $("rwT").value = "5";

  // ช่วงเวลามาจากไฟล์โมเดล ไม่ได้พิมพ์ทิ้งไว้เอง — โมเดลเปลี่ยนเมื่อไรหน้าเว็บเปลี่ยนตาม
  $("rwTime").innerHTML = rwData.time_names.map((t) => `<option value="${t}">วินาทีที่ ${t}</option>`).join("");
  $("rwTime").value = rwData.time_names[1] || rwData.time_names[0];

  drawRoundWin();

  // ----- โมเดลกริด -----
  const g = await api("/api/ml/grid");
  const G = g.metrics;

  drawKpis("gridKpis", [
    { k: "AUC",            v: G.auc.toFixed(3),                          s: `แบ่งแมพ ${g.grid_n}x${g.grid_n} ช่อง` },
    { k: "ดีกว่าเดาสุ่ม",   v: `${G.gain_pct.toFixed(1)}<small>%</small>`, s: `Brier ${G.brier_grid.toFixed(3)} จาก ${G.brier_base.toFixed(3)}` },
    { k: "การดวลที่ใช้",    v: fmt(G.duels),                              s: `${G.matches} แมตช์` },
    { k: "แมพ",            v: esc(g.map),                                s: "ตั้งค่าที่ pipeline/grid_ml.py" },
  ]);

  $("gridTable").innerHTML = tableHTML(
    ["ตำแหน่ง", "การดวล", "CT ชนะจริง", "โมเดลทาย"],
    g.cells.slice(0, 12).map((c) => [
      esc(c.place || "(ไม่ทราบ)"),
      { n: fmt(c.kills) },
      { n: `<span class="tag ${c.ct_win >= .5 ? "ct" : "t"}">${Math.round(c.ct_win * 100)}%</span>` },
      { n: `${Math.round(c.pred * 100)}%` },
    ]));
}

/** วาดผลของโมเดลโอกาสชนะรอบ ตามที่เลือกในช่องทั้ง 4 */
function drawRoundWin() {
  if (!rwData) return;

  const plant = $("rwPlant").value || "0";      // "0" = ยังไม่ปัก, "1" = ปักแล้ว
  const time = $("rwTime").value || rwData.time_names[0];
  // || ... = ค่าสำรอง เผื่อช่องเลือกยังว่างอยู่ ถ้าไม่ใส่ คีย์จะประกอบไม่ครบแล้วหาในตารางไม่เจอ

  // --- ตัวเลขใหญ่ของสถานะที่เลือกอยู่ ---
  const key = `${$("rwCt").value}v${$("rwT").value}|${plant}|${time}`;
  // คีย์หน้าตาแบบ "3v2|0|20-40s" — ต้องประกอบให้ตรงกับที่ pipeline/round_win.py เขียนไว้เป๊ะ ๆ
  const p = rwData.table[key];
  const n = rwData.support[key] || 0;    // support = จำนวนครั้งที่สถานะนี้เกิดขึ้นจริงในข้อมูล

  $("rwOut").innerHTML = p === undefined
    ? '<div class="empty">ไม่มีค่าของสถานะนี้</div>'
    : `<div style="display:flex; align-items:baseline; gap:14px; flex-wrap:wrap">
         <div style="font-size:44px; font-weight:800; color:var(--ct)">${Math.round(p * 100)}%</div>
         <div>
           <div>โอกาสที่ <b style="color:var(--ct)">CT</b> ชนะรอบ ·
                <b style="color:var(--t)">T</b> ${Math.round((1 - p) * 100)}%</div>
           <div class="sub">สถานะนี้เกิดขึ้นจริง ${fmt(n)} ครั้งในข้อมูล${n < 20 ? " — น้อยมาก ค่านี้ยังไม่ค่อยน่าเชื่อ" : ""}</div>
         </div>
       </div>`;

  // --- ตาราง 5x5 ของสถานะเดียวกัน (ปัก/เวลา เดิม) ---
  const head = ["CT \\ T", "1", "2", "3", "4", "5"];
  const body = [1, 2, 3, 4, 5].map((ct) =>
    [`<b>CT ${ct}</b>`].concat([1, 2, 3, 4, 5].map((t) => {
      const v = rwData.table[`${ct}v${t}|${plant}|${time}`];
      if (v === undefined) return { n: "—" };
      // ระบายสีพื้นช่อง: ยิ่ง CT ได้เปรียบยิ่งน้ำเงินเข้ม, ยิ่ง T ได้เปรียบยิ่งส้มเข้ม
      const rgb = v >= .5 ? "77,139,255" : "255,122,24";
      const strength = Math.abs(v - .5) * 2;         // Math.abs = ค่าสัมบูรณ์ (ตัดเครื่องหมายลบ) -> 0 ถึง 1
      return { n: `<span style="display:block; padding:4px 6px; border-radius:5px;
                    background:rgba(${rgb},${(strength * .55).toFixed(2)})">${Math.round(v * 100)}%</span>` };
    })));
  $("rwTable").innerHTML = tableHTML(head, body);
}


// --------------------------------------------------------------------------
// ส่วนที่ 8 — ตารางบอกว่าแต่ละหน้าใช้ฟังก์ชันโหลดตัวไหน
// --------------------------------------------------------------------------

const LOADERS = {
  overview: loadOverview,
  matches:  loadMatches,
  players:  loadPlayers,
  map:      loadMap,
  tactical: loadTactical,
  ml:       loadMl,
};


// --------------------------------------------------------------------------
// ส่วนที่ 9 — ผูกปุ่ม/ช่องเลือกต่าง ๆ เข้ากับการทำงาน
// --------------------------------------------------------------------------

$("mapFilter").addEventListener("change", loadOverview);
// change = เหตุการณ์ "ผู้ใช้เปลี่ยนค่าในช่องเลือก" -> โหลดภาพรวมใหม่ตามแมพที่เลือก

$("minMatches").addEventListener("change", loadPlayers);

$("heatMap").addEventListener("change", loadMap);

$("tacMap").addEventListener("change", loadTactical);

$("tacSide").addEventListener("click", (e) => {          // ปุ่มสลับ "มุมฝั่ง T / มุมฝั่ง CT"
  const btn = e.target.closest("button");                // closest("button") = ไล่หาปุ่มที่ใกล้ที่สุดจากจุดที่คลิก
  if (!btn) return;                                      // คลิกโดนที่ว่าง -> ไม่ต้องทำอะไร
  $("tacSide").querySelectorAll("button").forEach((b) => b.classList.remove("on"));
  btn.classList.add("on");
  tacSide = btn.dataset.side;                            // จำฝั่งที่เลือกไว้
  loadTactical();
});

// ช่องเลือก 4 ตัวของโมเดล — เปลี่ยนอันไหนก็วาดผลใหม่ทันที (ไม่ต้องขอข้อมูลจากเซิร์ฟเวอร์ซ้ำ
// เพราะตารางคำตอบทั้งหมดถูกโหลดมาเก็บไว้ในตัวแปร rwData ตั้งแต่ตอนเปิดหน้าแล้ว)
["rwCt", "rwT", "rwPlant", "rwTime"].forEach((id) =>
  $(id).addEventListener("change", drawRoundWin));

$("sideSeg").addEventListener("click", (e) => {          // e = ข้อมูลของเหตุการณ์ (คลิกโดนอะไร)
  const btn = e.target.closest("button");                // closest("button") = ไล่หาปุ่มที่ใกล้ที่สุดจากจุดที่คลิก
  if (!btn) return;                                      // คลิกโดนที่ว่าง -> ไม่ต้องทำอะไร
  $("sideSeg").querySelectorAll("button").forEach((b) => b.classList.remove("on"));  // ถอดไฮไลต์ปุ่มเดิม
  btn.classList.add("on");                               // ไฮไลต์ปุ่มที่เพิ่งกด
  heatSide = btn.dataset.side;                           // จำค่าที่เลือก ("", "ct", "t")
  loadMap();                                             // โหลดแผนที่ใหม่
});

$("btnLogout").addEventListener("click", async () => {
  await fetch("/auth/logout", { method: "POST" });       // POST = "ส่งคำสั่งไปให้" (GET = "ขอของมา")
  location.href = "/";                                   // กลับไปหน้าล็อกอิน
});


// --------------------------------------------------------------------------
// ส่วนที่ 10 — เริ่มทำงาน
// --------------------------------------------------------------------------

async function boot() {
  // --- 1) เช็กว่าล็อกอินอยู่ไหม ---
  const me = await fetch("/api/me");
  if (!me.ok) { location.href = "/"; return; }           // ไม่ผ่าน -> ไล่กลับหน้าล็อกอิน
  const { user } = await me.json();                      // { user } = ดึงเฉพาะช่อง user ออกมา (เรียกว่า destructuring)

  $("userName").textContent = user.name;                 // เอาชื่อไปโชว์บนแถบบน
  if (user.avatar) $("avatar").src = user.avatar;        // .src = ที่อยู่รูป (ใส่ก็ต่อเมื่อมีรูปจริง)

  // --- 2) เติมรายชื่อแมพลงช่องเลือกทั้งสองที่ ---
  const ms = await api("/api/matches");
  const maps = [...new Set(ms.map((m) => m.map_name))].sort();
  // new Set(...) = กล่องที่เก็บของซ้ำไม่ได้ -> ใช้กรองชื่อแมพที่ซ้ำกันออก
  // [...ของ] = แผ่กลับมาเป็น array ธรรมดา, .sort() = เรียงตามตัวอักษร

  $("mapFilter").innerHTML = '<option value="">ทุกแมพ</option>' +
    maps.map((m) => `<option value="${esc(m)}">${esc(m)}</option>`).join("");

  const mapOptions = maps.map((m) => `<option value="${esc(m)}">${esc(m)}</option>`).join("");
  $("heatMap").innerHTML = mapOptions;    // ช่องเลือกแมพของหน้า "แผนที่"
  $("tacMap").innerHTML  = mapOptions;    // ช่องเลือกแมพของหน้า "แท็คติก" (ใช้รายการเดียวกัน)

  // --- 3) เปิดหน้าตามที่อยู่ใน URL (ถ้าไม่มีก็หน้าแรก) ---
  showTab(location.hash.slice(1) || "overview");
}

boot().catch((e) => {                                    // .catch = "ถ้าเกิด error ระหว่างทาง ให้ทำสิ่งนี้"
  document.querySelector(".wrap").innerHTML =
    `<div class="err">โหลดข้อมูลไม่สำเร็จ: ${esc(e.message)}<br>
     ตรวจว่าฐานข้อมูลเปิดอยู่ไหม — <code>docker compose up -d db</code></div>`;
});
