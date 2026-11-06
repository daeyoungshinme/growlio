import { describe, it, expect, vi, beforeEach } from "vitest";
import { fireEvent, screen } from "@testing-library/react";
import { renderWithProviders } from "@/test/renderWithProviders";

const fetchDividendPlan = vi.fn();

vi.mock("@/api/invest", () => ({
  fetchDividendPlan: (...args: unknown[]) => fetchDividendPlan(...args),
}));
vi.mock("@/stores/themeStore", () => ({
  useThemeStore: () => ({ isDark: false, toggle: vi.fn() }),
}));

import YearlyDividendChart from "@/components/portfolio/YearlyDividendChart";

describe("YearlyDividendChart", () => {
  beforeEach(() => {
    fetchDividendPlan.mockReset();
  });

  it("조회 실패를 '배당 없음'처럼 숨기지 않고 다시 시도를 보여준다 (plans/113 B4)", async () => {
    fetchDividendPlan.mockRejectedValueOnce(new Error("network"));
    renderWithProviders(<YearlyDividendChart />);

    expect(await screen.findByText("연도별 배당을 불러오지 못했습니다.")).toBeInTheDocument();

    fetchDividendPlan.mockResolvedValueOnce({
      yearly_received: [{ year: 2025, amount_krw: 1_200_000, growth_pct: null }],
    });
    fireEvent.click(screen.getByRole("button", { name: "다시 시도" }));

    expect(await screen.findByText("연도별 실수령 배당 추이")).toBeInTheDocument();
    expect(fetchDividendPlan).toHaveBeenCalledTimes(2);
  });

  it("수령 이력이 없으면 카드를 그리지 않는다", async () => {
    fetchDividendPlan.mockResolvedValueOnce({ yearly_received: [] });
    const { container } = renderWithProviders(<YearlyDividendChart />);

    await vi.waitFor(() => expect(fetchDividendPlan).toHaveBeenCalled());
    expect(container.querySelector(".card")).toBeNull();
  });
});
