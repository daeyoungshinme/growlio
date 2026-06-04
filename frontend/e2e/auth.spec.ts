import { test, expect } from "@playwright/test";

test.describe("인증 흐름", () => {
  test("로그인 페이지가 렌더링된다", async ({ page }) => {
    await page.goto("/login");
    await expect(page).toHaveTitle(/Growlio/);
    await expect(page.getByRole("button", { name: /로그인/ })).toBeVisible();
  });

  test("인증 없이 대시보드 접근 시 로그인으로 리다이렉트된다", async ({ page }) => {
    await page.goto("/dashboard");
    await expect(page).toHaveURL(/\/login/);
  });

  test("잘못된 자격증명으로 로그인 시 에러 메시지가 표시된다", async ({ page }) => {
    await page.goto("/login");
    await page.fill('input[type="email"]', "wrong@example.com");
    await page.fill('input[type="password"]', "wrongpassword");
    await page.getByRole("button", { name: /로그인/ }).click();
    // 에러 메시지 혹은 실패 응답 확인
    await expect(page.locator("text=/오류|실패|잘못/")).toBeVisible({ timeout: 5000 });
  });
});
