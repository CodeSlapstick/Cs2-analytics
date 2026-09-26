// คำแปลภาษาอังกฤษ — กุญแจคือข้อความภาษาไทยในโค้ดแบบตรงตัวอักษร (ดู ../i18n.tsx)
export const EN_ANALYSIS: Record<string, string> = {
  // โหมด + ฝั่ง (AnalysisPage MODES / SIDES / SIDE_NOTE)
  "ทีมเราตายตรงไหน": "Where we die",
  "จุดที่ผู้เล่นในแมตช์ของทีมตาย ยิ่งแดงเข้มยิ่งตายบ่อย — เลือกฝั่ง รอบ หรือผู้เล่นได้จากแผงซ้าย":
    "Where players died in the team's matches. Darker red = more deaths. Pick a side, rounds or players in the left panel.",
  "เทียบกับทีมอาชีพ": "Compared with pros",
  "ตรงไหนที่ทีมเราเสียคนบ่อยกว่าทีมอาชีพ เทียบเป็นสัดส่วนของจุดตายทั้งหมด เพราะสองชุดมีจำนวนแมตช์ไม่เท่ากัน":
    "Where we lose players more often than pro teams, compared as a share of all death spots because the two sets have different numbers of matches.",
  "อ่านทางเราออกไหม": "Can they read us?",
  "ดูจากตำแหน่งผู้เล่นฝั่ง T ทีละวินาที ว่าเดาได้เร็วแค่ไหนว่าทีมจะเข้าไซต์ไหน — เดาออกเร็ว คู่แข่งที่ดูเทปก็อ่านทางออกเร็ว":
    "From T-side player positions second by second: how early can you guess which site the team will hit? If it's easy to guess early, opponents watching the demo can read you early too.",
  "ทั้งสองฝั่ง": "Both sides",
  "ตอนเป็น CT": "As CT",
  "ตอนเป็น T": "As T",
  "รวมทั้งสองฝั่ง": "both sides",
  "เฉพาะตอนเป็น CT": "as CT only",
  "เฉพาะตอนเป็น T": "as T only",

  // หัวหน้า + ตัวกรอง
  "กำลังโหลด…": "Loading…",
  "โหลดรายการแมตช์ไม่ได้: {msg}": "Couldn't load matches: {msg}",
  "เครื่องมือวิเคราะห์": "Analysis",
  "สิ่งที่ดู": "View",
  "แมพ": "Map",
  "แมตช์ของทีม": "Team matches",
  "ทุกแมตช์ที่อัปโหลด ({n})": "All uploaded matches ({n})",
  "โหลดข้อมูลไม่ได้: {msg}": "Couldn't load data: {msg}",
  "กำลังอ่านทีละรอบ…": "Reading round by round…",
  "กำลังนับจุดตาย…": "Counting death spots…",
  'ยังไม่ได้เลือกรอบเลยสักคน/รอบ — เลือกอย่างน้อยหนึ่งอย่างในแผงซ้าย หรือกด "ทั้งหมด" เพื่อดูภาพรวมอีกครั้ง':
    'No rounds selected — pick at least one in the left panel, or press "All" to see the overview again.',
  'ยังไม่ได้เลือกผู้เล่นเลยสักคน/รอบ — เลือกอย่างน้อยหนึ่งอย่างในแผงซ้าย หรือกด "ทั้งหมด" เพื่อดูภาพรวมอีกครั้ง':
    'No players selected — pick at least one in the left panel, or press "All" to see the overview again.',

  // แผงควบคุม heatmap
  "ตั้งค่าการแสดงผล heatmap": "Heatmap display settings",
  "ฝั่งของคนที่ตาย": "Side of the player who died",
  'เลือก "แมตช์ของทีม" แมตช์เดียวด้านบนก่อน ถึงจะเจาะจงรอบหรือผู้เล่นได้':
    'Pick a single match under "Team matches" above to filter by round or player.',
  "รอบ": "Round",
  "ผู้เล่น": "Players",
  "ทั้งหมด": "All",
  "ไม่เอาเลย": "None",
  "เลือกรอบ": "Select rounds",
  "เลือกผู้เล่น": "Choose players",
  "กำลังโหลดรายชื่อ…": "Loading roster…",
  "ปรับการแสดงผล": "Display settings",
  "รัศมี": "Radius",
  "รัศมีของจุดความร้อน": "Heat spot radius",
  "เบลอ": "Blur",
  "ความเบลอเพิ่มเติม": "Extra blur",
  "ความทึบ": "Opacity",
  "ความทึบของชั้นสี": "Color layer opacity",

  // อ่านทางเราออกไหม
  "ยังอ่านแมตช์นี้ไม่ได้": "Can't read this match yet",
  "ยังไม่มีโมเดลทายไซต์ของแมพ {map}": "No site model for {map} yet",
  "แมตช์นี้ไม่มีรอบที่ T วางบอมบ์ได้ จึงไม่มีเฉลยให้วัด":
    "This match has no rounds where T planted the bomb, so there is no answer to check against.",
  "ทีมเรา ถูกอ่านออกเฉลี่ยวินาทีที่": "Our team: read on average at second",
  "อ่านออก {read} จาก {rounds} รอบที่วางบอมบ์ · มัธยฐานวินาทีที่ {median}":
    "Read in {read} of {rounds} planted rounds · median second {median}",
  "ทีมอาชีพ ถูกอ่านออกเฉลี่ยวินาทีที่": "Pro teams: read on average at second",
  "จาก {rounds} รอบ · มัธยฐานวินาทีที่ {median}": "From {rounds} rounds · median second {median}",
  "ทีมนี้ถูกอ่านออก{gap} — ยิ่งเร็ว ฝ่ายรับยิ่งมีเวลาหมุนไปตั้งรับทัน":
    "This team gets read{gap}. The earlier the read, the more time defenders have to rotate.",
  "เร็วกว่าทีมอาชีพ {s} วินาที": "{s} s earlier than pro teams",
  "ทีมนี้ถูกอ่านออก{gap} — ปกปิดทิศทางได้ดีกว่าค่าเฉลี่ยของชุดเทียบ":
    "This team gets read{gap}. It hides its direction better than the comparison set's average.",
  "ช้ากว่าทีมอาชีพ {s} วินาที": "{s} s later than pro teams",
  "โดยเฉลี่ยรู้ทางก่อนบอมบ์ลงจริง {s} วินาที": "on average the site is known {s} s before the bomb goes down",
  "ดูทีละรอบ": "Rounds",
  "เข้าไซต์": "Site",
  "ถูกอ่านออกวินาทีที่": "Read at second",
  "ก่อนบอมบ์ลง": "Before plant",
  "ผลรอบ": "Result",
  "อ่านไม่ออก": "Not read",
  "{s} วิ": "{s} s",
  "{side} ชนะ": "{side} won",
  "ดูรอบนี้": "View round",
  'แถวที่เน้น = ถูกอ่านออกภายใน 8 วินาทีแรก · กด "ดูรอบนี้" แล้วหน้ารอบจะเปิดโหมดเล่นย้อนค้างไว้ที่วินาทีนั้นพอดี':
    'Highlighted rows = read within the first 8 seconds · press "View round" to open the round in playback, paused at that exact second.',
  "{note} · เทียบกับ{source}": "{note} · compared with {source}",
  "ทำนายเฉพาะรอบที่ T ได้วางบอมบ์ · เทรนจากชุดอ้างอิงเท่านั้น ไม่เคยเห็นแมตช์ที่ผู้ใช้อัปโหลด":
    "Only rounds where T planted the bomb are predicted · trained on the reference set only, never on uploaded matches",
  "เดโมทีมอาชีพ {n} แมตช์ ({rounds} รอบที่วางบอมบ์บน {map})": "{n} pro demos ({rounds} planted rounds on {map})",

  // ตาราง + คำอธิบายสี
  "{n} ช่อง": "{n} cells",
  "ไม่มีชื่อเรียก": "Unnamed",
  "คำอธิบายสี": "Color key",
  "สีของแต่ละโซน = ทีมเราตายบ่อยกว่าทีมอาชีพกี่เท่า ยิ่งเข้มยิ่งต่างมาก":
    "Zone color = how many times more often we die there than pro teams. Darker = bigger gap.",
  "ต่ำกว่า {near}× หรือทีมเราตายในโซนนั้นไม่ถึง {min} ครั้ง = ไม่ระบาย (ต่างกันไม่ชัดพอจะสรุปอะไรได้)":
    "Below {near}×, or fewer than {min} of our deaths in the zone = not shaded (the gap is too unclear to conclude anything).",
  "จุดที่ทีมเราตายบ่อยกว่าทีมอาชีพ": "Where we die more often than pro teams",
  "{a} · ตาย {ad} ครั้ง — เทียบกับ {b} · ตาย {bd} ครั้ง": "{a} · {ad} deaths — vs {b} · {bd} deaths",
  "ยังไม่มีจุดไหนที่ทีมเราตายบ่อยกว่าทีมอาชีพถึง {near}× และมีจำนวนมากพอจะสรุป — อัปโหลดแมตช์เพิ่มแล้วตัวเลขจะชัดขึ้น":
    "No spot yet where we die {near}× more often than pro teams with enough deaths to conclude anything. Upload more matches and the numbers will get clearer.",
  "ตรงไหนของแมพ": "Where on the map",
  "เราตาย": "Our deaths",
  "ของเรา": "Ours",
  "ทีมอาชีพ": "Pro teams",
  "ต่างกี่เท่า": "Times more",
  '"ของเรา" กับ "ทีมอาชีพ" คือสัดส่วนของจุดตายทั้งหมดในชุดนั้น ไม่ใช่จำนวนครั้งดิบ — ทีมอาชีพมี 50 แมตช์ ถ้าเอาจำนวนครั้งมาเทียบกันตรง ๆ ฝั่งที่มีแมตช์เยอะกว่าก็ตายเยอะกว่าเสมอ ซึ่งไม่ได้บอกอะไร':
    '"Ours" and "Pro teams" are each set\'s share of all death spots, not raw counts. The pro set has 50 matches; compare raw counts and the set with more matches always has more deaths, which tells you nothing.',
  "ยังไม่มีช่องไหนตายถึง {min} ครั้ง (ตายมากสุด {max} ครั้ง) — ข้อมูลน้อยเกินกว่าจะระบายแผนที่":
    "No cell has {min} deaths yet (the most is {max}) — too little data to shade the map.",
  "จำนวนครั้งที่ตายในช่องนั้น ({note}) ยิ่งเข้มยิ่งตายบ่อย": "Deaths per cell ({note}). Darker = more deaths.",
  "ครั้ง · ต่ำกว่า {min} ครั้งไม่ระบาย": "deaths · fewer than {min} not shaded",
  "ช่องที่ตายบ่อยที่สุด": "Most frequent death spots",
  "{label} · ตายรวม {d} ครั้ง ใน {n} ช่อง": "{label} · {d} deaths in {n} cells",
  "ตาย": "Deaths",
  "สัดส่วน": "Share",
  "{place} (ช่อง {cx}, {cy}) · ตาย {d} ครั้ง": "{place} (cell {cx}, {cy}) · {d} deaths",

  // ป้ายชุดข้อมูล (ประกอบใหม่จากฟิลด์ของ /api/analysis/deaths)
  "{demo} (1 แมตช์)": "{demo} (1 match)",
  "แมตช์ของทีม {n} แมตช์": "Team matches: {n}",
  "เดโมทีมอาชีพ {n} แมตช์": "Pro demos: {n} matches",
  "{n} รอบที่เลือก": "{n} rounds selected",
  "{n} คนที่เลือก": "{n} players selected",

  // ยังไม่มีอะไรให้เทียบ
  "ยังไม่มีแมตช์ให้เทียบ": "No matches to compare yet",
  "หน้านี้เทียบแมตช์ของทีมกับเดโมทีมอาชีพบนแมพเดียวกัน — ยังไม่มีแมตช์ที่อัปโหลดเข้ามาเลย":
    "This page compares the team's matches with pro demos on the same map. No matches have been uploaded yet.",
  "หน้านี้เทียบแมตช์ของทีมกับเดโมทีมอาชีพบนแมพเดียวกัน — มีแมตช์ที่อัปโหลด {n} แมตช์ แต่ยังไม่ตรงกับแมพที่มีเดโมทีมอาชีพให้เทียบ (ตอนนี้มีแค่ de_mirage)":
    "This page compares the team's matches with pro demos on the same map. {n} uploaded match(es), but none on a map with pro demos to compare against (currently only de_mirage).",
  "ไปหน้าแมตช์": "Go to matches",
};
