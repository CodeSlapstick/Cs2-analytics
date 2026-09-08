let rwData = null;    // เก็บตารางโมเดลไว้ จะได้ไม่ต้องขอใหม่ทุกครั้งที่เปลี่ยนช่องเลือก

async function load() {
  await fillMatchSelect();        // ช่องเลือกแมตช์ + อ่าน ?match= จาก URL (หน้า /upload ลิงก์มาแบบนี้)
  await loadRoundWin();
  await loadGrid();
  await renderInsight();          // โมเดลอ่านแมตช์ที่เลือก — ส่วนที่ผู้ใช้อัปเดโมมาเพื่อดู
}


// --------------------------------------------------------------------------
// แมตช์ที่เลือก — โมเดล "อ่าน" เดโมของผู้ใช้
//
// ผู้ใช้ไม่ได้อัปเดโมมาช่วยเทรน โมเดลเทรนไว้แล้วจากคลังของทีม
// ผู้ใช้อัปมาเพื่อให้โมเดลบอกว่า "แมตช์ของฉันมีอะไรสำคัญ" — ส่วนนี้คือคำตอบนั้น
// ตัวเลขทั้งหมดมาจาก /api/matches/{id}/rounds และ /review ซึ่งเปิดตารางโมเดลอ่าน ไม่ได้เทรนอะไรใหม่
// --------------------------------------------------------------------------

/** เติมรายการแมตช์ (ใหม่สุดบน) แล้วเลือกตาม ?match= ถ้ามี ไม่มีก็เลือกแมตช์ล่าสุด */
async function fillMatchSelect() {
  const ms = await api("/api/matches");
  const list = [...ms].reverse();
  const sel = $("mlMatch");
  sel.innerHTML = list.map((m) =>
    `<option value="${m.id}">#${m.id} · ${esc(m.team_a || "?")} vs ${esc(m.team_b || "?")} · ${esc(m.map_name)}</option>`
  ).join("");

  const wanted = new URLSearchParams(location.search).get("match");   // "/ml?match=51" -> "51"
  if (wanted && list.some((m) => String(m.id) === wanted)) sel.value = wanted;

  sel.addEventListener("change", () => {
    history.replaceState(null, "", `/ml?match=${sel.value}`);         // ให้ URL แชร์ต่อได้โดยไม่รีโหลดหน้า
    renderInsight();
  });
}

async function renderInsight() {
  const id = $("mlMatch").value;
  if (!id) {
    $("insightNote").textContent = "ยังไม่มีแมตช์ในระบบ — อัปโหลดเดโมที่หน้า อัปโหลด ก่อน";
    return;
  }
  $("insightRounds").innerHTML = '<div class="empty">กำลังอ่านแมตช์…</div>';

  // ขอสองอย่างพร้อมกัน: ไทม์ไลน์รายรอบ (จังหวะตัดสิน) และรีวิวรายคน (ใครเสียโอกาสมากสุด)
  const [tl, rv] = await Promise.all([api(`/api/matches/${id}/rounds`), api(`/api/matches/${id}/review`)]);
  const m = tl.match;

  $("insightTitle").textContent = `#${m.id} · ${m.team_a || "?"} vs ${m.team_b || "?"} · ${m.map_name}`;
  $("insightNote").innerHTML = tl.model.same_map
    ? `โมเดลอ่านแมตช์นี้จากตาราง P(CT ชนะรอบ) ที่เทรนจาก ${tl.model.trained_matches} แมตช์บน ${esc(tl.model.map)}`
    : `<b>ระวัง:</b> โมเดลเทรนจาก ${esc(tl.model.map)} แต่แมตช์นี้เป็น ${esc(m.map_name)} — ตัวเลขดูแค่คนเหลือ/ระเบิด/เวลา ไม่รู้จักแมพนี้`;

  // --- คิลที่พลิกเกมแรงที่สุดทั้งแมตช์ ---
  let best = null;
  tl.rounds.forEach((r) => {
    if (r.deciding == null) return;
    const k = r.kills[r.deciding];
    if (!best || Math.abs(k.delta) > Math.abs(best.k.delta)) best = { r, k };
  });
  const top = rv.players[0];                                            // เรียงจากคนที่การตายแพงที่สุดมาแล้ว
  const freeDeaths = rv.facts_available
    ? rv.players.reduce((s, p) => s + (p.facts ? p.facts.untraded_deaths : 0), 0) : null;

  drawKpis("insightKpis", [
    { k: "รอบทั้งหมด", v: fmt(tl.rounds.length), s: `CT ${m.ct_rounds} · T ${m.t_rounds}` },
    { k: "คิลที่พลิกเกมแรงสุด", v: best ? `${Math.round(Math.abs(best.k.delta) * 100)}<small>%</small>` : "—",
      s: best ? `รอบ ${best.r.round_num} · ${best.k.attacker || "?"} ฆ่า ${best.k.victim || "?"} (${best.k.before} → ${best.k.after})` : "" },
    { k: "เสียโอกาสมากสุด", v: top ? esc(top.name) : "—",
      s: top ? `การตาย ${top.deaths_seen} ครั้ง = ${top.cost_total.toFixed(2)} รอบ` : "" },
    { k: "ตายฟรีรวมทั้งแมตช์", v: freeDeaths == null ? "—" : fmt(freeDeaths),
      s: freeDeaths == null ? "แมตช์นี้ไม่มีข้อมูลรายรอบ" : "ตายแล้วไม่มีใครเทรดคืนใน 5 วิ" },
  ]);

  $("insightLinks").innerHTML = `
    <a class="btn-mini" href="/rounds/${m.id}">ไทม์ไลน์รายรอบเต็ม →</a>
    <a class="btn-mini" href="/review/${m.id}">รีวิวจุดพลาดรายคน →</a>`;

  // --- ตารางย่อ: รอบ | ใครชนะ | จังหวะตัดสิน | Δ ---
  $("insightRounds").innerHTML = tableHTML(
    ["รอบ", "ผล", "จังหวะตัดสิน", "สถานะ", "วินาที", "Δ P(CT)"],
    tl.rounds.map((r) => {
      const k = r.deciding != null ? r.kills[r.deciding] : null;
      const win = r.winner_side ? `<span class="tag ${r.winner_side}">${r.winner_side.toUpperCase()}</span>` : "—";
      if (!k) return [String(r.round_num), win, '<span class="sub">ไม่มีคิลที่วัดได้</span>', "—", "—", { n: "—" }];
      const d = k.delta, side = d >= 0 ? "ct" : "t";
      return [
        String(r.round_num), win,
        `${esc(k.attacker || "(ไม่มีคนยิง)")} ฆ่า ${esc(k.victim || "?")}`,
        `${esc(k.before)} → ${esc(k.after)}${k.planted ? ' <span class="tag weak">C4</span>' : ""}`,
        String(k.sec ?? "—"),
        { n: `<span class="delta ${side}">${d >= 0 ? "+" : ""}${Math.round(d * 100)}%</span>` },
      ];
    }));
}

// --------------------------------------------------------------------------
// โมเดลที่ 1 — โอกาสชนะรอบ จากสถานะกลางรอบ
// --------------------------------------------------------------------------

async function loadRoundWin() {
  rwData = await api("/api/ml/round-win");
  const M = rwData.metrics;

  drawKpis("rwKpis", [
    { k: "AUC",            v: M.auc.toFixed(3),                          s: "1.00 = ทายถูกหมด, 0.50 = เดาสุ่ม" },
    { k: "ดีกว่าเดาสุ่ม",   v: `${M.gain_pct.toFixed(1)}<small>%</small>`, s: `Brier ${M.brier.toFixed(3)} จาก ${M.brier_base.toFixed(3)}` },
    { k: "ข้อมูลที่ใช้เทรน", v: fmt(M.rounds),                             s: `${fmt(M.rows)} จุดตัดสินใจ · ${M.matches} แมตช์` },
    { k: "CT ชนะโดยรวม",   v: pct(M.ct_win_overall * 100, 100),          s: "ค่าตั้งต้นก่อนดูอะไรเลย" },
  ]);

  $("rwTrained").innerHTML = trainedLine(rwData);

  // เติมตัวเลือก 1-5 คน ให้ช่อง "CT เหลือ" กับ "T เหลือ"
  const opts = (label) => [1, 2, 3, 4, 5].map((n) => `<option value="${n}">${label} ${n} คน</option>`).join("");
  $("rwCt").innerHTML = opts("CT เหลือ");
  $("rwT").innerHTML = opts("T เหลือ");
  $("rwCt").value = "5";                        
  $("rwT").value = "5";

  // ช่วงเวลามาจากไฟล์โมเดล ไม่ได้พิมพ์ทิ้งไว้เอง — โมเดลเปลี่ยนเมื่อไรหน้าเว็บเปลี่ยนตาม
  $("rwTime").innerHTML = rwData.time_names.map((t) => `<option value="${t}">วินาทีที่ ${t}</option>`).join("");
  $("rwTime").value = rwData.time_names[1] || rwData.time_names[0];

  // เปลี่ยนช่องไหนก็วาดใหม่ทันที ไม่ต้องขอข้อมูลจากเซิร์ฟเวอร์ซ้ำ
  // เพราะตารางคำตอบทั้งหมดอยู่ในตัวแปร rwData แล้ว
  ["rwCt", "rwT", "rwPlant", "rwTime"].forEach((id) =>
    $(id).addEventListener("change", drawRoundWin));

  drawRoundWin();
}

/** วาดผลของโมเดล ตามที่เลือกในช่องทั้ง 4 */
function drawRoundWin() {
  const plant = $("rwPlant").value || "0";                  // "0" = ยังไม่ปัก, "1" = ปักแล้ว
  const time = $("rwTime").value || rwData.time_names[0];
  // || ... = ค่าสำรอง เผื่อช่องเลือกยังว่าง ถ้าไม่ใส่ คีย์จะประกอบไม่ครบแล้วหาในตารางไม่เจอ

  // --- ตัวเลขใหญ่ของสถานะที่เลือกอยู่ ---
  const key = `${$("rwCt").value}v${$("rwT").value}|${plant}|${time}`;
  // คีย์หน้าตาแบบ "3v2|0|20-40s" — ต้องประกอบให้ตรงกับที่ pipeline/round_win.py เขียนไว้เป๊ะ ๆ
  const p = rwData.table[key];
  const n = rwData.support[key] || 0;      // support = จำนวนครั้งที่สถานะนี้เกิดขึ้นจริงในข้อมูล

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

  // --- ตาราง 5x5 ของสถานะเดียวกัน (ปักระเบิด/ช่วงเวลา เดิม) ---
  const head = ["CT \\ T", "1", "2", "3", "4", "5"];
  const body = [1, 2, 3, 4, 5].map((ct) =>
    [`<b>CT ${ct}</b>`].concat([1, 2, 3, 4, 5].map((t) => {
      const v = rwData.table[`${ct}v${t}|${plant}|${time}`];
      if (v === undefined) return { n: "—" };
      // ระบายสีพื้นช่อง: ยิ่ง CT ได้เปรียบยิ่งน้ำเงินเข้ม, ยิ่ง T ได้เปรียบยิ่งส้มเข้ม
      const rgb = v >= .5 ? "77,139,255" : "255,122,24";
      const strength = Math.abs(v - .5) * 2;      // Math.abs = ค่าสัมบูรณ์ (ตัดเครื่องหมายลบ) -> ได้ 0 ถึง 1
      return { n: `<span style="display:block; padding:4px 6px; border-radius:5px;
                    background:rgba(${rgb},${(strength * .55).toFixed(2)})">${Math.round(v * 100)}%</span>` };
    })));
  $("rwTable").innerHTML = tableHTML(head, body);
}

// --------------------------------------------------------------------------
// โมเดลที่ 2 — กริด: ช่องไหนบนแมพที่ฝั่งไหนได้เปรียบ
// --------------------------------------------------------------------------

async function loadGrid() {
  const g = await api("/api/ml/grid");
  const G = g.metrics;

  drawKpis("gridKpis", [
    { k: "AUC",          v: G.auc.toFixed(3),                          s: `แบ่งแมพ ${g.grid_n}x${g.grid_n} ช่อง` },
    { k: "ดีกว่าเดาสุ่ม", v: `${G.gain_pct.toFixed(1)}<small>%</small>`, s: `Brier ${G.brier_grid.toFixed(3)} จาก ${G.brier_base.toFixed(3)}` },
    { k: "การดวลที่ใช้",  v: fmt(G.duels),                              s: `${G.matches} แมตช์` },
    { k: "แมพ",          v: esc(g.map),                                s: "ตั้งค่าที่ pipeline/grid_ml.py" },
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

// --------------------------------------------------------------------------
// เทรนใหม่จากฐานข้อมูล
// --------------------------------------------------------------------------

/** บรรทัดบอกว่าโมเดลนี้เทรนเมื่อไร จากแหล่งไหน กี่แมตช์ — ไว้ให้รู้ว่าอัปเดโมไปแล้วผลเปลี่ยนหรือยัง */
function trainedLine(d) {
  const when = d.trained_at ? new Date(d.trained_at).toLocaleString("th-TH") : "ไม่ทราบเวลา";
  const src = (d.source || "csv").split(" ")[0];          // "PostgreSQL postgresql://..." -> "PostgreSQL"
  return `เทรนเมื่อ ${esc(when)} · จาก ${esc(src)} · ${fmt(d.metrics.matches)} แมตช์ · แมพ ${esc(d.map)}`;
}

// การเทรนใหม่เป็นงานของทีม ไม่ใช่ของผู้ใช้ — จึงไม่มีปุ่มบนหน้านี้
// ทีมรันได้จาก CLI (python pipeline/round_win.py --source=db) หรือ POST /api/ml/retrain ผ่าน /docs

start(load);
