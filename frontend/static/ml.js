let rwData = null;    // เก็บตารางโมเดลไว้ จะได้ไม่ต้องขอใหม่ทุกครั้งที่เปลี่ยนช่องเลือก

async function load() {
  await loadRoundWin();
  await loadGrid();
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

start(load);
