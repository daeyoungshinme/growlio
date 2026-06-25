import path from "path";
import { sentryVitePlugin } from "@sentry/vite-plugin";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";
import { VitePWA } from "vite-plugin-pwa";

const apiDomain = process.env.VITE_API_DOMAIN ?? "localhost:8000";
const apiBase = `^https://${apiDomain.replace(/\./g, "\\.")}`;
const apiPattern = new RegExp(`${apiBase}/.*`);
const dashboardPattern = new RegExp(`${apiBase}/api/v1/dashboard(\\?.*)?$`);
const portfolioOverviewPattern = new RegExp(`${apiBase}/api/v1/portfolio/overview(\\?.*)?$`);
const accountsPattern = new RegExp(`${apiBase}/api/v1/assets(\\?.*)?$`);

export default defineConfig({
  build: {
    // "hidden": 소스맵 생성하되 번들에 참조 주석 미포함 — Sentry 업로드 후 삭제
    sourcemap: "hidden",
    rollupOptions: {
      output: {
        manualChunks: {
          "vendor-charts": ["recharts"],
          "vendor-query": ["@tanstack/react-query"],
          "vendor-dnd": ["@dnd-kit/core", "@dnd-kit/sortable", "@dnd-kit/utilities"],
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
          { src: "/icons/icon-192.png", sizes: "192x192", type: "image/png", purpose: "any" },
          { src: "/icons/icon-512.png", sizes: "512x512", type: "image/png", purpose: "any" },
          { src: "/icons/icon-512.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
        ],
      },
      workbox: {
        globPatterns: ["**/*.{html,ico,png,svg,woff,woff2,webmanifest}"],
        cleanupOutdatedCaches: true,
        navigateFallback: "/index.html",
        navigateFallbackDenylist: [/^\/api\//],
        runtimeCaching: [
          {
            urlPattern: dashboardPattern,
            handler: "StaleWhileRevalidate",
            options: {
              cacheName: "api-dashboard",
              expiration: { maxAgeSeconds: 300, maxEntries: 5 },
            },
          },
          {
            urlPattern: portfolioOverviewPattern,
            handler: "StaleWhileRevalidate",
            options: {
              cacheName: "api-portfolio",
              expiration: { maxAgeSeconds: 300, maxEntries: 5 },
            },
          },
          {
            urlPattern: accountsPattern,
            handler: "StaleWhileRevalidate",
            options: {
              cacheName: "api-accounts",
              expiration: { maxAgeSeconds: 300, maxEntries: 5 },
            },
          },
          {
            urlPattern: apiPattern,
            handler: "NetworkOnly",
          },
        ],
      },
    }),
  ],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
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
    setupFiles: ["./src/test/setup.ts", "./src/test/setup.tsx"],
    env: {
      VITE_SUPABASE_URL: "https://placeholder.supabase.co",
      VITE_SUPABASE_ANON_KEY: "placeholder-anon-key-for-tests",
    },
    exclude: ["**/node_modules/**", "**/e2e/**"],
    coverage: {
      provider: "v8",
      reporter: ["text", "lcov"],
      include: ["src/**/*.{ts,tsx}"],
      exclude: [
        "src/test/**",
        "src/types/**",
        "src/**/*.d.ts",
        "src/main.tsx",
        "src/App.tsx",
        "src/lib/**",
        "src/plugins/**",
        "src/hooks/useBiometric.ts",
        "src/hooks/useHaptic.ts",
        "src/hooks/usePullToRefresh.ts",
        "src/hooks/usePushNotifications.ts",
        "src/hooks/useWidget.ts",
        "src/hooks/useSwipeNavigation.ts",
        "src/hooks/useRegisterRefresh.ts",
        "src/hooks/rebalancingExecution/types.ts",
      ],
      thresholds: {
        lines: 60,
        functions: 46,
        branches: 40,
        statements: 57,
      },
    },
  },
});
