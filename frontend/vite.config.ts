import { sentryVitePlugin } from "@sentry/vite-plugin";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";
import { VitePWA } from "vite-plugin-pwa";

const apiDomain = process.env.VITE_API_DOMAIN ?? "growlio-api.onrender.com";
const apiPattern = new RegExp(`^https://${apiDomain.replace(/\./g, "\\.")}/.*`);

export default defineConfig({
  build: {
    // "hidden": 소스맵 생성하되 번들에 참조 주석 미포함 — Sentry 업로드 후 삭제
    sourcemap: "hidden",
    rollupOptions: {
      output: {
        manualChunks: {
          "vendor-charts": ["recharts"],
          "vendor-query": ["@tanstack/react-query"],
          "vendor-dnd": ["@dnd-kit/core", "@dnd-kit/sortable"],
        },
      },
    },
  },
  plugins: [
    react(),
    // SENTRY_AUTH_TOKEN이 있을 때만 빌드 시 소스맵 Sentry 업로드
    ...(process.env.SENTRY_AUTH_TOKEN
      ? [
          sentryVitePlugin({
            org: process.env.SENTRY_ORG,
            project: process.env.SENTRY_PROJECT,
            authToken: process.env.SENTRY_AUTH_TOKEN,
            release: { name: process.env.SENTRY_RELEASE },
            sourcemaps: { filesToDeleteAfterUpload: ["./dist/**/*.map"] },
            telemetry: false,
          }),
        ]
      : []),
    VitePWA({
      registerType: "autoUpdate",
      manifest: {
        name: "Growlio",
        short_name: "Growlio",
        description: "자산관리 대시보드",
        theme_color: "#2563EB",
        background_color: "#0F172A",
        display: "standalone",
        start_url: "/",
        icons: [
          { src: "/icons/icon-192.png", sizes: "192x192", type: "image/png" },
          {
            src: "/icons/icon-512.png",
            sizes: "512x512",
            type: "image/png",
            purpose: "any maskable",
          },
        ],
      },
      workbox: {
        globPatterns: ["**/*.{html,ico,png,svg,woff,woff2,webmanifest}"],
        cleanupOutdatedCaches: true,
        navigateFallback: "/index.html",
        navigateFallbackDenylist: [/^\/api\//],
        runtimeCaching: [
          {
            urlPattern: apiPattern,
            handler: "NetworkOnly",
          },
        ],
      },
    }),
  ],
  server: {
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    exclude: ["**/node_modules/**", "**/e2e/**"],
  },
});
