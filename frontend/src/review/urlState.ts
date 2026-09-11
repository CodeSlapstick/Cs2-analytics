import { useCallback } from "react";
import { useSearchParams } from "react-router-dom";

/**
 * state ของหน้าที่เก็บบน query string — refresh แล้วอยู่ที่เดิม และแชร์ลิงก์ให้คนอื่นเห็นแบบเดียวกันได้
 * แมตช์กับรอบอยู่ใน path (/matches/{demo_file}/rounds/{n}) ส่วนที่เหลืออยู่ที่นี่
 */
export interface ViewState {
  sidebar: boolean; // sb=0      ย่อ sidebar
  board: boolean; // board=1   เปิดแผงสกอร์บอร์ดทั้งแมตช์
  cells: boolean; // cells=1   ซ้อนประเภทช่องจาก grid_ml1
  hotspots: boolean; // hs=1      ซ้อนวง hotspot
  player: string | null; // p=<steamid> ไฮไลต์ผู้เล่น
  death: number | null; // d=<ลำดับ>  การตายที่เลือก
}

export function useViewState() {
  const [params, setParams] = useSearchParams();
  const d = Number(params.get("d"));
  const state: ViewState = {
    sidebar: params.get("sb") !== "0",
    board: params.get("board") === "1",
    cells: params.get("cells") === "1",
    hotspots: params.get("hs") === "1",
    player: params.get("p"),
    death: params.get("d") && Number.isInteger(d) && d > 0 ? d : null,
  };

  // toggle บนหน้าเดียวกันใช้ replace — ปุ่ม Back ของเบราว์เซอร์จะย้อนไปรอบ/แมตช์ก่อน ไม่ใช่ย้อนทีละคลิก
  const update = useCallback(
    (patch: Partial<ViewState>) => {
      setParams(
        (prev) => {
          const next = new URLSearchParams(prev);
          const put = (key: string, value: string | null) => (value === null ? next.delete(key) : next.set(key, value));
          if ("sidebar" in patch) put("sb", patch.sidebar ? null : "0");
          if ("board" in patch) put("board", patch.board ? "1" : null);
          if ("cells" in patch) put("cells", patch.cells ? "1" : null);
          if ("hotspots" in patch) put("hs", patch.hotspots ? "1" : null);
          if ("player" in patch) put("p", patch.player ?? null);
          if ("death" in patch) put("d", patch.death == null ? null : String(patch.death));
          return next;
        },
        { replace: true },
      );
    },
    [setParams],
  );

  return [state, update, params] as const;
}

/**
 * URL ของรอบหนึ่ง — ชื่อไฟล์เดโมถูก encode (มีจุดและขีด และอาจมีวงเล็บ)
 * drop = query ที่ไม่ควรติดไปด้วย เช่น เปลี่ยนรอบทิ้ง d, เปลี่ยนแมตช์ทิ้ง d กับ p (คนละชุดผู้เล่น)
 */
export function roundUrl(demo: string, round: number, params?: URLSearchParams, drop: string[] = []): string {
  const q = new URLSearchParams(params);
  drop.forEach((k) => q.delete(k));
  const s = q.toString();
  return `/matches/${encodeURIComponent(demo)}/rounds/${round}${s ? `?${s}` : ""}`;
}
