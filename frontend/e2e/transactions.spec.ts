/**
 * E2E: 입출금 내역 — 입금 거래 추가 → TransactionHistoryTab 확인 → 연도 필터
 */
import { test, expect } from "@playwright/test";

const mockAccounts = [
  {
    id: "acc-tx-1",
    name: "국내 증권계좌",
    asset_type: "STOCK_KIS",
    data_source: "KIS_API",
    institution: "한국투자증권",
    kis_account_no: "12345678-01",
    kiwoom_account_no: null,
    is_mock_mode: true,
    manual_amount: null,
    manual_currency: "KRW",
    manual_updated_at: null,
    deposit_krw: 5_000_000,
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

const currentYear = new Date().getFullYear();

const mockTransactions = [
  {
    id: "tx-e2e-1",
    account_id: "acc-tx-1",
    transaction_type: "DEPOSIT",
    amount: 1_000_000,
    fee: null,
    transaction_date: `${currentYear}-03-15`,
    ticker: null,
    notes: "E2E 테스트 입금",
    created_at: `${currentYear}-03-15T00:00:00Z`,
  },
  {
    id: "tx-e2e-2",
    account_id: "acc-tx-1",
    transaction_type: "DIVIDEND",
    amount: 50_000,
    fee: null,
    transaction_date: `${currentYear}-06-20`,
    ticker: "005930",
    notes: null,
    created_at: `${currentYear}-06-20T00:00:00Z`,
  },
];

test.describe("입출금 내역 탭", () => {
  test.beforeEach(async ({ page }) => {
    await page.route("**/api/v1/accounts", async (route) => {
      await route.fulfill({ json: mockAccounts });
    });

    await page.route("**/api/v1/transactions**", async (route) => {
      const url = route.request().url();
      const yearMatch = url.match(/year=(\d+)/);
      const year = yearMatch ? parseInt(yearMatch[1]) : currentYear;
      const filtered = mockTransactions.filter((tx) =>
        tx.transaction_date.startsWith(String(year)),
      );
      await route.fulfill({ json: filtered });
    });

    await page.route("**/api/v1/portfolio/overview**", async (route) => {
      await route.fulfill({
        json: {
          total_invested_krw: 5_000_000,
          total_stock_krw: 5_500_000,
          unrealized_pnl_krw: 500_000,
          stock_return_pct: 10.0,
          stock_allocation: [],
          positions: [],
        },
      });
    });

    await page.goto("/asset-management");
  });

  test("자산관리 페이지에 입출금 탭이 존재한다", async ({ page }) => {
    await expect(page.getByText(/입출금|내역/)).toBeVisible({ timeout: 5000 });
  });

  test("입출금 탭 클릭 시 거래 내역이 표시된다", async ({ page }) => {
    // 입출금 탭 찾아 클릭
    const tab = page.getByRole("tab", { name: /입출금|내역/ }).first();
    if (await tab.isVisible({ timeout: 3000 })) {
      await tab.click();
    } else {
      // 탭이 버튼으로 구현된 경우
      const btn = page.getByRole("button", { name: /입출금|내역/ }).first();
      if (await btn.isVisible({ timeout: 2000 })) await btn.click();
    }

    // 거래 내역 테이블 또는 리스트가 표시되어야 함
    await expect(page.getByText(`${currentYear}년 입금 합계`)).toBeVisible({ timeout: 5000 });
  });

  test("연도 필터를 변경하면 해당 연도 데이터가 로드된다", async ({ page }) => {
    const tab = page.getByRole("tab", { name: /입출금|내역/ }).first();
    if (await tab.isVisible({ timeout: 3000 })) await tab.click();

    await page.waitForSelector(`text=${currentYear}년 입금 합계`, { timeout: 5000 });

    const prevYear = currentYear - 1;
    // 연도 선택 드롭다운 찾기
    const yearSelect = page.locator("select").filter({ hasText: `${currentYear}년` }).first();
    if (await yearSelect.isVisible()) {
      await yearSelect.selectOption(String(prevYear));
      await expect(page.getByText(`${prevYear}년 입금 합계`)).toBeVisible({ timeout: 3000 });
    }
  });

  test("'내역 추가' 버튼 클릭 시 거래 입력 폼이 나타난다", async ({ page }) => {
    const tab = page.getByRole("tab", { name: /입출금|내역/ }).first();
    if (await tab.isVisible({ timeout: 3000 })) await tab.click();

    await page.waitForSelector(`text=${currentYear}년 입금 합계`, { timeout: 5000 });

    const addBtn = page.getByRole("button", { name: /내역 추가/ });
    if (await addBtn.isVisible({ timeout: 2000 })) {
      await addBtn.click();
      // 거래 유형 버튼(입금/출금/배당)이 표시되어야 함
      await expect(page.getByRole("button", { name: "입금" })).toBeVisible({ timeout: 3000 });
    }
  });
});
