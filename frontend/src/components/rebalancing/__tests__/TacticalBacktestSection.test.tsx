import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import type { TacticalBacktestResult } from "@/api/tactical";

vi.mock("@/hooks/useTacticalAllocation", () => ({ useTacticalBacktest: vi.fn() }));
// recharts는 jsdom에서 크기를 못 재므로 차트는 받은 시리즈 이름만 그리는 스텁으로 대체
vi.mock("@/components/backtest/BacktestResultChart", () => ({
  default: ({ series }: { series: { name: string }[] }) => (
    <div data-testid="chart">{series.map((s) => s.name).join(",")}</div>
  ),
}));

import * as hooks from "@/hooks/useTacticalAllocation";
import TacticalBacktestSection from "@/components/rebalancing/TacticalBacktestSection";
import { toChartSeries } from "@/components/rebalancing/tacticalLabels";

const metric = (name: string, cagr: number) => ({
  name,
  total_return_pct: cagr * 10,
  cagr_pct: cagr,
  mdd_pct: 20,
  sharpe_ratio: 0.9,
  volatility_pct: 15,
  sortino_ratio: 1.2,
});

function makeResult(overrides: Partial<TacticalBacktestResult> = {}): TacticalBacktestResult {
  return {
    years: 10,
    start_date: "2016-10-24",
    end_date: "2026-10-23",
    metrics: [
      metric("전술 배분", 13.1),
      metric("평균 비중 고정", 11.2),
      metric("SPY 보유", 12.5),
      metric("QQQ 보유", 17.0),
    ],
    series: [
      { date: "2016-10-24", strategy: 100, static: 100, spy: 100, qqq: 100 },
      { date: "2026-10-23", strategy: 340, static: 290, spy: 320, qqq: 480 },
    ],
    avg_weights: { QQQ: 40, SPY: 38, DIA: 0, QLD: 0, SSO: 0, CASH: 22 },
    turnover_pct_per_year: 85.3,
    regime_switches: 39,
    regime_time_pct: { RISK_ON: 60, NEUTRAL: 25, RISK_OFF: 15 },
    tilt_shift_pct: 0,
    tilt_switches: 0,
    tilt_time_pct: { FAVOR_QQQ: 0, BALANCED: 100, FAVOR_SPY: 0 },
    regime_timeline: Array.from({ length: 7 }, (_, i) => ({
      date: `2026-0${i + 1}-01`,
      regime: i % 2 ? "NEUTRAL" : "RISK_ON",
    })) as TacticalBacktestResult["regime_timeline"],
    macro_note: "매크로 입력은 VIX만으로 근사했습니다.",
    assumptions: "현금은 미국 3개월 국채 금리 · 거래비용 매매금액의 0.1%",
    ...overrides,
  };
}

describe("toChartSeries", () => {
  it("행 단위 series를 열 단위 차트 입력으로 바꾸고 DIA는 있을 때만 넣는다", () => {
    const out = toChartSeries(makeResult());
    expect(out.dates).toEqual(["2016-10-24", "2026-10-23"]);
    expect(out.series.map((s) => s.name)).toEqual([
      "전술 배분",
      "평균 비중 고정",
      "SPY 보유",
      "QQQ 보유",
    ]);
    expect(out.series[1].values).toEqual([100, 290]);

    const withDia = toChartSeries(
      makeResult({
        series: [{ date: "2016-10-24", strategy: 100, static: 100, spy: 100, qqq: 100, dia: 100 }],
      }),
    );
    expect(withDia.series[withDia.series.length - 1].name).toBe("DIA 보유");
  });
});

describe("TacticalBacktestSection", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
  });

  it("펼치면 지표표·회전율·차트·최근 국면 전환(5건+더 보기)을 보여준다", async () => {
    vi.mocked(hooks.useTacticalBacktest).mockReturnValue({
      data: makeResult(),
      isLoading: false,
      isError: false,
      error: null,
    } as unknown as ReturnType<typeof hooks.useTacticalBacktest>);
    render(<TacticalBacktestSection portfolioId="p1" />);

    fireEvent.click(screen.getByText("규칙 백테스트"));
    expect(screen.getByText("평균 비중 고정")).toBeDefined();
    expect(screen.getByText(/연 회전율 85.3%/)).toBeDefined();
    expect(screen.getByText(/국면 판단이 가치를 더한 거예요/)).toBeDefined();
    expect((await screen.findByTestId("chart")).textContent).toContain("평균 비중 고정");

    // 최신순 5건 — 가장 오래된 2026-01-01은 더 보기 전엔 숨김
    expect(screen.getByText("2026-07-01")).toBeDefined();
    expect(screen.queryByText("2026-01-01")).toBeNull();
    fireEvent.click(screen.getByText("더 보기 (2건)"));
    expect(screen.getByText("2026-01-01")).toBeDefined();
  });
});
