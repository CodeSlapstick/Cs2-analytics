import React from "react";
import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Link, Route, Routes } from "react-router-dom";
import { MatchLibrary } from "./pages/MatchLibrary";
import { MatchOverview } from "./pages/MatchOverview";
import { RoundReviewPage } from "./pages/RoundReviewPage";
import { ensureLogin } from "./api";
import "./styles.css";

// TanStack Query = ตัวจัดการ "ข้อมูลจากเซิร์ฟเวอร์" ทั้งแคช การโหลดซ้ำ และการ poll
const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false } },
});

function App() {
  return (
    <BrowserRouter>
      <header className="topbar">
        <Link to="/" className="brand">
          <span className="dot" /> CS2 SCOUTING
        </Link>
        <nav>
          <Link to="/">Match Library</Link>
          <a href="http://localhost:8000/upload" title="หน้าเว็บ Sprint 1 (vanilla) ที่ยังใช้ได้">
            หน้าเดิม ↗
          </a>
        </nav>
      </header>
      <main className="page">
        <Routes>
          <Route path="/" element={<MatchLibrary />} />
          <Route path="/matches/:id" element={<MatchOverview />} />
          <Route path="/matches/:demo/rounds/:n" element={<RoundReviewPage />} />
        </Routes>
      </main>
    </BrowserRouter>
  );
}

// Sprint 2 ยังไม่มีระบบผู้ใช้ — ล็อกอินโหมดทดสอบด้วย SteamID ตัวเดียวให้อัตโนมัติก่อน render
// (backend ต้องการคุกกี้สำหรับ /api/* ทุกตัว)
ensureLogin()
  .catch((e) => console.error("dev-login ไม่สำเร็จ:", e))
  .finally(() => {
    ReactDOM.createRoot(document.getElementById("root")!).render(
      <React.StrictMode>
        <QueryClientProvider client={queryClient}>
          <App />
        </QueryClientProvider>
      </React.StrictMode>,
    );
  });
