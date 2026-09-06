// ==========================================================================
// tactical.js — สมองของหน้า "แท็คติก"  (คู่กับ frontend/pages/tactical.html)
//
// แนวคิดหลัก: "การดวลแรกของรอบ" (opening duel) = คิลแรกสุดของรอบนั้น
// ใครชนะการดวลแรก มักลากยาวไปชนะทั้งรอบ เลยเป็นตัวเลขที่โค้ชดูก่อนเพื่อน
// ==========================================================================

let side = "t";     // มองจากมุมฝั่งไหน ("t" หรือ "ct")

async function load() {
  await fillMapSelect("tacMap");
  $("tacMap").addEventListener("change", draw);
  bindSeg("tacSide", (v) => { side = v; draw(); });   // ปุ่มสลับ มุมฝั่ง T / มุมฝั่ง CT
  await draw();
}

async function draw() {
  const map = $("tacMap").value;
  if (!map) return;

  const d = await api(`/api/tactical?map=${map}&side=${side}`);
  const S = d.summary;
  const sideName = side.toUpperCase();          // toUpperCase = เปลี่ยนเป็นตัวพิมพ์ใหญ่ "t" -> "T"

  // --- การ์ดตัวเลขสรุป ---
  drawKpis("tacKpis", [
    { k: "รอบทั้งหมด",     v: fmt(S.rounds),                             s: esc(map) },
    { k: `${sideName} ชนะ`, v: pct(S.wins, S.rounds),                    s: `${fmt(S.wins)} รอบ` },
    { k: "รอบที่ปักระเบิด", v: pct(S.planted, S.rounds),                  s: `${fmt(S.planted)} รอบ` },
    { k: "ปะทะแรกเฉลี่ย",  v: `${S.avg_first_contact}<small> วิ</small>`, s: "นับจากหมดเวลาซื้อของ" },
  ]);

  // --- ตารางการดวลแรก แยกตามตำแหน่งที่ยืน ---
  $("tacOpening").innerHTML = tableHTML(
    ["ตำแหน่ง", "ดวล", "ชนะดวล", "ชนะรอบ"],
    d.opening.map((o) => [
      esc(o.place),
      { n: o.duels },
      { n: badge(o.won, o.duels) },              // badge = ป้ายสี ดูง่ายกว่าตัวเลขเปล่า (อยู่ใน common.js)
      { n: badge(o.round_wins, o.duels) },
    ]));

  // --- ปะทะแรกเกิดตอนวินาทีที่เท่าไร ---
  $("tacTiming").innerHTML = barsWithRate(d.timing, "bucket", "rounds", "wins", "รอบ");

  // --- รอบจบด้วยอะไร ---
  // ไม่โชว์อัตราชนะ เพราะสาเหตุการจบบอกผู้ชนะอยู่ในตัวแล้ว (t_killed = T แพ้เสมอ จะได้ 0% ทุกที)
  drawBars("tacEndings", d.endings.map((e) => ({ name: reasonTH(e.reason), count: e.rounds })));

  // --- ปักระเบิดแล้วต่างกันแค่ไหน ---
  $("tacBomb").innerHTML = barsWithRate(d.bomb, "state", "rounds", "wins", "รอบ") +
    `<div class="sub" style="margin-top:10px">ตัวเลขในวงเล็บ = อัตราที่ฝั่ง ${sideName} ชนะรอบนั้น</div>`;
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

start(load);
