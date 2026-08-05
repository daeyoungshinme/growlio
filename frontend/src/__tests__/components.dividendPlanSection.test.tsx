import { describe, it, expect, vi, beforeEach } from "vitest";
import { fireEvent, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { renderWithProviders as renderWithProvidersBase } from "@/test/renderWithProviders";
import type { DividendPlanData } from "@/api/invest";
import type { GoalRecommendation } from "@/api/rebalancing";
import type { SettingsData } from "@/api/settings";

const fetchDividendPlan = vi.fn();
const fetchOverallGoalRecommendation = vi.fn();
const fetchSettings = vi.fn();
const updateGoalCandidateTickers = vi.fn();
const toastMock = vi.fn();

vi.mock("@/api/invest", () => ({
  fetchDividendPlan: (...args: unknown[]) => fetchDividendPlan(...args),
}));
vi.mock("@/api/rebalancing", () => ({
  fetchOverallGoalRecommendation: (...args: unknown[]) => fetchOverallGoalRecommendation(...args),
}));
vi.mock("@/api/settings", () => ({
  fetchSettings: (...args: unknown[]) => fetchSettings(...args),
  updateGoalCandidateTickers: (...args: unknown[]) => updateGoalCandidateTickers(...args),
}));
vi.mock("@/utils/toast", () => ({ toast: (...args: unknown[]) => toastMock(...args) }));
vi.mock("@/stores/themeStore", () => ({
  useThemeStore: () => ({ isDark: false, toggle: vi.fn() }),
}));

import DividendPlanSection from "@/components/invest/DividendPlanSection";

function renderWithProviders(ui: React.ReactElement) {
  return renderWithProvidersBase(<MemoryRouter>{ui}</MemoryRouter>);
}

function makeDividendPlan(overrides: Partial<DividendPlanData> = {}): DividendPlanData {
  return {
    annual_dividend_goal: 3_000_000,
    estimated_annual_krw: 2_000_000,
    estimated_monthly_krw: 166_667,
    actual_annual_received_krw: 1_500_000,
    goal_achievement_pct: 66.7,
    required_dividend_yield_pct: 4.0,
    current_dividend_yield_pct: 2.67,
    total_assets_krw: 75_000_000,
    monthly_projected: Array.from({ length: 12 }, (_, i) => ({
      month: i + 1,
      amount_krw: 166_667,
    })),
    monthly_received: [],
    yearly_received: [],
    ...overrides,
  };
}

function makeRecommendation(overrides: Partial<GoalRecommendation> = {}): GoalRecommendation {
  return {
    generated_at: "2026-07-24T00:00:00Z",
    is_configured: true,
    required_return_pct: null,
    required_dividend_yield_pct: 3.0,
    recommended_items: [],
    expected_return_pct: null,
    expected_dividend_yield_pct: 1.8,
    expected_volatility_pct: null,
    note: "등록된 후보로는 배당 목표(연 3.0%)를 달성하기 어렵습니다 — 아래 고배당 후보를 추가하면 도움이 됩니다",
    cagr_lookback_years: 10,
    risk_tolerance: "CONSERVATIVE",
    max_weight_pct: 40.0,
    market_signal_level: null,
    suggested_candidates: [
      {
        ticker: "JEPQ",
        name: "JPMorgan Nasdaq Equity Premium Income ETF",
        market: "NASDAQ",
        asset_class: "EQUITY",
        dividend_yield_pct: 9.95,
      },
    ],
    dividend_goal_status: "unreachable",
    ...overrides,
  };
}

function makeSettingsData(overrides: Partial<SettingsData> = {}): SettingsData {
  return {
    has_kis: false,
    has_dart: false,
    goal_amount: null,
    goal_annual_return_pct: null,
    annual_deposit_goal: null,
    monthly_deposit_amount: null,
    retirement_target_year: null,
    user_email: "test@example.com",
    notification_email: null,
    annual_dividend_goal: 3_000_000,
    fcm_token_stored: false,
    composite_signal_alerts_enabled: true,
    market_signal_daily_digest_enabled: false,
    year_end_tax_reminder_enabled: false,
    goal_achievement_alerts_enabled: true,
    monthly_report_enabled: true,
    recommendation_drift_alert_enabled: false,
    goal_candidate_tickers: [
      { ticker: "SPY", name: "SPDR S&P 500 ETF", market: "NYSE", asset_class: "EQUITY" },
    ],
    goal_risk_tolerance: "CONSERVATIVE",
    goal_max_weight_pct: 40.0,
    goal_cagr_lookback_years: 10,
    goal_short_term_equity_floor_pct: 80.0,
    goal_bond_ceiling_pct: null,
    goal_cash_ceiling_pct: null,
    age_group: null,
    birth_year: null,
    auto_rebalancing_max_order_value_krw: 50_000_000.0,
    auto_rebalancing_daily_value_cap_krw: null,
    ...overrides,
  };
}

describe("DividendPlanSection — 배당 목표 추천 ETF 섹션", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    fetchSettings.mockResolvedValue(makeSettingsData());
  });

  it("배당목표 + 추천이 설정된 경우 목표/기대 배당수익률 비교와 제안 후보를 보여준다", async () => {
    fetchDividendPlan.mockResolvedValue(makeDividendPlan());
    fetchOverallGoalRecommendation.mockResolvedValue(makeRecommendation());

    renderWithProviders(<DividendPlanSection onOpenSettings={vi.fn()} />);

    expect(await screen.findByText("배당 목표를 더 빨리 달성하려면?")).toBeDefined();
    expect(screen.getByText("+3.00%")).toBeDefined(); // 목표 배당수익률
    expect(screen.getByText("+1.80%")).toBeDefined(); // 기대 배당수익률
    expect(screen.getByText(/Nasdaq Equity Premium/)).toBeDefined();
    expect(screen.getByText("후보에 추가")).toBeDefined();
  });

  it("배당목표를 설정하지 않았으면 추천 섹션을 숨긴다", async () => {
    fetchDividendPlan.mockResolvedValue(makeDividendPlan({ annual_dividend_goal: null }));
    fetchOverallGoalRecommendation.mockResolvedValue(makeRecommendation());

    renderWithProviders(<DividendPlanSection onOpenSettings={vi.fn()} />);

    await screen.findByText("배당 목표 달성 현황");
    expect(screen.queryByText("배당 목표를 더 빨리 달성하려면?")).toBeNull();
  });

  it("추천 엔진이 미설정 상태(is_configured=false)면 추천 섹션을 숨긴다", async () => {
    fetchDividendPlan.mockResolvedValue(makeDividendPlan());
    fetchOverallGoalRecommendation.mockResolvedValue(
      makeRecommendation({ is_configured: false, suggested_candidates: [], note: null }),
    );

    renderWithProviders(<DividendPlanSection onOpenSettings={vi.fn()} />);

    await screen.findByText("배당 목표 달성 현황");
    expect(screen.queryByText("배당 목표를 더 빨리 달성하려면?")).toBeNull();
  });

  it("'후보에 추가' 클릭 시 등록 후보와 병합해 저장한다", async () => {
    fetchDividendPlan.mockResolvedValue(makeDividendPlan());
    fetchOverallGoalRecommendation.mockResolvedValue(makeRecommendation());
    updateGoalCandidateTickers.mockResolvedValue(undefined);

    renderWithProviders(<DividendPlanSection onOpenSettings={vi.fn()} />);

    fireEvent.click(await screen.findByText("후보에 추가"));

    await waitFor(() => expect(updateGoalCandidateTickers).toHaveBeenCalled());
    expect(updateGoalCandidateTickers.mock.calls[0][0]).toEqual([
      { ticker: "SPY", name: "SPDR S&P 500 ETF", market: "NYSE", asset_class: "EQUITY" },
      {
        ticker: "JEPQ",
        name: "JPMorgan Nasdaq Equity Premium Income ETF",
        market: "NASDAQ",
        asset_class: "EQUITY",
      },
    ]);
  });
});
