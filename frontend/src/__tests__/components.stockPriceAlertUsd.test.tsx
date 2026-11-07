import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, fireEvent, waitFor } from "@testing-library/react";
import { renderWithProviders } from "@/test/renderWithProviders";
import { StockPriceAlertSection } from "@/components/settings/StockPriceAlertSection";
import { createStockPriceAlert } from "@/api/alerts";

vi.mock("@/api/alerts", () => ({
  fetchStockPriceAlerts: vi.fn().mockResolvedValue([]),
  createStockPriceAlert: vi.fn().mockResolvedValue({}),
  reactivateStockPriceAlert: vi.fn(),
  deleteStockPriceAlert: vi.fn(),
}));

vi.mock("@/context/ExchangeRateContext", () => ({
  useExchangeRateContext: () => ({ rate: 1400, isLoading: false, error: null }),
}));

const suggestions = vi.hoisted(() => ({ list: [] as unknown[] }));
vi.mock("@/hooks/useStockSearch", () => ({
  useStockSearch: () => ({
    suggestions: suggestions.list,
    isSearching: false,
    search: vi.fn(),
    clearSuggestions: vi.fn(),
  }),
}));

vi.mock("@/utils/toast", () => ({ toast: vi.fn() }));

function pick(name: RegExp) {
  fireEvent.change(screen.getByLabelText("종목 검색"), { target: { value: "x" } });
  fireEvent.click(screen.getByRole("button", { name }));
}

describe("StockPriceAlertSection 목표가 단위(plans/118 C6)", () => {
  beforeEach(() => {
    vi.mocked(createStockPriceAlert).mockClear();
  });

  it("해외 종목은 달러로 입력받아 현재 환율로 원화 환산해 저장한다", async () => {
    suggestions.list = [
      { ticker: "SCHD", market: "NYSE", name: "Schwab US Dividend", exchange: "NYSE" },
    ];
    renderWithProviders(<StockPriceAlertSection />);
    pick(/Schwab/);

    fireEvent.change(screen.getByLabelText("목표가 (USD)"), { target: { value: "27.5" } });
    expect(screen.getByText(/≈ .*38,500/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "알림 추가" }));

    await waitFor(() => expect(createStockPriceAlert).toHaveBeenCalled());
    expect(vi.mocked(createStockPriceAlert).mock.calls[0]![0]).toMatchObject({
      ticker: "SCHD",
      target_price: 38_500,
    });
  });

  it("국내 종목은 원화 그대로 저장한다", async () => {
    suggestions.list = [{ ticker: "005930", market: "KOSPI", name: "삼성전자", exchange: "KRX" }];
    renderWithProviders(<StockPriceAlertSection />);
    pick(/삼성전자/);

    fireEvent.change(screen.getByLabelText("목표가 (원)"), { target: { value: "70000" } });
    fireEvent.click(screen.getByRole("button", { name: "알림 추가" }));

    await waitFor(() => expect(createStockPriceAlert).toHaveBeenCalled());
    expect(vi.mocked(createStockPriceAlert).mock.calls[0]![0]).toMatchObject({
      target_price: 70_000,
    });
  });
});
