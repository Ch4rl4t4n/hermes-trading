import { useEffect, useState } from "react";
import { STORAGE_KEYS } from "../utils/storageKeys";

function resolveInitialTheme() {
  if (typeof window === "undefined") return "dark";
  const storedTheme = window.localStorage.getItem(STORAGE_KEYS.THEME);
  if (storedTheme === "light" || storedTheme === "dark") return storedTheme;
  if (window.matchMedia && window.matchMedia("(prefers-color-scheme: light)").matches) return "light";
  return "dark";
}

function applyTheme(theme) {
  if (typeof document === "undefined") return;
  const root = document.documentElement;
  if (theme === "light") {
    root.setAttribute("data-theme", "light");
  } else {
    root.removeAttribute("data-theme");
  }
}

export function useTheme() {
  const [theme, setTheme] = useState(resolveInitialTheme);

  useEffect(() => {
    applyTheme(theme);
    if (typeof window !== "undefined") {
      window.localStorage.setItem(STORAGE_KEYS.THEME, theme);
    }
  }, [theme]);

  const toggleTheme = () => {
    setTheme((prev) => (prev === "light" ? "dark" : "light"));
  };

  return { theme, isLight: theme === "light", toggleTheme, setTheme };
}
