import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import BacktestResultChart from "@/components/backtest/BacktestResultChart";
import MonthlyDividendChart from "@/components/portfolio/MonthlyDividendChart";
import TreemapChart from "@/components/portfolio/TreemapChart";
import PortfolioWeightChart from "@/components/portfolio-analysis/PortfolioWeightChart";
import type { PortfolioItem } from "@/api/portfolios";

vi.mock("@/stores/themeStore", () => ({
  useThemeStore: (selector?: (state: { isDark: boolean }) => unknown) =>
    selector ? selector({ isDark: false }) : { isDark: false },
}));
vi.mock("@/hooks/useMediaQuery", () => ({ useIsSmUp: () => true }));

// 요약 문장 자체는 utils/__tests__/chartSummary.test.ts가 고정한다 — 여기선 차트에 실제로 붙는지 본다

describe("차트 대체 텍스트", () => {
  it("트리맵은 비중 큰 순서로 읽는다", () => {
    render(
      <TreemapChart
        title="종목 비중"
        data={[
          { name: "B", value: 100, pct: 25 },
          { name: "A", value: 300, pct: 75 },
        ]}
      />,
    );
    expect(screen.getByRole("img", { name: "종목 비중: A 75.0%, B 25.0%" })).toBeInTheDocument();
  });

  it("데이터가 없는 트리맵은 이미지로 노출하지 않는다", () => {
    render(<TreemapChart data={[]} />);
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
  });

  it("포트폴리오 비중 차트는 미배분까지 읽는다", () => {
    const items = [
      { ticker: "SPY", name: "SPY", weight: 60 },
      { ticker: "QQQ", name: "QQQ", weight: 30 },
    ] as PortfolioItem[];
    render(<PortfolioWeightChart items={items} />);
    expect(
      screen.getByRole("img", { name: "포트폴리오 비중 차트: SPY 60.0%, QQQ 30.0%, 미배분 10.0%" }),
    ).toBeInTheDocument();
  });

  it("월별 배당 차트는 실수령과 예상을 합쳐 읽는다", () => {
    render(
      <MonthlyDividendChart
        barData={[
          { name: "1월", month: 1, isPast: true, actual: 10_000, estimated: 0 },
          { name: "2월", month: 2, isPast: false, actual: 0, estimated: 50_000 },
        ]}
        currentYear={2026}
        selectedMonth={1}
        isDark={false}
        onMonthSelect={() => {}}
      />,
    );
    expect(
      screen.getByRole("img", {
        name: "2026년 월별 배당 차트: 합계 6만원, 최고 2월 5만원, 최저 1월 1만원",
      }),
    ).toBeInTheDocument();
  });

  it("백테스트 차트는 보기를 바꾸면 그 보기의 요약을 읽는다", () => {
    render(
      <BacktestResultChart
        dates={["2024-01-02", "2024-12-30", "2025-12-30"]}
        series={[{ name: "전략", values: [100, 120, 90] } as never]}
      />,
    );
    expect(screen.getByRole("img", { name: "누적 수익 차트: 전략 -10.0%" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "드로다운" }));
    expect(screen.getByRole("img", { name: "최대 낙폭 차트: 전략 -25.0%" })).toBeInTheDocument();
  });
});
