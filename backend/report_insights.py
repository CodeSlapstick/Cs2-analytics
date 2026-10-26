# -*- coding: utf-8 -*-
"""Deterministic report rules. Facts and possible causes are deliberately separate."""
from backend.report_schemas import Evidence, ReportInsight


def confidence(sample_size: int) -> str:
    if sample_size >= 20:
        return "high"
    if sample_size >= 10:
        return "medium"
    return "low"


def build_insights(raw: dict) -> list[ReportInsight]:
    players, rounds, hotspots = raw["players"], raw["rounds"], raw["hotspots"]
    sample = max((p["rounds"] for p in players), default=0)
    opening_deaths = sum(p["opening_deaths"] for p in players)
    deaths = sum(p["deaths"] for p in players)
    traded = sum(p["traded_deaths"] for p in players)
    out: list[ReportInsight] = []
    if hotspots:
        hot = hotspots[0]
        evidence = [Evidence(round_num=r["round_num"], time_seconds=r["first_death_t"],
                             text=f"รอบ {r['round_num']} มีผู้เสียชีวิต {r['deaths_count']} คน",
                             viewer_url=f"/matches/{raw['match']['demo_file']}/rounds/{r['round_num']}")
                    for r in sorted(rounds, key=lambda x: -x["deaths_count"])[:3]]
        out.append(ReportInsight(key="repeated_death_area", title=f"เสียชีวิตซ้ำบริเวณ {hot['place']}",
            observation=f"พบ {hot['deaths']} deaths ในบริเวณเดียว จาก {deaths} deaths ของกลุ่มที่เลือก",
            impact="การเสียผู้เล่นซ้ำในพื้นที่เดิมลดตัวเลือกในการควบคุมพื้นที่และการ trade",
            evidence=evidence, possible_causes=["อาจเข้าเปิดมุมก่อน utility พร้อม", "ระยะห่างของผู้เล่นคู่ trade อาจมากเกินไป"],
            confidence=confidence(hot["deaths"]), recommendation="เปิดรอบอ้างอิง ตรวจ utility ตำแหน่งเพื่อน และทางถอยก่อนการปะทะ",
            next_target=f"ลด deaths บริเวณ {hot['place']} อย่างน้อย 2 ครั้ง", sample_size=hot["deaths"]))
    if opening_deaths:
        out.append(ReportInsight(key="opening_deaths", title="เสียผู้เล่นคนแรกบ่อย",
            observation=f"เสีย opening duel {opening_deaths} ครั้งใน {sample} รอบ",
            impact="ทีมต้องเริ่มแก้สถานการณ์ด้วยจำนวนผู้เล่นน้อยกว่า",
            evidence=[Evidence(round_num=r["round_num"], time_seconds=r["first_death_t"], text=f"รอบ {r['round_num']} first death ที่ {round(r['first_death_t'] or 0)} วินาที", viewer_url=f"/matches/{raw['match']['demo_file']}/rounds/{r['round_num']}") for r in rounds if r["first_death_t"] is not None][:5],
            possible_causes=["อาจเริ่มปะทะก่อนมี flash support", "ผู้ตามอาจอยู่ไกลเกินระยะ trade"],
            confidence=confidence(sample), recommendation="กำหนด first-contact protocol และผู้เล่นที่รับผิดชอบ flash/trade",
            next_target=f"opening deaths ที่ไม่มี trade ไม่เกิน {max(1, opening_deaths // 2)} ครั้ง", sample_size=sample))
    untraded = max(0, deaths - traded)
    if deaths:
        out.append(ReportInsight(key="untraded_deaths", title="การเสียชีวิตที่ยังไม่ได้ trade",
            observation=f"มี deaths ที่ไม่ถูก trade {untraded} จาก {deaths} ครั้ง",
            impact="คู่แข่งรักษาความได้เปรียบด้านจำนวนผู้เล่นไว้ได้",
            evidence=[], possible_causes=["ระยะห่างของเพื่อนอาจไม่พร้อมยิงซ้ำ", "จังหวะเข้าพื้นที่อาจไม่พร้อมกัน"],
            confidence=confidence(deaths), recommendation="ซ้อมเข้าพื้นที่เป็นคู่และกำหนดระยะยิงซ้ำไม่เกิน 2 วินาที",
            next_target=f"ลด untraded deaths เหลือไม่เกิน {max(1, int(untraded * .7))} ครั้ง", sample_size=deaths))
    return out[:5]
