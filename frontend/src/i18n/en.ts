// รวมคำแปลภาษาอังกฤษทุกส่วนของแอป — แยกไฟล์ตามกลุ่มหน้า จะได้แก้พร้อมกันได้โดยไม่ชนกัน
import { EN_ANALYSIS } from "./en-analysis";
import { EN_CHARTS } from "./en-charts";
import { EN_CORE } from "./en-core";
import { EN_MATCH } from "./en-match";

export const EN: Record<string, string> = { ...EN_CORE, ...EN_MATCH, ...EN_ANALYSIS, ...EN_CHARTS };
