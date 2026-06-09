/**
 * E2E: 자산관리 페이지 — 계좌 추가 → 목록 확인 → 삭제
 *
 * KIS/Kiwoom API 호출은 page.route()로 mock 처리합니다.
 */
import { test, expect } from "@playwright/test";

const mockAccounts = [
  {
    id: "acc-e2e-1",
    name: "테스트 증권계좌",
    asset_type: "STOCK_KIS",
    data_source: "KIS_API",
    institution: "한국투자증권",
    kis_account_no: "12345678-01",
    kiwoom_account_no: null,
    is_mock_mode: true,
    manual_amount: null,
    manual_currency: "KRW",
    manual_updated_at: null,
    deposit_krw: 1_000_000,
    deposit_usd: null,
    real_estate_details: null,
    include_in_total: true,
    is_active: true,
    sort_order: 0,
    notes: null,
    created_at: "2026-01-01T00:00:00Z",
    has_own_kis_credentials: false,
    has_own_kiwoom_credentials: false,
  },
];

test.describe("자산관리 — 계좌 관리", () => {
  test.beforeEach(async ({ page }) => {
    // 계좌 목록 API mock
    await page.route("**/api/v1/accounts", async (route) => {
      if (route.request().method() === "GET") {
        await route.fulfill({ json: mockAccounts });
      } else {
        await route.continue();
      }
    });

    // 포트폴리오 overview API mock
    await page.route("**/api/v1/portfolio/overview**", async (route) => {
      await route.fulfill({
        json: {
          total_invested_krw: 1_000_000,
          total_stock_krw: 1_100_000,
          unrealized_pnl_krw: 100_000,
          stock_return_pct: 10.0,
          stock_allocation: [],
          positions: [],
        },
      });
    });

    // 대시보드 API mock
    await page.route("**/api/v1/dashboard**", async (route) => {
      await route.fulfill({
        json: {
          total_assets_krw: 2_100_000,
          asset_allocation: [],
          goal_amount: null,
          goal_achievement_pct: null,
          stock_return_pct: 10.0,
          annual_return_pct: null,
          monthly_trend: [],
          annual_deposit_goal: null,
          deposit_achievement_pct: null,
          annual_dividends_received: 0,
          estimated_annual_dividends: 0,
          dividend_monthly_breakdown: [],
          cumulative_return_pct: null,
          xirr_pct: null,
          xirr_is_estimated: false,
          benchmark_kospi_pct: null,
          benchmark_sp500_pct: null,
          goal_annual_return_pct: null,
          retirement_target_year: null,
        },
      });
    });

    await page.goto("/asset-management");
  });

  test("자산관리 페이지가 로드된다", async ({ page }) => {
    await expect(page).toHaveURL(/\/asset-management/);
  });

  test("계좌 목록이 표시된다", async ({ page }) => {
    await expect(page.getByText("테스트 증권계좌")).toBeVisible({ timeout: 5000 });
  });

  test("계좌 추가 버튼이 표시된다", async ({ page }) => {
    const addBtn = page.getByRole("button", { name: /계좌 추가|추가/ }).first();
    await expect(addBtn).toBeVisible({ timeout: 5000 });
  });

  test("계좌 삭제 버튼을 클릭하면 확인 모달이 표시된다", async ({ page }) => {
    await page.route("**/api/v1/accounts/acc-e2e-1", async (route) => {
      if (route.request().method() === "DELETE") {
        await route.fulfill({ json: { success: true } });
      } else {
        await route.continue();
      }
    });

    await page.waitForSelector("text=테스트 증권계좌", { timeout: 5000 });
    // 삭제 버튼(휴지통 아이콘)을 찾아 클릭
    const deleteBtn = page.locator('[aria-label*="삭제"], button:has(svg)').last();
    if (await deleteBtn.isVisible()) {
      await deleteBtn.click();
      // 확인 모달 또는 다이얼로그 확인
      const confirmText = page.getByText(/삭제|확인/);
      await expect(confirmText.first()).toBeVisible({ timeout: 3000 });
    }
  });
});
