import type { Config } from "tailwindcss";

export default {
  darkMode: "class",
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        primary: "#2563EB",
        success: "#16A34A",
        danger: "#DC2626",
        warning: "#D97706",
      },
    },
  },
  plugins: [],
} satisfies Config;
