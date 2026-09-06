/** โหลดข้อมูลแล้ววาดทั้งหน้า — ถูกเรียกโดย start() ที่บรรทัดล่างสุด */
async function load() {
  await fillMapSelect("mapFilter", true);         // เติมรายชื่อแมพ (true = มีตัวเลือก "ทุกแมพ" ด้วย)
  $("mapFilter").addEventListener("change", draw); // เปลี่ยนแมพเมื่อไร วาดใหม่เมื่อนั้น
  await draw();
}

/** วาดตัวเลขและกราฟทั้งหมด ตามแมพที่เลือกอยู่ */
async function draw() {
  const map = $("mapFilter").value;               // ค่าที่เลือกในช่องกรองแมพ ("" = ทุกแมพ)
  const s = await api("/api/stats" + (map ? "?map=" + map : ""));

  // --- การ์ดตัวเลขสรุป 5 ใบ ---
  drawKpis("kpis", [
    { k: "แมตช์",      v: fmt(s.matches),                      s: `${fmt(s.rounds)} รอบ` },
    { k: "คิลทั้งหมด",  v: fmt(s.total_kills),                  s: `เฉลี่ยรอบที่ ${s.avg_round}` },
    { k: "ยิงหัว",      v: `${s.headshot_rate}<small>%</small>`, s: `${fmt(s.headshots)} ครั้ง` },
    { k: "CT ฆ่า",     v: fmt(s.ct_kills),                      s: pct(s.ct_kills, s.total_kills) },
    { k: "T ฆ่า",      v: fmt(s.t_kills),                       s: pct(s.t_kills, s.total_kills) },
  ]);

  // --- กราฟแท่ง 2 อัน ---
  drawBars("wpBars", s.top_weapons);              // อาวุธที่ใช้ฆ่ามากสุด
  drawBars("plBars", s.top_places);               // จุดที่คนตายบ่อยสุด

  // --- ตารางแมตช์ล่าสุด 5 นัด ---
  const ms = await api("/api/matches");
  const last5 = ms.slice(-5).reverse();           // slice(-5) = เอา 5 ตัวท้าย, reverse() = กลับลำดับให้ใหม่สุดอยู่บน

  $("recent").innerHTML = tableHTML(
    ["แมพ", "ทีม", "รอบ", "CT", "T", "คิล"],       // ชื่อหัวคอลัมน์
    last5.map((m) => [
      esc(m.map_name),
      esc(m.team_a || "-") + " vs " + esc(m.team_b || "-"),   // || "-" = ไม่มีชื่อทีมให้ใส่ขีดแทน
      { n: m.rounds }, { n: m.ct_rounds }, { n: m.t_rounds }, { n: fmt(m.kills) },
      // {n: ...} = บอกว่าช่องนี้เป็นตัวเลข ให้ชิดขวา
    ]));
}

start(load);   // เช็กล็อกอิน -> วาดเมนู -> เรียก load() (ฟังก์ชัน start อยู่ใน common.js)