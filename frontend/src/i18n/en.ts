// รวมคำแปลภาษาอังกฤษทุกส่วนของแอป — แยกไฟล์ตามกลุ่มหน้า จะได้แก้พร้อมกันได้โดยไม่ชนกัน
import { EN_ANALYSIS } from "./en-analysis";
import { EN_CHARTS } from "./en-charts";
import { EN_CORE } from "./en-core";
import { EN_MATCH } from "./en-match";
import { EN_OPENING } from "./en-opening";
import { EN_COACH } from "./en-coach";

export const EN: Record<string, string> = { ...EN_CORE, ...EN_MATCH, ...EN_ANALYSIS, ...EN_CHARTS, ...EN_OPENING, ...EN_COACH };
