import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, fireEvent, waitFor } from "@testing-library/react";
import { renderWithProviders } from "@/test/renderWithProviders";
import { StockPriceAlertSection } from "@/components/settings/StockPriceAlertSection";
import { createStockPriceAlert, fetchStockPriceAlerts } from "@/api/alerts";

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
    expect(screen.getByText(/^\$27\.50 ≈ 38,500원 .* 현재 환율로 저장$/)).toBeInTheDocument();
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
    expect(screen.getByText("70,000원 (7만원)")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "알림 추가" }));

    await waitFor(() => expect(createStockPriceAlert).toHaveBeenCalled());
    expect(vi.mocked(createStockPriceAlert).mock.calls[0]![0]).toMatchObject({
      target_price: 70_000,
    });
  });

  it("원화로 입력한 뒤 해외 종목으로 바꾸면 목표가를 지운다(plans/119 C2)", () => {
    suggestions.list = [{ ticker: "005930", market: "KOSPI", name: "삼성전자", exchange: "KRX" }];
    renderWithProviders(<StockPriceAlertSection />);
    pick(/삼성전자/);
    fireEvent.change(screen.getByLabelText("목표가 (원)"), { target: { value: "30000" } });

    suggestions.list = [
      { ticker: "SCHD", market: "NYSE", name: "Schwab US Dividend", exchange: "NYSE" },
    ];
    pick(/Schwab/);
    expect(screen.getByLabelText("목표가 (USD)")).toHaveValue(null);
  });

  it("달러로 입력한 뒤 국내 종목으로 바꿔도 목표가를 지운다(plans/119 C2)", () => {
    suggestions.list = [
      { ticker: "SCHD", market: "NYSE", name: "Schwab US Dividend", exchange: "NYSE" },
    ];
    renderWithProviders(<StockPriceAlertSection />);
    pick(/Schwab/);
    fireEvent.change(screen.getByLabelText("목표가 (USD)"), { target: { value: "27" } });

    suggestions.list = [{ ticker: "005930", market: "KOSPI", name: "삼성전자", exchange: "KRX" }];
    pick(/삼성전자/);
    expect(screen.getByLabelText("목표가 (원)")).toHaveValue(null);
  });

  it("검색 결과에서 국내·미국 외 거래소 종목은 숨긴다", () => {
    suggestions.list = [
      { ticker: "SCHD", market: "NYSE", name: "Schwab US Dividend", exchange: "PCX" },
      { ticker: "SCHD.MX", market: "MEX", name: "Schwab Mexico", exchange: "MEX" },
      { ticker: "2788", market: "TOKYO", name: "애플인터내셔널", exchange: "TOKYO" },
    ];
    renderWithProviders(<StockPriceAlertSection />);
    fireEvent.change(screen.getByLabelText("종목 검색"), { target: { value: "x" } });
    expect(screen.getByRole("button", { name: /Schwab US Dividend/ })).toHaveTextContent(
      "미국 NYSE",
    );
    expect(screen.queryByRole("button", { name: /Schwab Mexico/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /애플인터내셔널/ })).not.toBeInTheDocument();
  });

  it("미국 종목 알림은 목록에 현재 환율 기준 달러도 보인다", async () => {
    vi.mocked(fetchStockPriceAlerts).mockResolvedValueOnce([
      {
        id: "a2",
        ticker: "SCHD",
        market: "NYSE",
        name: "SCHD",
        target_price: 38_500,
        direction: "BELOW",
        is_active: true,
        max_trigger_count: 1,
        trigger_count: 0,
        triggered_at: null,
        created_at: "2026-11-01T00:00:00Z",
        needs_reentry: false,
      },
    ]);
    renderWithProviders(<StockPriceAlertSection />);
    expect(await screen.findByText(/38,500원 \(약 \$27\.50\) 이하/)).toBeInTheDocument();
  });

  it("단위가 의심되는 옛 알림에 다시 입력하라는 안내를 보인다(plans/119 C3)", async () => {
    vi.mocked(fetchStockPriceAlerts).mockResolvedValueOnce([
      {
        id: "a1",
        ticker: "SCHD",
        market: "NYSE",
        name: "SCHD",
        target_price: 27,
        direction: "BELOW",
        is_active: true,
        max_trigger_count: 1,
        trigger_count: 0,
        triggered_at: null,
        created_at: "2026-11-01T00:00:00Z",
        needs_reentry: true,
      },
    ]);
    renderWithProviders(<StockPriceAlertSection />);
    expect(await screen.findByText(/다시 입력 필요/)).toBeInTheDocument();
  });
});
