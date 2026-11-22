import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { fireEvent, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { renderWithProviders as renderWithProvidersBase } from "@/test/renderWithProviders";
import type { DividendPlanData } from "@/api/invest";
import type { GoalRecommendation } from "@/api/rebalancing";

const fetchDividendPlan = vi.fn();
const fetchOverallGoalRecommendation = vi.fn();
const toastMock = vi.fn();

vi.mock("@/api/invest", () => ({
  fetchDividendPlan: (...args: unknown[]) => fetchDividendPlan(...args),
}));
vi.mock("@/api/rebalancing", () => ({
  fetchOverallGoalRecommendation: (...args: unknown[]) => fetchOverallGoalRecommendation(...args),
}));
const fetchSettings = vi.fn();
vi.mock("@/api/settings", () => ({
  fetchSettings: (...args: unknown[]) => fetchSettings(...args),
}));
vi.mock("@/utils/toast", () => ({ toast: (...args: unknown[]) => toastMock(...args) }));
vi.mock("@/stores/themeStore", () => ({
  useThemeStore: (sel?: (s: { isDark: boolean; toggle: () => void }) => unknown) => {
    const state = { isDark: false, toggle: vi.fn() };
    return sel ? sel(state) : state;
  },
}));

import DividendPlanSection from "@/components/invest/DividendPlanSection";
import { projectDividendGoal } from "@/utils/dividendGoalTimeline";
import { monthAfter } from "@/utils/dcaScenarioProjection";
import { fmtMonth } from "@/utils/format";

// 가짜 타이머가 실패한 테스트에서 다음 테스트로 새지 않게 항상 되돌린다(plans/146 B7)
afterEach(() => {
  vi.useRealTimers();
});

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

describe("DividendPlanSection — 배당 목표 추천 ETF 섹션", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
  });

  it("배당목표 + 추천이 설정된 경우 목표/기대 배당수익률 비교와 제안 후보를 보여준다", async () => {
    fetchDividendPlan.mockResolvedValue(makeDividendPlan());
    fetchOverallGoalRecommendation.mockResolvedValue(makeRecommendation());

    renderWithProviders(<DividendPlanSection onOpenSettings={vi.fn()} />);

    // 기본 접힘(docs/plans/67 P1-14) — 펼쳐서 확인
    fireEvent.click(await screen.findByText("배당 목표를 더 빨리 달성하려면?"));
    expect(screen.getByText("+3.00%")).toBeDefined(); // 목표 배당수익률
    expect(screen.getByText("+1.80%")).toBeDefined(); // 기대 배당수익률
    expect(screen.getByText(/Nasdaq Equity Premium/)).toBeDefined();
    // 후보 추가는 목표 조정 › 추천에서만(계획 106 C1) — 여기는 요약 + 링크
    expect(screen.queryByText("후보에 추가")).toBeNull();
    const link = screen.getByText("목표 조정에서 후보 추가·추천 비중 보기").closest("a");
    expect(decodeURIComponent(link?.getAttribute("href") ?? "")).toBe(
      "/rebalancing?rtab=목표 조정&gmode=추천",
    );
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

  it("불러오기에 실패하면 다시 시도할 수 있다", async () => {
    fetchDividendPlan
      .mockRejectedValueOnce(new Error("boom"))
      .mockResolvedValue(makeDividendPlan());
    fetchOverallGoalRecommendation.mockResolvedValue(makeRecommendation());
    renderWithProviders(<DividendPlanSection onOpenSettings={vi.fn()} />);
    fireEvent.click(await screen.findByRole("button", { name: "다시 시도" }));
    expect((await screen.findAllByText(/달성률/)).length).toBeGreaterThan(0);
    expect(fetchDividendPlan).toHaveBeenCalledTimes(2);
  });

  it("세후 예상 배당을 한 줄로 보여 준다(계획 143 E2)", async () => {
    fetchDividendPlan.mockResolvedValue(
      makeDividendPlan({
        estimated_annual_after_tax_krw: 1_692_000,
        estimated_monthly_after_tax_krw: 141_000,
        after_tax_note: "세후는 일반계좌 원천징수를 뺀 추정",
      }),
    );
    fetchOverallGoalRecommendation.mockResolvedValue(makeRecommendation());
    renderWithProviders(<DividendPlanSection onOpenSettings={vi.fn()} />);
    expect(await screen.findByText(/세후 예상 연 169만원/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "세후 예상 배당 설명" })).toBeInTheDocument();
  });

  it("옛 응답(세후 필드 없음)이면 세후 줄을 숨긴다", async () => {
    fetchDividendPlan.mockResolvedValue(makeDividendPlan());
    fetchOverallGoalRecommendation.mockResolvedValue(makeRecommendation());
    renderWithProviders(<DividendPlanSection onOpenSettings={vi.fn()} />);
    expect((await screen.findAllByText(/달성률/)).length).toBeGreaterThan(0);
    expect(screen.queryByText(/세후 예상/)).toBeNull();
  });

  it("배당 목표 달성 예상 시점을 보여 준다(계획 143 E3)", async () => {
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date(2026, 10, 15));
    // 7,500만원·연 200만원(2.67%) → 목표 300만원, 월 적립 100만원
    fetchSettings.mockResolvedValue({ monthly_deposit_amount: 1_000_000 });
    fetchDividendPlan.mockResolvedValue(makeDividendPlan());
    fetchOverallGoalRecommendation.mockResolvedValue(makeRecommendation());
    renderWithProviders(<DividendPlanSection onOpenSettings={vi.fn()} />);
    const months = projectDividendGoal(75_000_000, 2_000_000, 3_000_000, 1_000_000)?.months;
    expect(months).toBeGreaterThan(0);
    const expected = `${fmtMonth(monthAfter("2026-11", months ?? 0))} 달성 예상`;
    expect(await screen.findByText(new RegExp(expected))).toBeInTheDocument();
    expect(screen.getByText(/월 100만원 적립/)).toBeInTheDocument();
  });
});
