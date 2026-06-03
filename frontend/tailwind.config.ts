import type { Config } from "tailwindcss";

export default {
  darkMode: "class",
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        primary: {
          DEFAULT: "#2563EB",
          50: "#EFF6FF",
          100: "#DBEAFE",
          500: "#3B82F6",
          600: "#2563EB",
          700: "#1D4ED8",
        },
        success: {
          DEFAULT: "#16A34A",
          50: "#F0FDF4",
          500: "#22C55E",
          600: "#16A34A",
        },
        danger: {
          DEFAULT: "#DC2626",
          50: "#FEF2F2",
          500: "#EF4444",
          600: "#DC2626",
        },
        warning: {
          DEFAULT: "#D97706",
          50: "#FFFBEB",
          500: "#F59E0B",
          600: "#D97706",
        },
        info: {
          DEFAULT: "#0891B2",
          50: "#ECFEFF",
          500: "#06B6D4",
          600: "#0891B2",
        },
      },
    },
  },
  plugins: [],
} satisfies Config;
