import { describe, it, expect, vi, beforeEach } from "vitest";
import { fireEvent, screen, waitFor } from "@testing-library/react";
import { renderWithProviders } from "@/test/renderWithProviders";
import type { GoalRecommendation } from "@/api/rebalancing";
import type { SettingsData } from "@/api/settings";
import type { Portfolio } from "@/api/portfolios";
import type { AssetAccount } from "@/api/assets";

const fetchOverallGoalRecommendation = vi.fn();
const fetchSettings = vi.fn();
const updateGoalCandidateTickers = vi.fn();
const fetchPortfolios = vi.fn();
const updatePortfolio = vi.fn();
const fetchAccounts = vi.fn();
const useStockSearchMock = vi.fn();
const toastMock = vi.fn();

vi.mock("@/api/rebalancing", () => ({
  fetchOverallGoalRecommendation: (...args: unknown[]) => fetchOverallGoalRecommendation(...args),
}));

vi.mock("@/api/settings", () => ({
  fetchSettings: (...args: unknown[]) => fetchSettings(...args),
  updateGoalCandidateTickers: (...args: unknown[]) => updateGoalCandidateTickers(...args),
}));

vi.mock("@/api/portfolios", () => ({
  fetchPortfolios: (...args: unknown[]) => fetchPortfolios(...args),
  updatePortfolio: (...args: unknown[]) => updatePortfolio(...args),
}));

vi.mock("@/api/assets", () => ({
  fetchAccounts: (...args: unknown[]) => fetchAccounts(...args),
}));

vi.mock("@/hooks/useStockSearch", () => ({
  useStockSearch: (...args: unknown[]) => useStockSearchMock(...args),
}));

vi.mock("@/utils/toast", () => ({ toast: (...args: unknown[]) => toastMock(...args) }));

import GoalRecommendationCard from "@/components/rebalancing/GoalRecommendationCard";

function makePortfolio(overrides: Partial<Portfolio> = {}): Portfolio {
  return {
    id: "p1",
    name: "메인 포트폴리오",
    items: [{ ticker: "AAPL", name: "Apple", market: "NASDAQ", weight: 100 }],
    base_type: "STOCK_ONLY",
    account_ids: null,
    alert_scope: "AGGREGATE",
    sort_order: 0,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

function makeAccount(overrides: Partial<AssetAccount> = {}): AssetAccount {
  return {
    id: "a1",
    name: "키움 증권",
    asset_type: "STOCK_KIWOOM",
    data_source: "KIWOOM_API",
    institution: null,
    kis_account_no: null,
    kiwoom_account_no: "1234",
    is_mock_mode: false,
    manual_amount: null,
    manual_currency: "KRW",
    manual_updated_at: null,
    deposit_krw: 0,
    deposit_usd: null,
    real_estate_details: null,
    include_in_total: true,
    is_active: true,
    sort_order: 0,
    notes: null,
    created_at: "2026-01-01T00:00:00Z",
    has_own_kis_credentials: false,
    has_own_kiwoom_credentials: false,
    target_portfolio_id: null,
    ...overrides,
  };
}

function makeSettingsData(overrides: Partial<SettingsData> = {}): SettingsData {
  return {
    has_kis: false,
    has_dart: false,
    goal_amount: 100_000_000,
    goal_annual_return_pct: null,
    annual_deposit_goal: null,
    monthly_deposit_amount: null,
    retirement_target_year: 2040,
    user_email: "test@example.com",
    notification_email: null,
    auto_dca_enabled: false,
    auto_dca_day: null,
    auto_dca_amount: null,
    auto_dca_portfolio_id: null,
    auto_dca_account_id: null,
    auto_dca_last_executed_at: null,
    annual_dividend_goal: null,
    fcm_token_stored: false,
    composite_signal_alerts_enabled: true,
    goal_candidate_tickers: [],
    ...overrides,
  };
}

function makeRecommendation(overrides: Partial<GoalRecommendation> = {}): GoalRecommendation {
  return {
    generated_at: "2026-07-06T00:00:00Z",
    is_configured: true,
    required_return_pct: 8.5,
    required_dividend_yield_pct: null,
    recommended_items: [
      { ticker: "SPY", name: "SPDR S&P 500 ETF", market: "NYSE", weight: 60 },
      { ticker: "SCHD", name: "Schwab US Dividend Equity ETF", market: "NYSE", weight: 40 },
    ],
    expected_return_pct: 9.1,
    expected_dividend_yield_pct: 2.1,
    note: null,
    ...overrides,
  };
}

describe("GoalRecommendationCard", () => {
  beforeEach(() => {
    fetchOverallGoalRecommendation.mockReset();
    fetchSettings.mockReset();
    fetchSettings.mockResolvedValue(makeSettingsData());
    updateGoalCandidateTickers.mockReset();
    updateGoalCandidateTickers.mockResolvedValue({ detail: "저장되었습니다" });
    fetchPortfolios.mockReset();
    fetchPortfolios.mockResolvedValue([]);
    fetchAccounts.mockReset();
    fetchAccounts.mockResolvedValue([]);
    updatePortfolio.mockReset();
    toastMock.mockReset();
    useStockSearchMock.mockReset();
    useStockSearchMock.mockReturnValue({
      suggestions: [],
      isSearching: false,
      search: vi.fn(),
      clearSuggestions: vi.fn(),
    });
  });

  it("renders nothing while not configured", async () => {
    fetchOverallGoalRecommendation.mockResolvedValue(
      makeRecommendation({ is_configured: false, recommended_items: [] }),
    );
    const { container } = renderWithProviders(<GoalRecommendationCard />);
    await waitFor(() => expect(fetchOverallGoalRecommendation).toHaveBeenCalled());
    expect(container.textContent).toBe("");
  });

  it("shows the note and a candidate-manager entry point when there are no recommended items", async () => {
    fetchOverallGoalRecommendation.mockResolvedValue(
      makeRecommendation({ recommended_items: [], note: "이미 목표 금액을 달성했습니다" }),
    );
    renderWithProviders(<GoalRecommendationCard />);

    expect(await screen.findByText("목표 달성 추천 비중 (전체 자산 기준)")).toBeDefined();
    expect(screen.getByText("이미 목표 금액을 달성했습니다")).toBeDefined();
    expect(screen.getByText(/후보 ETF 관리/)).toBeDefined();
    expect(screen.queryByText(/에 적용/)).toBeNull();
  });

  it("still exposes the candidate-manager button when there are no candidate ETFs registered", async () => {
    fetchOverallGoalRecommendation.mockResolvedValue(
      makeRecommendation({
        recommended_items: [],
        note: "등록된 후보 종목이 없습니다 — 후보 ETF를 추가해주세요",
      }),
    );
    renderWithProviders(<GoalRecommendationCard />);

    expect(
      await screen.findByText("등록된 후보 종목이 없습니다 — 후보 ETF를 추가해주세요"),
    ).toBeDefined();

    fireEvent.click(screen.getByText(/후보 ETF 관리/));
    expect(
      await screen.findByText("목표 달성 추천 비중 계산에 함께 고려할 ETF 후보를 등록합니다."),
    ).toBeDefined();
  });

  it("renders recommended items and required/expected return", async () => {
    fetchOverallGoalRecommendation.mockResolvedValue(makeRecommendation());
    renderWithProviders(<GoalRecommendationCard />);

    expect(await screen.findByText("목표 달성 추천 비중 (전체 자산 기준)")).toBeDefined();
    expect(screen.getByText(/SPY/)).toBeDefined();
    expect(screen.getByText("60.0%")).toBeDefined();
    expect(screen.getByText("40.0%")).toBeDefined();
  });

  it("omits the mt-3 top margin class when noTopMargin is passed", async () => {
    fetchOverallGoalRecommendation.mockResolvedValue(makeRecommendation());
    const { container } = renderWithProviders(<GoalRecommendationCard noTopMargin />);
    await screen.findByText("목표 달성 추천 비중 (전체 자산 기준)");
    expect(container.firstChild).not.toHaveClass("mt-3");
  });

  it("shows previously saved candidate ETFs when the manager panel is expanded", async () => {
    fetchOverallGoalRecommendation.mockResolvedValue(makeRecommendation());
    fetchSettings.mockResolvedValue(
      makeSettingsData({
        goal_candidate_tickers: [
          { ticker: "TLT", name: "iShares 20+ Year Treasury Bond ETF", market: "NYSE" },
        ],
      }),
    );
    renderWithProviders(<GoalRecommendationCard />);

    fireEvent.click(await screen.findByText(/후보 ETF 관리/));

    expect(await screen.findByText(/TLT/)).toBeDefined();
  });

  it("adds a searched candidate and saves the merged list", async () => {
    fetchOverallGoalRecommendation.mockResolvedValue(makeRecommendation());
    useStockSearchMock.mockReturnValue({
      suggestions: [
        {
          ticker: "TLT",
          name: "iShares 20+ Year Treasury Bond ETF",
          market: "NYSE",
          exchange: "NASDAQ",
        },
      ],
      isSearching: false,
      search: vi.fn(),
      clearSuggestions: vi.fn(),
    });
    renderWithProviders(<GoalRecommendationCard />);

    fireEvent.click(await screen.findByText(/후보 ETF 관리/));
    fireEvent.change(screen.getByPlaceholderText("추가할 ETF 종목명 또는 코드 검색"), {
      target: { value: "TLT" },
    });
    fireEvent.mouseDown(await screen.findByText("iShares 20+ Year Treasury Bond ETF"));

    const saveButton = await screen.findByText("저장");
    fireEvent.click(saveButton);

    await waitFor(() => expect(updateGoalCandidateTickers).toHaveBeenCalled());
    expect(updateGoalCandidateTickers.mock.calls[0][0]).toEqual([
      { ticker: "TLT", name: "iShares 20+ Year Treasury Bond ETF", market: "NYSE" },
    ]);
  });

  it("removes a saved candidate and saves the updated list", async () => {
    fetchOverallGoalRecommendation.mockResolvedValue(makeRecommendation());
    fetchSettings.mockResolvedValue(
      makeSettingsData({
        goal_candidate_tickers: [
          { ticker: "TLT", name: "iShares 20+ Year Treasury Bond ETF", market: "NYSE" },
        ],
      }),
    );
    renderWithProviders(<GoalRecommendationCard />);

    fireEvent.click(await screen.findByText(/후보 ETF 관리/));
    await screen.findByText(/TLT/);

    fireEvent.click(screen.getByLabelText("iShares 20+ Year Treasury Bond ETF 제거"));
    fireEvent.click(await screen.findByText("저장"));

    await waitFor(() => expect(updateGoalCandidateTickers).toHaveBeenCalled());
    expect(updateGoalCandidateTickers.mock.calls[0][0]).toEqual([]);
  });

  it("shows a hint instead of an apply control when no portfolio is set as a goal target", async () => {
    fetchOverallGoalRecommendation.mockResolvedValue(makeRecommendation());
    fetchPortfolios.mockResolvedValue([makePortfolio()]);
    fetchAccounts.mockResolvedValue([makeAccount({ target_portfolio_id: null })]);
    renderWithProviders(<GoalRecommendationCard />);

    await screen.findByText("목표 달성 추천 비중 (전체 자산 기준)");
    expect(
      await screen.findByText(
        "포트폴리오 탭에서 목표 포트폴리오를 지정하면 추천 비중을 바로 적용할 수 있어요.",
      ),
    ).toBeDefined();
    expect(screen.queryByText(/에 적용/)).toBeNull();
  });

  it("applies normalized recommended weights to the single target portfolio and reports success", async () => {
    fetchOverallGoalRecommendation.mockResolvedValue(
      makeRecommendation({
        recommended_items: [
          { ticker: "SPY", name: "SPDR S&P 500 ETF", market: "NYSE", weight: 33.33 },
          { ticker: "SCHD", name: "Schwab US Dividend Equity ETF", market: "NYSE", weight: 33.33 },
          {
            ticker: "TLT",
            name: "iShares 20+ Year Treasury Bond ETF",
            market: "NYSE",
            weight: 33.33,
          },
        ],
      }),
    );
    const portfolio = makePortfolio({ id: "target-1", name: "은퇴 포트폴리오" });
    fetchPortfolios.mockResolvedValue([portfolio]);
    fetchAccounts.mockResolvedValue([makeAccount({ target_portfolio_id: "target-1" })]);
    updatePortfolio.mockResolvedValue({ ...portfolio, items: [] });
    const onApplied = vi.fn();

    renderWithProviders(<GoalRecommendationCard onApplied={onApplied} />);

    fireEvent.click(await screen.findByText("은퇴 포트폴리오에 적용"));
    fireEvent.click(await screen.findByText("적용"));

    await waitFor(() => expect(updatePortfolio).toHaveBeenCalled());
    expect(updatePortfolio).toHaveBeenCalledWith("target-1", {
      items: [
        { ticker: "SPY", name: "SPDR S&P 500 ETF", market: "NYSE", weight: 33.3 },
        { ticker: "SCHD", name: "Schwab US Dividend Equity ETF", market: "NYSE", weight: 33.3 },
        { ticker: "TLT", name: "iShares 20+ Year Treasury Bond ETF", market: "NYSE", weight: 33.4 },
      ],
    });
    await waitFor(() => expect(onApplied).toHaveBeenCalledWith("target-1"));
  });

  it("requires selecting a target portfolio when multiple portfolios are goal targets", async () => {
    fetchOverallGoalRecommendation.mockResolvedValue(makeRecommendation());
    fetchPortfolios.mockResolvedValue([
      makePortfolio({ id: "target-1", name: "국내 포트폴리오" }),
      makePortfolio({ id: "target-2", name: "해외 포트폴리오" }),
    ]);
    fetchAccounts.mockResolvedValue([
      makeAccount({ id: "a1", target_portfolio_id: "target-1" }),
      makeAccount({ id: "a2", target_portfolio_id: "target-2" }),
    ]);
    updatePortfolio.mockResolvedValue({});
    const onApplied = vi.fn();

    renderWithProviders(<GoalRecommendationCard onApplied={onApplied} />);

    const applyButton = await screen.findByText("목표 포트폴리오에 적용");
    expect(applyButton.closest("button")).toBeDisabled();

    fireEvent.change(screen.getByDisplayValue("포트폴리오 선택"), {
      target: { value: "target-2" },
    });
    expect(applyButton.closest("button")).not.toBeDisabled();

    fireEvent.click(applyButton);
    fireEvent.click(await screen.findByText("적용"));

    await waitFor(() =>
      expect(updatePortfolio).toHaveBeenCalledWith("target-2", expect.anything()),
    );
  });

  it("toasts an error and does not report success when saving the recommendation fails", async () => {
    fetchOverallGoalRecommendation.mockResolvedValue(makeRecommendation());
    fetchPortfolios.mockResolvedValue([makePortfolio({ id: "target-1" })]);
    fetchAccounts.mockResolvedValue([makeAccount({ target_portfolio_id: "target-1" })]);
    updatePortfolio.mockRejectedValue(new Error("저장 실패"));
    const onApplied = vi.fn();

    renderWithProviders(<GoalRecommendationCard onApplied={onApplied} />);

    fireEvent.click(await screen.findByText(/에 적용/));
    fireEvent.click(await screen.findByText("적용"));

    await waitFor(() => expect(toastMock).toHaveBeenCalled());
    expect(onApplied).not.toHaveBeenCalled();
  });
});
