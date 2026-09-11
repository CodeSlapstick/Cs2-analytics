// --------------------------------------------------------------------------
// หน้าอัปโหลดเดโม
//
// ส่งทีละไฟล์ ไม่ส่งพร้อมกันทั้งกอง เพราะฝั่งเซิร์ฟเวอร์ต้องแกะไฟล์ซึ่งกิน CPU เต็ม ๆ
// ยิงพร้อมกันสิบไฟล์ไม่ได้เร็วขึ้น มีแต่จะแย่ง CPU กันเองจนช้าลงทั้งกอง
// ส่งทีละไฟล์ยังทำให้ไฟล์ที่พังไม่ลากไฟล์อื่นล้มตามด้วย
// --------------------------------------------------------------------------

let queue = [];          // [{ name, size, state, pct, msg, result }]
let running = false;     // กำลังส่งอยู่ไหม — กันผู้ใช้กดซ้ำแล้วส่งซ้อนกัน
let maxMB = 600;         // เพดานขนาดไฟล์ อ่านจาก /api/config ตอนเปิดหน้า

const STATE = {          // สถานะของไฟล์หนึ่งไฟล์ในคิว
  wait:  { label: "รอคิว",         cls: "" },
  up:    { label: "กำลังอัปโหลด",  cls: "run" },
  parse: { label: "กำลังแกะไฟล์",  cls: "run" },
  done:  { label: "สำเร็จ",        cls: "ok" },
  fail:  { label: "ไม่สำเร็จ",     cls: "bad" },
};


async function load() {
  const cfg = await api("/api/config");
  maxMB = cfg.max_demo_mb || maxMB;
  $("limit").textContent = `ไฟล์ละไม่เกิน ${maxMB} MB`;

  bindDropzone();
  await drawMatches();
}


// --------------------------------------------------------------------------
// ส่วนที่ 1 — รับไฟล์เข้ามา
// --------------------------------------------------------------------------
function bindDropzone() {
  const drop = $("drop");
  const picker = $("picker");

  // คลิกหรือกด Enter/Space ที่กล่อง = เปิดหน้าต่างเลือกไฟล์
  drop.addEventListener("click", () => picker.click());
  drop.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") { e.preventDefault(); picker.click(); }
  });

  picker.addEventListener("change", () => {
    addFiles(picker.files);
    picker.value = "";     // ล้างค่า ไม่งั้นเลือกไฟล์เดิมซ้ำครั้งที่สองจะไม่เกิด event change
  });

  // ต้อง preventDefault ทั้ง dragover และ drop
  // ไม่งั้นเบราว์เซอร์จะใช้พฤติกรรมมาตรฐานคือ "เปิดไฟล์นั้นแทนหน้าเว็บ"
  drop.addEventListener("dragover", (e) => { e.preventDefault(); drop.classList.add("over"); });
  drop.addEventListener("dragleave", () => drop.classList.remove("over"));
  drop.addEventListener("drop", (e) => {
    e.preventDefault();
    drop.classList.remove("over");
    addFiles(e.dataTransfer.files);
  });
}

/** เอาไฟล์ที่ผู้ใช้เลือกมาต่อท้ายคิว แล้วเริ่มส่งถ้ายังไม่ได้เริ่ม */
function addFiles(fileList) {
  for (const f of fileList) {
    // คัดตั้งแต่ยังไม่ส่ง จะได้ไม่เสียเวลาอัปของที่เซิร์ฟเวอร์ปฏิเสธแน่ ๆ อยู่แล้ว
    if (!f.name.toLowerCase().endsWith(".dem")) {
      queue.push({ name: f.name, size: f.size, state: "fail", pct: 0, msg: "ไม่ใช่ไฟล์ .dem" });
      continue;
    }
    if (f.size > maxMB * 1024 * 1024) {
      queue.push({ name: f.name, size: f.size, state: "fail", pct: 0, msg: `ใหญ่เกิน ${maxMB} MB` });
      continue;
    }
    queue.push({ name: f.name, size: f.size, state: "wait", pct: 0, file: f });
  }
  drawQueue();
  runQueue();
}


// --------------------------------------------------------------------------
// ส่วนที่ 2 — ส่งไฟล์ทีละไฟล์
// --------------------------------------------------------------------------
async function runQueue() {
  if (running) return;                 // มีรอบส่งทำงานอยู่แล้ว ปล่อยให้มันไล่คิวต่อเอง
  running = true;

  let loaded = 0;                      // นับว่ารอบนี้โหลดเข้าฐานข้อมูลสำเร็จกี่ไฟล์
  const force = $("force").checked;

  for (const item of queue) {
    if (item.state !== "wait") continue;

    item.state = "up";
    drawQueue();

    try {
      item.result = await uploadOne(item.file, force, (pct) => {
        item.pct = pct;
        // อัปครบ 100% แล้วยังไม่ได้คำตอบ = เซิร์ฟเวอร์กำลังแกะไฟล์อยู่
        // บอกผู้ใช้ให้ตรงตามนั้น ไม่ปล่อยให้เห็น 100% ค้างแล้วนึกว่าเว็บแฮงก์
        item.state = pct >= 1 ? "parse" : "up";
        drawQueue();
      });
      item.state = "done";
      loaded++;
    } catch (e) {
      item.state = "fail";
      item.msg = e.message;
    }
    drawQueue();
  }

  running = false;
  if (loaded) await drawMatches();      // มีของใหม่เข้าฐานข้อมูล -> รีเฟรชตารางด้านล่าง
}

/**
 * ส่งไฟล์เดียวไปที่ /api/demos
 * ใช้ XMLHttpRequest ไม่ใช่ fetch เพราะ fetch ยังบอก "อัปไปกี่เปอร์เซ็นต์แล้ว" ไม่ได้
 * ซึ่งจำเป็นมากตอนอัปไฟล์หลายร้อยเมกะไบต์ ไม่งั้นผู้ใช้จะไม่รู้เลยว่ามันค้างหรือกำลังทำงาน
 */
function uploadOne(file, force, onProgress) {
  return new Promise((resolve, reject) => {
    const form = new FormData();       // FormData = ซองพัสดุแบบเดียวกับที่ฟอร์ม HTML ส่ง (multipart)
    form.append("file", file);
    form.append("force", force ? "1" : "0");

    const xhr = new XMLHttpRequest();
    xhr.open("POST", "/api/demos");

    xhr.upload.addEventListener("progress", (e) => {
      if (e.lengthComputable) onProgress(e.loaded / e.total);   // lengthComputable = รู้ขนาดรวมไหม
    });

    xhr.addEventListener("load", () => {
      if (xhr.status === 401) { location.href = "/"; return; }  // คุกกี้หมดอายุระหว่างอัป
      let body = {};
      try { body = JSON.parse(xhr.responseText); } catch { /* ตอบกลับไม่ใช่ JSON เช่นหน้า error ของ proxy */ }
      if (xhr.status >= 200 && xhr.status < 300) resolve(body);
      else reject(new Error(body.detail || `เซิร์ฟเวอร์ตอบ ${xhr.status}`));
    });

    xhr.addEventListener("error", () => reject(new Error("ส่งไฟล์ไม่ถึงเซิร์ฟเวอร์ — ตรวจว่าเซิร์ฟเวอร์ยังเปิดอยู่ไหม")));
    xhr.addEventListener("abort", () => reject(new Error("การอัปโหลดถูกยกเลิก")));

    xhr.send(form);
  });
}


// --------------------------------------------------------------------------
// ส่วนที่ 3 — วาดหน้าจอ
// --------------------------------------------------------------------------
const mb = (bytes) => (bytes / 1024 / 1024).toFixed(1) + " MB";

function drawQueue() {
  $("queueBox").classList.toggle("hidden", queue.length === 0);
  if (!queue.length) return;

  const done = queue.filter((q) => q.state === "done").length;
  const fail = queue.filter((q) => q.state === "fail").length;
  $("queueCount").textContent =
    `— สำเร็จ ${done} จาก ${queue.length}` + (fail ? ` · ไม่สำเร็จ ${fail}` : "");

  $("queue").innerHTML = queue.map((q) => {
    const st = STATE[q.state];
    const pct = Math.round((q.pct || 0) * 100);

    // แถบความคืบหน้า: ตอนอัปยาวตามเปอร์เซ็นต์จริง ตอนแกะไฟล์เต็มแถบเพราะยังบอกความคืบหน้าไม่ได้
    const bar = (q.state === "up" || q.state === "parse")
      ? `<div class="bar-bg"><div class="bar-fill" style="width:${q.state === "parse" ? 100 : pct}%"></div></div>`
      : "";

    return `
      <div class="q-row">
        <div class="q-head">
          <span class="q-name">${esc(q.name)}</span>
          <span class="tag ${st.cls}">${st.label}${q.state === "up" ? " " + pct + "%" : ""}</span>
        </div>
        <div class="q-sub">${esc(q.size ? mb(q.size) : "")}${q.result ? " · " + resultLine(q.result) : ""}${q.msg ? " · " + esc(q.msg) : ""}</div>
        ${bar}
      </div>`;
  }).join("");
}

/** บรรทัดสรุปของไฟล์ที่โหลดสำเร็จ — เอาเลขจริงจากที่เซิร์ฟเวอร์แกะได้มาโชว์ */
function resultLine(r) {
  const c = r.counts || {};
  const teams = r.team_a && r.team_b ? `${esc(r.team_a)} vs ${esc(r.team_b)} · ` : "";
  return `${teams}${esc(r.map_name)} · ${fmt(c.rounds)} รอบ · ${fmt(c.kills)} คิล · ${fmt(c.players)} คน` +
         (r.replaced ? " · เขียนทับของเดิม" : "") +
         ` · <a href="/ml?match=${r.match_id}">ดูว่า ML เห็นอะไรในแมตช์นี้ →</a>`;
}

/** ตารางแมตช์ที่อยู่ในฐานข้อมูลแล้ว — ใหม่สุดอยู่บน คลิกแถวเพื่อให้โมเดลอ่านแมตช์นั้น */
async function drawMatches() {
  const ms = await api("/api/matches");
  const rows = [...ms].reverse();      // [...ms] = ก๊อปมาก่อน เพราะ .reverse() แก้ array ตัวเดิม

  $("matches").innerHTML = tableHTML(
    ["#", "แมพ", "ทีม", "รอบ", "CT", "T", "คิล", ""],
    rows.map((m) => [
      String(m.id),
      esc(m.map_name),
      esc(m.team_a || "-") + " vs " + esc(m.team_b || "-"),
      { n: m.rounds }, { n: m.ct_rounds }, { n: m.t_rounds }, { n: fmt(m.kills) },
      { n: `<a class="btn-mini" href="/ml?match=${m.id}">ดูผล ML →</a>` },
    ]),
    { rowAttr: (i) => `class="click" data-i="${i}"` });   // ทุกแถวกดได้ + จำไว้ว่าเป็นแถวที่เท่าไร

  bindRows("matches", (i) => { location.href = `/ml?match=${rows[i].id}`; });   // bindRows อยู่ใน common.js
}

start(load);
