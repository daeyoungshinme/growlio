import { describe, it, expect, vi } from "vitest";
import { screen, fireEvent } from "@testing-library/react";
import { renderWithProviders } from "@/test/renderWithProviders";
import type { DCAProjectionPoint, GoalTimeline, YearlyAchievement } from "@/api/invest";
import type { OverseasPositionDetail } from "@/api/tax";

vi.mock("@/stores/themeStore", () => ({
  useThemeStore: () => ({ isDark: false, toggle: vi.fn() }),
}));

vi.mock("@/utils/dividendUtils", () => ({
  MONTH_LABELS: [
    "1월",
    "2월",
    "3월",
    "4월",
    "5월",
    "6월",
    "7월",
    "8월",
    "9월",
    "10월",
    "11월",
    "12월",
  ],
  dividendFreqInfo: vi.fn(() => ({ label: "분기", cls: "text-blue-500" })),
  weightBarColor: vi.fn(() => "bg-blue-500"),
  yieldBadgeClass: vi.fn(() => "bg-green-100 text-green-600"),
}));

vi.mock("@/hooks/useTaxSimulation", async () => {
  const actual = await vi.importActual("@/hooks/useTaxSimulation");
  return actual;
});

import DCAProjectionChart from "@/components/invest/DCAProjectionChart";
import GoalTimelineCard from "@/components/invest/GoalTimelineCard";
import MonthlyAchievementTable from "@/components/invest/MonthlyAchievementTable";
import YearlyAchievementTable from "@/components/invest/YearlyAchievementTable";
import TaxPlannerSection from "@/components/invest/TaxPlannerSection";
import { TaxSimulationCard } from "@/components/invest/TaxSimulationCard";
import { TaxRecommendationList } from "@/components/invest/TaxRecommendationList";
import { TaxPositionTable } from "@/components/invest/TaxPositionTable";

// ------- DCAProjectionChart -------
describe("DCAProjectionChart", () => {
  const mockData: DCAProjectionPoint[] = [
    {
      month: "2024-01",
      projected_krw: 1000000,
      actual_krw: 950000,
      achievement_pct: 95,
      has_data: true,
    },
    {
      month: "2024-02",
      projected_krw: 2000000,
      actual_krw: null,
      achievement_pct: null,
      has_data: false,
    },
    {
      month: "2025-01",
      projected_krw: 5000000,
      actual_krw: null,
      achievement_pct: null,
      has_data: false,
    },
  ];

  it("renders without crash with data", () => {
    renderWithProviders(<DCAProjectionChart data={mockData} />);
    const elems = screen.getAllByText(/이론 복리 곡선/);
    expect(elems.length).toBeGreaterThan(0);
  });

  it("renders without crash with empty data", () => {
    renderWithProviders(<DCAProjectionChart data={[]} />);
    expect(document.body).toBeDefined();
  });

  it("shows no actual data warning", () => {
    const noActualData: DCAProjectionPoint[] = [
      {
        month: "2024-01",
        projected_krw: 1000000,
        actual_krw: null,
        achievement_pct: null,
        has_data: false,
      },
    ];
    renderWithProviders(<DCAProjectionChart data={noActualData} />);
    expect(screen.getByText(/실제 자산 데이터가 없습니다/)).toBeDefined();
  });
});

// ------- GoalTimelineCard -------
describe("GoalTimelineCard", () => {
  const mockTimeline: GoalTimeline = {
    months_to_goal: 24,
    expected_goal_date: "2026-01",
    actual_expected_goal_date: "2025-09",
    current_progress_pct: 65.5,
    on_track: true,
    lead_lag_months: 4,
  };

  it("renders with timeline data", () => {
    renderWithProviders(<GoalTimelineCard timeline={mockTimeline} goalAmount={100000000} />);
    expect(screen.getByText("목표 달성 전망")).toBeDefined();
    expect(screen.getByText("65.5%")).toBeDefined();
  });

  it("renders 앞서고 있음 when lead > 0", () => {
    renderWithProviders(<GoalTimelineCard timeline={mockTimeline} goalAmount={100000000} />);
    expect(screen.getByText(/개월 앞서고 있음/)).toBeDefined();
  });

  it("renders 뒤처지고 있음 when lead < 0", () => {
    const laggingTimeline = { ...mockTimeline, lead_lag_months: -3, on_track: false };
    renderWithProviders(<GoalTimelineCard timeline={laggingTimeline} goalAmount={100000000} />);
    expect(screen.getByText(/개월 뒤처지고 있음/)).toBeDefined();
  });

  it("renders 계획과 정확히 일치 when lead = 0", () => {
    const exactTimeline = { ...mockTimeline, lead_lag_months: 0 };
    renderWithProviders(<GoalTimelineCard timeline={exactTimeline} goalAmount={100000000} />);
    expect(screen.getByText("계획과 정확히 일치")).toBeDefined();
  });

  it("renders with null progress", () => {
    const nullTimeline = { ...mockTimeline, current_progress_pct: null, on_track: null };
    renderWithProviders(<GoalTimelineCard timeline={nullTimeline} goalAmount={null} />);
    expect(screen.getByText("목표 달성 전망")).toBeDefined();
  });

  it("shows on_track badge when on_track = false", () => {
    const offTrack = { ...mockTimeline, on_track: false };
    renderWithProviders(<GoalTimelineCard timeline={offTrack} goalAmount={null} />);
    expect(screen.getByText(/계획 미달/)).toBeDefined();
  });
});

// ------- MonthlyAchievementTable -------
describe("MonthlyAchievementTable", () => {
  it("renders empty state when no past data", () => {
    const futureData: DCAProjectionPoint[] = [
      {
        month: "2099-01",
        projected_krw: 1000000,
        actual_krw: null,
        achievement_pct: null,
        has_data: false,
      },
    ];
    renderWithProviders(<MonthlyAchievementTable data={futureData} />);
    expect(screen.getByText("스냅샷 데이터가 없습니다.")).toBeDefined();
  });

  it("renders monthly data", () => {
    const pastData: DCAProjectionPoint[] = [
      {
        month: "2023-01",
        projected_krw: 1000000,
        actual_krw: 950000,
        achievement_pct: 95,
        has_data: true,
      },
      {
        month: "2023-02",
        projected_krw: 2000000,
        actual_krw: 2100000,
        achievement_pct: 105,
        has_data: true,
      },
    ];
    renderWithProviders(<MonthlyAchievementTable data={pastData} />);
    expect(screen.getByText(/월별 달성율/)).toBeDefined();
  });
});

// ------- YearlyAchievementTable -------
describe("YearlyAchievementTable", () => {
  it("renders empty state when no data", () => {
    renderWithProviders(<YearlyAchievementTable data={[]} />);
    expect(screen.getByText("스냅샷 데이터가 없습니다.")).toBeDefined();
  });

  it("renders yearly data", () => {
    const yearlyData: YearlyAchievement[] = [
      {
        year: 2023,
        projected_year_end_krw: 10000000,
        actual_year_end_krw: 9500000,
        achievement_pct: 95,
        has_data: true,
      },
      {
        year: 2024,
        projected_year_end_krw: 20000000,
        actual_year_end_krw: null,
        achievement_pct: null,
        has_data: false,
      },
    ];
    renderWithProviders(<YearlyAchievementTable data={yearlyData} />);
    expect(screen.getAllByText("연별 달성율").length).toBeGreaterThan(0);
    expect(screen.getAllByText("2023년").length).toBeGreaterThan(0);
  });
});

// ------- TaxSimulationCard -------
describe("TaxSimulationCard", () => {
  it("renders no-tax scenario (simTax = 0)", () => {
    renderWithProviders(
      <TaxSimulationCard
        totalSimPnl={1000000}
        alreadyRealized={0}
        simTotalRealized={1000000}
        simTax={0}
        simTaxDiff={0}
        currentTax={0}
      />,
    );
    expect(screen.getByText("매도 시뮬레이션 합계")).toBeDefined();
    expect(screen.getByText("0원")).toBeDefined();
  });

  it("renders tax scenario (simTax > 0)", () => {
    renderWithProviders(
      <TaxSimulationCard
        totalSimPnl={5000000}
        alreadyRealized={0}
        simTotalRealized={5000000}
        simTax={605000}
        simTaxDiff={605000}
        currentTax={0}
      />,
    );
    expect(screen.getByText("예상 납부 세금")).toBeDefined();
  });

  it("shows existing realized pnl when non-zero", () => {
    renderWithProviders(
      <TaxSimulationCard
        totalSimPnl={3000000}
        alreadyRealized={1000000}
        simTotalRealized={4000000}
        simTax={374000}
        simTaxDiff={374000}
        currentTax={0}
      />,
    );
    expect(screen.getByText("기존 실현 손익")).toBeDefined();
  });
});

// ------- TaxRecommendationList -------
describe("TaxRecommendationList", () => {
  const mockPos: OverseasPositionDetail = {
    ticker: "AAPL",
    name: "Apple Inc.",
    market: "NASDAQ",
    currency: "USD",
    account_id: "acc1",
    account_name: "테스트계좌",
    qty: 10,
    avg_price_krw: 1500000,
    current_price_krw: 1700000,
    avg_price_usd: 120,
    value_krw: 17000000,
    invested_krw: 15000000,
    unrealized_pnl_krw: 2000000,
    unrealized_pnl_pct: 13.3,
  };

  it("renders recommendations list", () => {
    const recommendations = [{ pos: mockPos, label: "전량 매도 권장", taxSaved: 55000 }];
    renderWithProviders(<TaxRecommendationList recommendations={recommendations} />);
    expect(screen.getByText(/절세 추천/)).toBeDefined();
    expect(screen.getByText("AAPL")).toBeDefined();
  });
});

// ------- TaxPositionTable -------
describe("TaxPositionTable", () => {
  const mockPos: OverseasPositionDetail = {
    ticker: "AAPL",
    name: "Apple Inc.",
    market: "NASDAQ",
    currency: "USD",
    account_id: "acc1",
    account_name: "테스트계좌",
    qty: 10,
    avg_price_krw: 1500000,
    current_price_krw: 1700000,
    avg_price_usd: 120,
    value_krw: 17000000,
    invested_krw: 15000000,
    unrealized_pnl_krw: 2000000,
    unrealized_pnl_pct: 13.3,
  };

  const lossPos: OverseasPositionDetail = {
    ...mockPos,
    ticker: "TSLA",
    name: "Tesla",
    unrealized_pnl_krw: -1000000,
    unrealized_pnl_pct: -6.7,
  };

  it("renders profit table", () => {
    renderWithProviders(
      <TaxPositionTable
        kind="profit"
        positions={[mockPos]}
        sellQtyMap={{}}
        maxTaxFreeProfit={2500000}
        totalLoss={0}
        hasAnyQtyInput={false}
        handleQtyChange={vi.fn()}
      />,
    );
    expect(screen.getAllByText("AAPL").length).toBeGreaterThan(0);
  });

  it("renders loss table", () => {
    renderWithProviders(
      <TaxPositionTable
        kind="loss"
        positions={[lossPos]}
        sellQtyMap={{}}
        maxTaxFreeProfit={2500000}
        totalLoss={-1000000}
        hasAnyQtyInput={false}
        handleQtyChange={vi.fn()}
      />,
    );
    expect(screen.getAllByText("TSLA").length).toBeGreaterThan(0);
  });

  it("renders qty input and handles change", () => {
    const handleQtyChange = vi.fn();
    renderWithProviders(
      <TaxPositionTable
        kind="profit"
        positions={[mockPos]}
        sellQtyMap={{ "AAPL-NASDAQ": 5 }}
        maxTaxFreeProfit={2500000}
        totalLoss={0}
        hasAnyQtyInput={true}
        handleQtyChange={handleQtyChange}
      />,
    );
    const inputs = screen.getAllByRole("spinbutton");
    if (inputs.length > 0) {
      fireEvent.change(inputs[0], { target: { value: "3" } });
      expect(handleQtyChange).toHaveBeenCalled();
    }
  });
});

// ------- TaxPlannerSection -------
describe("TaxPlannerSection", () => {
  it("renders empty state when no positions", () => {
    renderWithProviders(<TaxPlannerSection positions={[]} />);
    expect(screen.getByText("해외 종목 보유 현황이 없습니다.")).toBeDefined();
  });

  it("renders with positions", () => {
    const pos: OverseasPositionDetail = {
      ticker: "AAPL",
      name: "Apple Inc.",
      market: "NASDAQ",
      currency: "USD",
      account_id: "acc1",
      account_name: "테스트계좌",
      qty: 10,
      avg_price_krw: 1500000,
      current_price_krw: 1700000,
      avg_price_usd: 120,
      value_krw: 17000000,
      invested_krw: 15000000,
      unrealized_pnl_krw: 2000000,
      unrealized_pnl_pct: 13.3,
    };
    renderWithProviders(<TaxPlannerSection positions={[pos]} />);
    expect(screen.getByText(/해외 양도세 절세 플래너/)).toBeDefined();
    expect(screen.getAllByText(/250만원 공제/).length).toBeGreaterThan(0);
  });
});
