import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import { renderWithProviders } from "@/test/renderWithProviders";
import type { RebalancingAlert } from "@/api/alerts";
import type { AssetAccount } from "@/api/assets";

vi.mock("@/api/alerts", () => ({
  fetchAccountRebalancingAlerts: vi.fn(),
  updateAlertScope: vi.fn(),
}));

vi.mock("@/utils/toast", () => ({ toast: vi.fn() }));
vi.mock("@/utils/error", () => ({
  extractErrorMessage: vi.fn((e: unknown, fallback = "오류") =>
    e instanceof Error ? e.message : fallback,
  ),
}));
vi.mock("@/utils/queryInvalidation", () => ({
  invalidatePortfolioData: vi.fn().mockResolvedValue(undefined),
  invalidateRebalancingAlertData: vi.fn().mockResolvedValue(undefined),
}));

// RebalancingAlertModal 자체는 이 리스트 화면의 관심사가 아니므로 얕은 스텁으로 대체한다.
vi.mock("@/components/rebalancing/RebalancingAlertModal", () => ({
  default: () => <div data-testid="edit-modal" />,
}));

import { fetchAccountRebalancingAlerts } from "@/api/alerts";
import PerAccountRebalancingAlertList from "@/components/portfolio-analysis/PerAccountRebalancingAlertList";

function account(overrides: Partial<AssetAccount>): AssetAccount {
  return {
    id: "acc-1",
    name: "계좌",
    is_active: true,
    ...overrides,
  } as AssetAccount;
}

function alert(overrides: Partial<RebalancingAlert>): RebalancingAlert {
  return {
    id: "alert-1",
    portfolio_id: "port-1",
    account_id: "acc-1",
    threshold_pct: 5,
    schedule_type: "DAILY",
    schedule_day_of_week: null,
    schedule_day_of_month: null,
    trigger_condition: "DRIFT_ONLY",
    mode: "NOTIFY",
    strategy: "BUY_ONLY",
    order_type: "MARKET",
    market_condition_mode: "DISABLED",
    auto_execution_time: null,
    notify_time: "08:30",
    buy_wait_minutes: 10,
    is_active: true,
    last_triggered_at: null,
    created_at: "2024-01-01T00:00:00Z",
    updated_at: "2024-01-01T00:00:00Z",
    ...overrides,
  };
}

describe("PerAccountRebalancingAlertList", () => {
  beforeEach(() => vi.clearAllMocks());

  it("설정이 없는 계좌는 '미설정'을 표시한다", async () => {
    vi.mocked(fetchAccountRebalancingAlerts).mockResolvedValue([]);
    renderWithProviders(
      <PerAccountRebalancingAlertList
        portfolioId="port-1"
        portfolioName="테스트 포트폴리오"
        linkedAccounts={[account({ id: "acc-1", name: "KIS 계좌" })]}
        onClose={vi.fn()}
      />,
    );

    await waitFor(() => expect(screen.getByText("미설정")).toBeDefined());
  });

  it("NOTIFY 설정된 계좌는 스케줄·조건·임계값을 한 문장으로 보여준다", async () => {
    vi.mocked(fetchAccountRebalancingAlerts).mockResolvedValue([
      alert({ account_id: "acc-1", schedule_type: "DAILY", threshold_pct: 5, mode: "NOTIFY" }),
    ]);
    renderWithProviders(
      <PerAccountRebalancingAlertList
        portfolioId="port-1"
        portfolioName="테스트 포트폴리오"
        linkedAccounts={[account({ id: "acc-1", name: "KIS 계좌" })]}
        onClose={vi.fn()}
      />,
    );

    await waitFor(() =>
      expect(
        screen.getByText(/비중이 ±5\.0% 이상 이탈 시 매일 08:30에 알림을 받습니다\./),
      ).toBeDefined(),
    );
    expect(screen.queryByText(/매수만/)).toBeNull();
  });

  it("AUTO 설정된 계좌는 전략·주문유형 배지를 함께 보여준다", async () => {
    vi.mocked(fetchAccountRebalancingAlerts).mockResolvedValue([
      alert({
        account_id: "acc-1",
        mode: "AUTO",
        strategy: "BUY_ONLY",
        order_type: "LIMIT",
        auto_execution_time: "09:05",
      }),
    ]);
    renderWithProviders(
      <PerAccountRebalancingAlertList
        portfolioId="port-1"
        portfolioName="테스트 포트폴리오"
        linkedAccounts={[account({ id: "acc-1", name: "KIS 계좌" })]}
        onClose={vi.fn()}
      />,
    );

    await waitFor(() => expect(screen.getByText(/매수만.*지정가/)).toBeDefined());
  });

  it("last_triggered_at이 있으면 마지막 실행 시각을 표시한다", async () => {
    vi.mocked(fetchAccountRebalancingAlerts).mockResolvedValue([
      alert({ account_id: "acc-1", last_triggered_at: new Date().toISOString() }),
    ]);
    renderWithProviders(
      <PerAccountRebalancingAlertList
        portfolioId="port-1"
        portfolioName="테스트 포트폴리오"
        linkedAccounts={[account({ id: "acc-1", name: "KIS 계좌" })]}
        onClose={vi.fn()}
      />,
    );

    await waitFor(() => expect(screen.getByText(/마지막 실행:/)).toBeDefined());
  });
});
