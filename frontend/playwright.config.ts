import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: "html",
  use: {
    baseURL: "http://localhost:5173",
    trace: "on-first-retry",
  },
  projects: [
    // 인증 setup은 가장 먼저 실행
    {
      name: "setup",
      testMatch: "**/auth.setup.ts",
    },
    // 비인증 테스트
    {
      name: "chromium-unauth",
      use: { ...devices["Desktop Chrome"] },
      testMatch: ["**/auth.spec.ts", "**/dashboard.spec.ts"],
    },
    // 인증된 테스트 — setup에서 저장한 storageState 사용
    {
      name: "chromium-auth",
      use: {
        ...devices["Desktop Chrome"],
        storageState: "./e2e/.auth/user.json",
      },
      dependencies: ["setup"],
      testMatch: ["**/asset-management.spec.ts", "**/portfolio.spec.ts", "**/transactions.spec.ts"],
    },
  ],
  webServer: {
    command: "npm run dev",
    url: "http://localhost:5173",
    reuseExistingServer: !process.env.CI,
  },
});
