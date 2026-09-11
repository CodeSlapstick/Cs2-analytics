import React from "react";
import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Link, Route, Routes } from "react-router-dom";
import { ProtectedRoute } from "./components/ProtectedRoute";
import { UserMenu } from "./components/UserMenu";
import { LoginPage } from "./pages/LoginPage";
import { MatchLibrary } from "./pages/MatchLibrary";
import { MatchOverview } from "./pages/MatchOverview";
import { RoundReviewPage } from "./pages/RoundReviewPage";
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
        <UserMenu />
      </header>
      <main className="page">
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          {/* ทุกหน้าที่ดึงข้อมูลต้องล็อกอินก่อน — ยังไม่ล็อกอินเด้งไป /login?next=<ที่เดิม> */}
          <Route element={<ProtectedRoute />}>
            <Route path="/" element={<MatchLibrary />} />
            <Route path="/matches/:id" element={<MatchOverview />} />
            <Route path="/matches/:demo/rounds/:n" element={<RoundReviewPage />} />
          </Route>
        </Routes>
      </main>
    </BrowserRouter>
  );
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  </React.StrictMode>,
);
