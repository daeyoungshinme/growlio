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
    expect(screen.queryByText("전술 국면 미반영")).toBeNull();
    // 추세 판정에 쓰는 50일선 이격도 보인다(QQQ·SPY 두 행)
    expect(screen.getAllByText("50일선 대비")).toHaveLength(2);
    expect(screen.getByText("나스닥100 상승")).toBeDefined();
    expect(screen.getByText("S&P500 상승")).toBeDefined();
  });

  it("DIA가 조회되면 다우로 함께 보여주고 전술 국면 미반영을 알린다", () => {
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

    expect(screen.getByText("전술 국면 미반영")).toBeDefined();
    expect(screen.getByText("추세 혼조")).toBeDefined();
    expect(screen.getByText("다우 혼조")).toBeDefined();
  });
});
