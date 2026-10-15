import { create } from "zustand";
import { storageGet, storageSet } from "@/utils/safeStorage";

interface ThemeState {
  isDark: boolean;
  toggle: () => void;
}

function getInitialDark(): boolean {
  const stored = storageGet("theme");
  if (stored === "dark") return true;
  if (stored === "light") return false;
  return window.matchMedia("(prefers-color-scheme: dark)").matches;
}

export const useThemeStore = create<ThemeState>((set) => ({
  isDark: getInitialDark(),
  toggle: () =>
    set((state) => {
      const next = !state.isDark;
      storageSet("theme", next ? "dark" : "light");
      document.documentElement.classList.toggle("dark", next);
      return { isDark: next };
    }),
}));
