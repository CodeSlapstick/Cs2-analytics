let matchList = [];    // let = ตัวแปรที่เปลี่ยนค่าได้ — เก็บรายการแมตช์ไว้ใช้ตอนคลิกแถว

async function load() {
  matchList = await api("/api/matches");
  $("matchCount").textContent = `(${matchList.length} นัด)`;   // .length = จำนวนสมาชิกใน array

  // --- ตารางฝั่งซ้าย ---
  $("matchTable").innerHTML = tableHTML(
    ["#", "แมพ", "รอบ", "CT", "T", "คิล"],
    matchList.map((m) => [
      String(m.id), esc(m.map_name),
      { n: m.rounds }, { n: m.ct_rounds }, { n: m.t_rounds }, { n: fmt(m.kills) },
    ]),
    { rowAttr: (i) => `class="click" data-i="${i}"` }   // ทุกแถวกดได้ + จำไว้ว่าเป็นแถวที่เท่าไร
  );

  bindRows("matchTable", (i) => openMatch(matchList[i].id));   // bindRows อยู่ใน common.js
}

/** เปิดรายละเอียดของแมตช์หนึ่งนัด ลงกล่องฝั่งขวา */
async function openMatch(id) {
  const box = $("matchDetail");
  box.innerHTML = '<div class="empty">กำลังโหลด…</div>';      
  const d = await api("/api/matches/" + id);

  // --- ไทม์ไลน์รายรอบ: กล่องสี่เหลี่ยม 1 กล่อง = 1 รอบ ---
  const timeline = d.rounds.map((r) => `
    <div class="rnd ${["ct", "t"].includes(r.winner_side) ? r.winner_side : "na"}"
         title="รอบ ${r.round_num} · ${esc(r.end_reason || "")} · ${r.kills} คิล">
      ${r.round_num}
    </div>`).join("");
  // class="rnd ct" หรือ "rnd t" -> CSS ระบายน้ำเงิน/ส้มตามฝั่งที่ชนะ
  // includes(...) = เช็กว่าค่านี้อยู่ในรายการไหม ถ้าข้อมูลไม่บอกว่าใครชนะ ใช้ "na" (เทา)

  // --- สกอร์บอร์ด ---
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

start(load);
