import { test, expect } from "@playwright/test";

// 로그인이 필요한 테스트는 스토리지 상태 재사용 (CI 환경 고려)
// 이 파일은 로그인된 상태를 가정. 실제 테스트 실행 전 auth.setup.ts로 세션 생성 필요.

test.describe("대시보드 페이지", () => {
  test.beforeEach(async ({ page }) => {
    // 비로그인 상태에서는 로그인 페이지로 리다이렉트됨을 확인
    await page.goto("/dashboard");
  });

  test("비인증 사용자는 로그인 페이지로 이동한다", async ({ page }) => {
    await expect(page).toHaveURL(/\/login/);
  });
});

test.describe("회원가입 페이지", () => {
  test("회원가입 폼이 렌더링된다", async ({ page }) => {
    await page.goto("/register");
    await expect(page.getByRole("heading", { name: /회원가입|계정 만들기/ })).toBeVisible();
    await expect(page.locator('input[type="email"]')).toBeVisible();
    await expect(page.locator('input[type="password"]')).toBeVisible();
  });

  test("이미 계정이 있으면 로그인 링크가 표시된다", async ({ page }) => {
    await page.goto("/register");
    await expect(page.getByRole("link", { name: /로그인/ })).toBeVisible();
  });
});
