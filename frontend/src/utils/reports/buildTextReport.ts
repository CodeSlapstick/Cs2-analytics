import type { ReportData } from "../../types/report";

const line = "=".repeat(68);
const divider = "-".repeat(68);

export function buildTextReport(report: ReportData) {
  const h = report.header;
  const out = [line, "CS2 PLAIN TEXT PERFORMANCE REPORT", line,
    `ประเภท: ${h.report_type === "coach" ? "Coach" : "Player"}`,
    `ผู้เล่น: ${h.player_name ?? "—"}`,
    `แมตช์: ${h.team_a ?? "ทีม A"} vs ${h.team_b ?? "ทีม B"}`,
    `แผนที่: ${h.map_name ?? "—"}`,
    `ผลตามฝั่ง: CT ${h.score_ct} — ${h.score_t} T`,
    `จำนวนรอบ: ${h.rounds}`, `วันที่สร้าง: ${h.generated_at}`, `Dataset version: ${h.dataset_version}`];
  add(out, "1. สรุปสำหรับตัดสินใจ", report.executive_summary);
  add(out, "2. ประเด็นสำคัญ", report.insights.map((i) => `${i.title}\nสิ่งที่เกิดขึ้น: ${i.observation}\nผลกระทบ: ${i.impact}\nหลักฐาน: ${i.evidence.map((e) => e.text).join("; ") || "ไม่มีรอบอ้างอิง"}\nสาเหตุที่เป็นไปได้: ${i.possible_causes.join("; ") || "ยังไม่มีข้อมูลยืนยัน"}\nความเชื่อมั่น: ${i.confidence} (n=${i.sample_size})\nวิธีแก้: ${i.recommendation}\nเป้าหมาย: ${i.next_target}`));
  add(out, "3. ตัวเลขสำคัญ", report.kpis.map((k) => `${k.label}: ${k.value ?? "ไม่มีข้อมูล"} | เทียบ: ${k.comparison ?? "ไม่มี"} | n=${k.sample_size} | ${k.explanation}`));
  add(out, "4. รอบที่ควรเปิดดู", report.turning_points.map((r) => `รอบ ${r.round_num} | ${r.buy_type ?? "—"} | ${r.event} | ${r.improvement} | ${r.viewer_url}`));
  add(out, "5. วิเคราะห์รายฝั่ง", report.side_analysis.map((s) => `${s.side.toUpperCase()}: ชนะ ${s.wins}/${s.rounds} | ปัญหา: ${s.problems.join("; ")} | แก้: ${s.actions.join("; ")}`));
  add(out, "6. Economy", report.economy.map((e) => `รอบ ${e.round_num} | ${e.buy_type} | ${e.result} | ${e.recommendation}`));
  if (h.report_type === "player") add(out, "7. รายงานผู้เล่น", report.players.map((p) => `${p.name}: ${p.kills}/${p.deaths}/${p.assists}, ADR ${p.adr}, KAST ${p.kast}%, Rating ${p.rating}`));
  add(out, "8. แผนฝึก", report.training_plan.map((a) => `${a.title} | ปัญหา: ${a.problem} | หลักฐาน: ${a.evidence} | วิธีฝึก: ${a.method} | KPI: ${a.target}`));
  add(out, "9. เป้าหมายนัดถัดไป", report.next_match_goals);
  add(out, "10. หมายเหตุข้อมูล", [`เดโม ${report.data_quality.demos} ไฟล์, ${report.data_quality.rounds} รอบ`, `ข้อมูลที่ขาด: ${report.data_quality.missing.join("; ") || "ไม่มี"}`, `ค่าประมาณ: ${report.data_quality.estimated.join("; ") || "ไม่มี"}`, ...report.data_quality.warnings]);
  return `${out.join("\n").trim()}\n`;
}

function add(out: string[], title: string, rows: string[]) {
  out.push("", divider, title, divider, ...(rows.length ? rows.map((row, index) => `${index + 1}. ${row}`) : ["ไม่มีข้อมูล"]));
}
