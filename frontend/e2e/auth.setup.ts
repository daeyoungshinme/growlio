/**
 * E2E 인증 Setup — 로그인 후 storageState 저장
 *
 * TEST_USER_EMAIL / TEST_USER_PASSWORD 환경 변수가 없으면 건너뜁니다.
 * playwright.config.ts의 setup project에서 실행됩니다.
 */
import { test as setup, expect } from "@playwright/test";
import path from "path";
import fs from "fs";

export const AUTH_FILE = path.join(__dirname, ".auth/user.json");

setup("인증 상태 저장", async ({ page }) => {
  const email = process.env.TEST_USER_EMAIL;
  const password = process.env.TEST_USER_PASSWORD;

  if (!email || !password) {
    // 자격증명이 없으면 빈 auth 파일 생성 후 건너뜀
    const dir = path.dirname(AUTH_FILE);
    if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
    fs.writeFileSync(AUTH_FILE, JSON.stringify({ cookies: [], origins: [] }));
    return;
  }

  await page.goto("/login");
  await expect(page.getByRole("button", { name: /로그인/ })).toBeVisible();

  await page.fill('input[type="email"]', email);
  await page.fill('input[type="password"]', password);
  await page.getByRole("button", { name: /로그인/ }).click();

  // 로그인 성공 → 대시보드로 이동 확인
  await page.waitForURL(/\/dashboard/, { timeout: 10_000 });
  await expect(page).toHaveURL(/\/dashboard/);

  await page.context().storageState({ path: AUTH_FILE });
});
