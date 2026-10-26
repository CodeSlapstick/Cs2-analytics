import { DownloadIcon } from "../../icons/download-icon";

type Props = { disabled: boolean; working: "pdf" | "txt" | "copy" | null; onPdf(): void; onText(): void; onCopy(): void; onPrint(): void };

export function ExportReportButtons({ disabled, working, onPdf, onText, onCopy, onPrint }: Props) {
  return <div className="pr-actions">
    <button type="button" disabled={disabled} onClick={onPdf}><DownloadIcon />{working === "pdf" ? "กำลังสร้าง PDF…" : "Export PDF"}</button>
    <button type="button" disabled={disabled} onClick={onText}>{working === "txt" ? "กำลังสร้าง TXT…" : "Download TXT"}</button>
    <button type="button" disabled={disabled} onClick={onCopy}>{working === "copy" ? "กำลังคัดลอก…" : "Copy Plain Text"}</button>
    <button type="button" disabled={disabled} onClick={onPrint}>Print</button>
  </div>;
}
