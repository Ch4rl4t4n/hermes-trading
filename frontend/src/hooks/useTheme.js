import { useEffect } from "react";
import { STORAGE_KEYS } from "../utils/storageKeys";

/**
 * Hermes is dark-only. The previous light-mode toggle was removed across
 * the app per design — this hook stays for compatibility but always
 * resolves to dark, removes any stale theme attribute and clears the
 * cached preference so old clients also normalise to dark.
 */
function applyDark() {
  if (typeof document === "undefined") return;
  document.documentElement.removeAttribute("data-theme");
}

export function useTheme() {
  useEffect(() => {
    applyDark();
    if (typeof window !== "undefined") {
      try {
        window.localStorage.removeItem(STORAGE_KEYS.THEME);
      } catch {
        /* ignore */
      }
    }
  }, []);

  return {
    theme: "dark",
    isLight: false,
    toggleTheme: () => {},
    setTheme: () => {},
  };
}
