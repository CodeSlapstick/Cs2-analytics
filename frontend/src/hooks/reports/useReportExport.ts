import { useState, type RefObject } from "react";
import { toPng } from "html-to-image";
import type { ReportData } from "../../types/report";
import { buildTextReport } from "../../utils/reports/buildTextReport";
import { downloadTextFile } from "../../utils/reports/downloadTextFile";

const safe = (value: string) => value.normalize("NFC").replace(/[^\p{L}\p{N}._-]+/gu, "-").replace(/^-+|-+$/g, "") || "match";

export function useReportExport(report: ReportData | undefined, documentRef: RefObject<HTMLDivElement>, filename?: string) {
  const [working, setWorking] = useState<"pdf" | "txt" | "copy" | null>(null);
  const [error, setError] = useState("");
  const [progress, setProgress] = useState("");
  const date = report?.header.generated_at.slice(0, 10) ?? "report";
  const subject = report?.header.report_type === "player" ? report.header.player_name ?? "player" : report?.header.team_a ?? "team";
  const base = filename ? safe(filename) : report ? `${safe(subject)}-${safe(report.header.map_name ?? "map")}-${date}-${report.header.report_type}-report` : "report";
  async function pdf() {
    if (!report || !documentRef.current || working) return;
    setWorking("pdf"); setError(""); setProgress("กำลังเตรียมฟอนต์และกราฟ");
    try {
      await document.fonts?.ready;
      const charts = [...documentRef.current.querySelectorAll<HTMLElement>("[data-report-chart]")];
      const deadline = Date.now() + 8000;
      while (charts.some((chart) => chart.dataset.ready !== "true") && Date.now() < deadline) {
        await new Promise((resolve) => window.setTimeout(resolve, 80));
      }
      if (charts.some((chart) => chart.dataset.ready !== "true")) throw new Error("Economy chart did not finish rendering");
      const { jsPDF } = await import("jspdf");
      const pages = [...documentRef.current.querySelectorAll<HTMLElement>(".pr-page")];
      if (!pages.length) throw new Error("รายงานไม่มีหน้าที่พร้อมส่งออก");
      const file = new jsPDF({ orientation: "portrait", unit: "mm", format: "a4", compress: true });
      for (let i = 0; i < pages.length; i += 1) {
        setProgress(`กำลังสร้างหน้า ${i + 1} / ${pages.length}`);
        if (i) file.addPage();
        let image: string;
        try { image = await toPng(pages[i], { backgroundColor: "#fff", cacheBust: true, pixelRatio: 1.7, width: pages[i].scrollWidth, height: pages[i].scrollHeight }); }
        catch (cause) { throw new Error(`สร้างหัวข้อ ${pages[i].dataset.reportSection ?? pages[i].querySelector("header strong")?.textContent ?? `หน้า ${i + 1}`} ไม่สำเร็จ`, { cause }); }
        file.addImage(image, "PNG", 0, 0, 210, 297, undefined, "FAST");
      }
      setProgress("กำลังบันทึกไฟล์");
      file.save(`${base}.pdf`);
    } catch (cause) { console.error(cause); setError(cause instanceof Error ? cause.message : "สร้าง PDF ไม่สำเร็จ กรุณาลองอีกครั้ง"); } finally { setWorking(null); setProgress(""); }
  }
  function text() { if (!report || working) return; setWorking("txt"); downloadTextFile(buildTextReport(report), `${base}.txt`); setWorking(null); }
  async function copy() { if (!report || working) return; setWorking("copy"); try { await navigator.clipboard.writeText(buildTextReport(report)); } catch { setError("คัดลอกไม่สำเร็จ"); } finally { setWorking(null); } }
  return { working, progress, error, pdf, text, copy, print: () => window.print() };
}
