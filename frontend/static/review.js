// --------------------------------------------------------------------------
// หน้ารีวิวจุดพลาดรายคน — /review/{match_id}
//
// ตอบสามคำถามที่ข้อมูลตอบได้จริง (ดู docstring ของ /api/matches/{id}/review)
//   A  การตายไหนแพงที่สุด      โอกาสชนะรอบของทีมหายไปกี่ % ตอนคุณตาย
//   C  ตายฟรีกี่ครั้ง          ตายแล้วเพื่อนไม่เทรดคืนใน 5 วินาที
//   B  ดวลในจุดเสียเปรียบ      ตายในช่องที่โมเดลกริดบอกว่าฝั่งเราชนะน้อยกว่า 40% (เฉพาะแมพที่มีกริด)
//
// สิ่งที่หน้านี้ตั้งใจ "ไม่" บอก: ทำไมถึงแพ้ดวล (เล็ง/ปืน) — โมเดลไม่เคยดูสองอย่างนั้น
// --------------------------------------------------------------------------

let data = null;

const sideTag = (side, text) =>
  side === "ct" || side === "t" ? `<span class="tag ${side}">${esc(text)}</span>` : esc(text || "—");

/** ต้นทุนเป็น % ของโอกาสชนะรอบ — สีส้มยิ่งเข้มยิ่งแพง */
const costTag = (c) => c == null ? '<span class="sub">—</span>'
  : `<span class="delta t">−${Math.round(c * 100)}%</span>`;

const rounds1 = (x) => (x == null ? "—" : x.toFixed(2));


async function load() {
  const id = location.pathname.split("/").filter(Boolean).pop();
  data = await api(`/api/matches/${id}/review`);
  const m = data.match;

  $("head").innerHTML = `
    <div>
      <div class="eyebrow">${esc(m.map_name)} · แมตช์ #${m.id}</div>
      <h1>${esc(m.team_a || "?")} vs ${esc(m.team_b || "?")}</h1>
      <div class="sub" style="margin-top:6px">
        <span class="tag ct">CT ${m.ct_rounds}</span> <span class="tag t">T ${m.t_rounds}</span>
        · ${m.rounds} รอบ · ${fmt(m.kills)} คิล
        · <a href="/rounds/${m.id}">ไทม์ไลน์รายรอบ</a> · <a href="/matches">← กลับหน้าแมตช์</a>
      </div>
    </div>`;

  // บอกให้ชัดว่าตัวเลขแต่ละส่วนมาจากอะไร และส่วนไหนใช้กับแมตช์นี้ไม่ได้
  const notes = [];
  notes.push(data.model.same_map
    ? `A ใช้ตาราง P(CT ชนะรอบ) ที่เทรนจาก ${data.model.trained_matches} แมตช์บน ${esc(data.model.map)}`
    : `<b>ระวัง:</b> ตาราง P(CT ชนะรอบ) เทรนจาก ${esc(data.model.map)} แต่แมตช์นี้เป็น ${esc(m.map_name)} — A ยังใช้ได้เพราะดูแค่คนเหลือ/ระเบิด/เวลา ไม่ดูตำแหน่ง`);
  notes.push(data.grid
    ? `B ใช้โมเดลกริดของ ${esc(data.grid.map)} (${data.grid.matches} แมตช์) เกณฑ์ "เสียเปรียบ" = ฝั่งเราชนะดวลในช่องนั้นต่ำกว่า ${Math.round(data.grid.bad_cell_p * 100)}%`
    : `B ใช้ไม่ได้กับแมตช์นี้ — โมเดลกริดมีเฉพาะ Mirage`);
  notes.push(data.facts_available
    ? `C จากข้อมูลรายคนรายรอบของแมตช์นี้`
    : `C ใช้ไม่ได้ — แมตช์นี้โหลดจาก csv รุ่นเก่า ไม่มีข้อมูลรายคนรายรอบ (เดโมที่อัปผ่านหน้า /upload จะมี)`);
  $("modelNote").innerHTML = notes.join("<br>");

  // --- ตารางทุกคน เรียงจากคนที่การตายแพงที่สุด ---
  $("playerTable").innerHTML = tableHTML(
    ["นักแข่ง", "ฝั่งเริ่ม", "ตาย", "เสียโอกาสรวม (รอบ)", "ตายฟรี", "จุดเสียเปรียบ"],
    data.players.map((p) => [
      esc(p.name),
      sideTag(p.side, p.side ? p.side.toUpperCase() : "—"),
      { n: p.deaths_seen },
      { n: `<b>${rounds1(p.cost_total)}</b>` },
      { n: p.facts ? p.facts.untraded_deaths : "—" },
      { n: data.grid ? p.bad_cell_deaths.length : "—" },
    ]),
    { rowAttr: (i) => `class="click${i === 0 ? " sel" : ""}" data-i="${i}"` });
  bindRows("playerTable", (i) => showPlayer(data.players[i]));

  if (data.players.length) showPlayer(data.players[0]);
}


function showPlayer(p) {
  // ---------- A ----------
  $("aTitle").textContent = `การตายที่แพงที่สุดของ ${p.name}`;
  const avg = p.costly_deaths.length ? p.cost_total / Math.max(p.deaths_seen, 1) : 0;
  drawKpis("aKpis", [
    { k: "เสียโอกาสรวม", v: `${rounds1(p.cost_total)}<small> รอบ</small>`, s: `จากการตาย ${p.deaths_seen} ครั้ง` },
    { k: "เฉลี่ยต่อการตาย", v: `${Math.round(avg * 100)}<small>%</small>`, s: "ของโอกาสชนะรอบ" },
    { k: "แพงที่สุด", v: p.costly_deaths[0] ? `${Math.round(p.costly_deaths[0].cost * 100)}<small>%</small>` : "—",
      s: p.costly_deaths[0] ? `รอบ ${p.costly_deaths[0].round_num} · ${p.costly_deaths[0].before} → ${p.costly_deaths[0].after}` : "" },
  ]);
  $("aTable").innerHTML = p.costly_deaths.length
    ? tableHTML(
        ["รอบ", "วินาที", "สถานะ", "ที่", "ถูกฆ่าโดย", "เสียไป", "ผลรอบ"],
        p.costly_deaths.map((d) => [
          String(d.round_num), String(d.sec ?? "—"),
          `${esc(d.before)} → ${esc(d.after)}${d.planted ? ' <span class="tag weak">C4</span>' : ""}`,
          esc(d.place || "—"), esc(d.killer || "(ไม่มีคนยิง)"),
          { n: costTag(d.cost) },
          d.round_won == null ? "—" : d.round_won ? '<span class="tag ct">ชนะ</span>' : '<span class="tag t weak">แพ้</span>',
        ]))
    : '<div class="empty">ไม่มีการตายที่วัดได้</div>';

  // ---------- C ----------
  if (p.facts) {
    const f = p.facts;
    drawKpis("cKpis", [
      { k: "ตายฟรี", v: fmt(f.untraded_deaths), s: `จากการตาย ${f.deaths} ครั้ง` },
      { k: "ตายเป็นคนแรก", v: fmt(f.opening_deaths), s: `ถูกเทรดคืน ${f.opening_traded} · ฟรี ${f.opening_deaths - f.opening_traded}` },
      { k: "รอดถึงจบรอบ", v: pct(f.survived, f.rounds), s: `${f.survived} จาก ${f.rounds} รอบ` },
      { k: "KAST", v: pct(f.kast_rounds, f.rounds), s: "ฆ่า / ช่วย / รอด / ถูกเทรด" },
    ]);
    const freeOpen = f.opening_deaths - f.opening_traded;
    $("cNote").textContent = freeOpen > 0
      ? `${freeOpen} รอบที่ทีมเริ่มแบบ 4v5 เพราะคุณตายเป็นคนแรกและไม่มีใครเก็บคืน — นี่คือรูปแบบที่ควรแก้ก่อน`
      : f.untraded_deaths > 0
        ? `ตายฟรี ${f.untraded_deaths} ครั้ง แต่ไม่ใช่ตอนเปิดรอบ — ดูตำแหน่งตอนตายในตาราง A ประกอบ`
        : "ทุกครั้งที่ตาย เพื่อนเทรดคืนได้ — ยืนในระยะที่ทีมช่วยกันได้";
  } else {
    $("cKpis").innerHTML = "";
    $("cNote").textContent = "แมตช์นี้ไม่มีข้อมูลรายคนรายรอบ (โหลดจาก csv รุ่นเก่า)";
  }

  // ---------- B ----------
  if (!data.grid) {
    $("bNote").textContent = `ใช้ไม่ได้กับแมตช์นี้ — โมเดลกริดมีเฉพาะ Mirage ตอนนี้`;
    $("bTable").innerHTML = "";
    return;
  }
  $("bNote").textContent = p.bad_cell_deaths.length
    ? `${p.bad_cell_deaths.length} ครั้งที่ตายในช่องที่ฝั่ง ${p.side ? p.side.toUpperCase() : ""} ชนะดวลน้อยกว่า ${Math.round(data.grid.bad_cell_p * 100)}% ตามสถิติ ${data.grid.matches} แมตช์`
    : "ไม่มีการตายในช่องที่สถิติบอกว่าเสียเปรียบ — จุดที่เลือกสู้ไม่ใช่ปัญหา";
  $("bTable").innerHTML = p.bad_cell_deaths.length
    ? tableHTML(
        ["รอบ", "ช่อง (callout)", "ฝั่งเราชนะตรงนี้", "จากกี่ดวล", "สถานะตอนตาย", "เสียไป"],
        p.bad_cell_deaths.map((d) => [
          String(d.round_num), esc(d.cell_place || d.place || "—"),
          { n: `<span class="tag t">${Math.round(d.cell_own_p * 100)}%</span>` },
          { n: fmt(d.cell_kills) },
          `${esc(d.before)} → ${esc(d.after)}`,
          { n: costTag(d.cost) },
        ]))
    : "";
}

start(load);
