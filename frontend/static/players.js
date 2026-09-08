let playerList = [];

async function load() {
  $("minMatches").addEventListener("change", draw);   // เปลี่ยนตัวกรองเมื่อไร วาดตารางใหม่
  await draw();
}

/** วาดตารางอันดับ ตามตัวกรองที่เลือกอยู่ */
async function draw() {
  const min = $("minMatches").value || "1";      // || "1" = ถ้าช่องว่าง ให้ใช้ 1 (backend ไม่รับค่าว่าง)
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

  bindRows("playerTable", (i) => openPlayer(playerList[i].steam_id));
}

/** เปิดรายละเอียดของนักแข่งคนเดียว ลงกล่องฝั่งขวา */
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
  // ต้องสร้างกล่องเปล่า 3 กล่องนี้ลงหน้าเว็บก่อน แล้วค่อยวาดกราฟใส่
  // (ไม่งั้น drawBars หากล่องไม่เจอ เพราะมันยังไม่มีอยู่จริง)

  drawBars("pWp", d.weapons);
  drawBars("pKill", d.kill_places);
  drawBars("pDeath", d.death_places);
}

start(load);