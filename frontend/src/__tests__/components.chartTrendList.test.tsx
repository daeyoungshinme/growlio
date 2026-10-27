import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import type { TacticalMarket } from "@/api/tactical";
import ChartTrendList from "@/components/rebalancing/ChartTrendList";

const TECHNICALS: TacticalMarket["technicals"] = {
  QQQ: {
    close: 716.19,
    sma20: 730.0,
    sma60: 720.0,
    sma120: 700.0,
    sma50: 726.17,
    sma200: 674.72,
    rsi14: 40.2,
    macd_hist: -5.08,
    drawdown_pct: -5.7,
    trend: "UP",
    pullback_stage: "SMA60",
  },
  SPY: {
    close: 767.87,
    sma50: 767.24,
    sma200: 722.78,
    rsi14: 48.9,
    macd_hist: -1.16,
    drawdown_pct: -1.4,
    trend: "UP",
    pullback_stage: "SMA60",
  },
};

describe("ChartTrendList", () => {
  it("QQQ·SPY 추세와 이평선 이격을 보여주고, 웅덩이 배지는 QQQ에만 단다", () => {
    render(<ChartTrendList technicals={TECHNICALS} />);

    expect(screen.getAllByText("추세 상승")).toHaveLength(2);
    // QQQ 종가 716.19 / 20일선 730 → -1.9%
    expect(screen.getByText("-1.9%")).toBeDefined();
    expect(screen.getAllByText("60일선 웅덩이")).toHaveLength(1);
    expect(screen.queryByText("참고 · 국면 판단 미반영")).toBeNull();
  });

  it("DIA가 조회되면 참고 지표로 함께 보여준다", () => {
    render(
      <ChartTrendList
        technicals={{
          ...TECHNICALS,
          DIA: {
            close: 470.1,
            sma50: 472.3,
            sma200: 455.0,
            rsi14: 45.0,
            macd_hist: -0.8,
            drawdown_pct: -2.1,
            trend: "NEUTRAL",
          },
        }}
      />,
    );

    expect(screen.getByText("참고 · 국면 판단 미반영")).toBeDefined();
    expect(screen.getByText("추세 혼조")).toBeDefined();
  });
});
