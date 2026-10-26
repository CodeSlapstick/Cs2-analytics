import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { useT } from "./i18n";

type Theme = "light" | "dark";

const STORE_KEY = "cs2-untitled-theme";
const LEGACY_STORE_KEY = "cs2-scouting-theme";
const ThemeContext = createContext<{ theme: Theme; toggle: () => void } | null>(null);

function initialTheme(): Theme {
  try {
    const saved = localStorage.getItem(STORE_KEY) ?? localStorage.getItem(LEGACY_STORE_KEY);
    if (saved === "light" || saved === "dark") return saved;
  } catch {
    // Storage can be unavailable in private or restricted browser contexts.
  }
  return "light";
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setTheme] = useState<Theme>(initialTheme);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    document.documentElement.style.colorScheme = theme;
    try {
      localStorage.setItem(STORE_KEY, theme);
      localStorage.removeItem(LEGACY_STORE_KEY);
    } catch {
      // The visual theme still works when persistence is unavailable.
    }
  }, [theme]);

  const value = useMemo(() => ({
    theme,
    toggle: () => setTheme((current) => current === "dark" ? "light" : "dark"),
  }), [theme]);

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function ThemeToggle({ className = "" }: { className?: string }) {
  const context = useContext(ThemeContext);
  const { lang } = useT();
  if (!context) throw new Error("ThemeToggle must be used inside ThemeProvider");

  const next = context.theme === "dark" ? "light" : "dark";
  const label = lang === "th"
    ? `เปลี่ยนเป็นโหมด${next === "light" ? "สว่าง" : "มืด"}`
    : `Switch to ${next} mode`;

  return (
    <button
      type="button"
      className={`theme-toggle ${className}`.trim()}
      onClick={context.toggle}
      aria-label={label}
      title={label}
      aria-pressed={context.theme === "light"}
    >
      <svg className="theme-sun" viewBox="0 0 24 24" aria-hidden="true">
        <circle cx="12" cy="12" r="3.5" />
        <path d="M12 2v2M12 20v2M4.93 4.93l1.42 1.42M17.65 17.65l1.42 1.42M2 12h2M20 12h2M4.93 19.07l1.42-1.42M17.65 6.35l1.42-1.42" />
      </svg>
      <svg className="theme-moon" viewBox="0 0 24 24" aria-hidden="true">
        <path d="M20.2 15.4A8.4 8.4 0 0 1 8.6 3.8 8.5 8.5 0 1 0 20.2 15.4Z" />
      </svg>
    </button>
  );
}
