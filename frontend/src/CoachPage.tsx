import { useQuery } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";
import { api, matchesQuery, type Side } from "./api";
import { useT } from "./i18n";
import "./coach.css";

const REASONS: Record<string, string> = {
  model_unavailable: "ยังไม่มีโมเดล Coach ที่เทรนแล้ว",
  unsupported_map: "โมเดล Coach รุ่นนี้รองรับ Mirage เท่านั้น",
  missing_economy: "รอบนี้ไม่มีข้อมูลอุปกรณ์ก่อนเริ่มรอบครบ 5 คน จึงยังเสนอ tactic ไม่ได้",
  training_match: "แมตช์นี้อยู่ในชุดเทรน เลือกแมตช์ที่อัปโหลดเพื่อดูคำแนะนำที่ไม่ประเมินข้อมูลเทรนซ้ำ",
  insufficient_support: "ยังไม่มี pattern ที่มีหลักฐานพอสำหรับรอบนี้",
};

export function CoachPage() {
  const { t } = useT();
  const [params, setParams] = useSearchParams();
  const matches = useQuery(matchesQuery);
  const ready = matches.data?.filter((m) => m.status === "done") ?? [];
  const match = ready.find((m) => m.demo_file === params.get("demo")) ?? ready.find((m) => m.source === "upload" && m.map_name === "de_mirage") ?? ready.find((m) => m.source === "upload") ?? ready[0];
  const side: Side = params.get("side") === "ct" ? "ct" : "t";
  const coach = useQuery({ queryKey: ["coach", match?.demo_file, side], queryFn: () => api.coach(match!.demo_file, side), enabled: !!match });
  const round = coach.data?.rounds.find((r) => String(r.round_num) === params.get("round")) ?? coach.data?.rounds[0];
  function change(key: string, value: string) {
    const next = new URLSearchParams(params); next.set(key, value);
    if (key === "demo") next.delete("round");
    setParams(next);
  }
  const validation = coach.data?.model?.validation;
  return <section className="coach-page">
    <h1>Coach <span className="small muted">{t("ทดลอง ML")}</span></h1>
    <p className="muted">{t("เลือก tactic ที่น่าลองจาก pattern ของรอบอาชีพที่ชนะในบริบทอุปกรณ์คล้ายกัน พร้อมรอบอ้างอิง")}</p>
    <div className="filters card coach-filters">
      <label>{t("แมตช์")}<select value={match?.demo_file ?? ""} onChange={(e) => change("demo", e.target.value)}>{ready.map((m) => <option key={m.id} value={m.demo_file}>{m.demo_file} · {m.map_name ?? "—"} · {m.source === "upload" ? t("ทีมเรา") : t("ทีมอาชีพ")}</option>)}</select></label>
      <label>{t("ฝั่ง")}<select value={side} onChange={(e) => change("side", e.target.value)}><option value="t">T</option><option value="ct">CT</option></select></label>
      <label>{t("รอบ")}<select value={round?.round_num ?? ""} disabled={!coach.data?.rounds.length} onChange={(e) => change("round", e.target.value)}>{coach.data?.rounds.map((r) => <option key={r.round_num} value={r.round_num}>R{r.round_num}</option>)}</select></label>
    </div>
    {match && <p className="coach-match-summary small"><span title={match.demo_file}>{match.demo_file}</span> · {match.map_name ?? "—"} · {match.source === "upload" ? t("ทีมเรา") : t("ทีมอาชีพ")}</p>}
    <p className="coach-disclosure">{t("เป็นคำแนะนำเชิงทดลองจากข้อมูลย้อนหลัง ไม่ใช่ tactic ที่ดีที่สุดหรือโอกาสชนะ โมเดลเลียนแบบ pattern ของรอบที่ชนะ ไม่ได้พิสูจน์ว่า tactic ทำให้ชนะ")}</p>
    {matches.isError || coach.isError ? <div className="card" role="alert">{t("โหลด Coach ไม่สำเร็จ")}<button type="button" className="btn-ghost" onClick={() => { void matches.refetch(); if (match) void coach.refetch(); }}>{t("ลองอีกครั้ง")}</button></div>
      : matches.isPending || (match && coach.isPending) ? <div className="card" role="status">{t("กำลังวิเคราะห์ tactic…")}</div>
      : !match ? <div className="card"><p>{t("ยังไม่มีแมตช์ที่พร้อมวิเคราะห์")}</p><Link to="/matches">{t("แมตช์")}</Link></div>
      : !coach.data?.available ? <div className="card"><h2>{t("ยังแนะนำ tactic ไม่ได้")}</h2><p>{t(REASONS[coach.data?.reason ?? "model_unavailable"])}</p></div>
      : !round ? <div className="card">{t("ไม่มีรอบที่ตรงกับตัวกรอง")}</div>
      : <>
        <div className="coach-round-heading"><h2>R{round.round_num} · {side.toUpperCase()}</h2><Link to={`/matches/${encodeURIComponent(match.demo_file)}/rounds/${round.round_num}`}>{t("ดูรอบนี้")}</Link><Link to="/opening-route">Opening Route</Link></div>
        {!round.available ? <div className="card"><p>{t(REASONS[round.reason ?? "insufficient_support"])}</p></div> : <>
          {round.experimental && <p className="coach-disclosure">{t("ผลทดสอบยังไม่ดีกว่า baseline จึงใช้สำรวจตัวเลือกเท่านั้น")}</p>}
          <div className="coach-options">{round.options.map((option, index) => <article className="card" key={option.id}>
            <h2>{index + 1}. {option.name}</h2>
            <p className="small muted">{t("{rounds} รอบที่ชนะ · {matches} แมตช์อาชีพ", { rounds: option.rounds, matches: option.matches })}</p>
            <p>{t("น้ำหนักตัวเลือกจากโมเดล")} <strong>{Math.round(option.match_share * 100)}%</strong></p>
            <p className="small muted">{t("สัดส่วนผู้เล่นที่สังเกตได้แถววินาทีที่ 15")}</p>
            <dl className="coach-profile">{(["a", "mid", "b", "other"] as const).map((area) => <div key={area}><dt>{area === "other" ? t("พื้นที่อื่น") : area.toUpperCase()}</dt><dd>{Math.round(option.profile[`${area}_15`] * 100)}%</dd></div>)}</dl>
            <h3 className="small">{t("รอบอ้างอิงที่บริบทใกล้กัน")}</h3>
            <div className="coach-evidence">{option.evidence.map((e) => <Link key={`${e.demo_file}:${e.round_num}`} title={e.demo_file} to={`/matches/${encodeURIComponent(e.demo_file)}/rounds/${e.round_num}`}>R{e.round_num} · {e.demo_file}</Link>)}</div>
          </article>)}</div>
          <p className="small muted">{t("ชื่อ tactic เป็นคำอธิบาย centroid ที่จัดกลุ่มจากตำแหน่ง 5/15/25 วินาทีและ Utility ไม่ใช่แผนที่โค้ชติด label ไว้")}</p>
        </>}
      </>}
    {coach.data?.model && <div className="card coach-model"><h2>{t("หลักฐานการเทรน")}</h2>
      <p>{t("เทรนจากแมตช์อาชีพ {n} แมตช์เท่านั้น ไม่ใช้แมตช์อัปโหลด", { n: coach.data.model.reference_matches })}</p>
      {validation && <p>{t("ทาย pattern ของรอบที่ชนะในแมตช์ทดสอบ: {accuracy}% · baseline {baseline}% · {n} รอบ", { accuracy: (validation.accuracy * 100).toFixed(1), baseline: (validation.baseline * 100).toFixed(1), n: validation.test_winning_rounds })}</p>}
      {validation && <p className="small muted">{t("ผลทดลองจากการแบ่งชุดทดสอบครั้งเดียว ยังไม่ใช่หลักฐานว่าโมเดลมีประสิทธิภาพที่เชื่อถือได้ในหลายสถานการณ์")}</p>}
      <p className="small muted">{t("แยก train/test ตามแมตช์ และ fit scaler กับ cluster เฉพาะ train ในการวัดผล Input คำแนะนำใช้เฉพาะอุปกรณ์ก่อนเริ่มรอบและสถานะ pistol ไม่ใช้ผลรอบหรือตำแหน่งอนาคต")}</p>
      <p className="small muted">{t("เวลาเปิดรอบเดิมอาจ fallback เป็น round start และข้อมูล Utility ไม่รับรองว่าครบ ใช้ผลนี้เป็นจุดเริ่มต้นสำหรับ review กับทีม")}</p>
    </div>}
  </section>;
}
