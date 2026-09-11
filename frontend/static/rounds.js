// --------------------------------------------------------------------------
// หน้าไทม์ไลน์รายรอบ — /rounds/{match_id}
//
// เอา "ตารางโอกาสชนะรอบ" (output/round_win.json) มาอ่านแมตช์นี้ทีละคิล
// ทุกคิลจึงมีตัวเลขว่า ก่อนคิลนี้ CT มีโอกาสชนะรอบกี่ % แล้วหลังคิลเป็นเท่าไร
// คิลที่ขยับตัวเลขมากที่สุดในรอบ = จังหวะตัดสินรอบ
//
// ไม่มีการเทรนอะไรที่นี่ — เซิร์ฟเวอร์แค่เปิดตารางดู หน้านี้จึงใช้ได้ทันทีกับแมตช์ที่เพิ่งอัปโหลด
// --------------------------------------------------------------------------

const REASON = {                 // end_reason ในฐานข้อมูล -> ข้อความที่คนอ่านรู้เรื่อง
  t_killed:     "ฆ่า T หมด",
  ct_killed:    "ฆ่า CT หมด",
  bomb_defused: "กู้ระเบิดทัน",
  bomb_exploded:"ระเบิดทำงาน",
  time_ran_out: "หมดเวลา",
};

const sideTag = (side, text) =>
  side === "ct" || side === "t"
    ? `<span class="tag ${side}">${esc(text)}</span>`
    : esc(text);                                          // ไม่มีฝั่ง (ตายจาก C4 / ตกที่สูง) = ไม่ระบายสี

const pctTxt = (p) => (p == null ? "—" : Math.round(p * 100) + "%");

/** ป้าย Δ — บวก = CT ได้เปรียบขึ้น (น้ำเงิน), ลบ = T ได้เปรียบขึ้น (ส้ม) */
function deltaTag(d) {
  if (d == null) return '<span class="sub">—</span>';
  const side = d >= 0 ? "ct" : "t";
  return `<span class="delta ${side}">${d >= 0 ? "+" : ""}${Math.round(d * 100)}%</span>`;
}


async function load() {
  const id = location.pathname.split("/").filter(Boolean).pop();   // "/rounds/51" -> "51"
  const d = await api(`/api/matches/${id}/rounds`);
  const m = d.match;

  $("head").innerHTML = `
    <div>
      <div class="eyebrow">${esc(m.map_name)} · แมตช์ #${m.id}</div>
      <h1>${esc(m.team_a || "?")} vs ${esc(m.team_b || "?")}</h1>
      <div class="sub" style="margin-top:6px">
        <span class="tag ct">CT ${m.ct_rounds}</span> <span class="tag t">T ${m.t_rounds}</span>
        · ${d.rounds.length} รอบ · ${fmt(m.kills)} คิล
        · <a href="/review/${m.id}">รีวิวจุดพลาดรายคน →</a> · <a href="/matches">← กลับหน้าแมตช์</a>
      </div>
    </div>`;

  // โมเดลเทรนจากแมพเดียว ถ้าแมตช์นี้เป็นแมพอื่น ตัวเลขยังพอใช้เปรียบเทียบได้ แต่ต้องบอกให้รู้
  $("modelNote").innerHTML = d.model.same_map
    ? `โมเดลเทรนจาก ${d.model.trained_matches} แมตช์บน ${esc(d.model.map)} ·
       เส้น = P(CT ชนะรอบ) หลังแต่ละคิล · จุดใหญ่ = คิลที่ขยับโอกาสมากที่สุดในรอบ`
    : `<b>ระวัง:</b> โมเดลเทรนจาก ${esc(d.model.map)} แต่แมตช์นี้เป็น ${esc(m.map_name)} —
       ตัวเลขมาจากคนเหลือ / ระเบิด / เวลา เท่านั้น โมเดลไม่รู้จักแมพนี้`;

  $("rounds").innerHTML = d.rounds.length
    ? d.rounds.map((r) => roundHTML(r, d.model.p_start)).join("")
    : '<div class="empty">แมตช์นี้ไม่มีข้อมูลรอบ</div>';
}


/** กราฟเส้นเล็ก ๆ ของ P(CT ชนะ) ตลอดรอบ — จุดแรกคือ 5v5 ต้นรอบ ตามด้วยค่าหลังแต่ละคิล */
function spark(r, p0) {
  const pts = [p0, ...r.kills.map((k) => k.p_after)];
  const W = 260, H = 44, n = pts.length;
  const x = (i) => (n > 1 ? (i / (n - 1)) * (W - 8) + 4 : W / 2);
  const y = (p) => H - 4 - p * (H - 8);                 // p=1 อยู่บน, p=0 อยู่ล่าง

  let path = "";
  pts.forEach((p, i) => {
    if (p == null) return;                              // สถานะที่ตารางไม่มีค่า -> เว้นจุดนั้นไป
    path += (path ? " L" : "M") + x(i).toFixed(1) + "," + y(p).toFixed(1);
  });
  const col = r.winner_side === "ct" ? "var(--ct)" : r.winner_side === "t" ? "var(--t)" : "var(--muted)";
  const dots = r.kills.map((k, i) => k.p_after == null ? "" :
    `<circle cx="${x(i + 1).toFixed(1)}" cy="${y(k.p_after).toFixed(1)}" r="${i === r.deciding ? 4.5 : 2}" fill="${col}"/>`
  ).join("");

  return `<svg viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" role="img"
               aria-label="โอกาสชนะของ CT ตลอดรอบ ${r.round_num}">
    <line x1="4" y1="${H / 2}" x2="${W - 4}" y2="${H / 2}" stroke="currentColor" stroke-opacity=".18" stroke-dasharray="3 3"/>
    <path d="${path}" fill="none" stroke="${col}" stroke-width="2" stroke-linejoin="round"/>
    ${dots}
  </svg>`;
}


function roundHTML(r, p0) {
  const k = r.deciding != null ? r.kills[r.deciding] : null;
  const deciding = k
    ? `${sideTag(k.attacker_side, k.attacker || "(ไม่มีคนยิง)")} ฆ่า ${sideTag(k.victim_side, k.victim || "?")}
       <div class="sub">${esc(k.before)} → ${esc(k.after)} · วินาทีที่ ${k.sec}${k.planted ? " · ระเบิดลงแล้ว" : ""}</div>
       ${deltaTag(k.delta)}`
    : '<span class="sub">ไม่มีคิลที่วัดได้</span>';

  const kills = r.kills.length
    ? tableHTML(
        ["วินาที", "คนยิง", "คนตาย", "สถานะ", "P(CT) ก่อน → หลัง", "Δ"],
        r.kills.map((x) => [
          String(x.sec ?? "—"),
          sideTag(x.attacker_side, x.attacker || "(ไม่มีคนยิง)"),
          sideTag(x.victim_side, x.victim || "?"),
          `${esc(x.before)} → ${esc(x.after)}${x.planted ? ' <span class="tag weak">C4</span>' : ""}`,
          `${pctTxt(x.p_before)} → ${pctTxt(x.p_after)}`,
          { n: deltaTag(x.delta) },
        ]),
        { rowAttr: (i) => (i === r.deciding ? 'class="sel"' : "") })   // ไฮไลต์แถวจังหวะตัดสิน
    : '<div class="empty">รอบนี้ไม่มีคิล</div>';

  const winner = ["ct", "t"].includes(r.winner_side) ? r.winner_side : "na";
  return `
    <div class="rw-round">
      <div class="rnd ${winner}" title="รอบ ${r.round_num}">${r.round_num}</div>
      <div>
        ${spark(r, p0)}
        <div class="sub">
          ${esc(REASON[r.end_reason] || r.end_reason || "ไม่ทราบสาเหตุ")} · ${r.kills.length} คิล
          ${r.bomb_plant_sec != null ? `· ระเบิดลงวินาทีที่ ${r.bomb_plant_sec}` : ""}
          · จบที่ P(CT) ${pctTxt(r.p_final)}
        </div>
      </div>
      <div class="rw-dec"><div class="eyebrow">จังหวะตัดสิน</div>${deciding}</div>
      <details class="rw-kills"><summary>ดูทุกคิลในรอบ ${r.round_num}</summary>${kills}</details>
    </div>`;
}

start(load);
