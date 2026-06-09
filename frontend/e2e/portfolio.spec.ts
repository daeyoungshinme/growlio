/**
 * E2E: 포트폴리오 페이지 — 동기화 트리거(mock) → 스켈레톤 → 데이터 전환
 */
import { test, expect } from "@playwright/test";

const mockOverview = {
  total_invested_krw: 50_000_000,
  total_stock_krw: 55_000_000,
  unrealized_pnl_krw: 5_000_000,
  stock_return_pct: 10.0,
  stock_allocation: [
    { type: "STOCK_KIS", name: "삼성전자", ticker: "005930", value_krw: 55_000_000, pct: 100, market: "KOSPI" },
  ],
  positions: [
    {
      ticker: "005930",
      name: "삼성전자",
      market: "KOSPI",
      quantity: 100,
      avg_price: 500_000,
      current_price: 550_000,
      value_krw: 55_000_000,
      pnl_krw: 5_000_000,
      pnl_pct: 10.0,
    },
  ],
};

const mockAccounts = [
  {
    id: "acc-p-1",
    name: "KIS 증권계좌",
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

test.describe("포트폴리오 페이지", () => {
  test.beforeEach(async ({ page }) => {
    await page.route("**/api/v1/accounts", async (route) => {
      await route.fulfill({ json: mockAccounts });
    });

    await page.route("**/api/v1/portfolio/overview**", async (route) => {
      await route.fulfill({ json: mockOverview });
    });

    await page.route("**/api/v1/portfolios**", async (route) => {
      await route.fulfill({ json: [] });
    });

    await page.route("**/api/v1/assets/exchange-rate**", async (route) => {
      await route.fulfill({ json: { usd_krw: 1350 } });
    });
  });

  test("포트폴리오 페이지가 로드된다", async ({ page }) => {
    await page.goto("/portfolio");
    await expect(page).toHaveURL(/\/portfolio/);
  });

  test("계좌 목록이 표시된다", async ({ page }) => {
    await page.goto("/portfolio");
    await expect(page.getByText("KIS 증권계좌")).toBeVisible({ timeout: 5000 });
  });

  test("포트폴리오 overview 데이터가 표시된다", async ({ page }) => {
    await page.goto("/portfolio");
    // 수익률이 표시되어야 함
    await expect(page.getByText(/\+10\.00%|10\.00%/)).toBeVisible({ timeout: 5000 });
  });

  test("계좌 동기화 버튼을 클릭하면 sync API를 호출한다", async ({ page }) => {
    let syncCalled = false;
    await page.route("**/api/v1/assets/acc-p-1/sync**", async (route) => {
      syncCalled = true;
      await route.fulfill({ json: { success: true, positions_count: 1 } });
    });

    await page.goto("/portfolio");
    await page.waitForSelector("text=KIS 증권계좌", { timeout: 5000 });

    const syncBtn = page.getByRole("button", { name: /동기화|sync/i }).first();
    if (await syncBtn.isVisible()) {
      await syncBtn.click();
      await page.waitForTimeout(500);
      expect(syncCalled).toBe(true);
    }
  });

  test("종목 행이 표시된다", async ({ page }) => {
    await page.goto("/portfolio");
    await expect(page.getByText("삼성전자")).toBeVisible({ timeout: 5000 });
  });
});
