import { describe, it, expect, vi } from "vitest";
import { screen, fireEvent } from "@testing-library/react";
import { renderWithProviders } from "@/test/renderWithProviders";
import BacktestTab from "@/components/rebalancing/BacktestTab";
import { runBacktest } from "@/api/backtest";

vi.mock("@/api/portfolios", () => ({
  fetchPortfolios: vi.fn().mockResolvedValue([]),
  fetchPortfolioOverviewLite: vi.fn(),
}));

vi.mock("@/api/backtest", () => ({
  runBacktest: vi.fn().mockResolvedValue({ dates: [], series: [], metrics: [] }),
}));

vi.mock("@/utils/toast", () => ({ toast: vi.fn() }));
// 차트는 테마 스토어(matchMedia)를 읽는다 — 이 테스트는 결과 유무만 본다
vi.mock("@/components/backtest/BacktestResultChart", () => ({ default: () => null }));
vi.mock("@/components/backtest/BacktestMetricsTable", () => ({ default: () => null }));

const EMPTY_MESSAGE = /해당 기간의 가격 데이터가 없습니다/;

describe("BacktestTab (plans/119 C6)", () => {
  it("조건을 바꾸면 이전 실행 결과를 지운다", async () => {
    renderWithProviders(<BacktestTab />);
    fireEvent.click(await screen.findByRole("button", { name: /백테스팅 실행/ }));
    expect(await screen.findByText(EMPTY_MESSAGE)).toBeInTheDocument();

    fireEvent.click(screen.getByLabelText("S&P 500 포함"));
    expect(screen.queryByText(EMPTY_MESSAGE)).not.toBeInTheDocument();
    expect(runBacktest).toHaveBeenCalledTimes(1);
  });

  it("날짜를 비우면 실행할 수 없다", async () => {
    const { container } = renderWithProviders(<BacktestTab />);
    const runButton = await screen.findByRole("button", { name: /백테스팅 실행/ });
    expect(runButton).toBeEnabled();

    const startInput = container.querySelector('input[type="date"]')!;
    fireEvent.change(startInput, { target: { value: "" } });
    expect(runButton).toBeDisabled();
  });
});
