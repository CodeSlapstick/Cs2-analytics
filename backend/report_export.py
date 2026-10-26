# -*- coding: utf-8 -*-
"""Plain-text serialization from the canonical ReportResponse."""
from backend.report_schemas import ReportResponse


def build_text_report(report: ReportResponse) -> str:
    h = report.header
    line = "=" * 68
    out = [line, "CS2 PLAIN TEXT PERFORMANCE REPORT", line,
           f"ประเภท: {'Coach' if h.report_type == 'coach' else 'Player'}",
           f"ผู้เล่น: {h.player_name or '—'}", f"แมตช์: {(h.team_a or 'ทีม A')} vs {(h.team_b or 'ทีม B')}",
           f"แผนที่: {h.map_name or '—'}", f"ผลตามฝั่ง: CT {h.score_ct} — {h.score_t} T",
           f"จำนวนรอบ: {h.rounds}", f"วันที่สร้าง: {h.generated_at}", f"Dataset version: {h.dataset_version}"]
    section(out, "1. สรุปสำหรับตัดสินใจ", report.executive_summary)
    section(out, "2. ประเด็นสำคัญ", [
        f"{i.title}\nสิ่งที่เกิดขึ้น: {i.observation}\nผลกระทบ: {i.impact}\nหลักฐาน: {evidence(i)}\n"
        f"สาเหตุที่เป็นไปได้: {'; '.join(i.possible_causes) or 'ยังไม่มีข้อมูลยืนยัน'}\n"
        f"ความเชื่อมั่น: {i.confidence} ({i.sample_size} ตัวอย่าง)\nวิธีแก้: {i.recommendation}\nเป้าหมาย: {i.next_target}"
        for i in report.insights])
    section(out, "3. ตัวเลขสำคัญ", [f"{k.label}: {k.value} | เทียบ: {k.comparison or 'ไม่มี'} | n={k.sample_size} | {k.explanation}" for k in report.kpis])
    section(out, "4. รอบที่ควรเปิดดู", [f"รอบ {r.round_num} | {r.buy_type or '—'} | {r.event} | {r.improvement} | {r.viewer_url}" for r in report.turning_points])
    section(out, "5. วิเคราะห์รายฝั่ง", [f"{s.side.upper()}: ชนะ {s.wins}/{s.rounds} | ปัญหา: {'; '.join(s.problems)} | แก้: {'; '.join(s.actions)}" for s in report.side_analysis])
    section(out, "6. Economy", [f"รอบ {e.round_num} | {e.buy_type} | {e.result} | {e.recommendation}" for e in report.economy] or ["ไม่พบรอบที่เข้าเกณฑ์จากข้อมูลที่มี"])
    if h.report_type == "player":
        section(out, "7. รายงานผู้เล่น", [f"{p.name}: {p.kills}/{p.deaths}/{p.assists}, ADR {p.adr}, KAST {p.kast}%, Rating {p.rating}" for p in report.players])
    section(out, "8. แผนฝึก", [f"{a.title} | ปัญหา: {a.problem} | หลักฐาน: {a.evidence} | วิธีฝึก: {a.method} | KPI: {a.target}" for a in report.training_plan])
    section(out, "9. เป้าหมายนัดถัดไป", report.next_match_goals)
    section(out, "10. หมายเหตุข้อมูล", [f"เดโม {report.data_quality.demos} ไฟล์, {report.data_quality.rounds} รอบ",
        f"ข้อมูลที่ขาด: {'; '.join(report.data_quality.missing) or 'ไม่มี'}",
        f"ค่าประมาณ: {'; '.join(report.data_quality.estimated) or 'ไม่มี'}"] + report.data_quality.warnings)
    return "\n".join(out).rstrip() + "\n"


def section(out: list[str], title: str, rows: list[str]) -> None:
    out.extend(["", "-" * 68, title, "-" * 68])
    out.extend(f"{index}. {row}" for index, row in enumerate(rows, 1))


def evidence(insight) -> str:
    return "; ".join(e.text for e in insight.evidence) or "ไม่มีรอบอ้างอิงที่ระบุได้"
